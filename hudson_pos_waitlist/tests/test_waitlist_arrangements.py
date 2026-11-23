# -*- coding: utf-8 -*-
"""Seating arrangements: closest suitable table(s) for a guest's party size and preference.

Real POS floors and tables (pos_restaurant TestFrontendCommon):
    Main Floor   : tables 5, 4, 2
    Second Floor : tables 1, 3
Each test sets the seats it needs and deactivates the tables it does not use.
"""
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.pos_restaurant.tests.test_frontend import TestFrontendCommon

from .test_waitlist_join import _form


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistArrangements(TestFrontendCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pos_config.write({'enable_qr_self_join': True, 'waitlist_minutes_per_party': 10})
        cls.Entry = cls.env['pos.waitlist.entry']
        cls.tables = {t.table_number: t for t in cls.pos_config.floor_ids.table_ids}
        cls.second_key = cls.Entry._floor_public_key(cls.pos_config, cls.second_floor)

    def _guest(self, phone='9550000001', **kw):
        entry, _c = self.Entry._join_from_qr(self.pos_config, _form(phone=phone, **kw))
        return entry

    def _rows(self, entry):
        data = self.Entry.with_user(self.pos_user).get_seatable_tables(self.pos_config.id, entry.id)
        return {r['table_number']: r for r in data['tables']}, data

    def _seat(self, entry, table):
        table_arg = [t.id for t in table] if isinstance(table, (list, tuple)) else table.id
        return self.Entry.with_user(self.pos_user).pos_seat_guest(
            self.pos_config.id, entry.id, 'waiting', table_arg)

    def _draft_order(self, table, guests=0):
        self.pos_config.current_session_id or self.pos_config.open_ui()
        return self.env['pos.order'].create({
            'table_id': table.id,
            'customer_count': guests,
            'company_id': self.env.company.id,
            'session_id': self.pos_config.current_session_id.id,
            'amount_paid': 0.0, 'amount_total': 0.0, 'amount_tax': 0.0, 'amount_return': 0.0,
        })

    def _only(self, **seats):
        """Keep only tables ``t<number>=<seats>`` active, with those seats."""
        for number, table in self.tables.items():
            key = f't{number}'
            if key in seats:
                table.write({'seats': seats[key], 'active': True})
            else:
                table.active = False

    def _arrangements(self, entry):
        _rows, data = self._rows(entry)
        return [a['table_numbers'] for a in data['arrangements']], data

    # TC-01
    def test_tc01_party_of_two_prefers_two_seats(self):
        self._only(t5=2, t4=4)
        arrangements, _data = self._arrangements(self._guest(party_size='2'))
        self.assertEqual(arrangements[0], [5])
        self.assertIn([4], arrangements)

    # TC-02
    def test_tc02_party_of_four_single_then_two_plus_two(self):
        self._only(t4=4, t5=2, t2=2)
        arrangements, data = self._arrangements(self._guest(party_size='4'))
        self.assertEqual(arrangements[:2], [[4], [2, 5]])
        combo = data['arrangements'][1]
        self.assertEqual((combo['available'], combo['seats'], combo['spare']), ([2, 2], 4, 0))

    # TC-03
    def test_tc03_no_four_top_uses_two_plus_two_never_one_seat(self):
        self._only(t5=2, t2=2, t4=1)
        arrangements, data = self._arrangements(self._guest(party_size='4'))
        self.assertEqual(arrangements[0], [2, 5])
        self.assertNotIn([4], arrangements)
        rows = {r['table_number']: r for r in data['tables']}
        self.assertEqual((rows[4]['status'], rows[4]['selectable']), ('too_small', False))
        for arrangement in data['arrangements']:
            self.assertGreaterEqual(arrangement['seats'], 4, "never an arrangement short of seats")

    # TC-04
    def test_tc04_party_of_seven_four_plus_three(self):
        self._only(t4=4, t5=3)
        arrangements, data = self._arrangements(self._guest(party_size='7'))
        self.assertEqual(arrangements, [[4, 5]])
        self.assertEqual(data['arrangements'][0]['seats'], 7)
        entry = self._guest(phone='9550000002', party_size='7')
        result = self._seat(entry, [self.tables[4], self.tables[5]])
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual(self.tables[5].parent_id, self.tables[4], "one arrangement: standard POS merge")

    # TC-05
    def test_tc05_shareable_partially_occupied_table(self):
        self._only(t5=4)
        self._draft_order(self.tables[5], guests=2)
        entry = self._guest(party_size='2', share_table='share')
        _arr, data = self._arrangements(entry)
        row = data['tables'][0]
        self.assertEqual((row['status'], row['occupied'], row['seats'], row['free_seats']),
                         ('shared', 2, 4, 2))
        best = data['arrangements'][0]
        self.assertTrue(best['shared'])
        self.assertEqual((best['occupied'], best['capacity'], best['available']), ([2], [4], [2]))
        self.assertIn('2 / 4 occupied', row['reason'])
        # Party of 3 at a 4-seat table with 1 guest.
        self.env['pos.order'].search([('table_id', '=', self.tables[5].id)]).customer_count = 1
        arrangements, _data = self._arrangements(
            self._guest(phone='9550000002', party_size='3', share_table='share'))
        self.assertEqual(arrangements, [[5]])
        result = self._seat(entry, self.tables[5])
        self.assertTrue(result['ok'], result['message'])
        self.assertTrue(result['shared'])

    # TC-06
    def test_tc06_private_never_partially_occupied(self):
        self._only(t5=4, t4=4)
        self._draft_order(self.tables[5], guests=2)
        entry = self._guest(party_size='2', share_table='private')
        arrangements, data = self._arrangements(entry)
        self.assertNotIn([5], arrangements)
        self.assertEqual(arrangements, [[4]])
        self.assertFalse(self._seat(entry, self.tables[5])['ok'])
        # A busy table is never combined either.
        self._only(t5=4, t4=2, t2=2)
        self._draft_order(self.tables[5], guests=1)
        arrangements, _data = self._arrangements(self._guest(phone='9550000002', party_size='6'))
        self.assertEqual(arrangements, [])

    # TC-07
    def test_tc07_exact_fit_before_oversized(self):
        self._only(t4=4, t5=6)
        arrangements, _data = self._arrangements(self._guest(party_size='4'))
        self.assertEqual(arrangements, [[4], [5]])

    def test_capacity_fit_before_fewer_tables(self):
        """Party 4: 2 + 2 (exact) ranks above a 6-seat table (2 spare)."""
        self._only(t5=2, t2=2, t4=6)
        arrangements, _data = self._arrangements(self._guest(party_size='4'))
        self.assertEqual(arrangements, [[2, 5], [4]])

    def test_shared_exact_fit_before_oversized_own_table(self):
        self._only(t5=4, t4=6)
        self._draft_order(self.tables[5], guests=2)
        arrangements, _data = self._arrangements(self._guest(party_size='2', share_table='share'))
        self.assertEqual(arrangements, [[5], [4]])

    # TC-08
    def test_tc08_nearest_combination_first(self):
        self._only(t5=2, t4=2, t2=2)
        layout = {'width': 100, 'height': 100}
        self.tables[5].floor_plan_layout = dict(layout, left=0, top=0)
        self.tables[2].floor_plan_layout = dict(layout, left=110, top=0)
        self.tables[4].floor_plan_layout = dict(layout, left=600, top=600)
        arrangements, _data = self._arrangements(self._guest(party_size='4'))
        self.assertEqual(arrangements[0], [2, 5], "the two adjacent tables")
        self.assertEqual(len(arrangements), 3)
        # Move table 4 next to table 5: now it is the nearest pair.
        self.tables[4].floor_plan_layout = dict(layout, left=0, top=105)
        arrangements, _data = self._arrangements(self._guest(phone='9550000002', party_size='4'))
        self.assertEqual(arrangements[0], [4, 5])

    def test_combinations_are_minimal_and_same_floor(self):
        self._only(t5=4, t4=4, t2=4, t1=4, t3=4)
        arrangements, data = self._arrangements(self._guest(party_size='6'))
        self.assertTrue(arrangements)
        Table = self.env['restaurant.table']
        for combo in data['arrangements']:
            self.assertEqual(len(combo['table_ids']), 2, "4 + 4 is enough: never three tables")
            self.assertEqual(len(Table.browse(combo['table_ids']).floor_id), 1)

    # TC-09
    def test_tc09_preferred_floor_unavailable(self):
        self._only(t1=4, t3=4, t4=4)
        orders = self._draft_order(self.tables[1], guests=4) | self._draft_order(self.tables[3], guests=4)
        entry = self._guest(party_size='4', preferred_floor=self.second_key)
        arrangements, data = self._arrangements(entry)
        self.assertTrue(data['preference_relaxed'])
        self.assertEqual(arrangements, [[4]], "never a busy table because it is on the preferred floor")
        # Preferred floor with a suitable table: honoured.
        orders.state = 'cancel'
        self._only(t1=4, t4=4)
        arrangements, data = self._arrangements(
            self._guest(phone='9550000002', party_size='4', preferred_floor=self.second_key))
        self.assertFalse(data['preference_relaxed'])
        self.assertEqual(arrangements, [[1]])

    # TC-10
    def test_tc10_table_taken_before_confirmation(self):
        self._only(t4=4, t5=2, t2=2)
        entry = self._guest(party_size='4')
        arrangements, _data = self._arrangements(entry)
        self.assertEqual(arrangements[0], [4])
        self._draft_order(self.tables[4], guests=2)  # another terminal opened the table
        result = self._seat(entry, self.tables[4])
        self.assertFalse(result['ok'])
        self.assertEqual(entry.state, 'waiting')
        fresh = [a['table_numbers'] for a in result['tables']['arrangements']]
        self.assertEqual(fresh, [[2, 5]], "the picker gets the current arrangements")

    # TC-11 (sequential; the threaded variant is in test_waitlist_pos)
    def test_tc11_same_combination_assigned_once(self):
        self._only(t5=2, t2=2)
        first = self._guest(party_size='4')
        second = self._guest(phone='9550000002', party_size='4')
        self.assertTrue(self._seat(first, [self.tables[2], self.tables[5]])['ok'])
        result = self._seat(second, [self.tables[2], self.tables[5]])
        self.assertFalse(result['ok'])
        self.assertEqual(second.state, 'waiting')

    def test_max_party_size_rejected_but_large_party_combined(self):
        self.pos_config.waitlist_max_party_size = 8
        with self.assertRaises(ValidationError):
            self._guest(party_size='9')
        self._only(t5=4, t4=4)
        arrangements, _data = self._arrangements(self._guest(phone='9550000002', party_size='8'))
        self.assertEqual(arrangements, [[4, 5]])
