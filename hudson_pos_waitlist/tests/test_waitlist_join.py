# -*- coding: utf-8 -*-
import re
import sys
import threading
import traceback
from urllib.parse import urlparse

from odoo import api, SUPERUSER_ID
from odoo.exceptions import ValidationError
from odoo.orm.environments import Transaction
from odoo.sql_db import db_connect, PG_CONCURRENCY_EXCEPTIONS_TO_RETRY
from odoo.tests import HttpCase, TransactionCase, tagged

from ..controllers.main import PosWaitlistController


def _form(**overrides):
    values = {
        'guest_name': 'Ada Lovelace',
        'phone': '+1 555 010 0001',
        'party_size': '4',
        'preferred_floor': 'any',
        'share_table': 'private',
        'tags': [],
    }
    values.update(overrides)
    return values


class WaitlistCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Entry = cls.env['pos.waitlist.entry']
        cls.config_a = cls.env['pos.config'].create({
            'name': 'Waitlist Resto A', 'enable_qr_self_join': True, 'waitlist_minutes_per_party': 10})
        cls.config_b = cls.env['pos.config'].create({
            'name': 'Waitlist Resto B', 'enable_qr_self_join': True, 'waitlist_minutes_per_party': 15})

    def join(self, config=None, **overrides):
        return self.Entry._join_from_qr(config or self.config_a, _form(**overrides))


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistJoin(WaitlistCommon):

    def test_join_creates_first_token(self):
        entry, created = self.join(tags=['high_chair', 'birthday'])
        self.assertTrue(created)
        self.assertEqual(entry.token, 'W-001')
        self.assertEqual(entry.source, 'qr')
        self.assertEqual(entry.state, 'waiting')
        self.assertTrue(entry.join_time)
        self.assertEqual(entry.config_id, self.config_a)
        self.assertEqual(entry.company_id, self.config_a.company_id)
        self.assertEqual(entry.party_size, 4)
        self.assertEqual(sorted(entry.tag_ids.mapped('code')), ['birthday', 'high_chair'])
        self.assertEqual(entry.position, 1)
        self.assertEqual(entry.quoted_wait, 10)

        second, _created = self.join(phone='+1 555 010 0002')
        self.assertEqual(second.token, 'W-002')
        self.assertEqual(second.quoted_wait, 10, "flat average: not 2nd in line x 10")

    def test_access_token_is_random_and_not_derived(self):
        entry, _created = self.join()
        token = entry.sudo().access_token
        self.assertGreaterEqual(len(token), 40)
        self.assertNotIn(str(entry.id), token.split('-'))
        self.assertNotIn('5550100001', token)
        self.assertNotIn(self.env.cr.dbname, token)
        other, _created = self.join(phone='+1 555 010 0003')
        self.assertNotEqual(token, other.sudo().access_token)

    def test_duplicate_active_entry_is_recovered(self):
        entry, created = self.join()
        self.assertTrue(created)
        # Same phone typed differently, other details changed: still the same guest.
        again, created = self.join(phone='+1 (555) 010-0001', party_size='6')
        self.assertFalse(created)
        self.assertEqual(again, entry)
        self.assertEqual(again.party_size, 4)
        self.assertEqual(self.Entry.search_count([('config_id', '=', self.config_a.id)]), 1)

    def test_rejoin_allowed_after_entry_is_done(self):
        for state in ('seated', 'cancelled', 'left', 'no_show'):
            entry, created = self.join()
            self.assertTrue(created)
            entry.state = state
            self.assertTrue(entry.end_time)
        entry, created = self.join()
        self.assertTrue(created)
        self.assertEqual(entry.token, 'W-005')

    def test_same_phone_multiple_visits_same_day(self):
        """The phone is not a customer id: each closed visit lets the same phone join again."""
        others = [self.join(phone=f'55588800{i:02d}')[0] for i in range(13)]  # W-001..W-013
        visit1, created = self.join(phone='+1 555 010 0001')
        self.assertTrue(created)
        self.assertEqual(visit1.token, 'W-014')
        # Only a WAITING entry blocks a duplicate join (double tap / re-scan).
        again, created = self.join(phone='15550100001')
        self.assertFalse(created)
        self.assertEqual(again, visit1)
        visit1.state = 'seated'
        visit2, created = self.join(phone='+1 555 010 0001')
        self.assertTrue(created, "a seated visit is closed: same phone joins again")
        self.assertNotEqual(visit2, visit1)
        self.assertEqual((visit2.token, visit2.state, visit2.queue_date),
                         ('W-015', 'waiting', visit1.queue_date))
        self.assertNotEqual(visit2.sudo().access_token, visit1.sudo().access_token)
        self.assertEqual(visit1.state, 'seated', "the earlier visit keeps its own history")
        for closed in ('cancelled', 'left', 'no_show'):
            visit2.state = closed
            visit2, created = self.join(phone='+1 555 010 0001')
            self.assertTrue(created, f"{closed} closes the visit")
        self.assertEqual(self.Entry.search_count([('phone_normalized', '=', '15550100001')]), 5)
        self.assertEqual(len(others), 13)

    def test_numbering_does_not_depend_on_who_joins(self):
        """A guest (public user) and a host (POS user) in other timezones share one daily queue."""
        far_east = self.env['res.users'].create({
            'name': 'Host Kiribati', 'login': 'wl_tz_east', 'tz': 'Pacific/Kiritimati'})   # UTC+14
        far_west = self.env['res.users'].create({
            'name': 'Host Samoa', 'login': 'wl_tz_west', 'tz': 'Pacific/Pago_Pago'})       # UTC-11
        first, _c = self.Entry.with_user(far_east).sudo()._join_from_qr(self.config_a, _form(phone='5550000001'))
        second, _c = self.Entry.with_user(far_west).sudo()._join_from_qr(self.config_a, _form(phone='5550000002'))
        public = self.env.ref('base.public_user')
        third, _c = self.Entry.with_user(public).sudo()._join_from_qr(self.config_a, _form(phone='5550000003'))
        self.assertEqual([first.token, second.token, third.token], ['W-001', 'W-002', 'W-003'])
        self.assertEqual(len({first.queue_date, second.queue_date, third.queue_date}), 1)

    def test_invalid_party_size_rejected(self):
        for bad in ('0', '-2', 'abc', '2.5', '', '51', None):
            with self.assertRaises(ValidationError, msg=f"party_size={bad!r}"):
                self.join(party_size=bad)
        self.assertFalse(self.Entry.search([('config_id', '=', self.config_a.id)]))

    def test_invalid_preferences_rejected(self):
        with self.assertRaises(ValidationError):
            self.join(preferred_floor='rooftop')
        with self.assertRaises(ValidationError):
            self.join(share_table='always')
        with self.assertRaises(ValidationError):
            self.join(tags=['not_a_tag'])
        self.assertFalse(self.Entry.search([('config_id', '=', self.config_a.id)]))

    def test_invalid_name_and_phone_rejected(self):
        with self.assertRaises(ValidationError):
            self.join(guest_name='   ')
        for bad in ('', '12', 'call me', '+1 555 <script>', '1' * 20):
            with self.assertRaises(ValidationError, msg=f"phone={bad!r}"):
                self.join(phone=bad)

    def test_restaurants_are_isolated(self):
        entry_a, _created = self.join(self.config_a)
        entry_b, created_b = self.join(self.config_b)
        self.assertTrue(created_b, "Same phone at another restaurant is a new entry")
        self.assertNotEqual(entry_a, entry_b)
        self.assertEqual(entry_b.token, 'W-001', "Each POS has its own queue numbers")
        recovered_a, created = self.join(self.config_a)
        self.assertFalse(created)
        self.assertEqual(recovered_a, entry_a)
        recovered_b, created = self.join(self.config_b)
        self.assertFalse(created)
        self.assertEqual(recovered_b, entry_b)

    def test_position_is_dynamic(self):
        e1, _c = self.join(phone='5550000001')
        e2, _c = self.join(phone='5550000002')
        e3, _c = self.join(phone='5550000003')
        self.assertEqual((e1.position, e2.position, e3.position), (1, 2, 3))
        e1.state = 'seated'
        self.env.invalidate_all()
        self.assertEqual((e1.position, e2.position, e3.position), (0, 1, 2))
        e2.state = 'cancelled'
        self.env.invalidate_all()
        self.assertEqual(e3.position, 1)

    def test_public_status_exposes_only_own_entry(self):
        entry, _c = self.join()
        self.join(guest_name='Other Guest', phone='5559999999')
        status = entry._public_status()
        self.assertEqual(status['token'], 'W-001')
        self.assertEqual(status['restaurant_name'], 'Waitlist Resto A')
        flat = repr(status)
        for secret in ('Other Guest', '5559999999', 'Ada Lovelace', '555 010 0001', self.env.cr.dbname):
            self.assertNotIn(secret, flat)
        self.assertNotIn('id', status)

    def test_access_token_lookup(self):
        entry, _c = self.join()
        self.assertEqual(self.Entry._get_by_access_token(entry.sudo().access_token), entry)
        self.assertFalse(self.Entry._get_by_access_token('x' * 43))
        self.assertFalse(self.Entry._get_by_access_token(''))

    def test_pos_rpc_payload(self):
        self.join()
        data = self.Entry.get_active_entries(self.config_a.id)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['token'], 'W-001')
        self.assertNotIn('access_token', data[0])


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistRoutes(HttpCase, WaitlistCommon):

    def post_join(self, config, **overrides):
        return self.url_open(f'/waitlist/join/{config.waitlist_token}', data=_form(**overrides),
                             allow_redirects=False)

    def test_join_form_renders(self):
        res = self.url_open(f'/waitlist/join/{self.config_a.waitlist_token}')
        self.assertEqual(res.status_code, 200)
        for text in ('Guest Name', 'Phone Number', 'Party Size',
                     'Private table only', 'High Chair', 'Wheelchair', 'Birthday'):
            self.assertIn(text, res.text)
        self.assertNotIn(f'value="{self.config_a.id}"', res.text)
        self.assertNotIn('wl_floor_field', res.text, "a POS without floor plan asks no floor")
        for legacy in ('Indoor', 'Outdoor'):
            self.assertNotIn(legacy, res.text)

    def test_submit_redirects_to_own_status_page(self):
        res = self.post_join(self.config_a, tags=['wheelchair'])
        self.assertEqual(res.status_code, 303)
        path = urlparse(res.headers['Location']).path
        self.assertRegex(path, r'^/waitlist/s/[A-Za-z0-9_-]{43}$')

        entry = self.Entry.search([('config_id', '=', self.config_a.id)])
        self.assertEqual(len(entry), 1)
        self.assertEqual(path, f'/waitlist/s/{entry.sudo().access_token}')

        page = self.url_open(path)
        self.assertEqual(page.status_code, 200)
        self.assertIn('W-001', page.text)
        self.assertIn('Waitlist Resto A', page.text)
        self.assertNotIn('555 010 0001', page.text)
        self.assertNotIn(self.env.cr.dbname, page.text)

        data = self.url_open(path + '/json').json()
        self.assertEqual(data['token'], 'W-001')
        self.assertNotIn('position', data)
        self.assertEqual(data['estimated_wait'], 10)
        self.assertEqual(data['state'], 'waiting')

    def test_repeated_post_recovers_existing_entry(self):
        first = self.post_join(self.config_a)
        second = self.post_join(self.config_a)
        self.assertEqual(second.status_code, 303)
        self.assertEqual(urlparse(first.headers['Location']).path,
                         urlparse(second.headers['Location']).path)
        self.assertIn('existing=1', second.headers['Location'])
        self.assertEqual(self.Entry.search_count([('config_id', '=', self.config_a.id)]), 1)

    def test_invalid_submit_shows_errors(self):
        res = self.post_join(self.config_a, party_size='0', preferred_floor='roof')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Party size', res.text)
        self.assertFalse(self.Entry.search([('config_id', '=', self.config_a.id)]))

    def test_disabled_restaurant_rejects_submit(self):
        self.config_b.enable_qr_self_join = False
        res = self.post_join(self.config_b)
        self.assertEqual(res.status_code, 404)
        self.assertFalse(self.Entry.search([('config_id', '=', self.config_b.id)]))

    def test_invalid_access_token_is_generic_404(self):
        entry, _c = self.join()
        for bad in ('x' * 43, 'short', str(entry.id), entry.token):
            res = self.url_open(f'/waitlist/s/{bad}')
            self.assertEqual(res.status_code, 404, bad)
            self.assertIn('Waitlist Unavailable', res.text)
            self.assertNotIn('Waitlist Resto A', res.text)
            self.assertNotIn('W-001', res.text)
        self.assertEqual(self.url_open('/waitlist/s/' + 'x' * 43 + '/json').status_code, 404)

    def test_status_page_live_updates_both_ways(self):
        entry, _c = self.join()
        path = f'/waitlist/s/{entry.sudo().access_token}'
        page = self.url_open(path).text
        # Live updater and every state block are on the page whatever the current state.
        for marker in ('id="wl_seated_alert"', 'id="wl_stats"', 'id="wl_alerts_btn"', path + '/json'):
            self.assertIn(marker, page)
        # Bookmark tip lives in the block revealed once alerts are enabled.
        self.assertRegex(page, re.compile(r'id="wl_alerts_on" hidden="hidden">.*?Keep this page open or '
                                          r'bookmark it to easily check your waitlist status\.', re.S))
        for state, expected in (('seated', ('seated', 0)), ('waiting', ('waiting', 10)),
                                ('cancelled', ('cancelled', 0)), ('waiting', ('waiting', 10))):
            entry.state = state
            data = self.url_open(path + '/json?t=1').json()
            self.assertEqual((data['state'], data['estimated_wait']), expected)
            self.assertNotIn('position', data)
        # Closed pages keep the updater too (a host may reopen the entry).
        self.assertIn(path + '/json', self.url_open(path).text)

    def test_status_page_never_shows_other_guests(self):
        mine, _c = self.join(guest_name='Mine')
        self.join(guest_name='Someone Else', phone='5551234567')
        page = self.url_open(f'/waitlist/s/{mine.sudo().access_token}')
        self.assertNotIn('Someone Else', page.text)
        self.assertNotIn('5551234567', page.text)
        self.assertNotIn('W-002', page.text)


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistTrackingLink(HttpCase, WaitlistCommon):
    """"Track My Waitlist" on the join form: only for this browser's active entry at this POS."""

    def form(self, config):
        res = self.url_open(f'/waitlist/join/{config.waitlist_token}')
        self.assertEqual(res.status_code, 200)
        return res.text

    def join_via_form(self, config, **overrides):
        res = self.url_open(f'/waitlist/join/{config.waitlist_token}', data=_form(**overrides),
                            allow_redirects=False)
        self.assertEqual(res.status_code, 303)
        return self.Entry.search([('config_id', '=', config.id)], order='id desc', limit=1)

    def set_cookie(self, config, value):
        name = PosWaitlistController._tracking_cookie_name(config)
        self.opener.cookies.set(name, value, path='/waitlist/')

    def assertTracking(self, html, entry):
        self.assertIn('id="wl_track"', html)
        self.assertIn('Track My Waitlist', html)
        self.assertIn(f'href="/waitlist/s/{entry.sudo().access_token}"', html)
        self.assertIn(entry.token, html)

    def assertNoTracking(self, html):
        self.assertNotIn('id="wl_track"', html)
        self.assertNotIn('/waitlist/s/', html)

    def test_hidden_without_entry(self):
        self.assertNoTracking(self.form(self.config_a))

    def test_shown_while_waiting(self):
        entry = self.join_via_form(self.config_a)
        self.assertEqual(entry.state, 'waiting')
        self.assertTracking(self.form(self.config_a), entry)

    def test_hidden_once_entry_is_done(self):
        for state in ('seated', 'cancelled', 'left', 'no_show'):
            entry = self.join_via_form(self.config_a)
            self.assertTracking(self.form(self.config_a), entry)
            entry.state = state
            self.assertNoTracking(self.form(self.config_a))

    def test_second_visit_from_same_phone_and_browser(self):
        """Visit 1 seated, then the same phone scans again the same day: a new visit."""
        visit1 = self.join_via_form(self.config_a)
        visit1_token = visit1.sudo().access_token
        visit1.state = 'seated'
        self.assertNoTracking(self.form(self.config_a))
        visit2 = self.join_via_form(self.config_a)
        self.assertNotEqual(visit2, visit1)
        self.assertEqual((visit1.token, visit2.token, visit2.state), ('W-001', 'W-002', 'waiting'))
        self.assertTracking(self.form(self.config_a), visit2)
        # Each visit keeps its own status page.
        self.assertEqual(self.url_open(f'/waitlist/s/{visit1_token}/json').json()['state'], 'seated')
        self.assertEqual(self.url_open(f'/waitlist/s/{visit2.sudo().access_token}/json').json()['state'],
                         'waiting')

    def test_viewing_form_creates_nothing(self):
        self.join_via_form(self.config_a)
        for _i in range(3):
            self.form(self.config_a)
        self.assertEqual(self.Entry.search_count([('config_id', '=', self.config_a.id)]), 1)

    def test_recovered_entry_still_tracked(self):
        entry = self.join_via_form(self.config_a)
        for cookie in list(self.opener.cookies):
            if cookie.name.startswith('hudson_wl_'):
                self.opener.cookies.clear(cookie.domain, cookie.path, cookie.name)
        self.assertNoTracking(self.form(self.config_a))
        # Same phone joins again (e.g. new phone browser): existing entry recovered, link back.
        again = self.join_via_form(self.config_a)
        self.assertEqual(again, entry)
        self.assertEqual(self.Entry.search_count([('config_id', '=', self.config_a.id)]), 1)
        self.assertTracking(self.form(self.config_a), entry)

    def test_status_link_on_new_device_enables_tracking(self):
        entry, _c = self.join()
        self.assertNoTracking(self.form(self.config_a))
        self.url_open(f'/waitlist/s/{entry.sudo().access_token}')
        self.assertTracking(self.form(self.config_a), entry)

    def test_other_restaurant_never_shows_link(self):
        entry_a = self.join_via_form(self.config_a)
        self.assertNoTracking(self.form(self.config_b))
        # Even a cookie for B carrying A's token is refused.
        self.set_cookie(self.config_b, entry_a.sudo().access_token)
        self.assertNoTracking(self.form(self.config_b))
        self.assertFalse(self.Entry._get_active_tracking_entry(self.config_b, entry_a.sudo().access_token))

    def test_forged_cookie_ignored(self):
        for value in ('x' * 43, 'not a token', '1'):
            self.set_cookie(self.config_a, value)
            self.assertNoTracking(self.form(self.config_a))


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistConfigAndTags(WaitlistCommon):

    def test_estimated_wait_is_the_configured_average(self):
        """Every waiting guest sees the POS's Average Waiting Time, whatever their place in line."""
        guests = [self.join(phone=f'55500000{i:02d}')[0] for i in range(10)]
        self.assertEqual([g._public_status()['estimated_wait'] for g in guests], [10] * 10,
                         "10th in line still sees ~10 minutes, never 100")
        self.config_a.waitlist_minutes_per_party = 7
        guests[0].state = 'seated'
        self.env.invalidate_all()
        self.assertEqual(guests[0]._public_status()['estimated_wait'], 0)
        self.assertEqual({g._public_status()['estimated_wait'] for g in guests[1:]}, {7})
        # Other restaurants use their own setting.
        other, _c = self.join(self.config_b)
        self.assertEqual(other._public_status()['estimated_wait'], 15)

    def test_guest_status_reveals_no_queue_position(self):
        guests = [self.join(phone=f'55500001{i:02d}', party_size='2')[0] for i in range(5)]
        last = guests[-1]
        self.assertEqual(last.position, 5, "the host still knows the order internally")
        status = last._public_status()
        self.assertNotIn('position', status)
        for key, value in status.items():
            self.assertNotEqual(value, 5, f"{key} could reveal the queue position")
            self.assertNotEqual(value, 4, f"{key} could reveal the parties ahead")

    def test_minutes_per_party_minimum_one(self):
        self.assertEqual(self.env['pos.config'].create({'name': 'Default WL'}).waitlist_minutes_per_party, 10)
        for bad in (0, -5):
            with self.assertRaises(ValidationError):
                self.config_a.waitlist_minutes_per_party = bad
        self.config_a.waitlist_minutes_per_party = 1

    def test_tag_code_generated_and_kept_on_rename(self):
        Tag = self.env['pos.waitlist.tag']
        tag = Tag.create({'name': 'Window Seat'})
        self.assertEqual(tag.code, 'window_seat')
        self.assertEqual(Tag.create({'name': 'Window  seat!'}).code, 'window_seat_2')
        tag.write({'name': 'Window Table', 'code': False})
        self.assertEqual(tag.code, 'window_seat')
        entry, _c = self.join(tags=['window_seat'])
        self.assertEqual(entry.tag_ids, tag)
        tag.active = False
        with self.assertRaises(ValidationError):
            self.join(phone='5550000009', tags=['window_seat'])


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistFindMyPlace(HttpCase, WaitlistCommon):

    def find(self, config, phone, **extra):
        return self.url_open(f'/waitlist/join/{config.waitlist_token}/find',
                             data=dict(phone=phone, **extra), allow_redirects=False)

    def tracking_cookie(self, config):
        name = PosWaitlistController._tracking_cookie_name(config)
        return next((c.value for c in self.opener.cookies if c.name == name), None)

    def assertRecovered(self, res, entry):
        self.assertEqual(res.status_code, 303)
        self.assertEqual(urlparse(res.headers['Location']).path, f'/waitlist/s/{entry.sudo().access_token}')
        self.assertEqual(self.tracking_cookie(entry.config_id), entry.sudo().access_token)

    def test_form_shows_find_my_place(self):
        res = self.url_open(f'/waitlist/join/{self.config_a.waitlist_token}')
        self.assertIn('Already on the waitlist?', res.text)
        self.assertIn('Find My Place', res.text)
        self.assertIn(f'action="/waitlist/join/{self.config_a.waitlist_token}/find"', res.text)

    def test_recovers_waiting(self):
        entry, _c = self.join()
        token = entry.sudo().access_token
        # Typed differently on the new phone: same guest.
        self.assertRecovered(self.find(self.config_a, '+1 (555) 010-0001'), entry)
        self.opener.cookies.clear()
        self.assertRecovered(self.find(self.config_a, '15550100001'), entry)
        self.assertEqual(entry.sudo().access_token, token, "Existing access token reused")
        self.assertEqual(self.Entry.search_count([('config_id', '=', self.config_a.id)]), 1)
        # The join form on this browser now offers Track My Waitlist.
        self.assertIn('id="wl_track"', self.url_open(f'/waitlist/join/{self.config_a.waitlist_token}').text)

    def test_done_entries_not_recovered(self):
        entry, _c = self.join()
        for state in ('seated', 'cancelled', 'left', 'no_show'):
            entry.state = state
            res = self.find(self.config_a, '+1 555 010 0001')
            self.assertEqual(res.status_code, 200)
            self.assertIn('No active waitlist entry found for this number.', res.text)
            self.assertNotIn(entry.sudo().access_token, res.text)
            self.assertIsNone(self.tracking_cookie(self.config_a))

    def test_wrong_phone_and_other_restaurant(self):
        entry_a, _c = self.join(self.config_a)
        for config, phone in ((self.config_a, '5559999999'), (self.config_b, '+1 555 010 0001')):
            res = self.find(config, phone)
            self.assertEqual(res.status_code, 200)
            self.assertIn('No active waitlist entry found for this number.', res.text)
            self.assertNotIn(entry_a.token, res.text)
            self.assertNotIn('Ada Lovelace', res.text)
        self.assertEqual(self.Entry.search_count([]), 1, "Lookup never creates entries")

    def test_invalid_phone_and_disabled_restaurant(self):
        res = self.find(self.config_a, 'call me')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Please enter a valid phone number.', res.text)
        self.join(self.config_b)
        self.config_b.enable_qr_self_join = False
        self.assertEqual(self.find(self.config_b, '+1 555 010 0001').status_code, 404)
        self.assertEqual(self.url_open('/waitlist/join/' + 'x' * 22 + '/find',
                                       data={'phone': '5550100001'}).status_code, 404)

    def test_rate_limited(self):
        entry, _c = self.join()
        for i in range(10):
            self.assertEqual(self.find(self.config_a, f'555000{i:04d}').status_code, 200)
        res = self.find(self.config_a, '+1 555 010 0001')
        self.assertEqual(res.status_code, 429)
        self.assertIn('Too many attempts. Please try again in a few minutes.', res.text)
        self.assertNotIn(entry.sudo().access_token, res.text)
        # Normal joining is not rate limited.
        join = self.url_open(f'/waitlist/join/{self.config_a.waitlist_token}',
                             data=_form(phone='5551112222'), allow_redirects=False)
        self.assertEqual(join.status_code, 303)
        # Window expired -> lookups work again.
        self.env['pos.waitlist.lookup.attempt'].search([]).attempt_time = '2000-01-01 00:00:00'
        self.assertRecovered(self.find(self.config_a, '+1 555 010 0001'), entry)
        self.env['pos.waitlist.lookup.attempt']._gc_lookup_attempts()
        self.assertEqual(self.env['pos.waitlist.lookup.attempt'].search_count([]), 1)

    def test_rate_limit_is_per_client_behind_local_proxy(self):
        """Behind a local proxy/tunnel every guest comes from loopback: limit per forwarded client."""
        def find_as(client, spoofed=None):
            xff = f'{spoofed}, {client}' if spoofed else client
            return self.url_open(f'/waitlist/join/{self.config_a.waitlist_token}/find',
                                 data={'phone': '5550000000'}, headers={'X-Forwarded-For': xff},
                                 allow_redirects=False)
        for _i in range(10):
            self.assertEqual(find_as('203.0.113.7').status_code, 200)
        self.assertEqual(find_as('203.0.113.7').status_code, 429)
        # A forged left-most hop does not reset the limit; another guest is unaffected.
        self.assertEqual(find_as('203.0.113.7', spoofed='198.51.100.1').status_code, 429)
        self.assertEqual(find_as('203.0.113.8').status_code, 200)


