# -*- coding: utf-8 -*-
"""Preferred Floor / Area, internal table matching, host table assignment, normal POS flow.

Real POS floors and tables (pos_restaurant TestFrontendCommon):
    Main Floor   : tables 5, 4, 2 (4 seats each)
    Second Floor : tables 1, 3    (4 seats each)
"""
import re
from datetime import timedelta
from urllib.parse import urlparse

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.pos_restaurant.tests.test_frontend import TestFrontendCommon

from .test_waitlist_join import _form


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistFloorMatching(TestFrontendCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pos_config.write({'enable_qr_self_join': True, 'waitlist_minutes_per_party': 10})
        cls.Entry = cls.env['pos.waitlist.entry']
        cls.tables = {t.table_number: t for t in cls.pos_config.floor_ids.table_ids}
        cls.main_key = cls.Entry._floor_public_key(cls.pos_config, cls.main_floor)
        cls.second_key = cls.Entry._floor_public_key(cls.pos_config, cls.second_floor)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _guest(self, phone='5550000001', **kw):
        """A guest who just joined: Waiting, ready to be seated (no intermediate step)."""
        entry, _c = self.Entry._join_from_qr(self.pos_config, _form(phone=phone, **kw))
        return entry

    def _rows(self, entry):
        data = self.Entry.with_user(self.pos_user).get_seatable_tables(self.pos_config.id, entry.id)
        return {r['table_number']: r for r in data['tables']}, data

    def _seat(self, entry, table, expected='waiting'):
        return self.Entry.with_user(self.pos_user).pos_seat_guest(
            self.pos_config.id, entry.id, expected, table.id if table else False)

    def _draft_order(self, table, guests=0):
        self.pos_config.current_session_id or self.pos_config.open_ui()
        return self.env['pos.order'].create({
            'table_id': table.id,
            'customer_count': guests,
            'company_id': self.env.company.id,
            'session_id': self.pos_config.current_session_id.id,
            'amount_paid': 0.0, 'amount_total': 0.0, 'amount_tax': 0.0, 'amount_return': 0.0,
        })

    # ------------------------------------------------------------------
    # Customer: preferred floor
    # ------------------------------------------------------------------
    def test_any_floor_is_default(self):
        entry = self._guest()
        self.assertFalse(entry.preferred_floor_id)
        self.assertEqual(entry._public_status()['floor_pref'], 'Any Floor')
        payload = self.Entry.get_pos_queue(self.pos_config.id)['entries'][0]
        self.assertEqual((payload['floor_pref_label'], payload['preferred_floor_id']), ('Any Floor', False))

    def test_floor_options_are_the_pos_floors(self):
        options = self.Entry._public_floor_options(self.pos_config)
        self.assertEqual([label for _key, label in options], ['Any Floor', 'Main Floor', 'Second Floor'])
        self.assertEqual(options[0][0], 'any')
        floor_ids = {str(self.main_floor.id), str(self.second_floor.id)}
        for key, _label in options:
            self.assertNotRegex(key, r'^\d+$', "floor keys are not database ids")
            self.assertNotIn(key, floor_ids)
        self.assertEqual(self.Entry._floor_from_public_key(self.pos_config, self.second_key),
                         (self.second_floor, True))

    def test_specific_floor_is_stored(self):
        entry = self._guest(preferred_floor=self.second_key)
        self.assertEqual(entry.preferred_floor_id, self.second_floor)
        self.assertEqual(entry._public_status()['floor_pref'], 'Second Floor')

    def test_invalid_floor_values_rejected(self):
        other_config = self.env['pos.config'].create({'name': 'Other Resto', 'enable_qr_self_join': True})
        other_floor = self.env['restaurant.floor'].create({
            'name': 'Rooftop', 'pos_config_ids': [(4, other_config.id)]})
        self.env['restaurant.table'].create({'table_number': 70, 'floor_id': other_floor.id, 'seats': 4})
        foreign_key = self.Entry._floor_public_key(other_config, other_floor)
        for bad in (foreign_key, str(self.main_floor.id), 'f' + '0' * 16, 'indoor', 'outdoor'):
            with self.assertRaises(ValidationError, msg=bad):
                self._guest(preferred_floor=bad)
        self.assertFalse(self.Entry.search([('config_id', '=', self.pos_config.id)]))

    def test_floor_of_other_pos_cannot_be_written(self):
        other_floor = self.env['restaurant.floor'].create({'name': 'Elsewhere'})
        entry = self._guest()
        with self.assertRaises(ValidationError):
            entry.preferred_floor_id = other_floor

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------
    def test_any_floor_matches_across_all_floors(self):
        rows, data = self._rows(self._guest(party_size='2'))
        self.assertEqual(set(rows), {1, 2, 3, 4, 5})
        self.assertTrue(all(r['status'] == 'match' for r in rows.values()))
        self.assertEqual({r['floor_name'] for r in rows.values()}, {'Main Floor', 'Second Floor'})
        self.assertEqual(len(data['available_ids']), 5)

    def test_specific_floor_restricts_matching(self):
        rows, data = self._rows(self._guest(preferred_floor=self.second_key))
        self.assertEqual({n for n, r in rows.items() if r['selectable']}, {1, 3})
        for number in (2, 4, 5):
            self.assertEqual(rows[number]['status'], 'other_floor')
            self.assertFalse(rows[number]['selectable'])
        self.assertEqual(sorted(data['available_ids']), sorted([self.tables[1].id, self.tables[3].id]))
        self.assertEqual(data['preferred_floor_id'], self.second_floor.id)

    def test_party_size_and_best_fit(self):
        self.tables[1].seats = 2
        self.tables[3].seats = 8
        self.tables[4].seats = 6
        rows, data = self._rows(self._guest(party_size='5'))
        self.assertEqual(rows[1]['status'], 'too_small')
        self.assertTrue(rows[1]['selectable'], "a too-small table stays the host's call")
        self.assertEqual(rows[4]['status'], 'match')
        self.assertEqual(rows[3]['status'], 'match')
        order = [r['table_number'] for r in data['tables']]
        self.assertLess(order.index(4), order.index(3), "6 seats fits a party of 5 better than 8")
        self.assertGreater(order.index(1), order.index(3), "too-small tables come after suitable ones")

    def test_private_guest_never_gets_an_occupied_table(self):
        self._draft_order(self.tables[5], guests=2)
        rows, _data = self._rows(self._guest(party_size='2', share_table='private'))
        self.assertEqual(rows[5]['status'], 'busy')
        self.assertIn('open order', rows[5]['reason'])
        self.assertFalse(rows[5]['selectable'])

    def test_sharing_guest_can_join_a_table_with_free_seats(self):
        self._draft_order(self.tables[5], guests=2)  # 4 seats, 2 taken
        rows, _data = self._rows(self._guest(party_size='2', share_table='share'))
        self.assertEqual((rows[5]['status'], rows[5]['free_seats']), ('shared', 2))
        self.assertTrue(rows[5]['selectable'])
        rows, _data = self._rows(self._guest(phone='5550000002', party_size='3', share_table='share'))
        self.assertEqual(rows[5]['status'], 'busy', "not enough free seats for 3")

    def test_hold_blocks_table_and_counts_for_sharing(self):
        first = self._guest(party_size='2')
        self.assertTrue(self._seat(first, self.tables[4])['ok'])
        rows, _data = self._rows(self._guest(phone='5550000002', party_size='2'))
        self.assertEqual(rows[4]['status'], 'busy')
        self.assertIn(first.token, rows[4]['reason'])
        rows, _data = self._rows(self._guest(phone='5550000003', party_size='2', share_table='share'))
        self.assertEqual((rows[4]['status'], rows[4]['free_seats']), ('shared', 2))
        # Hold expires without an order: free again.
        first.end_time = fields.Datetime.now() - timedelta(hours=1)
        rows, _data = self._rows(self._guest(phone='5550000004', party_size='2'))
        self.assertEqual(rows[4]['status'], 'match')

    def test_merged_and_inactive_tables_are_left_out(self):
        self.tables[2].parent_id = self.tables[4]
        self.tables[1].active = False
        rows, _data = self._rows(self._guest())
        self.assertNotIn(2, rows, "merged child table: its orders live on the parent")
        self.assertNotIn(1, rows)

    # ------------------------------------------------------------------
    # Host assignment
    # ------------------------------------------------------------------
    def test_host_seats_on_preferred_floor(self):
        entry = self._guest(preferred_floor=self.second_key, party_size='3')
        result = self._seat(entry, self.tables[3])
        self.assertTrue(result['ok'], result['message'])
        self.assertFalse(result['shared'])
        self.assertEqual((entry.state, entry.table_id), ('seated', self.tables[3]))
        status = entry._public_status()
        self.assertEqual((status['state'], status['table'], status['active']), ('seated', 3, False))
        self.assertNotIn(self.tables[3].id, result['tables']['available_ids'])

    def test_table_on_other_floor_refused(self):
        entry = self._guest(preferred_floor=self.second_key)
        result = self._seat(entry, self.tables[4])
        self.assertFalse(result['ok'])
        self.assertIn('Second Floor', result['message'])
        self.assertEqual((entry.state, entry.table_id.id), ('waiting', False))

    def test_private_guest_refused_on_occupied_table(self):
        self._draft_order(self.tables[5], guests=1)
        entry = self._guest(party_size='2')
        result = self._seat(entry, self.tables[5])
        self.assertFalse(result['ok'])
        self.assertIn('open order', result['message'])
        self.assertEqual(entry.state, 'waiting')

    def test_sharing_guest_seated_at_shared_table(self):
        self._draft_order(self.tables[5], guests=2)
        entry = self._guest(party_size='2', share_table='share')
        result = self._seat(entry, self.tables[5])
        self.assertTrue(result['ok'], result['message'])
        self.assertTrue(result['shared'])
        self.assertEqual(entry.table_id, self.tables[5])
        # The table is now full for anyone else.
        rows, _data = self._rows(self._guest(phone='5550000002', party_size='1', share_table='share'))
        self.assertEqual(rows[5]['status'], 'busy')

    def test_stale_table_rejected(self):
        entry = self._guest()
        table = self.tables[2]
        table_id = table.id
        table.active = False
        result = self.Entry.with_user(self.pos_user).pos_seat_guest(
            self.pos_config.id, entry.id, 'waiting', table_id)
        self.assertFalse(result['ok'])
        self.assertEqual(entry.state, 'waiting')
        result = self.Entry.with_user(self.pos_user).pos_seat_guest(
            self.pos_config.id, entry.id, 'waiting', 999999)
        self.assertFalse(result['ok'])
        self.assertEqual(entry.state, 'waiting')

    def test_closed_visit_cannot_be_seated(self):
        for i, closed in enumerate(('cancelled', 'left', 'no_show')):
            entry = self._guest(phone=f'55500003{i:02d}')
            self.assertTrue(self.Entry.pos_change_state(self.pos_config.id, entry.id, 'waiting', closed)['ok'])
            result = self._seat(entry, self.tables[4], expected=closed)
            self.assertFalse(result['ok'], closed)
            self.assertEqual((entry.state, entry.table_id.id), (closed, False))

    def test_matching_of_other_pos_entry_not_disclosed(self):
        other_config = self.env['pos.config'].create({'name': 'Other Resto', 'enable_qr_self_join': True})
        foreign, _c = self.Entry._join_from_qr(other_config, _form())
        data = self.Entry.get_seatable_tables(self.pos_config.id, foreign.id)
        self.assertFalse(data['preferred_floor_id'])
        result = self.Entry.pos_seat_guest(self.pos_config.id, foreign.id, 'waiting', self.tables[4].id)
        self.assertFalse(result['ok'])
        self.assertEqual(foreign.state, 'waiting')

    # ------------------------------------------------------------------
    # Public form (HTTP)
    # ------------------------------------------------------------------
    def test_join_form_offers_floors_never_tables(self):
        res = self.url_open(f'/waitlist/join/{self.pos_config.waitlist_token}')
        self.assertEqual(res.status_code, 200)
        for text in ('Preferred Floor / Area', 'Any Floor', 'Main Floor', 'Second Floor',
                     f'value="{self.main_key}"', f'value="{self.second_key}"'):
            self.assertIn(text, res.text)
        self.assertRegex(res.text, r'name="preferred_floor" value="any"\s+checked')
        for secret in (f'value="{self.main_floor.id}"', f'value="{self.second_floor.id}"'):
            self.assertNotIn(secret, res.text)
        self.assertNotIn('name="table', res.text, "the guest never chooses a table")
        for legacy in ('Indoor', 'Outdoor'):
            self.assertNotIn(legacy, res.text)

    def test_posted_table_is_ignored(self):
        data = dict(_form(preferred_floor=self.main_key), table_id=str(self.tables[4].id),
                    table=str(self.tables[4].id))
        res = self.url_open(f'/waitlist/join/{self.pos_config.waitlist_token}', data=data,
                            allow_redirects=False)
        self.assertEqual(res.status_code, 303, res.text[:300])
        access_token = re.search(r'/waitlist/s/([A-Za-z0-9_-]+)', urlparse(res.headers['Location']).path).group(1)
        entry = self.Entry.sudo().search([('access_token', '=', access_token)])
        self.assertEqual((entry.preferred_floor_id, entry.table_id.id, entry.state),
                         (self.main_floor, False, 'waiting'))

    # ------------------------------------------------------------------
    # Complete normal POS flow (browser)
    # ------------------------------------------------------------------
    def test_full_flow_preferred_floor_seat_open_and_pay(self):
        """Join (Second Floor, 3 guests) -> call -> Seat Guest -> table 3 -> Seat & Open ->
        guest count 3 -> add product -> send to kitchen -> pay -> next order."""
        entry = self._guest(preferred_floor=self.second_key, party_size='3')
        self.pos_config.with_user(self.pos_user).open_ui()
        orders_before = self.env['pos.order'].search_count([])

        self.start_pos_tour('hudson_pos_waitlist_floor_full_flow_tour', pos_config=self.pos_config)

        self.assertEqual((entry.state, entry.table_id), ('seated', self.tables[3]))
        orders = self.env['pos.order'].search([('table_id', '=', self.tables[3].id)])
        self.assertEqual(len(orders), 1, "exactly one normal POS order, no waitlist order")
        self.assertEqual(self.env['pos.order'].search_count([]), orders_before + 1)
        self.assertIn(orders.state, ('paid', 'done'))
        self.assertEqual(orders.customer_count, 3, "guest count = waitlist party size")
        self.assertEqual(orders.lines.product_id.name, 'Coca-Cola')
        self.assertEqual(entry._public_status()['table'], 3)
        # Paid and closed: the table is free again for the next guest.
        rows, _data = self._rows(self._guest(phone='5550000009'))
        self.assertEqual(rows[3]['status'], 'match')
