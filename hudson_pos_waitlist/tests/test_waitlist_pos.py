# -*- coding: utf-8 -*-
"""POS Waitlist screen: host actions, server-side transitions, multi-terminal safety."""
import threading

from odoo.exceptions import ValidationError
from odoo.sql_db import db_connect, PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tests import new_test_user, tagged

from . import test_waitlist_join
from .test_waitlist_join import WaitlistCommon, _form


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistPosActions(WaitlistCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.host = new_test_user(cls.env, login='waitlist_host', groups='point_of_sale.group_pos_user')

    def change(self, entry, expected, new, user=None):
        Entry = self.Entry.with_user(user or self.host)
        return Entry.pos_change_state(entry.config_id.id, entry.id, expected, new)

    def test_queue_payload(self):
        self.join(phone='9550000001', tags=['birthday'])
        self.join(phone='9550000002', party_size='6', share_table='share')
        queue = self.Entry.with_user(self.host).get_pos_queue(self.config_a.id)
        self.assertTrue(queue['enabled'])
        self.assertTrue(queue['server_time'])
        first, second = queue['entries']
        # Host screen keeps the order (position); the estimate is the flat Average Waiting Time.
        self.assertEqual((first['token'], first['position'], first['estimated_wait']), ('W-001', 1, 10))
        self.assertEqual((second['token'], second['position'], second['estimated_wait']), ('W-002', 2, 10))
        self.assertEqual(second['floor_pref_label'], 'Any Floor')
        self.assertFalse(second['preferred_floor_id'])
        self.assertEqual(second['share_table_short'], 'Can share')
        self.assertEqual(second['share_table_label'], "I'm willing to share a table")
        self.assertEqual(first['allowed_states'], ['seated', 'cancelled', 'left', 'no_show'])
        self.assertNotIn('access_token', first)

    def test_estimated_wait_uses_pos_setting(self):
        self.config_a.waitlist_minutes_per_party = 7
        self.join(phone='9550000001')
        self.join(phone='9550000002')
        waits = [e['estimated_wait'] for e in self.Entry.get_pos_queue(self.config_a.id)['entries']]
        self.assertEqual(waits, [7, 7])

    def test_full_host_flow(self):
        """Waiting -> Seated in one host action (this POS has no floor plan: no table needed)."""
        entry, _created = self.join()
        result = self.change(entry, 'waiting', 'seated')
        self.assertTrue(result['ok'], result['message'])
        self.assertEqual(entry.state, 'seated')
        self.assertTrue(entry.end_time)
        self.assertEqual(result['queue']['entries'], [], "seated guests leave the active list")
        self.assertFalse(entry._public_status()['active'])

    def test_called_status_is_gone(self):
        self.assertNotIn('called', dict(self.Entry._fields['state'].selection))
        entry, _created = self.join()
        result = self.change(entry, 'waiting', 'called')
        self.assertFalse(result['ok'])
        self.assertEqual(entry.state, 'waiting')
        with self.assertRaises(ValueError):
            entry.write({'state': 'called'})

    def test_migration_moves_called_back_to_waiting(self):
        """1.8 migration: entries left in the removed 'called' state are waiting again."""
        import importlib.util
        from odoo.tools.misc import file_path
        entry, _created = self.join()
        self.env.flush_all()
        self.env.cr.execute("UPDATE pos_waitlist_entry SET state = 'called', end_time = now() WHERE id = %s",
                            (entry.id,))
        path = file_path('hudson_pos_waitlist/migrations/20.0.1.8.0/pre-migrate.py')
        spec = importlib.util.spec_from_file_location('wl_pre_migrate_1_8', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, '20.0.1.7.0')
        entry.invalidate_recordset()
        self.assertEqual((entry.state, entry.end_time, entry.token), ('waiting', False, 'W-001'))
        self.assertEqual(entry.position, 1)

    def test_every_allowed_transition(self):
        allowed = [('waiting', 'seated'), ('waiting', 'cancelled'), ('waiting', 'left'), ('waiting', 'no_show')]
        for i, (start, target) in enumerate(allowed):
            entry, _created = self.join(phone=f'95500001{i:02d}')
            result = self.change(entry, start, target)
            self.assertTrue(result['ok'], (start, target, result['message']))
            self.assertEqual(entry.state, target)

    def test_invalid_transitions_rejected(self):
        entry, _created = self.join()
        for target in ('waiting', 'bogus', 'called'):
            result = self.change(entry, 'waiting', target)
            self.assertFalse(result['ok'], target)
            self.assertEqual(result['state'], 'waiting')
        self.assertEqual(entry.state, 'waiting')
        for closed in ('seated', 'cancelled', 'left', 'no_show'):
            other, _created = self.join(phone=f'95500009{len(closed):02d}')
            self.change(other, 'waiting', closed)
            for target in ('waiting', 'seated', 'cancelled'):
                if target == closed:
                    continue
                result = self.change(other, closed, target)
                self.assertFalse(result['ok'], f"closed visit {closed} -> {target} must be refused")
            self.assertEqual(other.state, closed)

    def test_stale_terminal_gets_latest_state(self):
        """Terminal A seats the guest; terminal B, still showing 'waiting', tries to cancel."""
        entry, _created = self.join()
        self.assertTrue(self.change(entry, 'waiting', 'seated')['ok'])
        result = self.change(entry, 'waiting', 'cancelled')
        self.assertFalse(result['ok'])
        self.assertEqual(result['state'], 'seated')
        self.assertEqual(entry.state, 'seated')
        self.assertIn('another terminal', result['message'])

    def test_stale_even_when_transition_would_be_valid(self):
        """B saw 'waiting' and clicks Mark Left after A cancelled the guest: B's click is refused."""
        entry, _created = self.join()
        self.change(entry, 'waiting', 'cancelled')
        result = self.change(entry, 'waiting', 'left')
        self.assertFalse(result['ok'])
        self.assertEqual(entry.state, 'cancelled')

    def test_entry_of_other_pos_refused(self):
        entry, _created = self.join(config=self.config_b)
        result = self.Entry.with_user(self.host).pos_change_state(
            self.config_a.id, entry.id, 'waiting', 'seated')
        self.assertFalse(result['ok'])
        self.assertEqual(entry.state, 'waiting')

    def test_pos_user_cannot_bypass_with_write(self):
        entry, _created = self.join()
        entry.with_user(self.host).write({'state': 'cancelled'})
        self.assertEqual(entry.state, 'cancelled')
        with self.assertRaises(ValidationError):
            entry.with_user(self.host).write({'state': 'waiting'})
        self.assertEqual(entry.state, 'cancelled', "a POS user cannot reopen a closed visit")

    def test_status_change_notifies_pos(self):
        entry, _created = self.join()
        self.env.cr.precommit.data.pop("bus.bus.values", None)
        self.change(entry, 'waiting', 'seated')
        token = self.config_a.access_token
        types = [type_ for _channel, type_, _msg in self.env.cr.precommit.data.get("bus.bus.values", [])]
        self.assertIn(f'{token}-waitlist_updated', types)


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistPosConcurrency(test_waitlist_join.TestWaitlistConcurrency):
    """Two terminals act on the same guest at the same moment: only one wins."""

    # Reuse the base class's committed-data helpers, not its join tests (they run there).
    test_concurrent_same_phone_creates_one_entry = None
    test_concurrent_different_phones_get_unique_tokens = None

    def _change_in_new_transaction(self, entry_id, expected, new, barrier, results):
        barrier.wait()
        for _attempt in range(20):
            with db_connect(self.dbname).cursor() as cr:
                try:
                    env = self._env(cr)
                    result = env['pos.waitlist.entry'].pos_change_state(
                        self.config_id, entry_id, expected, new)
                    cr.flush()
                    cr.transaction = None
                    cr.commit()
                    results.append((new, result['ok'], result['state']))
                    return
                except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                    cr.transaction = None
                    cr.rollback()
                except Exception as e:  # noqa: BLE001
                    cr.transaction = None
                    cr.rollback()
                    results.append(('error', repr(e), None))
                    return
        results.append(('error', 'too many retries', None))

    def test_two_terminals_same_guest(self):
        with db_connect(self.dbname).cursor() as cr:
            env = self._env(cr)
            config = env['pos.config'].browse(self.config_id)
            entry, _created = env['pos.waitlist.entry']._join_from_qr(config, _form())
            entry_id = entry.id
            cr.flush()
            cr.transaction = None
            cr.commit()

        barrier = threading.Barrier(2)
        results = []
        threads = [threading.Thread(target=self._change_in_new_transaction,
                                    args=(entry_id, 'waiting', new, barrier, results), daemon=True)
                   for new in ('seated', 'cancelled')]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        self.assertFalse([t for t in threads if t.is_alive()], "terminals did not finish")
        self.assertFalse([r for r in results if r[0] == 'error'], results)
        winners = [r for r in results if r[1]]
        losers = [r for r in results if not r[1]]
        self.assertEqual(len(winners), 1, results)
        self.assertEqual(len(losers), 1, results)
        winner_state = winners[0][0]
        self.assertEqual(losers[0][2], winner_state, "the loser is told the winner's state")
        rows = self._committed_entries()
        self.assertEqual(rows[0][2], winner_state)

    def test_left_while_other_terminal_cancels(self):
        """Terminal A marks a waiting guest Left while terminal B cancels the same guest."""
        with db_connect(self.dbname).cursor() as cr:
            env = self._env(cr)
            entry, _created = env['pos.waitlist.entry']._join_from_qr(
                env['pos.config'].browse(self.config_id), _form())
            entry_id = entry.id
            cr.flush()
            cr.transaction = None
            cr.commit()

        barrier = threading.Barrier(2)
        results = []
        threads = [threading.Thread(target=self._change_in_new_transaction,
                                    args=(entry_id, 'waiting', new, barrier, results), daemon=True)
                   for new in ('left', 'cancelled')]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        self.assertFalse([t for t in threads if t.is_alive()], "terminals did not finish")
        self.assertFalse([r for r in results if r[0] == 'error'], results)
        self.assertEqual(sorted(r[1] for r in results), [False, True], results)
        winner = next(r for r in results if r[1])[0]
        loser = next(r for r in results if not r[1])
        self.assertEqual(loser[2], winner, "the loser is told the winner's state")
        state, end_time = self._entry_row(entry_id)
        self.assertEqual(state, winner)
        self.assertTrue(end_time, "the closed visit has an end time")

    def _entry_row(self, entry_id):
        with db_connect(self.dbname).cursor() as cr:
            cr.execute("SELECT state, end_time FROM pos_waitlist_entry WHERE id = %s", (entry_id,))
            return cr.fetchone()


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistSettings(WaitlistCommon):

    def test_minutes_per_party_from_main_settings(self):
        settings = self.env['res.config.settings'].create({'pos_config_id': self.config_a.id})
        self.assertEqual(settings.pos_waitlist_minutes_per_party, 10)
        settings.pos_waitlist_minutes_per_party = 12
        settings.execute()
        self.assertEqual(self.config_a.waitlist_minutes_per_party, 12)
        self.join()
        self.assertEqual(self.Entry.get_pos_queue(self.config_a.id)['entries'][0]['estimated_wait'], 12)


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistSeatConcurrency(test_waitlist_join.TestWaitlistConcurrency):
    """Two terminals seat two different guests at the same table at the same moment."""

    test_concurrent_same_phone_creates_one_entry = None
    test_concurrent_different_phones_get_unique_tokens = None

    def _seat_in_new_transaction(self, entry_id, table_id, barrier, results):
        barrier.wait()
        for _attempt in range(20):
            with db_connect(self.dbname).cursor() as cr:
                try:
                    env = self._env(cr)
                    result = env['pos.waitlist.entry'].pos_seat_guest(
                        self.config_id, entry_id, 'waiting', table_id)
                    cr.flush()
                    cr.transaction = None
                    cr.commit()
                    results.append((entry_id, result['ok'], result['state']))
                    return
                except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                    cr.transaction = None
                    cr.rollback()
                except Exception as e:  # noqa: BLE001
                    cr.transaction = None
                    cr.rollback()
                    results.append(('error', repr(e), None))
                    return
        results.append(('error', 'too many retries', None))

    def _cleanup_floor(self, floor_id):
        with db_connect(self.dbname).cursor() as cr:
            cr.execute("DELETE FROM pos_waitlist_entry WHERE config_id = %s", (self.config_id,))
            cr.execute("DELETE FROM restaurant_table WHERE floor_id = %s", (floor_id,))
            cr.execute("DELETE FROM restaurant_floor WHERE id = %s", (floor_id,))
            cr.commit()

    def test_two_terminals_same_table(self):
        with db_connect(self.dbname).cursor() as cr:
            env = self._env(cr)
            config = env['pos.config'].browse(self.config_id)
            floor = env['restaurant.floor'].create({'name': 'Race Floor', 'pos_config_ids': [(4, config.id)]})
            table = env['restaurant.table'].create({'table_number': 7, 'floor_id': floor.id, 'seats': 4})
            Entry = env['pos.waitlist.entry']
            entries = Entry.browse()
            for phone in ('9550000001', '9550000002'):
                entry, _c = Entry._join_from_qr(config, _form(phone=phone))
                entries |= entry
            entry_ids, table_id, floor_id = entries.ids, table.id, floor.id
            cr.flush()
            cr.transaction = None
            cr.commit()
        self.addCleanup(self._cleanup_floor, floor_id)

        barrier = threading.Barrier(2)
        results = []
        threads = [threading.Thread(target=self._seat_in_new_transaction,
                                    args=(entry_id, table_id, barrier, results), daemon=True)
                   for entry_id in entry_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        self.assertFalse([t for t in threads if t.is_alive()], "terminals did not finish")
        self.assertFalse([r for r in results if r[0] == 'error'], results)
        self.assertEqual(sorted(r[1] for r in results), [False, True], results)
        loser = next(r for r in results if not r[1])
        self.assertEqual(loser[2], 'waiting', "the other guest stays waiting to pick another table")

        with db_connect(self.dbname).cursor() as cr:
            cr.execute("SELECT count(*) FROM pos_waitlist_entry WHERE table_id = %s AND state = 'seated'",
                       (table_id,))
            self.assertEqual(cr.fetchone()[0], 1)

    def test_two_terminals_same_table_combination(self):
        """Terminal A and B seat two parties of 4 at the same 2 + 2 combination: one wins."""
        with db_connect(self.dbname).cursor() as cr:
            env = self._env(cr)
            config = env['pos.config'].browse(self.config_id)
            floor = env['restaurant.floor'].create({'name': 'Race Floor 3', 'pos_config_ids': [(4, config.id)]})
            tables = env['restaurant.table'].create([
                {'table_number': 10, 'floor_id': floor.id, 'seats': 2},
                {'table_number': 11, 'floor_id': floor.id, 'seats': 2},
            ])
            Entry = env['pos.waitlist.entry']
            entries = Entry.browse()
            for phone in ('9550000001', '9550000002'):
                entry, _c = Entry._join_from_qr(config, _form(phone=phone, party_size='4'))
                entries |= entry
            entry_ids, table_ids, floor_id = entries.ids, tables.ids, floor.id
            cr.flush()
            cr.transaction = None
            cr.commit()
        self.addCleanup(self._cleanup_floor, floor_id)

        barrier = threading.Barrier(2)
        results = []
        threads = [threading.Thread(target=self._seat_in_new_transaction,
                                    args=(entry_id, table_ids, barrier, results), daemon=True)
                   for entry_id in entry_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        self.assertFalse([t for t in threads if t.is_alive()], "terminals did not finish")
        self.assertFalse([r for r in results if r[0] == 'error'], results)
        self.assertEqual(sorted(r[1] for r in results), [False, True], results)
        loser = next(r for r in results if not r[1])
        self.assertEqual(loser[2], 'waiting', "the other party stays waiting to pick again")

        with db_connect(self.dbname).cursor() as cr:
            cr.execute("SELECT count(*) FROM pos_waitlist_entry WHERE config_id = %s AND state = 'seated'",
                       (self.config_id,))
            self.assertEqual(cr.fetchone()[0], 1)
            cr.execute("SELECT count(*) FROM restaurant_table WHERE id = %s AND parent_id = %s",
                       (table_ids[1], table_ids[0]))
            self.assertEqual(cr.fetchone()[0], 1, "merged once under the main table")
            # Unmerge so the cleanup can delete the tables.
            cr.execute("UPDATE restaurant_table SET parent_id = NULL WHERE floor_id = %s", (floor_id,))
            cr.commit()

    def test_two_terminals_seat_same_guest_at_different_tables(self):
        with db_connect(self.dbname).cursor() as cr:
            env = self._env(cr)
            config = env['pos.config'].browse(self.config_id)
            floor = env['restaurant.floor'].create({'name': 'Race Floor 2', 'pos_config_ids': [(4, config.id)]})
            tables = env['restaurant.table'].create([
                {'table_number': 8, 'floor_id': floor.id, 'seats': 4},
                {'table_number': 9, 'floor_id': floor.id, 'seats': 4},
            ])
            entry, _c = env['pos.waitlist.entry']._join_from_qr(config, _form())
            entry_id, table_ids, floor_id = entry.id, tables.ids, floor.id
            cr.flush()
            cr.transaction = None
            cr.commit()
        self.addCleanup(self._cleanup_floor, floor_id)

        barrier = threading.Barrier(2)
        results = []
        threads = [threading.Thread(target=self._seat_in_new_transaction,
                                    args=(entry_id, table_id, barrier, results), daemon=True)
                   for table_id in table_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        self.assertFalse([t for t in threads if t.is_alive()], "terminals did not finish")
        self.assertFalse([r for r in results if r[0] == 'error'], results)
        self.assertEqual(sorted(r[1] for r in results), [False, True], results)
        loser = next(r for r in results if not r[1])
        self.assertEqual(loser[2], 'seated', "the other terminal is told the guest is already seated")

        with db_connect(self.dbname).cursor() as cr:
            cr.execute("SELECT state, table_id FROM pos_waitlist_entry WHERE id = %s", (entry_id,))
            state, seated_table = cr.fetchone()
            self.assertEqual(state, 'seated')
            self.assertIn(seated_table, table_ids)
            env = self._env(cr)
            free = env['pos.waitlist.entry'].get_seatable_tables(self.config_id)['available_ids']
            other_table = next(t for t in table_ids if t != seated_table)
            self.assertIn(other_table, free, "the losing terminal's table was not consumed")
            self.assertNotIn(seated_table, free)
            cr.transaction = None
            cr.rollback()
