# -*- coding: utf-8 -*-
"""End-to-end: guest phone -> POS -> table seating -> guest status page.

Uses the real public routes (join form, status page, status JSON), the real POS in Chrome,
and the guest's real status page in Chrome with its own live-update script.
"""
import json
import re

from odoo.tests import tagged

from odoo.addons.pos_restaurant.tests.test_frontend import TestFrontendCommon

E2E_TOKEN = 'e2eWaitlistToken0001'


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistEndToEnd(TestFrontendCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pos_config.write({
            'enable_qr_self_join': True,
            'waitlist_minutes_per_party': 10,
            'waitlist_token': E2E_TOKEN,
        })
        cls.Entry = cls.env['pos.waitlist.entry']
        cls.tables = {t.table_number: t for t in cls.pos_config.floor_ids.table_ids}

    # ------------------------------------------------------------------
    # Guest phone helpers (anonymous HTTP, like a phone that scanned the QR)
    # ------------------------------------------------------------------
    def phone_join(self, **values):
        data = {'guest_name': 'Ada Lovelace', 'phone': '+91 95501 00001', 'phone_country': 'IN', 'party_size': '4',
                'preferred_floor': self.Entry._floor_public_key(self.pos_config, self.main_floor),
                'share_table': 'private'}
        data.update(values)
        response = self.url_open(f'/waitlist/join/{E2E_TOKEN}', data=data, allow_redirects=False)
        self.assertEqual(response.status_code, 303, response.text[:500])
        location = response.headers['Location']
        access_token = re.search(r'/waitlist/s/([A-Za-z0-9_-]+)', location).group(1)
        return self.Entry.sudo().search([('access_token', '=', access_token)]), access_token

    def status_json(self, access_token):
        """The guest page's poll: 200 while waiting, 410 (final state, tracking ended) once closed."""
        response = self.url_open(f'/waitlist/s/{access_token}/json')
        data = response.json()
        self.assertEqual(response.status_code, 200 if data['active'] else 410)
        return data

    def status_page(self, access_token):
        response = self.url_open(f'/waitlist/s/{access_token}')
        self.assertEqual(response.status_code, 200)
        return response.text

    # ------------------------------------------------------------------
    # 1. Customer join -> POS -> call -> seat, with a phone and a second terminal
    # ------------------------------------------------------------------
    def test_e2e_join_call_seat_on_pos(self):
        ada, ada_token = self.phone_join()
        self.assertEqual((ada.token, ada.state, ada.source, ada.party_size, ada.preferred_floor_id),
                         ('W-001', 'waiting', 'qr', 4, self.main_floor))
        self.assertEqual(ada.config_id, self.pos_config)
        status = self.status_json(ada_token)
        # Main Floor has free 4-seat tables: no wait, whatever the configured average.
        self.assertEqual((status['state'], status['estimated_wait'], status['estimated_wait_label']),
                         ('waiting', 0, '~0–5 min'))
        self.assertNotIn('position', status)

        self.pos_config.with_user(self.pos_user).open_ui()
        self.start_pos_tour('hudson_pos_waitlist_e2e_tour', pos_config=self.pos_config)

        grace = self.Entry.sudo().search([('config_id', '=', self.pos_config.id), ('token', '=', 'W-002')])
        self.assertEqual((grace.guest_name, grace.source, grace.share_table), ('Grace Hopper', 'qr', 'share'))
        self.assertEqual((ada.state, ada.table_id.table_number), ('seated', 4))
        self.assertEqual((grace.state, grace.table_id.table_number), ('seated', 2))
        self.assertEqual(self.Entry.get_pos_queue(self.pos_config.id)['entries'], [])

        status = self.status_json(ada_token)
        self.assertEqual((status['state'], status['table'], status['active']), ('seated', 4, False))
        page = self.status_page(ada_token)  # guest refreshes the page
        self.assertIn('Seated', page)
        self.assertIn('id="wl_detail_table"', page)

    # ------------------------------------------------------------------
    # 2. The guest's status page follows the host live (real browser, no reload)
    # ------------------------------------------------------------------
    def test_e2e_status_page_live(self):
        entry, access_token = self.phone_join()
        context = json.dumps({
            'config': self.pos_config.id,
            'entry': entry.id,
            'table': self.tables[5].id,
        })
        code = """
(async () => {
    const ctx = %s;
    const realFetch = window.fetch.bind(window);
    const $ = (id) => document.getElementById(id);
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    async function until(check, what, ms = 15000) {
        const start = Date.now();
        while (Date.now() - start < ms) {
            try { if (check()) { return; } } catch (e) { /* not there yet */ }
            await sleep(200);
        }
        throw new Error('Timed out waiting for: ' + what + ' (page state: ' + $('wl_state_label').textContent + ')');
    }
    async function host(method, args) {
        const r = await realFetch('/web/dataset/call_kw', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({jsonrpc: '2.0', method: 'call',
                params: {model: 'pos.waitlist.entry', method, args, kwargs: {}}}),
        });
        const data = await r.json();
        if (data.error || !data.result.ok) { throw new Error(method + ': ' + JSON.stringify(data.error || data.result.message)); }
    }
    // Record the alert instead of buzzing the test machine.
    window.__vibrations = [];
    Object.defineProperty(navigator, 'vibrate', {configurable: true, value: (p) => { window.__vibrations.push(p); return true; }});
    try {
        await until(() => $('wl_state_label').textContent.trim() === 'Waiting', 'Waiting');
        // Only the configured average wait; nothing that reveals the place in line.
        const stats = $('wl_stats').textContent.replace(/\\s+/g, ' ');
        if (!stats.includes("You're on the waitlist") || !stats.includes('Estimated Average Wait')
                || !stats.includes('~10 minutes')) {
            throw new Error('average wait block missing: ' + stats);
        }
        if ($('wl_position') || /position|ahead/i.test(document.getElementById('wl_status_card').textContent)) {
            throw new Error('queue position / parties ahead shown to the guest');
        }

        // Connection lost, then back.
        window.fetch = () => Promise.reject(new TypeError('offline'));
        await until(() => $('wl_live_text').textContent.includes('Reconnecting'), 'Reconnecting banner');
        window.fetch = realFetch;
        window.dispatchEvent(new Event('online'));
        await until(() => $('wl_live_text').textContent === 'Live updates', 'Live again after reconnect');

        // Waiting -> Seated in one host action: the seated box is the "your table is ready" moment.
        await host('pos_seat_guest', [ctx.config, ctx.entry, 'waiting', ctx.table]);
        await until(() => $('wl_state_label').textContent.trim() === 'Seated', 'Seated');
        await until(() => !$('wl_seated_alert').hidden, 'Your table is ready box');
        await until(() => !$('wl_seated_table').hidden && $('wl_seated_table').textContent.includes('Table 5'), 'go to Table 5');
        if (!$('wl_seated_host').hidden) { throw new Error('host stand text shown although a table is assigned'); }
        await until(() => window.__vibrations.length > 0, 'vibration alert');
        await until(() => document.title.includes('ready'), 'title alert');
        await until(() => $('wl_status_card').classList.contains('wl-flash'), 'flash alert');
        await until(() => !$('wl_msg_seated').hidden, 'Enjoy your meal');
        await until(() => !$('wl_detail_table_row').hidden && $('wl_detail_table').textContent === '5', 'table 5');
        if (!$('wl_stats').hidden) { throw new Error('position still shown while seated'); }
        if (!$('wl_alerts').hidden) { throw new Error('alert controls still shown'); }
        if (document.querySelector('[id*="called"]')) { throw new Error('a Called element is still on the page'); }
        // Seated is the end of tracking: no more polling, way back to the QR join form.
        await until(() => $('wl_live_text').textContent === 'Tracking ended for this visit', 'tracking ended');
        await until(() => !$('wl_join_again').hidden, 'join again link');
        let calls = 0;
        window.fetch = (...args) => { calls++; return realFetch(...args); };
        window.dispatchEvent(new Event('focus'));
        window.dispatchEvent(new Event('online'));
        await sleep(4500);  // longer than one poll interval
        window.fetch = realFetch;
        if (calls) { throw new Error('the seated page kept polling (' + calls + ' requests)'); }
        console.log('test successful');
    } catch (e) {
        console.error('Status page E2E failed: ' + e.message);
    }
})();
""" % context
        self.browser_js(f'/waitlist/s/{access_token}', code,
                        ready="!!document.getElementById('wl_status_card')",
                        login='pos_user', timeout=90)
        self.assertEqual((entry.state, entry.table_id), ('seated', self.tables[5]))

    # ------------------------------------------------------------------
    # 2b. POS UI edge cases: counts, layout, refresh, picker, races, double click
    # ------------------------------------------------------------------
    def test_ui_edge_cases(self):
        Tag = self.env['pos.waitlist.tag']
        extra = Tag.create([{'name': 'Anniversary Celebration Dinner'},
                            {'name': 'Window seat please if available'},
                            {'name': 'Allergy: nuts and shellfish'}])
        long_name = 'Bartholomew Maximilian Fitzgerald Montgomery of Westminster Estates'
        # Above the floor plan's own capacity: allowed by the POS's Maximum Party Size.
        self.pos_config.waitlist_max_party_size = 60
        big, big_token = self.phone_join(guest_name=long_name, party_size='50')
        big.sudo().tag_ids = [(6, 0, Tag.search([]).ids)]
        # A table never seats a party short of seats: give the big party two large tables.
        self.tables[2].seats = 50
        self.tables[4].seats = 50
        self.assertEqual(len(big.tag_ids), 6)
        others = {}
        for i, name in enumerate(('Grace Hopper', 'Cancel Me', 'Leave Me', 'No Show Me'), start=2):
            others[f'W-{i:03d}'], _t = self.phone_join(guest_name=name, phone=f'+91 95503 000{i:02d}',
                                                       party_size='2')
        self.pos_config.with_user(self.pos_user).open_ui()
        occupied = self.env['pos.order'].create({
            'table_id': self.tables[5].id,
            'company_id': self.env.company.id,
            'session_id': self.pos_config.current_session_id.id,
            'amount_paid': 0.0, 'amount_total': 0.0, 'amount_tax': 0.0, 'amount_return': 0.0,
        })
        self.assertEqual(occupied.state, 'draft')

        self.start_pos_tour('hudson_pos_waitlist_ui_edge_tour', pos_config=self.pos_config)

        phone = self.Entry.sudo().search([('config_id', '=', self.pos_config.id), ('token', '=', 'W-006')])
        self.assertEqual((big.state, big.table_id.table_number), ('seated', 2))
        self.assertEqual((phone.state, phone.table_id.table_number), ('seated', 4))
        self.assertEqual([others[t].state for t in ('W-002', 'W-003', 'W-004', 'W-005')],
                         ['cancelled', 'cancelled', 'left', 'no_show'])
        self.assertEqual(self.Entry.search_count([('table_id', '=', self.tables[2].id)]), 1,
                         "double click seated the guest once")
        self.assertEqual(self.Entry.search_count([('table_id', '=', self.tables[5].id)]), 0,
                         "occupied table never assigned")
        status = self.status_json(big_token)
        self.assertEqual((status['state'], status['table'], status['active']), ('seated', 2, False))
        self.assertEqual(len(extra), 3)

    # ------------------------------------------------------------------
    # 3. Other edge cases on the guest side
    # ------------------------------------------------------------------
    def test_e2e_closed_states_on_status_page(self):
        cases = [('cancelled', 'waiting', 'Cancelled'), ('left', 'waiting', 'Left'),
                 ('no_show', 'waiting', 'No Show')]
        for i, (target, start, label) in enumerate(cases):
            entry, access_token = self.phone_join(phone=f'+91 95502 000{i:02d}')
            result = self.Entry.with_user(self.pos_user).pos_change_state(
                self.pos_config.id, entry.id, start, target)
            self.assertTrue(result['ok'], result['message'])
            status = self.status_json(access_token)
            self.assertEqual((status['state'], status['active'], status['table']), (target, False, False))
            page = self.status_page(access_token)
            self.assertIn(label, page)
            self.assertIn('This waitlist entry is closed', page)
            # The guest can rejoin with the same phone once the entry is closed.
            again, _token = self.phone_join(phone=f'+91 95502 000{i:02d}')
            self.assertNotEqual(again, entry)
            again.sudo().write({'state': 'cancelled'})

    def test_e2e_stale_and_invalid_links(self):
        entry, access_token = self.phone_join()
        for bad in ('x' * 43, 'not-a-token', access_token[:-1] + ('A' if access_token[-1] != 'A' else 'B')):
            self.assertEqual(self.url_open(f'/waitlist/s/{bad}').status_code, 404, bad)
            self.assertEqual(self.url_open(f'/waitlist/s/{bad}/json').status_code, 404, bad)
        entry.sudo().unlink()  # entry removed from the back office
        self.assertEqual(self.url_open(f'/waitlist/s/{access_token}').status_code, 404)
        self.assertEqual(self.url_open(f'/waitlist/s/{access_token}/json').status_code, 404)

    def test_e2e_empty_waitlist(self):
        queue = self.Entry.with_user(self.pos_user).get_pos_queue(self.pos_config.id)
        self.assertEqual(queue['entries'], [])
        self.assertTrue(queue['enabled'])
