# -*- coding: utf-8 -*-
"""Preferred Floor / Area, internal table matching, host table assignment, normal POS flow.

Real POS floors and tables (pos_restaurant TestFrontendCommon):
    Main Floor   : tables 5, 4, 2 (4 seats each)
    Second Floor : tables 1, 3    (4 seats each)
"""
import re
from datetime import timedelta
from urllib.parse import urlparse

from odoo import Command, fields
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
    def _guest(self, phone='9550000001', **kw):
        """A guest who just joined: Waiting, ready to be seated (no intermediate step)."""
        entry, _c = self.Entry._join_from_qr(self.pos_config, _form(phone=phone, **kw))
        return entry

    def _rows(self, entry):
        data = self.Entry.with_user(self.pos_user).get_seatable_tables(self.pos_config.id, entry.id)
        return {r['table_number']: r for r in data['tables']}, data

    def _seat(self, entry, table, expected='waiting'):
        if isinstance(table, (list, tuple)):
            table_arg = [t.id for t in table]
        else:
            table_arg = table.id if table else False
        return self.Entry.with_user(self.pos_user).pos_seat_guest(
            self.pos_config.id, entry.id, expected, table_arg)

    def _draft_order(self, table, guests=0, **vals):
        self.pos_config.current_session_id or self.pos_config.open_ui()
        return self.env['pos.order'].create({
            'table_id': table.id,
            'customer_count': guests,
            'company_id': self.env.company.id,
            'session_id': self.pos_config.current_session_id.id,
            'amount_paid': 0.0, 'amount_total': 0.0, 'amount_tax': 0.0, 'amount_return': 0.0,
            **vals,
        })

    def _open_own_order(self, entry, result):
        """What the POS does after seating ("Seat and Open"): the guest's own new order on the
        table, with the uuid the server issued and the guest's customer."""
        self.assertTrue(result['order_uuid'])
        return self._draft_order(entry.table_id, guests=entry.party_size, uuid=result['order_uuid'],
                                 partner_id=entry.partner_id.id)

    def _sync_target(self, uuid, table):
        """The server order a POS sync of draft order ``uuid`` on ``table`` updates (empty = new)."""
        self.pos_config.current_session_id or self.pos_config.open_ui()
        return self.env['pos.order']._get_open_order({
            'uuid': uuid, 'table_id': table.id, 'state': 'draft',
            'session_id': self.pos_config.current_session_id.id})

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
        self.assertFalse(rows[1]['selectable'], "a table short of seats is never offered alone")
        self.assertTrue(rows[1]['combinable'], "... but it can be combined with another free table")
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
        rows, _data = self._rows(self._guest(phone='9550000002', party_size='3', share_table='share'))
        self.assertEqual(rows[5]['status'], 'busy', "not enough free seats for 3")

    def test_hold_blocks_table_and_counts_for_sharing(self):
        first = self._guest(party_size='2', share_table='share')
        self.assertTrue(self._seat(first, self.tables[4])['ok'])
        rows, _data = self._rows(self._guest(phone='9550000002', party_size='2'))
        self.assertEqual(rows[4]['status'], 'busy')
        self.assertIn(first.token, rows[4]['reason'])
        rows, _data = self._rows(self._guest(phone='9550000003', party_size='2', share_table='share'))
        self.assertEqual((rows[4]['status'], rows[4]['free_seats']), ('shared', 2))
        # Hold expires without an order: free again.
        first.end_time = fields.Datetime.now() - timedelta(hours=1)
        rows, _data = self._rows(self._guest(phone='9550000004', party_size='2'))
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
        rows, _data = self._rows(self._guest(phone='9550000002', party_size='1', share_table='share'))
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
            entry = self._guest(phone=f'95500003{i:02d}')
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
    # Suggestion priority: capacity > availability > floor > sharing > hints
    # ------------------------------------------------------------------
    def test_busy_preferred_floor_does_not_force_a_table(self):
        self._draft_order(self.tables[1], guests=2)
        self._draft_order(self.tables[3], guests=2)
        entry = self._guest(preferred_floor=self.second_key, party_size='2')
        rows, data = self._rows(entry)
        self.assertTrue(data['preference_relaxed'], "Second Floor is full: every floor is offered")
        self.assertEqual({n for n, r in rows.items() if r['selectable']}, {2, 4, 5})
        self.assertNotIn('other_floor', {r['status'] for r in rows.values()})
        result = self._seat(entry, self.tables[4])
        self.assertTrue(result['ok'], result['message'])

    def test_too_small_preferred_floor_falls_back_to_capacity(self):
        self.tables[1].seats = 2
        self.tables[3].seats = 2
        self.tables[4].seats = 6
        rows, data = self._rows(self._guest(preferred_floor=self.second_key, party_size='5'))
        self.assertTrue(data['preference_relaxed'])
        self.assertEqual(data['tables'][0]['table_number'], 4, "party size first, then the floor")
        self.assertEqual(rows[1]['status'], 'too_small')

    def test_preferred_floor_honoured_only_when_suitable(self):
        rows, data = self._rows(self._guest(preferred_floor=self.main_key, party_size='4'))
        self.assertFalse(data['preference_relaxed'])
        self.assertEqual({r['floor_name'] for r in data['tables'] if r['selectable']}, {'Main Floor'})

    def test_note_and_tags_hint_but_never_override(self):
        rows, data = self._rows(self._guest(party_size='2', guest_note='Second floor please, by the window'))
        self.assertTrue(rows[1]['hint'] and rows[3]['hint'])
        self.assertFalse(rows[4]['hint'])
        self.assertEqual(data['tables'][0]['floor_name'], 'Second Floor', "suggested tables first")
        # A hint never makes a busy table pickable nor ranks it above a free one.
        self._draft_order(self.tables[1], guests=2)
        self._draft_order(self.tables[3], guests=2)
        rows, data = self._rows(self._guest(phone='9550000002', party_size='2', guest_note='second floor'))
        self.assertEqual((rows[1]['status'], rows[1]['selectable']), ('busy', False))
        self.assertIn(data['tables'][0]['table_number'], (2, 4, 5))
        # A tag configured with suggested floors.
        tag = self.env['pos.waitlist.tag'].create({'name': 'Quiet Corner', 'floor_ids': [(6, 0, self.main_floor.ids)]})
        rows, data = self._rows(self._guest(phone='9550000003', party_size='2', tags=[tag.code]))
        self.assertTrue(rows[4]['hint'])
        self.assertEqual(data['tables'][0]['floor_name'], 'Main Floor')

    # ------------------------------------------------------------------
    # Party size limit and parties larger than one table
    # ------------------------------------------------------------------
    def test_party_size_limit_from_floor_plan(self):
        self.assertEqual(self.pos_config._waitlist_party_size_limit(), 12, "Main Floor: 3 x 4 seats")
        with self.assertRaises(ValidationError):
            self._guest(party_size='13')
        self.tables[1].seats = 20
        self.assertEqual(self.pos_config._waitlist_party_size_limit(), 24)
        self.assertEqual(self._guest(party_size='24').party_size, 24)
        self.pos_config.waitlist_max_party_size = 60
        self.assertEqual(self._guest(phone='9550000002', party_size='60').party_size, 60)

    def test_oversized_party_gets_same_floor_combination(self):
        rows, data = self._rows(self._guest(party_size='7'))  # every table has 4 seats
        self.assertTrue(all(r['status'] == 'too_small' for r in rows.values()))
        self.assertTrue(data['combinations'])
        Table = self.env['restaurant.table']
        for combo in data['combinations']:
            self.assertEqual(len(combo['table_ids']), 2)
            self.assertGreaterEqual(combo['seats'], 7)
            self.assertEqual(len(Table.browse(combo['table_ids']).floor_id), 1, "never across floors")

    def test_combination_wastes_fewest_seats(self):
        self.tables[5].seats = 6
        self.tables[2].seats = 2
        self.tables[3].seats = 5
        _rows, data = self._rows(self._guest(party_size='7'))
        best = data['combinations'][0]
        self.assertEqual((best['table_numbers'], best['seats']), ([2, 5], 8))
        self.assertEqual(best['floor_name'], 'Main Floor')

    def test_single_table_ranked_before_combination(self):
        self.tables[4].seats = 8
        _rows, data = self._rows(self._guest(party_size='7'))
        self.assertEqual(data['arrangements'][0]['table_numbers'], [4], "one 8-seat table first")
        for combo in data['combinations']:
            self.assertNotIn(self.tables[4].id, combo['table_ids'], "4 alone fits: never 4 + another")
            self.assertGreaterEqual(combo['seats'], 7)

    def test_combined_tables_seated_as_one_party(self):
        entry = self._guest(party_size='7')
        result = self._seat(entry, [self.tables[4], self.tables[5]])
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual(entry.table_id, self.tables[4], "first table is the main table")
        self.assertEqual(entry.table_ids, self.tables[4] | self.tables[5])
        self.assertEqual(self.tables[5].parent_id, self.tables[4], "standard POS table merge")
        self.assertEqual(result['merged_tables'],
                         [{'id': self.tables[5].id, 'parent_id': self.tables[4].id, 'parent_side': 'right'}])
        self.assertEqual(entry._public_status()['table'], '4 + 5')
        # Nobody else can get either table.
        other = self._guest(phone='9550000002', party_size='2')
        rows, _data = self._rows(other)
        self.assertEqual(rows[4]['status'], 'busy')
        self.assertNotIn(5, rows, "merged under table 4")
        for table in (self.tables[4], self.tables[5]):
            self.assertFalse(self._seat(other, table)['ok'])
        self.assertEqual(other.state, 'waiting')

    def test_too_small_table_refused_alone_and_short_combination_refused(self):
        entry = self._guest(party_size='7')
        result = self._seat(entry, self.tables[4])
        self.assertFalse(result['ok'])
        self.assertIn('combine', result['message'])
        self.tables[5].seats = 2
        result = self._seat(entry, [self.tables[4], self.tables[5]])
        self.assertFalse(result['ok'], "4 + 2 = 6 seats for 7 guests")
        self.assertIn('6 seats', result['message'])
        self.assertEqual((entry.state, entry.table_ids.ids), ('waiting', []))
        self.assertFalse(self.tables[5].parent_id)

    def test_combined_tables_must_be_free_and_on_one_floor(self):
        entry = self._guest(party_size='7')
        result = self._seat(entry, [self.tables[4], self.tables[1]])
        self.assertFalse(result['ok'])
        self.assertIn('same floor', result['message'])
        self._draft_order(self.tables[5], guests=1)
        result = self._seat(entry, [self.tables[4], self.tables[5]])
        self.assertFalse(result['ok'])
        self.assertIn('open order', result['message'])
        self.assertEqual((entry.state, entry.table_ids.ids), ('waiting', []))
        self.assertFalse(self.tables[4].parent_id or self.tables[5].parent_id)

    # ------------------------------------------------------------------
    # Dynamic floors
    # ------------------------------------------------------------------
    def test_new_floor_available_without_new_qr(self):
        qr_url = self.pos_config.qr_join_url
        floor = self.env['restaurant.floor'].create({
            'name': 'Rooftop', 'sequence': 50, 'pos_config_ids': [(4, self.pos_config.id)]})
        self.env['restaurant.table'].create({'table_number': 30, 'floor_id': floor.id, 'seats': 6})
        html = self.url_open(f'/waitlist/join/{self.pos_config.waitlist_token}').text
        self.assertIn('Rooftop', html)
        key = self.Entry._floor_public_key(self.pos_config, floor)
        self.assertIn(f'value="{key}"', html)
        entry = self._guest(preferred_floor=key, party_size='5')
        rows, data = self._rows(entry)
        self.assertIn('Rooftop', [f['name'] for f in data['floors']])
        self.assertEqual({n for n, r in rows.items() if r['selectable']}, {30})
        floor.name = 'Sky Deck'
        labels = [label for _key, label in self.Entry._public_floor_options(self.pos_config)]
        self.assertIn('Sky Deck', labels)
        self.assertNotIn('Rooftop', labels)
        self.assertEqual(self.Entry._floor_from_public_key(self.pos_config, key), (floor, True),
                         "a rename keeps the posted key valid")
        self.assertEqual(self.pos_config.qr_join_url, qr_url, "no QR regeneration needed")

    # ------------------------------------------------------------------
    # Customer tracking ends at Seated
    # ------------------------------------------------------------------
    def _find(self, phone):
        return self.url_open(f'/waitlist/join/{self.pos_config.waitlist_token}/find',
                             data={'phone': phone, 'phone_country': 'IN'}, allow_redirects=False)

    def _join_by_form(self, **overrides):
        res = self.url_open(f'/waitlist/join/{self.pos_config.waitlist_token}', data=_form(**overrides),
                            allow_redirects=False)
        self.assertEqual(res.status_code, 303, res.text[:300])
        access_token = re.search(r'/waitlist/s/([A-Za-z0-9_-]+)', urlparse(res.headers['Location']).path).group(1)
        return self.Entry.sudo().search([('access_token', '=', access_token)]), access_token

    def test_tracking_ends_at_seated(self):
        entry, access_token = self._join_by_form(phone='9876500001', party_size='3')
        status_url = f'/waitlist/s/{access_token}'
        join_url = f'/waitlist/join/{self.pos_config.waitlist_token}'
        # Waiting: tracked (live JSON, poller on the page, Track link, Find My Place).
        self.assertEqual(self.url_open(status_url + '/json').status_code, 200)
        self.assertIn(status_url + '/json', self.url_open(status_url).text)
        self.assertIn('id="wl_track"', self.url_open(join_url).text)
        self.assertEqual(self._find('9876500001').status_code, 303)

        self.assertTrue(self._seat(entry, self.tables[4])['ok'])
        # The poll that sees the change gets the final state once, as 410: polling stops there.
        res = self.url_open(status_url + '/json')
        self.assertEqual(res.status_code, 410)
        self.assertEqual(res.headers.get('Cache-Control'), 'no-store, max-age=0')
        final = res.json()
        self.assertEqual((final['state'], final['table'], final['active'], final['tracking_ended']),
                         ('seated', 4, False, True))
        self.assertEqual(self.url_open(status_url + '/json').status_code, 410, "still ended on every retry")
        # Reopening the old link: final Seated page with the table, no live updater, way back to the QR form.
        page = self.url_open(status_url)
        self.assertEqual(page.status_code, 200)
        self.assertIn('data-state="seated"', page.text)
        self.assertIn('Please go to Table 4.', page.text)
        self.assertIn('Tracking ended for this visit', page.text)
        self.assertNotIn(status_url + '/json', page.text)
        self.assertNotIn('id="wl_status_poll"', page.text)
        self.assertIn(f'href="{join_url}?new=1"', page.text)
        self.assertNotRegex(page.text, r'id="wl_join_again"[^>]*hidden=')
        # No active session anywhere: no Track link, no Find My Place, no tracking entry.
        self.assertFalse(self.Entry._get_active_tracking_entry(self.pos_config, access_token))
        self.assertNotIn('id="wl_track"', self.url_open(join_url + '?new=1').text)
        res = self._find('9876500001')
        self.assertEqual(res.status_code, 200)
        self.assertIn('No active waitlist entry found for this number.', res.text)
        self.assertFalse(self.Entry._find_my_place(self.pos_config, '9876500001', 'IN'))
        # A new visit through the QR form is a new entry; the seated one is unchanged.
        seated_values = (entry.state, entry.token, entry.table_id, entry.sudo().access_token)
        again, again_token = self._join_by_form(phone='9876500001')
        self.assertNotEqual(again, entry)
        self.assertNotEqual(again_token, access_token)
        self.assertNotEqual(again.token, entry.token)
        self.assertEqual(again.state, 'waiting')
        self.assertEqual((entry.state, entry.token, entry.table_id, entry.sudo().access_token), seated_values)
        self.assertEqual(self.url_open(status_url + '/json').status_code, 410)

    def test_back_to_join_form_while_seated_shows_status(self):
        """Seated and still at the table: Back to (or a new scan of) the QR join form returns the
        guest to their own status page instead of an empty form. ?new=1 ("Join the waitlist
        again") still opens the form, and once the visit is over the form is normal again."""
        entry, access_token = self._join_by_form(phone='9876500002', party_size='2')
        status_url = f'/waitlist/s/{access_token}'
        join_url = f'/waitlist/join/{self.pos_config.waitlist_token}'
        self.assertTrue(self._seat(entry, self.tables[4])['ok'])
        self.assertTrue(entry._seating_active())
        # The status page keeps this browser's visit remembered while the guest is at the table.
        self.assertIn('data-state="seated"', self.url_open(status_url).text)

        res = self.url_open(join_url, allow_redirects=False)
        self.assertEqual(res.status_code, 303)
        self.assertEqual(urlparse(res.headers['Location']).path, status_url)
        self.assertIn('Please go to Table 4.', self.url_open(join_url).text)
        # Deliberate new visit: the form opens.
        res = self.url_open(join_url + '?new=1', allow_redirects=False)
        self.assertEqual(res.status_code, 200)
        self.assertIn('id="wl_submit"', res.text)

        # Visit over (table hold expired, no order): the normal join form again.
        entry, access_token = self._join_by_form(phone='9876500003', party_size='2')
        self.assertTrue(self._seat(entry, self.tables[5])['ok'])
        self.url_open(f'/waitlist/s/{access_token}')
        self.assertEqual(self.url_open(join_url, allow_redirects=False).status_code, 303)
        entry.sudo().end_time = fields.Datetime.now() - timedelta(days=1)
        self.assertFalse(entry._seating_active())
        res = self.url_open(join_url, allow_redirects=False)
        self.assertEqual(res.status_code, 200)
        self.assertIn('id="wl_submit"', res.text)

    # ------------------------------------------------------------------
    # Payment -> Odoo's own table release (the waitlist only reads it)
    # ------------------------------------------------------------------
    def _pay(self, order):
        """Pay ``order`` through the standard POS payment flow (pos.make.payment ->
        _process_saved_order -> action_pos_order_paid, as a POS sync of a paid order)."""
        if not order.lines:
            price = 2.5
            order.write({
                'lines': [Command.create({
                    'name': f'WL/{order.id}', 'product_id': self.coca_cola_test.id, 'qty': 1,
                    'price_unit': price, 'price_subtotal': price, 'price_subtotal_incl': price,
                    'tax_ids': [Command.clear()],
                })],
                'amount_total': price, 'amount_tax': 0.0,
            })
        self.env['pos.make.payment'].with_context(active_id=order.id, active_ids=order.ids).create({
            'amount': order.amount_total, 'payment_method_id': self.bank_payment_method.id,
        }).check()
        self.assertIn(order.state, ('paid', 'done'))

    def test_payment_releases_table_through_odoo_flow(self):
        """Seat -> own order on the table -> normal payment -> the table is free again for the
        waitlist (matching and wait estimate), with no waitlist-side release step."""
        entry = self._guest(phone='9876500011', party_size='2')
        result = self._seat(entry, self.tables[3])
        order = self._open_own_order(entry, result)
        self.assertEqual((order.table_id, order.partner_id, entry.pos_order_id), (self.tables[3], entry.partner_id, order))
        # Every other table taken: the next guest waits for a table to be released.
        for number in (1, 2, 4, 5):
            self._draft_order(self.tables[number], guests=4)
        nxt = self._guest(phone='9876500012', party_size='2')
        rows, _data = self._rows(nxt)
        self.assertEqual(rows[3]['status'], 'busy')
        self.assertIn('open order', rows[3]['reason'])
        waiting_before = nxt._get_wait_info()['estimated_wait']
        self.assertGreater(waiting_before, 0)

        self.env.cr.precommit.data.pop('bus.bus.values', None)
        self._pay(order)
        # Released by Odoo's lifecycle alone (no draft order on the table any more).
        self.assertFalse(self.env['pos.order'].search_count([('table_id', '=', self.tables[3].id),
                                                             ('state', '=', 'draft')]))
        self.assertTrue(self.tables[3].active)
        self.assertFalse(self.tables[3].parent_id)
        rows, _data = self._rows(nxt)
        self.assertEqual((rows[3]['status'], rows[3]['selectable']), ('match', True))
        self.assertEqual(nxt._get_wait_info()['estimated_wait'], 0, "the released table seats the next guest")
        # Open POS / backend waitlist screens were told to reload (existing live-update path).
        bus_types = [t for _c, t, _m in self.env.cr.precommit.data.get('bus.bus.values', [])]
        self.assertIn(f'{self.pos_config.access_token}-waitlist_updated', bus_types)
        # The visit is complete; the entry keeps its history.
        self.assertEqual((entry.state, entry.table_id, entry._seating_order()), ('seated', self.tables[3], order))
        self.assertTrue(entry._public_status()['completed'])
        self.assertTrue(self._seat(nxt, self.tables[3])['ok'])

    # ------------------------------------------------------------------
    # Shared table: one POS order (and bill) per party
    # ------------------------------------------------------------------
    def _seat_two_sharing_parties(self):
        """Guest A (3, shareable) at table 4 (4 seats), then guest B (1, shareable) in the last seat."""
        table = self.tables[4]
        guest_a = self._guest(phone='9550001001', guest_name='Guest Alpha', party_size='3', share_table='share')
        res_a = self._seat(guest_a, table)
        self.assertTrue(res_a['ok'], res_a['message'])
        self.assertFalse(res_a['shared'], "A had a free table")
        order_a = self._open_own_order(guest_a, res_a)

        guest_b = self._guest(phone='9550001002', guest_name='Guest Bravo', party_size='1', share_table='share')
        rows, _data = self._rows(guest_b)
        self.assertEqual((rows[4]['status'], rows[4]['occupied'], rows[4]['seats'], rows[4]['free_seats']),
                         ('shared', 3, 4, 1))
        self.assertIn('3 / 4 occupied, 1 seats available', rows[4]['reason'])
        res_b = self._seat(guest_b, table)
        self.assertTrue(res_b['ok'], res_b['message'])
        self.assertTrue(res_b['shared'])
        self.assertNotEqual(res_b['order_uuid'], res_a['order_uuid'])
        # B's first sync is a new order: never written into A's open order (pos_restaurant's
        # standard rule attaches a new table order to the table's open order).
        self.assertFalse(self._sync_target(res_b['order_uuid'], table))
        order_b = self._open_own_order(guest_b, res_b)
        return table, guest_a, order_a, guest_b, order_b

    def test_shareable_guests_share_table_with_separate_orders(self):
        table, guest_a, order_a, guest_b, order_b = self._seat_two_sharing_parties()
        self.assertNotEqual(order_a, order_b)
        self.assertEqual((order_a.table_id, order_b.table_id), (table, table), "same physical table")
        self.assertEqual((guest_a.table_id, guest_b.table_id), (table, table))
        # Each guest keeps their own order and customer.
        self.assertEqual((guest_a.pos_order_id, guest_b.pos_order_id), (order_a, order_b))
        self.assertEqual((guest_a._seating_order(), guest_b._seating_order()), (order_a, order_b))
        self.assertEqual((order_a.partner_id, order_b.partner_id), (guest_a.partner_id, guest_b.partner_id))
        self.assertNotEqual(guest_a.partner_id, guest_b.partner_id)
        self.assertEqual((order_a.customer_count, order_b.customer_count), (3, 1))
        self.assertEqual((guest_a.shared_seating, guest_b.shared_seating), (False, True))
        # Every later sync of either order updates that order only.
        self.assertEqual(self._sync_target(order_a.uuid, table), order_a)
        self.assertEqual(self._sync_target(order_b.uuid, table), order_b)
        # 4 / 4 occupied: nobody else fits, sharing or not.
        rows, _data = self._rows(self._guest(phone='9550001003', party_size='1', share_table='share'))
        self.assertEqual((rows[4]['status'], rows[4]['occupied'], rows[4]['free_seats']), ('busy', 4, 0))

    def test_paying_guest_a_leaves_guest_b_open(self):
        table, guest_a, order_a, guest_b, order_b = self._seat_two_sharing_parties()
        self._pay(order_a)
        self.assertEqual(order_b.state, 'draft', "paying A never pays / closes B")
        self.assertFalse(order_b.payment_ids)
        status_a, status_b = guest_a._public_status(), guest_b._public_status()
        self.assertEqual((status_a['completed'], status_a['seating_active'], status_a['table']), (True, False, False))
        self.assertEqual((status_b['completed'], status_b['seating_active'], status_b['table']), (False, True, 4))
        # The table is still taken by B only: 1 / 4.
        rows, _data = self._rows(self._guest(phone='9550001004', party_size='3', share_table='share'))
        self.assertEqual((rows[4]['status'], rows[4]['occupied'], rows[4]['free_seats']), ('shared', 1, 3))
        rows, _data = self._rows(self._guest(phone='9550001005', party_size='2'))
        self.assertEqual(rows[4]['status'], 'busy', "a private party still waits for the whole table")
        # B pays too: the table is free again.
        self._pay(order_b)
        self.assertTrue(guest_b._public_status()['completed'])
        rows, _data = self._rows(self._guest(phone='9550001006', party_size='2'))
        self.assertEqual(rows[4]['status'], 'match')

    def test_paying_guest_b_leaves_guest_a_open(self):
        table, guest_a, order_a, guest_b, order_b = self._seat_two_sharing_parties()
        self._pay(order_b)
        self.assertEqual(order_a.state, 'draft', "paying B never pays / closes A")
        self.assertTrue(guest_b._public_status()['completed'])
        status_a = guest_a._public_status()
        self.assertEqual((status_a['seating_active'], status_a['table']), (True, 4))
        self.assertEqual(self._sync_target(order_a.uuid, table), order_a)
        rows, _data = self._rows(self._guest(phone='9550001007', party_size='1', share_table='share'))
        self.assertEqual((rows[4]['status'], rows[4]['occupied'], rows[4]['free_seats']), ('shared', 3, 1))

    def test_order_opened_later_for_held_guest_is_not_merged_into_sharing_guest(self):
        """A seated (shareable, "Seat Only", no order yet); B shares the table and orders first;
        then the host opens A's order from the floor plan: A gets their own order."""
        table = self.tables[4]
        guest_a = self._guest(phone='9550001011', party_size='2', share_table='share')
        self.assertTrue(self._seat(guest_a, table)['ok'])
        guest_b = self._guest(phone='9550001012', party_size='2', share_table='share')
        res_b = self._seat(guest_b, table)
        self.assertTrue(res_b['shared'])
        order_b = self._open_own_order(guest_b, res_b)
        floor_uuid = 'aaaaaaaa-0000-4000-8000-000000000001'
        self.assertFalse(self._sync_target(floor_uuid, table), "never merged into B's order")
        order_a = self._draft_order(table, guests=2, uuid=floor_uuid)
        # (create_date is the test transaction's start: seat A just before it.)
        guest_a.end_time = order_a.create_date - timedelta(seconds=1)
        self.assertEqual((guest_a._seating_order(), guest_b._seating_order()), (order_a, order_b))
        self.assertEqual(self._sync_target(floor_uuid, table), order_a)

    def test_normal_table_keeps_standard_order_merge(self):
        """No shared waitlist seating on the table: the standard pos_restaurant rule is untouched
        (a second terminal's new order on an open table goes to the table's open order)."""
        walk_in = self._draft_order(self.tables[2], guests=2)
        self.assertEqual(self._sync_target('bbbbbbbb-0000-4000-8000-000000000002', self.tables[2]), walk_in)
        self.assertEqual(self._sync_target(walk_in.uuid, self.tables[2]), walk_in)
        entry = self._guest(phone='9550001021', party_size='2')
        result = self._seat(entry, self.tables[5])
        order = self._open_own_order(entry, result)
        self.assertEqual(self._sync_target('bbbbbbbb-0000-4000-8000-000000000003', self.tables[5]), order)

    def test_private_seating_keeps_the_whole_table(self):
        table = self.tables[4]
        private = self._guest(phone='9550001031', party_size='2', share_table='private')
        result = self._seat(private, table)
        self.assertTrue(result['ok'], result['message'])
        sharer = self._guest(phone='9550001032', party_size='1', share_table='share')

        def check_blocked():
            rows, _data = self._rows(sharer)
            self.assertEqual((rows[4]['status'], rows[4]['free_seats'], rows[4]['selectable']), ('busy', 0, False))
            self.assertIn('Private seating', rows[4]['reason'])
            refused = self._seat(sharer, table)
            self.assertFalse(refused['ok'])
            self.assertEqual(sharer.state, 'waiting')

        check_blocked()  # table hold
        self._open_own_order(private, result)
        check_blocked()  # the private party's own order
        # Same when the host seated with "Seat Only" and opened the table from the floor plan.
        other = self._guest(phone='9550001033', party_size='2', share_table='private')
        self.assertTrue(self._seat(other, self.tables[5])['ok'])
        floor_order = self._draft_order(self.tables[5], guests=2)
        other.end_time = floor_order.create_date - timedelta(seconds=1)
        self.assertEqual(other._seating_order(), floor_order)
        rows, _data = self._rows(sharer)
        self.assertEqual((rows[5]['status'], rows[5]['occupied'], rows[5]['free_seats']), ('busy', 2, 0))
        # A walk-in's order (no waitlist guest) can still be shared, as before.
        self._draft_order(self.tables[2], guests=2)
        rows, _data = self._rows(sharer)
        self.assertEqual((rows[2]['status'], rows[2]['free_seats']), ('shared', 2))

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
        self.assertEqual(orders.partner_id, entry.partner_id, "the waitlist customer is on the order")
        # Paid: the visit is completed, the guest's page no longer shows the table.
        status = entry._public_status()
        self.assertEqual((status['table'], status['completed'], status['seating_active']), (False, True, False))
        self.assertEqual(entry._seating_order(), orders)
        # Paid and closed: the table is free again for the next guest.
        rows, _data = self._rows(self._guest(phone='9550000009'))
        self.assertEqual(rows[3]['status'], 'match')