@tagged('post_install', '-at_install', 'hudson_waitlist')
class TestWaitlistConcurrency(TransactionCase):
    """Real concurrent transactions (own DB connections, committed data, REPEATABLE READ)."""

    THREADS = 6

    def _env(self, cr):
        # Post-install tests run while the main thread holds Registry._lock, so
        # api.Environment -> Registry(dbname) would block forever in a worker thread.
        # Hand the already-loaded registry to the cursor instead.
        cr.transaction = Transaction(self.registry)
        cr.transaction._check_signaling(cr)  # sets up the ORM caches, as Environment.__new__ does
        return api.Environment(cr, SUPERUSER_ID, {})

    def setUp(self):
        super().setUp()
        self.dbname = self.env.cr.dbname
        with db_connect(self.dbname).cursor() as cr:
            env = self._env(cr)
            self.config_id = env['pos.config'].create({
                'name': 'Waitlist Concurrency', 'enable_qr_self_join': True}).id
            cr.commit()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        with db_connect(self.dbname).cursor() as cr:
            cr.execute("DELETE FROM pos_waitlist_entry WHERE config_id = %s", (self.config_id,))
            cr.execute("DELETE FROM pos_waitlist_counter WHERE config_id = %s", (self.config_id,))
            self._env(cr)['pos.config'].browse(self.config_id).unlink()
            cr.commit()

    def _join_in_new_transaction(self, values, barrier, results):
        """Like an HTTP request: own transaction, replayed on serialization failures."""
        barrier.wait()
        for _attempt in range(20):
            with db_connect(self.dbname).cursor() as cr:
                try:
                    env = self._env(cr)
                    config = env['pos.config'].browse(self.config_id)
                    entry, created = env['pos.waitlist.entry']._join_from_qr(config, values)
                    result = (entry.id, entry.token, created)
                    cr.flush()
                    # Transaction.reset() after commit/rollback calls Registry(dbname), which the
                    # test runner's Registry._lock blocks: end the transaction without the ORM layer.
                    cr.transaction = None
                    cr.commit()
                    results.append(result)
                    return
                except PG_CONCURRENCY_EXCEPTIONS_TO_RETRY:
                    cr.transaction = None
                    cr.rollback()
                except Exception as e:  # noqa: BLE001
                    cr.transaction = None
                    cr.rollback()
                    results.append(('error', repr(e), False))
                    return
        results.append(('error', 'too many retries', False))

    def _run_concurrently(self, values_list):
        barrier = threading.Barrier(len(values_list))
        results = []
        threads = [threading.Thread(target=self._join_in_new_transaction, args=(v, barrier, results),
                                    daemon=True)
                   for v in values_list]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        stuck = [t for t in threads if t.is_alive()]
        if stuck:
            frames = sys._current_frames()
            dump = '\n'.join(''.join(traceback.format_stack(frames[t.ident])) for t in stuck[:2])
            self.fail(f"{len(stuck)} concurrent joins did not finish:\n{dump}")
        errors = [r for r in results if r[0] == 'error']
        self.assertFalse(errors, errors)
        self.assertEqual(len(results), len(values_list))
        return results

    def _committed_entries(self):
        with db_connect(self.dbname).cursor() as cr:
            cr.execute("SELECT token, phone_normalized, state FROM pos_waitlist_entry WHERE config_id = %s",
                       (self.config_id,))
            return cr.fetchall()

    def test_concurrent_same_phone_creates_one_entry(self):
        results = self._run_concurrently([_form() for _i in range(self.THREADS)])
        self.assertEqual(len({r[0] for r in results}), 1, results)
        self.assertEqual(sum(1 for r in results if r[2]), 1, "exactly one request creates the entry")
        rows = self._committed_entries()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 'W-001')

    def test_concurrent_different_phones_get_unique_tokens(self):
        values = [_form(phone=f'55500000{i:02d}') for i in range(self.THREADS)]
        results = self._run_concurrently(values)
        self.assertTrue(all(r[2] for r in results))
        tokens = sorted(row[0] for row in self._committed_entries())
        self.assertEqual(tokens, [f'W-{i:03d}' for i in range(1, self.THREADS + 1)])
        self.assertTrue(all(re.match(r'^W-\d{3}$', t) for t in tokens))
