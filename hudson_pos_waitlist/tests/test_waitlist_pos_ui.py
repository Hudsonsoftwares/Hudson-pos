# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.pos_restaurant.tests.test_frontend import TestFrontendCommon

from .test_waitlist_join import _form


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistPosUi(TestFrontendCommon):
    """Seat Guest at existing POS restaurant tables (real floors, tables and orders)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pos_config.write({'enable_qr_self_join': True, 'waitlist_minutes_per_party': 10})
        cls.Entry = cls.env['pos.waitlist.entry']
        cls.tables = {t.table_number: t for t in cls.pos_config.floor_ids.table_ids}

    def _waiting_guest(self, phone='9550000001', name='Ada Lovelace', **kw):
        entry, _c = self.Entry._join_from_qr(self.pos_config, _form(guest_name=name, phone=phone, **kw))
        return entry

    def _seat(self, entry, table, expected='waiting'):
        return self.Entry.with_user(self.pos_user).pos_seat_guest(
            self.pos_config.id, entry.id, expected, table.id if table else False)

    def _draft_order(self, table):
        self.pos_config.current_session_id or self.pos_config.open_ui()
        return self.env['pos.order'].create({
            'table_id': table.id,
            'company_id': self.env.company.id,
            'session_id': self.pos_config.current_session_id.id,
            'amount_paid': 0.0, 'amount_total': 0.0, 'amount_tax': 0.0, 'amount_return': 0.0,
        })

    # ------------------------------------------------------------------
    # Server rules
    # ------------------------------------------------------------------
    def test_seatable_tables_are_the_pos_floor_plan(self):
        data = self.Entry.with_user(self.pos_user).get_seatable_tables(self.pos_config.id)
        self.assertEqual(sorted(data['available_ids']), sorted(t.id for t in self.tables.values()))

    def test_seat_requires_a_table_on_restaurant_pos(self):
        entry = self._waiting_guest()
        result = self.Entry.with_user(self.pos_user).pos_change_state(
            self.pos_config.id, entry.id, 'waiting', 'seated')
        self.assertFalse(result['ok'])
        self.assertIn('Choose a table', result['message'])
        self.assertFalse(self._seat(entry, None)['ok'])
        self.assertEqual(entry.state, 'waiting')

    def test_seat_at_free_table(self):
        entry = self._waiting_guest()
        table = self.tables[4]
        result = self._seat(entry, table)
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual((entry.state, entry.table_id), ('seated', table))
        self.assertTrue(entry.end_time)
        self.assertEqual(result['queue']['entries'], [], "seated guest leaves the active list")
        self.assertNotIn(table.id, result['tables']['available_ids'], "table is now held")
        status = entry._public_status()
        self.assertEqual((status['state'], status['table']), ('seated', 4))

    def test_waiting_guest_seated_directly(self):
        """Waiting -> Seated in one host action: no intermediate status."""
        entry, _c = self.Entry._join_from_qr(self.pos_config, _form())
        self.assertEqual(entry.state, 'waiting')
        result = self._seat(entry, self.tables[4], expected='waiting')
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual((entry.state, entry.table_id), ('seated', self.tables[4]))

    def test_stale_terminal_cannot_seat(self):
        entry = self._waiting_guest()
        self.Entry.pos_change_state(self.pos_config.id, entry.id, 'waiting', 'cancelled')
        result = self._seat(entry, self.tables[4])
        self.assertFalse(result['ok'])
        self.assertEqual(result['state'], 'cancelled')
        self.assertFalse(entry.table_id)

    def test_table_with_open_order_is_refused(self):
        table = self.tables[5]
        self._draft_order(table)
        self.assertNotIn(table.id, self.Entry.get_seatable_tables(self.pos_config.id)['available_ids'])
        entry = self._waiting_guest()
        result = self._seat(entry, table)
        self.assertFalse(result['ok'])
        self.assertIn('open order', result['message'])
        self.assertEqual(entry.state, 'waiting', "guest stays waiting to pick another table")
        self.assertNotIn(table.id, result['tables']['available_ids'])
        self.assertIn(self.tables[4].id, result['tables']['available_ids'])

    def test_same_table_cannot_get_two_guests(self):
        first = self._waiting_guest()
        second = self._waiting_guest(phone='9550000002', name='Grace Hopper')
        table = self.tables[2]
        self.assertTrue(self._seat(first, table)['ok'])
        result = self._seat(second, table)
        self.assertFalse(result['ok'])
        self.assertIn(first.token, result['message'])
        self.assertEqual(second.state, 'waiting')
        self.assertTrue(self._seat(second, self.tables[3])['ok'], "another table works")

    def test_hold_ends_when_table_order_is_closed(self):
        entry = self._waiting_guest()
        table = self.tables[1]
        self.assertTrue(self._seat(entry, table)['ok'])
        # The guest's order reaches the server later (its own request / transaction).
        order = self._draft_order(table)
        order.flush_recordset()
        self.env.cr.execute("UPDATE pos_order SET create_date = %s WHERE id = %s",
                            (entry.end_time + timedelta(seconds=5), order.id))
        order.invalidate_recordset(['create_date'])
        self.assertNotIn(table.id, self.Entry.get_seatable_tables(self.pos_config.id)['available_ids'])
        order.write({'state': 'cancel'})
        self.assertIn(table.id, self.Entry.get_seatable_tables(self.pos_config.id)['available_ids'],
                      "after the order is closed the table is free again")

    def test_hold_expires_without_order(self):
        entry = self._waiting_guest()
        table = self.tables[1]
        self.assertTrue(self._seat(entry, table)['ok'])
        entry.end_time = fields.Datetime.now() - timedelta(hours=1)
        self.assertIn(table.id, self.Entry.get_seatable_tables(self.pos_config.id)['available_ids'])

    def test_other_pos_table_refused(self):
        other_floor = self.env['restaurant.floor'].create({'name': 'Elsewhere'})
        other_table = self.env['restaurant.table'].create({'table_number': 99, 'floor_id': other_floor.id})
        entry = self._waiting_guest()
        result = self._seat(entry, other_table)
        self.assertFalse(result['ok'])
        self.assertEqual(entry.state, 'waiting')

    # ------------------------------------------------------------------
    # Browser
    # ------------------------------------------------------------------
    def test_waitlist_panel_host_actions(self):
        Entry = self.Entry
        main_floor_key = Entry._floor_public_key(self.pos_config, self.main_floor)
        first, _c = Entry._join_from_qr(self.pos_config, _form(guest_name='Ada Lovelace',
                                                               preferred_floor=main_floor_key))
        second, _c = Entry._join_from_qr(self.pos_config, _form(guest_name='Grace Hopper', phone='9550000002'))

        self.pos_config.with_user(self.pos_user).open_ui()
        self.start_pos_tour('hudson_pos_waitlist_tour', pos_config=self.pos_config)

        self.assertEqual(first.state, 'seated')
        self.assertEqual(first.table_id.table_number, 4)
        self.assertEqual(second.state, 'cancelled')

    def test_seat_and_open_table_keeps_normal_order_flow(self):
        guest = self._waiting_guest()
        self.pos_config.with_user(self.pos_user).open_ui()
        self.start_pos_tour('hudson_pos_waitlist_seat_open_tour', pos_config=self.pos_config)

        table = self.tables[5]
        self.assertEqual((guest.state, guest.table_id), ('seated', table))
        order = self.env['pos.order'].search([('table_id', '=', table.id), ('state', '=', 'draft')])
        self.assertEqual(len(order), 1, "the normal POS order was created on the seated table")
        self.assertEqual(order.customer_count, guest.party_size)
        self.assertNotIn(table.id, self.Entry.get_seatable_tables(self.pos_config.id)['available_ids'])

    def test_seat_request_replayed_after_lost_response(self):
        """POS lost the answer (refresh / reconnect) and sends the same seat request again."""
        entry = self._waiting_guest()
        first = self._seat(entry, self.tables[4])
        self.assertTrue(first['ok'])
        again = self._seat(entry, self.tables[4])
        self.assertFalse(again['ok'])
        self.assertEqual(again['state'], 'seated')
        retry_other_table = self._seat(entry, self.tables[2])
        self.assertFalse(retry_other_table['ok'])
        self.assertEqual(entry.table_id, self.tables[4], "the first seating is kept")
        self.assertIn(self.tables[2].id, retry_other_table['tables']['available_ids'])
        # A reloaded POS gets the current queue.
        self.assertEqual(self.Entry.with_user(self.pos_user).get_pos_queue(self.pos_config.id)['entries'], [])
