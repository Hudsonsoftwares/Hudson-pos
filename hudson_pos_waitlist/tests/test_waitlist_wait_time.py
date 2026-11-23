# -*- coding: utf-8 -*-
"""Dynamic, capacity-aware waiting time (pos.waitlist.entry._queue_wait_estimates).

Every scenario builds its own floor plan on a real restaurant POS and occupies tables the
standard POS way (a draft pos.order on the table); a table is released by paying its order.
Average Waiting Time = 10 min (baseline pace while there are no recent seatings).
"""
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.pos_restaurant.tests.test_frontend import TestFrontendCommon

from .test_waitlist_join import _form


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistWaitTime(TestFrontendCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pos_config.write({'enable_qr_self_join': True, 'waitlist_minutes_per_party': 10,
                              'waitlist_max_party_size': 40})
        cls.Entry = cls.env['pos.waitlist.entry']
        cls._phone = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _restaurant(self, *floors):
        """Replace the POS floor plan. ``floors``: one list of seat counts per floor."""
        created = []
        for index, seats in enumerate(floors):
            floor = self.env['restaurant.floor'].create({
                'name': f'WT Floor {index + 1}', 'sequence': index + 1,
                'pos_config_ids': [(4, self.pos_config.id)]})
            created.append(floor)
            for number, size in enumerate(seats, start=1):
                self.env['restaurant.table'].create({
                    'table_number': (index + 1) * 100 + number, 'floor_id': floor.id, 'seats': size})
        self.pos_config.floor_ids = [(6, 0, [f.id for f in created])]
        return created

    def _tables(self, floor=None):
        floors = floor or self.pos_config.floor_ids
        return floors.table_ids.sorted('table_number')

    def _occupy(self, tables, guests=0):
        self.pos_config.current_session_id or self.pos_config.open_ui()
        return self.env['pos.order'].create([{
            'table_id': table.id,
            'customer_count': guests,
            'company_id': self.env.company.id,
            'session_id': self.pos_config.current_session_id.id,
            'amount_paid': 0.0, 'amount_total': 0.0, 'amount_tax': 0.0, 'amount_return': 0.0,
        } for table in tables])

    def _guest(self, size=2, **kw):
        type(self)._phone += 1
        entry, _created = self.Entry._join_from_qr(
            self.pos_config, _form(phone=f'95600{self._phone:05d}', party_size=str(size), **kw))
        return entry

    def _waits(self, entries):
        estimates = self.Entry._queue_wait_estimates(self.pos_config)
        return [estimates.get(e.id) for e in entries]

    def _payload(self):
        entries = self.Entry.with_user(self.pos_user).get_pos_queue(self.pos_config.id)['entries']
        return {e['token']: e for e in entries}

    def _bus_types(self):
        return [type_ for _channel, type_, _msg in self.env.cr.precommit.data.get("bus.bus.values", [])]

    def _clear_bus(self):
        self.env.cr.precommit.data.get("bus.bus.values", []).clear()

    # ------------------------------------------------------------------
    # Capacity / availability
    # ------------------------------------------------------------------
    def test_spec_example_free_tables_seat_the_queue(self):
        """20 tables, 15 occupied, 5 free, 5 waiting couples: nobody waits 5 x 10 = 50 min."""
        self._restaurant([4] * 20)
        self._occupy(self._tables()[:15])
        guests = [self._guest() for _i in range(5)]
        self.assertEqual(self._waits(guests), [0.0] * 5)
        self.assertEqual(guests[-1]._public_status()['estimated_wait_label'], '~0–5 min')

    def test_10_vs_30_table_restaurant(self):
        """Same queue, same occupied tables: the bigger restaurant's free tables shorten it."""
        self._restaurant([4] * 10)
        self._occupy(self._tables())
        guests = [self._guest() for _i in range(6)]
        small = self._waits(guests)
        self.assertTrue(all(w > 0 for w in small), small)

        # The same restaurant grown to 30 tables (floors cannot change while a session is
        # open, tables can): 25 occupied, 5 free.
        floor = self.pos_config.floor_ids
        new_tables = self.env['restaurant.table'].create([
            {'table_number': 500 + n, 'floor_id': floor.id, 'seats': 4} for n in range(20)])
        self._occupy(new_tables[:15])
        self.assertEqual(len(self.Entry._seatable_tables(self.pos_config)), 30)
        large = self._waits(guests)
        self.assertEqual(large[:5], [0.0] * 5, "5 free tables seat 5 parties now")
        self.assertLess(large[5], small[5])
        self.assertTrue(all(lg <= sm for lg, sm in zip(large, small)))

    def test_occupied_and_free_tables_change_the_estimate(self):
        self._restaurant([4, 4])
        table_a, table_b = self._tables()
        guest = self._guest()
        self.assertEqual(self._waits(guest), [0.0])
        order_a, order_b = self._occupy(table_a | table_b)
        self.assertEqual(self._waits(guest), [10.0], "no free table: next table to free up")
        order_a.state = 'cancel'  # the POS cancels the table's order: free again
        self.assertEqual(self._waits(guest), [0.0])

    def test_party_size_and_large_party_combination(self):
        """2-seat table free, two 6-seat tables busy. Queue: 6 guests, 2 guests, 10 guests."""
        self._restaurant([2, 6, 6])
        small, big_a, big_b = self._tables()
        self._occupy(big_a | big_b)
        six = self._guest(size=6)
        two = self._guest(size=2)
        ten = self._guest(size=10)
        w_six, w_two, w_ten = self._waits(six | two | ten)
        self.assertEqual(w_two, 0.0, "the couple behind takes the free 2-seat table now")
        self.assertEqual(w_six, 10.0, "6 guests wait for the first 6-seat table")
        self.assertGreater(w_ten, w_six, "10 guests need two tables combined, later")
        self.assertIsNotNone(w_ten)

    def test_party_that_can_never_fit(self):
        self._restaurant([4, 4])
        entry = self.Entry.create({'config_id': self.pos_config.id, 'guest_name': 'Big Group',
                                   'phone': '+91 95700 00001', 'party_size': 30})
        self.assertEqual(self._waits(entry), [None])
        status = entry._public_status()
        # Conservative, never a falsely short / exact number: "30+ min".
        self.assertEqual((status['estimated_wait'], status['estimated_wait_label'],
                          status['estimated_wait_min'], status['estimated_wait_max']),
                         (30, '30+ min', 30, False))

    def test_shared_table_and_preferred_floor(self):
        floor_1, floor_2 = self._restaurant([6], [4])
        shared_table = self._tables(floor_1)
        self._occupy(shared_table, guests=2)  # 4 seats left at the 6-seat table
        self._occupy(self._tables(floor_2))
        sharer = self._guest(share_table='share')
        private = self._guest()
        self.assertEqual(self._waits(sharer | private), [0.0, 10.0])

        floor_2_key = self.Entry._floor_public_key(self.pos_config, floor_2)
        prefers_2 = self._guest(preferred_floor=floor_2_key, size=4)
        self.assertGreater(self._waits(prefers_2)[0], 0)
        # A preference for a floor that cannot hold the party never blocks it.
        too_big_for_2 = self._guest(preferred_floor=floor_2_key, size=6)
        self.assertIsNotNone(self._waits(too_big_for_2)[0])

    # ------------------------------------------------------------------
    # Queue ahead
    # ------------------------------------------------------------------
    def test_never_position_times_average_and_cancel_moves_queue(self):
        self._restaurant([4, 4])
        self._occupy(self._tables())
        g1, g2, g3 = self._guest(), self._guest(), self._guest()
        before = self._waits(g1 | g2 | g3)
        self.assertEqual(before[0], 10.0)
        self.assertLess(before[0], before[1])
        self.assertLess(before[1], before[2])
        g2.state = 'cancelled'
        self.assertEqual(self._waits(g3), [before[1]], "W-003 moves into W-002's slot")
        g1.state = 'left'
        self.assertEqual(self._waits(g3), [before[0]])

    def test_quote_at_join_is_the_guest_own_estimate(self):
        self._restaurant([4, 4])
        self._occupy(self._tables())
        g1, g2 = self._guest(), self._guest()
        self.assertEqual((g1.quoted_wait, g2.quoted_wait), (10, 20))

    # ------------------------------------------------------------------
    # POS flow: payment releases a table, seating holds one
    # ------------------------------------------------------------------
    def test_payment_releases_table_through_pos_flow(self):
        self._restaurant([4, 4])
        table_a, table_b = self._tables()
        order_a, _order_b = self._occupy(table_a | table_b)
        g1, g2 = self._guest(), self._guest()
        self.assertEqual(self._waits(g1 | g2), [10.0, 20.0])

        self._clear_bus()
        order_a.action_pos_order_paid()  # the standard POS payment completion
        self.assertIn(order_a.state, ('paid', 'done'))
        self.assertIn(f'{self.pos_config.access_token}-waitlist_updated', self._bus_types(),
                      "open POS waitlists are told to refresh")
        self.assertNotIn(table_a.id, self.Entry._table_occupancy(table_a | table_b),
                         "the POS's own rule now sees table A free")
        self.assertEqual(self._waits(g1 | g2), [0.0, 10.0])
        self.assertEqual(self._payload()[g1.token]['estimated_wait_label'], '~0–5 min')

        # Seating W-001 at table A holds it again: W-002 still waits for table B.
        result = self.Entry.with_user(self.pos_user).pos_seat_guest(
            self.pos_config.id, g1.id, 'waiting', table_a.id)
        self.assertTrue(result['ok'], result['message'])
        self.assertIn(table_a.id, self.Entry._table_occupancy(table_a | table_b))
        self.assertEqual(self._waits(g2), [10.0])

    def test_new_table_order_notifies_waitlist(self):
        self._restaurant([4, 4])
        self._guest()
        self._clear_bus()
        self._occupy(self._tables()[:1])
        self.assertIn(f'{self.pos_config.access_token}-waitlist_updated', self._bus_types())

    def test_table_change_notifies_waitlist(self):
        self._restaurant([4], [4])  # two floors of 4 seats: 6 guests cannot be seated
        guest = self._guest(size=6)
        self.assertEqual(self._waits(guest), [None])
        self._clear_bus()
        self._tables()[0].seats = 6
        self.assertIn(f'{self.pos_config.access_token}-waitlist_updated', self._bus_types())
        self.assertEqual(self._waits(guest), [0.0])

    # ------------------------------------------------------------------
    # Recent seating rate vs configured average
    # ------------------------------------------------------------------
    def _seated_history(self, minutes_ago):
        now = fields.Datetime.now()
        for index, ago in enumerate(minutes_ago):
            self.Entry.create({'config_id': self.pos_config.id, 'guest_name': 'Past Guest',
                               'phone': f'+91 95800 {index:05d}', 'party_size': 2,
                               'state': 'seated', 'end_time': now - timedelta(minutes=ago)})

    def test_configured_average_is_the_fallback(self):
        self._restaurant([4])
        self._occupy(self._tables())
        self._seated_history([200, 197, 194, 191])  # outside the rolling window
        self.assertEqual(self.Entry._seating_interval(self.pos_config), (10.0, False))
        guest = self._guest()
        self.assertEqual(self._waits(guest), [10.0])
        self.pos_config.waitlist_minutes_per_party = 7
        self.assertEqual(self._waits(guest), [7.0])

    def test_recent_seating_rate_drives_the_pace(self):
        self._restaurant([4])
        self._occupy(self._tables())
        # A party seated every 3 minutes over the last half hour (10 gaps: fully trusted).
        self._seated_history([30, 27, 24, 21, 18, 15, 12, 9, 6, 3, 0])
        interval, observed = self.Entry._seating_interval(self.pos_config)
        self.assertTrue(observed)
        self.assertAlmostEqual(interval, 3.0, delta=0.2)
        guest = self._guest()
        self.assertAlmostEqual(self._waits(guest)[0], 3.0, delta=0.2)

    def test_few_recent_seatings_are_blended_with_the_average(self):
        self._restaurant([4])
        self._occupy(self._tables())
        self._seated_history([9, 6, 3, 0])  # 3 gaps of 3 min
        interval, observed = self.Entry._seating_interval(self.pos_config)
        self.assertTrue(observed)
        self.assertTrue(3.0 < interval < 10.0, interval)

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------
    def test_ranges(self):
        rng = self.Entry._wait_range
        self.assertEqual([rng(0), rng(4.9), rng(7), rng(13), rng(17), rng(24), rng(29.9), rng(30), rng(80)],
                         [(0, 5), (0, 5), (5, 10), (10, 15), (15, 20), (20, 30), (20, 30), (30, None), (30, None)])
        self.assertEqual(rng(None), (30, None))
        label = self.Entry._wait_label
        self.assertEqual([label(0), label(13), label(23), label(45), label(None)],
                         ['~0–5 min', '~10–15 min', '~20–30 min', '30+ min', '30+ min'])

    def test_guest_page_and_pos_show_the_same_estimate(self):
        self._restaurant([4])
        self._occupy(self._tables())
        g1, g2 = self._guest(), self._guest()
        payload = self._payload()
        for guest in (g1, g2):
            status = guest._public_status()
            self.assertNotIn('position', status)
            for key in ('estimated_wait', 'estimated_wait_min', 'estimated_wait_max', 'estimated_wait_label'):
                self.assertEqual(status[key], payload[guest.token][key], key)
        self.assertEqual(g1._public_status()['estimated_wait_label'], '~10–15 min')
        data = self.url_open(f'/waitlist/s/{g2.sudo().access_token}/json').json()
        self.assertEqual(data['estimated_wait_label'], '~20–30 min')
        page = self.url_open(f'/waitlist/s/{g2.sudo().access_token}').text
        self.assertIn('~20–30 min', page)

    def test_backend_shows_the_same_server_estimate(self):
        self._restaurant([4])
        self._occupy(self._tables())
        g1, g2 = self._guest(), self._guest()
        payload = self._payload()
        backend = self.Entry.with_user(self.pos_user).browse((g1 | g2).ids)
        self.assertEqual(backend.mapped('estimated_wait_label'),
                         [payload[g1.token]['estimated_wait_label'], payload[g2.token]['estimated_wait_label']])
        g1.state = 'cancelled'
        self.env.invalidate_all()
        self.assertFalse(g1.estimated_wait_label, "closed entries have no estimate")
        self.assertEqual(g2.estimated_wait_label, '~10–15 min', "W-002 moved up")

    # ------------------------------------------------------------------
    # Validation scenarios of the specification
    # ------------------------------------------------------------------
    def test_scenario_1_two_suitable_free_tables(self):
        self._restaurant([4] * 10)
        self._occupy(self._tables()[:8])
        guest = self._guest(size=4)
        self.assertEqual(self._waits(guest), [0.0])
        self.assertEqual(guest._public_status()['estimated_wait_label'], '~0–5 min')

    def test_scenario_2_all_occupied_uses_queue_and_pace(self):
        self._restaurant([4] * 10)
        self._occupy(self._tables())
        guests = [self._guest() for _i in range(3)]
        self.assertEqual(self._waits(guests), [10.0, 20.0, 30.0])
        self.assertEqual([g._public_status()['estimated_wait_label'] for g in guests],
                         ['~10–15 min', '~20–30 min', '30+ min'])

    def test_scenario_4_party_of_8_with_only_4_seat_tables(self):
        floor_1, floor_2 = self._restaurant([4, 4, 4], [4])
        self._occupy(self._tables(floor_1)[:2])  # one 4-seat table free on each floor
        eight = self._guest(size=8)
        self.assertGreater(self._waits(eight)[0], 0,
                           "one free 4-seat table (or two on different floors) is not enough")
        # A second 4-seat table frees up on floor 1: two tables can be combined right now.
        self.env['pos.order'].search([('table_id', '=', self._tables(floor_1)[0].id)]).state = 'cancel'
        self.assertEqual(self._waits(eight), [0.0])

    def test_scenario_8_no_near_term_capacity_is_30_plus(self):
        self._restaurant([4, 4])
        self._occupy(self._tables())
        guests = [self._guest() for _i in range(5)]
        self.assertEqual(guests[-1]._public_status()['estimated_wait_label'], '30+ min')

    def test_estimation_never_reserves_a_table(self):
        self._restaurant([4, 4])
        tables = self._tables()
        guests = [self._guest() for _i in range(3)]
        self.Entry._queue_wait_estimates(self.pos_config)
        self._payload()
        self.assertEqual(self.Entry._table_occupancy(tables), {})
        self.assertFalse(self.Entry.browse([g.id for g in guests]).table_id)
        self.assertEqual(set(self.Entry.browse([g.id for g in guests]).mapped('state')), {'waiting'})

    def test_payment_refreshes_backend_views_too(self):
        self._restaurant([4])
        (order,) = self._occupy(self._tables())
        self._guest()
        self._clear_bus()
        order.action_pos_order_paid()
        self.assertIn('hudson_waitlist_changed', self._bus_types())

    # ------------------------------------------------------------------
    # Robust pace and actual waits
    # ------------------------------------------------------------------
    def test_one_outlier_seating_does_not_distort_the_pace(self):
        # Every 3 min, except one 40-minute lull: the median ignores it (a mean would say ~6.4).
        self._seated_history([67, 64, 61, 58, 55, 15, 12, 9, 6, 3, 0])
        interval, observed = self.Entry._seating_interval(self.pos_config)
        self.assertTrue(observed)
        self.assertAlmostEqual(interval, 3.0, delta=0.2)

    def _seated_with_wait(self, waits, quoted):
        now = fields.Datetime.now()
        for index, waited in enumerate(waits):
            end = now - timedelta(minutes=index * 10)  # pace = baseline (10 min)
            self.Entry.create({'config_id': self.pos_config.id, 'guest_name': 'Past Guest',
                               'phone': f'+91 95900 {index:05d}', 'party_size': 2, 'state': 'seated',
                               'quoted_wait': quoted, 'join_time': end - timedelta(minutes=waited),
                               'end_time': end})

    def test_actual_waits_longer_than_quoted_stretch_estimates(self):
        self._restaurant([4])
        self._occupy(self._tables())
        self._seated_with_wait([12, 13, 13, 14], quoted=10)  # guests waited ~30% longer
        factor = self.Entry._wait_calibration(self.pos_config)
        self.assertAlmostEqual(factor, 1.3, delta=0.01)
        guest = self._guest()
        self.assertGreater(self._waits(guest)[0], 10.0)

    def test_actual_waits_shorter_than_quoted_never_shorten(self):
        self._seated_with_wait([2, 3, 2, 3], quoted=10)
        self.assertEqual(self.Entry._wait_calibration(self.pos_config), 1.0)

    def test_actual_wait_calibration_is_capped(self):
        self._seated_with_wait([60, 60, 60], quoted=10)
        self.assertEqual(self.Entry._wait_calibration(self.pos_config), 1.5)

    def test_free_table_stays_zero_whatever_the_calibration(self):
        self._restaurant([4])
        self._seated_with_wait([60, 60, 60], quoted=10)
        guest = self._guest()
        self.assertEqual(self._waits(guest), [0.0])
