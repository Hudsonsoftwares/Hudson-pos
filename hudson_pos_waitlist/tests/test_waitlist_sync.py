# -*- coding: utf-8 -*-
"""Status synchronization: Backend Waitlist menu <-> POS Waitlist screen <-> Track My Waitlist.

The pos.waitlist.entry record is the only source of truth. Every change, wherever it is
made, must (1) ping the POS screens of that config, (2) ping the backend views and
(3) be what the guest's status JSON returns on its next poll.
"""
from odoo.tests import HttpCase, new_test_user, tagged

from .test_waitlist_join import WaitlistCommon, _form

ALL_STATES = ('waiting', 'seated', 'cancelled', 'left', 'no_show')


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistStatusSync(HttpCase, WaitlistCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.host = new_test_user(cls.env, login='wl_sync_host', groups='point_of_sale.group_pos_user')
        cls.manager = new_test_user(cls.env, login='wl_sync_manager', groups='point_of_sale.group_pos_manager')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _clear_bus(self):
        # Empty in place: the bus keeps a reference to this list until commit.
        self.env.cr.precommit.data.get("bus.bus.values", []).clear()

    def _bus_types(self):
        return [type_ for _channel, type_, _msg in self.env.cr.precommit.data.get("bus.bus.values", [])]

    def _bus_messages(self, type_):
        return [msg for _channel, t, msg in self.env.cr.precommit.data.get("bus.bus.values", []) if t == type_]

    def assertSynced(self, entry, msg=''):
        """POS + backend were pinged, and the guest's JSON shows the record's state."""
        types = self._bus_types()
        self.assertIn(f'{self.config_a.access_token}-waitlist_updated', types, f"POS not notified {msg}")
        backend = self._bus_messages('hudson_waitlist_changed')
        self.assertTrue(any(entry.id in m['entry_ids'] for m in backend), f"backend not notified {msg}")
        status = self.url_open(f'/waitlist/s/{entry.sudo().access_token}/json').json()
        self.assertEqual(status['state'], entry.state, f"guest page out of sync {msg}")
        queue = self.Entry.with_user(self.host).get_pos_queue(self.config_a.id)['entries']
        in_queue = {e['id']: e['state'] for e in queue}
        if entry.state == 'waiting':
            self.assertEqual(in_queue.get(entry.id), entry.state, f"POS queue out of sync {msg}")
        else:
            self.assertNotIn(entry.id, in_queue, f"closed entry still on POS {msg}")

    # ------------------------------------------------------------------
    # Backend -> POS + guest
    # ------------------------------------------------------------------
    def test_backend_change_reaches_pos_and_guest_for_every_state(self):
        entry, _c = self.join()
        for state in ALL_STATES[1:] + ('waiting',):  # through every state, then back to waiting
            self._clear_bus()
            entry.with_user(self.manager).write({'state': state})
            self.assertSynced(entry, f"after backend -> {state}")

    def test_backend_correction_reopens_on_pos_and_guest(self):
        entry, _c = self.join()
        entry.with_user(self.manager).write({'state': 'cancelled'})
        self._clear_bus()
        entry.with_user(self.manager).write({'state': 'waiting'})
        self.assertSynced(entry, "after reopening")
        self.assertFalse(entry.end_time, "reopened entry is active again")
        data = self.url_open(f'/waitlist/s/{entry.sudo().access_token}/json').json()
        self.assertEqual(data['estimated_wait'], 10)
        self.assertNotIn('position', data)

    def test_backend_delete_reaches_pos_and_guest(self):
        entry, _c = self.join()
        access_token = entry.sudo().access_token
        entry_id = entry.id
        self._clear_bus()
        entry.with_user(self.manager).unlink()
        self.assertIn(f'{self.config_a.access_token}-waitlist_updated', self._bus_types())
        self.assertTrue(any(entry_id in m['entry_ids'] for m in self._bus_messages('hudson_waitlist_changed')))
        self.assertEqual(self.url_open(f'/waitlist/s/{access_token}/json').status_code, 404)
        self.assertEqual(self.Entry.with_user(self.host).get_pos_queue(self.config_a.id)['entries'], [])

    # ------------------------------------------------------------------
    # POS -> backend + guest
    # ------------------------------------------------------------------
    def test_pos_actions_reach_backend_and_guest(self):
        flows = [('waiting', 'seated')]
        entry, _c = self.join(phone='5550000001')
        for start, target in flows:
            self._clear_bus()
            self.assertTrue(self.Entry.with_user(self.host).pos_change_state(
                self.config_a.id, entry.id, start, target)['ok'])
            self.assertSynced(entry, f"after POS {start} -> {target}")
        for i, (start, target) in enumerate([('waiting', 'cancelled'), ('waiting', 'left'),
                                             ('waiting', 'no_show')]):
            other, _c = self.join(phone=f'55500002{i:02d}')
            self._clear_bus()
            self.assertTrue(self.Entry.with_user(self.host).pos_change_state(
                self.config_a.id, other.id, start, target)['ok'])
            self.assertSynced(other, f"after POS {start} -> {target}")

    def test_new_guest_reaches_pos_and_backend(self):
        self._clear_bus()
        entry, _c = self.join()
        self.assertIn(f'{self.config_a.access_token}-waitlist_created', self._bus_types())
        self.assertTrue(any(entry.id in m['entry_ids'] for m in self._bus_messages('hudson_waitlist_changed')))

    def test_backend_message_carries_no_guest_data(self):
        entry, _c = self.join(guest_name='Private Person', phone='5557770001')
        self._clear_bus()
        entry.with_user(self.manager).write({'state': 'seated'})
        for message in self._bus_messages('hudson_waitlist_changed'):
            flat = repr(message)
            for secret in ('Private Person', '5557770001', entry.sudo().access_token):
                self.assertNotIn(secret, flat)
            self.assertEqual(set(message), {'entry_ids', 'company_ids'})

    def test_pos_user_still_bound_to_host_flow_from_backend(self):
        entry, _c = self.join()
        entry.with_user(self.host).write({'state': 'seated'})
        with self.assertRaises(Exception):
            entry.with_user(self.host).write({'state': 'waiting'})
        self.assertEqual(entry.state, 'seated')

    # ------------------------------------------------------------------
    # Backend views follow live (browser)
    # ------------------------------------------------------------------
    def test_backend_views_follow_pos_live(self):
        self.join(phone='5550000001', guest_name='Ada Lovelace')
        self.join(phone='5550000002', guest_name='Grace Hopper')
        self.env['pos.waitlist.entry'].search([('config_id', '!=', self.config_a.id)]).sudo().unlink()
        action = self.env.ref('hudson_pos_waitlist.action_pos_waitlist_entry')
        self.start_tour(f'/odoo/action-{action.id}', 'hudson_pos_waitlist_backend_sync_tour', login='admin')
        entries = self.Entry.search([('config_id', '=', self.config_a.id)], order='token')
        self.assertEqual(entries.mapped('state'), ['seated', 'cancelled'])
