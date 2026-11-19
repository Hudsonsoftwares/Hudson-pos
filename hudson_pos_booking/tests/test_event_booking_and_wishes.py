# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import re
from datetime import date, datetime, timedelta
import pytz

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import HttpCase, TransactionCase, tagged


def _ensure_restaurant_setup(env):
    """Helper to guarantee an active booking POS config, floor, and tables exist in test env."""
    bank_journal = env['account.journal'].search([('type', '=', 'bank')], limit=1)
    if not bank_journal:
        bank_journal = env['account.journal'].create({
            'name': 'Event Bank Test',
            'type': 'bank',
            'code': 'EBNK',
        })
    sale_journal = env['account.journal'].search([('type', '=', 'sale')], limit=1)
    if not sale_journal:
        sale_journal = env['account.journal'].create({
            'name': 'Event Sale Test',
            'type': 'sale',
            'code': 'ESAL',
        })
    payment_method = env['pos.payment.method'].search([('journal_id', '=', bank_journal.id)], limit=1)
    if not payment_method:
        payment_method = env['pos.payment.method'].create({
            'name': 'Event Bank Payment',
            'type': 'bank',
            'journal_id': bank_journal.id,
        })

    other_type = env.ref('hudson_pos_booking.appointment_type_event_other', raise_if_not_found=False)
    pos_config = env['pos.config'].create({
        'name': 'Hudson Celebration POS',
        'journal_id': sale_journal.id,
        'closing_journal_id': sale_journal.id,
        'payment_method_ids': [(4, payment_method.id)],
        'module_pos_restaurant': True,
        'use_booking': True,
        'booking_appointment_type_id': other_type.id if other_type else False,
    })
    floor = env['restaurant.floor'].create({
        'name': 'Celebration Hall',
        'pos_config_ids': [(4, pos_config.id)],
    })
    table_1 = env['restaurant.table'].create({
        'table_number': 101,
        'floor_id': floor.id,
        'seats': 6,
        'allow_website_booking': True,
    })
    table_2 = env['restaurant.table'].create({
        'table_number': 102,
        'floor_id': floor.id,
        'seats': 4,
        'allow_website_booking': True,
    })
    (table_1 | table_2)._sync_appointment_resource()
    return pos_config, floor, table_1, table_2


def _make_extra_event_type(env, name, category, emoji):
    """Extra resource-based celebration type. The module itself only ships the single
    'Celebrate Your Life Events' type; these are used to test cross-type table exclusivity."""
    return env['appointment.type'].create({
        'name': name,
        'booking_target': 'resources',
        'assign_method': 'random',
        'schedule_based_on': 'website',
        'is_event_booking': True,
        'event_category': category,
        'event_emoji': emoji,
        'is_published': True,
        'appointment_tz': 'UTC',
    })


@tagged('post_install', '-at_install')
class TestEventProvisioningAndPos(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.partner_id.tz = 'UTC'
        cls.env.user.tz = 'UTC'
        cls.created_by_cat = cls.env['appointment.type'].sudo()._ensure_default_event_booking_setup()
        cls.pos_config, cls.floor, cls.table_1, cls.table_2 = _ensure_restaurant_setup(cls.env)
        cls.other_type = cls.env.ref('hudson_pos_booking.appointment_type_event_other')
        cls.birthday_type = _make_extra_event_type(cls.env, 'Test Birthday Type', 'birthday', '🎂')
        cls.anniv_type = _make_extra_event_type(cls.env, 'Test Anniversary Type', 'anniversary', '💍')
        cls.win_type = _make_extra_event_type(cls.env, 'Test Win Type', 'win', '🏆')
        # Normalize TZ to UTC for deterministic timestamp assertions
        cls.other_type.write({'appointment_tz': 'UTC'})

    def test_01_event_types_questions_legacy_unpublish_and_idempotency(self):
        """Provisioning creates the single 'Celebrate Your Life Events' type without auto-allocating tables; config picker shows only allowed tables."""
        # Create a table with allow_website_booking=False and an orphaned table to verify config filtering
        table_private = self.env['restaurant.table'].create({
            'table_number': 103,
            'floor_id': self.floor.id,
            'seats': 4,
            'allow_website_booking': False,
        })
        table_private._sync_appointment_resource()

        # Create a legacy unpublished-candidate 'Table Booking' + a booking on it + a config pointing to it
        legacy_type = self.env['appointment.type'].create({
            'name': 'Table Booking',
            'is_event_booking': False,
            'booking_target': 'resources',
            'assign_method': 'customer',
            'is_published': True,
        })
        legacy_partner = self.env['res.partner'].create({'name': 'Legacy Guest', 'phone': '+919000011111'})
        start = fields.Datetime.now() + timedelta(days=10)
        legacy_booking = self.env['appointment.booking'].create({
            'appointment_type_id': legacy_type.id,
            'partner_id': legacy_partner.id,
            'party_size': 2,
            'start_datetime': start,
            'end_datetime': start + timedelta(hours=2),
            'state': 'confirmed',
        })
        legacy_cfg = self.env['pos.config'].create({
            'name': 'Legacy POS Config',
            'journal_id': self.pos_config.journal_id.id,
            'closing_journal_id': self.pos_config.closing_journal_id.id,
            'payment_method_ids': [(6, 0, self.pos_config.payment_method_ids.ids)],
            'module_pos_restaurant': True,
            'use_booking': True,
            'booking_appointment_type_id': legacy_type.id,
        })

        # Run setup twice to verify migration + idempotency
        res1 = self.env['appointment.type'].sudo()._ensure_default_event_booking_setup()
        res2 = self.env['appointment.type'].sudo()._ensure_default_event_booking_setup()

        self.assertEqual(set(res2), {'other'})
        self.assertEqual(res2['other'], self.other_type)
        self.assertEqual(self.other_type.name, 'Celebrate Your Life Events')
        for key in ('other',):
            self.assertEqual(res1[key].id, res2[key].id)
            # Created unpublished; the admin publishes it
            self.assertFalse(res2[key].is_published)
            self.assertTrue(res2[key].is_event_booking)
            self.assertEqual(res2[key].booking_target, 'resources')
            self.assertEqual(res2[key].assign_method, 'random')
            self.assertEqual(res2[key].schedule_based_on, 'website')
            # Tables must NOT be auto-allocated onto appointment types by default
            self.assertFalse(res2[key].resource_ids)
            # Only allowed website-bookable POS floor tables appear in allowed_resource_ids
            self.assertIn(self.table_1.appointment_resource_id, res2[key].allowed_resource_ids)
            self.assertIn(self.table_2.appointment_resource_id, res2[key].allowed_resource_ids)
            self.assertNotIn(table_private.appointment_resource_id, res2[key].allowed_resource_ids)
            # 3 life event questions attached: Event type / Special day date / Special requests
            roles = set(res2[key].question_ids.mapped('question_role'))
            self.assertEqual(roles, {'celebration_type', 'occasion_date', 'special_requests'})

        q_type = self.env.ref('hudson_pos_booking.question_event_celebration_type')
        self.assertEqual(q_type.question_type, 'select')
        self.assertEqual(q_type.answer_ids.sorted('sequence').mapped('name'),
                         ['Birthday', 'Anniversary', 'Engagement', 'Wedding', 'Other'])

        # Resource picker RPCs (name_search, search_read, web_search_read) show ONLY allow_website_booking=True tables
        ResourcePicker = self.env['appointment.resource'].with_context(appointment_booking_target='resources')
        ns_ids = {rid for rid, _label in ResourcePicker.name_search('')}
        self.assertIn(self.table_1.appointment_resource_id.id, ns_ids)
        self.assertIn(self.table_2.appointment_resource_id.id, ns_ids)
        self.assertNotIn(table_private.appointment_resource_id.id, ns_ids)

        wsr_ids = {r['id'] for r in ResourcePicker.web_search_read([], {'display_name': {}})['records']}
        self.assertIn(self.table_1.appointment_resource_id.id, wsr_ids)
        self.assertNotIn(table_private.appointment_resource_id.id, wsr_ids)

        # Exclusive table allocation per Event Type:
        # Giving table_1 to Birthday must hide table_1 from all other Event Types & block duplicate assignment
        self.birthday_type.write({'resource_ids': [(4, self.table_1.appointment_resource_id.id)]})
        self.assertIn(self.table_1.appointment_resource_id, self.birthday_type.allowed_resource_ids)
        for other_evt in (self.anniv_type, self.win_type, self.other_type):
            self.assertNotIn(self.table_1.appointment_resource_id, other_evt.allowed_resource_ids)
            self.assertIn(self.table_2.appointment_resource_id, other_evt.allowed_resource_ids)

        AnnivPicker = self.env['appointment.resource'].with_context(
            appointment_booking_target='resources',
            active_appointment_type_id=self.anniv_type.id,
        )
        anniv_ns_ids = {rid for rid, _label in AnnivPicker.name_search('')}
        self.assertNotIn(self.table_1.appointment_resource_id.id, anniv_ns_ids)
        self.assertIn(self.table_2.appointment_resource_id.id, anniv_ns_ids)

        # Attempting to force-assign Birthday's table_1 to Anniversary raises ValidationError
        with self.assertRaises(ValidationError):
            self.anniv_type.write({'resource_ids': [(4, self.table_1.appointment_resource_id.id)]})

        # Unassigning table_1 from Birthday keeps allow_website_booking=True and makes it available again
        self.birthday_type.write({'resource_ids': [(3, self.table_1.appointment_resource_id.id)]})
        self.assertTrue(self.table_1.allow_website_booking)
        self.assertIn(self.table_1.appointment_resource_id, self.anniv_type.allowed_resource_ids)

        # Appointment Resources menu/list clearly flags & filters allowed vs disallowed POS tables
        Resource = self.env['appointment.resource']
        self.assertTrue(self.table_1.appointment_resource_id.allow_website_booking)
        self.assertFalse(table_private.appointment_resource_id.allow_website_booking)
        allowed_list = Resource.search([('allow_website_booking', '=', True)])
        disabled_list = Resource.search([('allow_website_booking', '=', False)])
        self.assertIn(self.table_1.appointment_resource_id, allowed_list)
        self.assertNotIn(table_private.appointment_resource_id, allowed_list)
        self.assertIn(table_private.appointment_resource_id, disabled_list)
        self.assertNotIn(self.table_1.appointment_resource_id, disabled_list)
        res_action = self.env.ref('appointment.action_appointment_resource')
        # The "Allow Website Booking" toggle and its filters are no longer shown in the UI
        self.assertNotIn('search_default_website_booking_allowed', str(res_action.context))

        # Toggling allow_website_booking directly on appointment.resource syncs back to table & unlinks from event type
        self.birthday_type.write({'resource_ids': [(4, self.table_1.appointment_resource_id.id)]})
        self.table_1.appointment_resource_id.write({'allow_website_booking': False})
        self.assertFalse(self.table_1.allow_website_booking)
        self.assertNotIn(self.table_1.appointment_resource_id, self.birthday_type.resource_ids)
        self.table_1.appointment_resource_id.write({'allow_website_booking': True})
        self.assertTrue(self.table_1.allow_website_booking)

        q_date = self.env.ref('hudson_pos_booking.question_event_occasion_date')
        self.assertEqual(q_date.question_type, 'date')
        self.assertTrue(q_date.is_occasion_date)
        self.assertTrue(q_date.is_reusable)

        # Legacy type unpublished (never deleted) and historical booking preserved
        self.assertFalse(legacy_type.is_published)
        self.assertTrue(legacy_booking.exists())
        # Legacy POS config repointed to Celebrate Your Life Events
        self.assertEqual(legacy_cfg.booking_appointment_type_id, self.other_type)

    def test_01b_former_occasion_types_retired_into_life_events(self):
        """Former Birthday type (by XML id) is deleted after handing its bookings, tables and POS configs over."""
        old_birthday = _make_extra_event_type(self.env, 'Celebrate Your Birthday', 'birthday', '🎂')
        old_birthday.write({'resource_ids': [(4, self.table_1.appointment_resource_id.id)]})
        imd = self.env['ir.model.data'].search([
            ('module', '=', 'hudson_pos_booking'), ('name', '=', 'appointment_type_event_birthday'),
        ])
        imd.unlink()
        self.env['ir.model.data'].create({
            'module': 'hudson_pos_booking', 'name': 'appointment_type_event_birthday',
            'model': 'appointment.type', 'res_id': old_birthday.id, 'noupdate': True,
        })
        start = fields.Datetime.now() + timedelta(days=12)
        old_booking = self.env['appointment.booking'].create({
            'appointment_type_id': old_birthday.id,
            'customer_name': 'Old Birthday Guest',
            'customer_phone': '+919000022222',
            'party_size': 2,
            'start_datetime': start,
            'end_datetime': start + timedelta(hours=2),
            'state': 'confirmed',
        })
        self.pos_config.write({'booking_appointment_type_id': old_birthday.id})

        self.env['appointment.type'].sudo()._ensure_default_event_booking_setup()

        self.assertFalse(old_birthday.exists())
        self.assertFalse(self.env.ref('hudson_pos_booking.appointment_type_event_birthday', raise_if_not_found=False))
        self.assertIn(self.table_1.appointment_resource_id, self.other_type.resource_ids)
        self.assertTrue(old_booking.exists())
        self.assertEqual(old_booking.appointment_type_id, self.other_type)
        self.assertEqual(old_booking.celebration_type, 'birthday')
        self.assertEqual(self.pos_config.booking_appointment_type_id, self.other_type)
        self.other_type.write({'resource_ids': [(3, self.table_1.appointment_resource_id.id)]})

    def test_01d_publish_without_resource_and_config_popup(self):
        """No resource is not a validation error: the type can be published; the popup assigns tables."""
        life = self.other_type
        life.write({'resource_ids': [(5, 0, 0)]})
        self.assertFalse(life.hudson_resource_config_warning)
        life.write({'is_published': True})
        self.assertTrue(life.is_published)
        life.write({'is_published': False})

        # Popup = the appointment type itself, in a dedicated dialog view on the stock Resources field
        action = life.action_hudson_configure_resources()
        self.assertEqual(action['res_model'], 'appointment.type')
        self.assertEqual(action['res_id'], life.id)
        self.assertEqual(action['target'], 'new')
        popup_view = self.env.ref('hudson_pos_booking.appointment_type_view_form_hudson_configure_resources')
        self.assertEqual(action['views'], [(popup_view.id, 'form')])
        self.assertIn('name="resource_ids"', popup_view.arch)
        self.assertNotEqual(self.env['appointment.type'].get_formview_id(), popup_view.id)

        self.assertIn(self.table_1.appointment_resource_id, life.allowed_resource_ids)
        life.write({'resource_ids': [(6, 0, [self.table_1.appointment_resource_id.id])]})
        life.action_hudson_save_resources_and_publish()
        self.assertTrue(life.is_published)
        self.assertEqual(life.assign_method, 'random')
        self.assertFalse(life.hudson_resource_config_warning)

        # Losing its last table keeps the type published (no resource validation)
        life.write({'resource_ids': [(5, 0, 0)]})
        self.assertTrue(life.is_published)

        # A table owned by another type is not offered in the Resources field and cannot be forced
        self.birthday_type.write({'resource_ids': [(4, self.table_2.appointment_resource_id.id)]})
        self.assertNotIn(self.table_2.appointment_resource_id, life.allowed_resource_ids)
        with self.assertRaises(ValidationError):
            life.write({'resource_ids': [(4, self.table_2.appointment_resource_id.id)]})
        self.birthday_type.write({'resource_ids': [(3, self.table_2.appointment_resource_id.id)]})

    def test_01c_life_event_answers_sync_to_booking(self):
        """Event Type / Special Day Date / Special Requests answers fill the structured booking fields."""
        q_type = self.env.ref('hudson_pos_booking.question_event_celebration_type')
        q_date = self.env.ref('hudson_pos_booking.question_event_occasion_date')
        q_req = self.env.ref('hudson_pos_booking.question_event_special_requests')
        start = fields.Datetime.now() + timedelta(days=9)
        booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.other_type.id,
            'customer_name': 'Life Event Guest',
            'customer_phone': '+919000033333',
            'party_size': 4,
            'start_datetime': start,
            'end_datetime': start + timedelta(hours=2),
            'state': 'confirmed',
            'answer_ids': [
                (0, 0, {'question_id': q_type.id, 'value_text': 'Engagement',
                        'value_answer_ids': [(6, 0, q_type.answer_ids.filtered(lambda a: a.name == 'Engagement').ids)]}),
                (0, 0, {'question_id': q_date.id, 'value_text': '2024-02-14'}),
                (0, 0, {'question_id': q_req.id, 'value_text': 'Ring cake at 9 PM'}),
            ],
        })
        self.assertEqual(booking.celebration_type, 'engagement')
        self.assertEqual(booking.celebration_event_name, 'Engagement')
        self.assertEqual(booking.celebration_event_emoji, '💖')
        self.assertEqual(booking.occasion_date, date(2024, 2, 14))
        self.assertIn('Ring cake at 9 PM', booking.guest_details)
        self.assertIn('Engagement', booking._format_celebration_wish_message('day', 2025))

    def test_02_cross_event_table_double_booking_blocked(self):
        """Booking Table 101 under Birthday blocks Table 101 under Wedding Anniversary."""
        start_dt = (fields.Datetime.now() + timedelta(days=6)).replace(hour=14, minute=0, second=0, microsecond=0)
        self.env['pos.config'].pos_create_booking(self.pos_config.id, {
            'appointment_type_id': self.birthday_type.id,
            'customer_name': 'Rahul Nair',
            'customer_phone': '+919876500001',
            'celebrant_name': 'Ananya',
            'occasion_title': '5th Birthday',
            'occasion_date': '2021-06-15',
            'party_size': 4,
            'table_id': self.table_1.id,
            'start_datetime': fields.Datetime.to_string(start_dt),
            'duration': 2.0,
        })

        # Same table under Wedding Anniversary overlaps -> blocked by UserError
        with self.assertRaises(UserError):
            self.env['pos.config'].pos_create_booking(self.pos_config.id, {
                'appointment_type_id': self.anniv_type.id,
                'customer_name': 'Meera',
                'customer_phone': '+919876500002',
                'party_size': 2,
                'table_id': self.table_1.id,
                'start_datetime': fields.Datetime.to_string(start_dt + timedelta(minutes=30)),
                'duration': 1.5,
            })

        # When table_1 is exclusively assigned to Birthday, booking it under Anniversary at ANY time is blocked
        self.birthday_type.write({'resource_ids': [(4, self.table_1.appointment_resource_id.id)]})
        free_slot = start_dt + timedelta(days=2)
        with self.assertRaises(UserError):
            self.env['pos.config'].pos_create_booking(self.pos_config.id, {
                'appointment_type_id': self.anniv_type.id,
                'customer_name': 'Meera Exclusive Check',
                'customer_phone': '+919876500003',
                'party_size': 2,
                'table_id': self.table_1.id,
                'start_datetime': fields.Datetime.to_string(free_slot),
                'duration': 1.5,
            })
        with self.assertRaises(ValidationError):
            self.env['appointment.booking'].create({
                'appointment_type_id': self.anniv_type.id,
                'customer_name': 'Direct ORM Cross-Event',
                'customer_phone': '+919876500004',
                'resource_ids': [(6, 0, [self.table_1.appointment_resource_id.id])],
                'party_size': 2,
                'start_datetime': free_slot,
                'end_datetime': free_slot + timedelta(hours=2),
                'state': 'confirmed',
            })
        # Cleanup table_1 allocation so sibling tests start clean
        self.birthday_type.write({'resource_ids': [(3, self.table_1.appointment_resource_id.id)]})

    def test_03_pos_session_load_and_event_crud(self):
        """POS loads appointment.type, defaults walk-in to Celebrate Your Life Events, supports editing & safe partner match."""
        models_loaded = self.env['pos.session']._load_pos_data_models(self.pos_config)
        self.assertIn('appointment.type', models_loaded)
        self.assertIn('appointment.booking', models_loaded)

        at_domain = self.env['appointment.type']._load_pos_data_domain({'pos.config': self.pos_config})
        loaded_types = self.env['appointment.type'].search(at_domain)
        self.assertIn(self.other_type, loaded_types)
        self.assertIn(self.birthday_type, loaded_types)
        at_fields = self.env['appointment.type']._load_pos_data_fields(self.pos_config)
        for fname in ('name', 'event_category', 'event_emoji', 'is_event_booking', 'is_published'):
            self.assertIn(fname, at_fields)

        # Put same phone on company partner to verify safe partner matching NEVER attaches company partner!
        self.pos_config.company_id.partner_id.write({'phone': '+91 98470 11223'})

        # 1. Default event type -> Celebrate Your Life Events
        slot1 = (fields.Datetime.now() + timedelta(days=7)).replace(hour=13, minute=0, second=0, microsecond=0)
        res = self.env['pos.config'].pos_create_booking(self.pos_config.id, {
            'customer_name': 'Karthik Walk-in',
            'customer_phone': '9847011223',
            'party_size': 2,
            'table_id': self.table_2.id,
            'start_datetime': fields.Datetime.to_string(slot1),
            'duration': 2.0,
        })
        payload = res['appointment.booking'][0]
        booking = self.env['appointment.booking'].browse(payload['id'])
        self.assertEqual(booking.appointment_type_id, self.other_type)
        self.assertNotEqual(booking.partner_id, self.pos_config.company_id.partner_id)
        self.assertNotEqual(booking.partner_id.id, 1)
        self.assertFalse(booking.customer_email)
        self.assertEqual(payload['appointment_type_id'], self.other_type.id)
        self.assertEqual(payload['event_emoji'], '🎉')

        # 2. Update to Win Celebration with celebrant & special day
        upd = self.env['pos.config'].pos_update_booking(self.pos_config.id, booking.id, {
            'appointment_type_id': self.win_type.id,
            'celebrant_name': 'Team Hudson',
            'occasion_title': 'Championship Trophy',
            'occasion_date': '2026-11-20',
        })
        upd_payload = upd['appointment.booking'][0]
        self.assertEqual(booking.appointment_type_id, self.win_type)
        self.assertEqual(booking.celebrant_name, 'Team Hudson')
        self.assertEqual(booking.occasion_title, 'Championship Trophy')
        self.assertEqual(booking.occasion_date, date(2026, 11, 20))
        self.assertEqual(upd_payload['event_emoji'], '🏆')
        self.assertEqual(upd_payload['occasion_date'], '2026-11-20')

        # 3. Invalid appointment_type_id or bad occasion_date raises UserError
        user_only_type = self.env['appointment.type'].create({'name': 'Staff Only', 'booking_target': 'users'})
        with self.assertRaises(UserError):
            self.env['pos.config'].pos_create_booking(self.pos_config.id, {
                'appointment_type_id': user_only_type.id,
                'customer_name': 'Bad Type',
                'customer_phone': '+919999988888',
                'table_id': self.table_1.id,
                'start_datetime': fields.Datetime.to_string(slot1),
            })
        with self.assertRaises(UserError):
            self.env['pos.config'].pos_update_booking(self.pos_config.id, booking.id, {
                'occasion_date': 'not-a-date',
            })


@tagged('post_install', '-at_install')
class TestWebsiteEventHttpFlow(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.partner_id.tz = 'UTC'
        cls.env.user.tz = 'UTC'
        cls.env['appointment.type'].sudo()._ensure_default_event_booking_setup()
        cls.pos_config, cls.floor, cls.table_1, cls.table_2 = _ensure_restaurant_setup(cls.env)
        cls.life_type = cls.env.ref('hudson_pos_booking.appointment_type_event_other')
        # Client manually allocates the tables to the single Life Events type
        cls.life_type.write({'appointment_tz': 'UTC'})
        # Admin configures the tables through the backend popup, which also publishes the type
        cls.life_type.write({
            'resource_ids': [(6, 0, [cls.table_1.appointment_resource_id.id,
                                     cls.table_2.appointment_resource_id.id])],
        })
        cls.life_type.action_hudson_save_resources_and_publish()
        cls.q_type = cls.env.ref('hudson_pos_booking.question_event_celebration_type')
        cls.q_requests = cls.env.ref('hudson_pos_booking.question_event_special_requests')
        cls.q_date = cls.env.ref('hudson_pos_booking.question_event_occasion_date')
        cls.dish = cls.env['product.product'].create({
            'name': 'Birthday Truffle Cake',
            'type': 'consu',
            'available_in_pos': True,
            'sale_ok': True,
            'lst_price': 450.0,
            'taxes_id': [(5, 0, 0)],
        })

    def _extract_csrf(self, html_text):
        m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html_text)
        self.assertTrue(m, "CSRF token must be present in form HTML")
        return m.group(1)

    def test_01_index_phone_only_required_questions_preorder_cancel_and_wish_prefill(self):
        """Full HTTP flow: index excludes Table Booking, phone-only booking works, pre-order defers confirmation, wish link prefills."""
        legacy = self.env['appointment.type'].create({
            'name': 'Table Booking',
            'booking_target': 'resources',
            'is_event_booking': False,
            'is_published': False,
        })

        # 1. Public /appointment lists the single Life Events type and hides unpublished Table Booking
        idx_res = self.url_open('/appointment')
        self.assertEqual(idx_res.status_code, 200)
        idx_html = idx_res.text
        self.assertIn('Celebrate Your Life Events', idx_html)
        for retired_name in ('Celebrate Your Birthday', 'Wedding Anniversary', 'Your Win Celebration', 'Other Celebrations'):
            self.assertNotIn(retired_name, idx_html)
        self.assertNotIn('>Table Booking<', idx_html)
        self.assertNotIn(f'/appointment/{legacy.id}', idx_html)

        target_date = (fields.Date.today() + timedelta(days=5)).strftime('%Y-%m-%d')

        # 1b. Slot page: valid dates/times/party sizes, but no resource picker or table names for customers
        preview_res = self.url_open(f'/appointment/{self.life_type.id}?date={target_date}&party_size=2')
        self.assertEqual(preview_res.status_code, 200)
        preview_html = preview_res.text
        self.assertNotIn('staff_selection_container', preview_html)
        self.assertNotIn('staff_user_id_radio', preview_html)
        self.assertRegex(preview_html, r'name="time"')
        self.assertRegex(preview_html, r'<option[^>]*value="6"')  # largest table seats 6
        self.assertNotRegex(preview_html, r'<option[^>]*value="7"')
        self.assertNotIn(self.table_1.appointment_resource_id.name, idx_html)

        # 2. Load /info page -> check Phone required, Email optional, Date input exists
        info_url = f'/appointment/{self.life_type.id}/info?date={target_date}&time=14:00&party_size=4'
        info_res = self.url_open(info_url)
        self.assertEqual(info_res.status_code, 200)
        info_html = info_res.text
        self.assertIn('Phone number *', info_html)
        self.assertIn('Email', info_html)
        self.assertIn('(Optional)', info_html)
        self.assertIn('type="date"', info_html)
        self.assertIn('Event Type', info_html)
        self.assertIn('Engagement', info_html)
        self.assertIn('Special Requests', info_html)
        # Free-text notes card is replaced by the Special Requests question
        self.assertNotIn('name="customer_notes"', info_html)
        csrf = self._extract_csrf(info_html)

        # 3. Missing required celebration answer should redirect with missing_fields
        bad_submit = self.url_open(
            f'/appointment/{self.life_type.id}/submit',
            data={
                'csrf_token': csrf,
                'date': target_date,
                'time': '14:00',
                'party_size': '2',
                'name': 'Arjun Menon',
                'phone': '+919876543210',
                'email': '',
                f'question_{self.q_type.id}': '',
                f'question_{self.q_date.id}': '',
            },
            allow_redirects=False,
        )
        self.assertIn(bad_submit.status_code, (302, 303))
        self.assertIn('error=missing_fields', bad_submit.headers.get('Location', ''))

        # 4. Phone-only submit (no email) with valid answers succeeds & queues SMS
        ok_submit = self.url_open(
            f'/appointment/{self.life_type.id}/submit',
            data={
                'csrf_token': csrf,
                'date': target_date,
                'time': '14:00',
                'party_size': '2',
                'staff_user_id': str(self.table_1.appointment_resource_id.id),
                'name': 'Arjun Menon',
                'phone': '+919876543210',
                'email': '',
                f'question_{self.q_type.id}': 'Birthday',
                f'question_{self.q_requests.id}': 'Cake for Diya at 8 PM',
                f'question_{self.q_date.id}': '2020-11-12',
            },
            allow_redirects=False,
        )
        self.assertEqual(ok_submit.status_code, 200)
        self.assertIn('Celebration Details', ok_submit.text)
        self.assertIn('Birthday', ok_submit.text)

        booking = self.env['appointment.booking'].sudo().search([
            ('customer_phone', '=', '+919876543210'),
        ], order='id desc', limit=1)
        self.assertTrue(booking)
        self.assertEqual(booking.customer_name, 'Arjun Menon')
        self.assertFalse(booking.customer_email)
        self.assertEqual(booking.celebration_type, 'birthday')
        self.assertIn('Cake for Diya at 8 PM', booking.guest_details)
        self.assertEqual(booking.occasion_date, date(2020, 11, 12))
        self.assertTrue(booking.confirmation_sent)

        # Answer stored with typed value_date
        date_ans = booking.answer_ids.filtered(lambda a: a.question_id == self.q_date)
        self.assertEqual(date_ans.value_date, date(2020, 11, 12))

        # Transactional SMS queued for phone-only booking
        sms_recs = self.env['sms.sms'].sudo().search([('number', '=', '+919876543210')])
        self.assertTrue(sms_recs, "SMS confirmation must be queued for phone-only booking")

        # 5. Wish prefill URL prefills /appointment/<id>/info while tampered token is ignored
        wish_url = f'/appointment/{self.life_type.id}?wish_ref={booking.id}&wish_token={booking.access_token}'
        wish_page = self.url_open(wish_url)
        self.assertEqual(wish_page.status_code, 200)
        self.assertIn(f'value="{booking.access_token}"', wish_page.text)

        wish_info = self.url_open(
            f'/appointment/{self.life_type.id}/info?date={target_date}&time=16:00&party_size=2&wish_ref={booking.id}&wish_token={booking.access_token}'
        )
        self.assertEqual(wish_info.status_code, 200)
        self.assertIn('Arjun Menon', wish_info.text)
        self.assertIn('+919876543210', wish_info.text)
        self.assertRegex(wish_info.text, r'<option[^>]*value="Birthday"[^>]*selected')
        self.assertIn('2020-11-12', wish_info.text)

        tampered_info = self.url_open(
            f'/appointment/{self.life_type.id}/info?date={target_date}&time=16:00&party_size=2&wish_ref={booking.id}&wish_token=tampered_invalid'
        )
        self.assertEqual(tampered_info.status_code, 200)
        self.assertNotRegex(tampered_info.text, r'<option[^>]*value="Birthday"[^>]*selected')

        # 6. Pre-order food booking defers confirmation until SO/payment confirmation
        pre_info = self.url_open(f'/appointment/{self.life_type.id}/info?date={target_date}&time=17:00&party_size=2')
        pre_csrf = self._extract_csrf(pre_info.text)
        pre_res = self.url_open(
            f'/appointment/{self.life_type.id}/submit',
            data={
                'csrf_token': pre_csrf,
                'date': target_date,
                'time': '17:00',
                'party_size': '2',
                'staff_user_id': str(self.table_2.appointment_resource_id.id),
                'name': 'Priya Nair',
                'phone': '+919811122233',
                'email': 'priya@example.com',
                f'question_{self.q_type.id}': 'Anniversary',
                f'question_{self.q_requests.id}': 'Window table please',
                f'question_{self.q_date.id}': '2021-05-10',
                f'food_qty_{self.dish.id}': '1',
            },
            allow_redirects=False,
        )
        self.assertIn(pre_res.status_code, (302, 303))
        self.assertIn('/payment?token=', pre_res.headers.get('Location', ''))
        pre_booking = self.env['appointment.booking'].sudo().search([
            ('customer_phone', '=', '+919811122233'),
        ], limit=1)
        self.assertTrue(pre_booking)
        self.assertEqual(pre_booking.state, 'pending_payment')
        self.assertFalse(pre_booking.confirmation_sent, "Pre-order confirmation must wait until payment/SO confirmation")
        self.assertTrue(pre_booking.sale_order_id)

        # Confirm SO via payment transaction simulation -> triggers confirmation once
        pre_booking.sale_order_id.action_confirm()
        self.assertEqual(pre_booking.state, 'confirmed')
        self.assertTrue(pre_booking.confirmation_sent)

        # 7. Cancel phone-only booking succeeds cleanly with SMS and no email error
        cancel_res = self.url_open(
            f'/appointment/cancel/{booking.id}?token={booking.access_token}',
            allow_redirects=False,
        )
        self.assertIn(cancel_res.status_code, (302, 303))
        booking.invalidate_recordset(['state'])
        self.assertEqual(booking.state, 'cancelled')


@tagged('post_install', '-at_install')
class TestCelebrationWishesCron(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.partner_id.tz = 'UTC'
        cls.env['appointment.type'].sudo()._ensure_default_event_booking_setup()
        cls.birthday_type = cls.env.ref('hudson_pos_booking.appointment_type_event_other')  # Celebrate Your Life Events
        cls.birthday_type.write({
            'appointment_tz': 'UTC',
            'enable_anniversary_wishes': True,
            'wish_send_advance_invite': True,
            'wish_advance_days': 7,
            'wish_send_on_day': True,
        })
        cls.partner_full = cls.env['res.partner'].create({
            'name': 'Rohan Kapoor',
            'email': 'rohan@example.com',
            'phone': '+919822200001',
        })
        cls.partner_phone_only = cls.env['res.partner'].create({
            'name': 'Sita Devi',
            'phone': '+919822200002',
            'email': False,
        })

    def test_01_next_year_wishes_advance_day_toggles_leap_and_idempotency(self):
        """Test Year 0 guard, T-7 advance invite with Grab a party here link, Special Day wish, toggles, and Feb 29 leap year."""
        # Booking made on 2026-11-01 for occasion_date = 2000-11-12
        booked_start = datetime(2026, 11, 1, 12, 0, 0)
        b_full = self.env['appointment.booking'].create({
            'appointment_type_id': self.birthday_type.id,
            'partner_id': self.partner_full.id,
            'customer_name': 'Rohan Kapoor',
            'customer_email': 'rohan@example.com',
            'customer_phone': '+919822200001',
            'celebrant_name': 'Rohan Jr.',
            'celebration_type': 'birthday',
            'occasion_title': '10th Birthday',
            'occasion_date': date(2000, 11, 12),
            'start_datetime': booked_start,
            'end_datetime': booked_start + timedelta(hours=2),
            'state': 'checked_out',
        })

        # Year 0 (<14 days from booking): must NOT fire on 2026-11-05 or 2026-11-12
        s_y0_adv = self.env['appointment.booking']._cron_send_celebration_wishes(reference_date=date(2026, 11, 5))
        self.assertEqual(s_y0_adv['advance_sent'], 0)
        s_y0_day = self.env['appointment.booking']._cron_send_celebration_wishes(reference_date=date(2026, 11, 12))
        self.assertEqual(s_y0_day['day_sent'], 0)

        # Next year T-7 (2027-11-05): advance invite Email + SMS sent with "Grab a party here" + wish_ref/wish_token
        s_y1_adv = self.env['appointment.booking']._cron_send_celebration_wishes(reference_date=date(2027, 11, 5))
        self.assertGreaterEqual(s_y1_adv['advance_sent'], 1)
        self.assertEqual(b_full.wish_last_advance_year, 2027)

        adv_mail = self.env['mail.mail'].sudo().search([
            ('email_to', 'ilike', 'rohan@example.com'),
        ], order='id desc', limit=1)
        self.assertTrue(adv_mail)
        self.assertIn('Grab a party here', adv_mail.body_html)
        self.assertIn(f'wish_ref={b_full.id}', adv_mail.body_html)
        self.assertIn(f'wish_token={b_full.access_token}', adv_mail.body_html)

        adv_sms = self.env['sms.sms'].sudo().search([
            ('number', '=', '+919822200001'),
        ], order='id desc', limit=1)
        self.assertTrue(adv_sms)
        self.assertIn('Grab a party here', adv_sms.body)
        self.assertIn(f'wish_ref={b_full.id}', adv_sms.body)

        # Re-running on same day is idempotent
        s_y1_adv_again = self.env['appointment.booking']._cron_send_celebration_wishes(reference_date=date(2027, 11, 5))
        self.assertEqual(s_y1_adv_again['advance_sent'], 0)

        # Special Day (2027-11-12): sends day wish & marks wish_last_day_year = 2027
        s_y1_day = self.env['appointment.booking']._cron_send_celebration_wishes(reference_date=date(2027, 11, 12))
        self.assertGreaterEqual(s_y1_day['day_sent'], 1)
        self.assertEqual(b_full.wish_last_day_year, 2027)
        s_y1_day_again = self.env['appointment.booking']._cron_send_celebration_wishes(reference_date=date(2027, 11, 12))
        self.assertEqual(s_y1_day_again['day_sent'], 0)

        # Phone-only booking on Feb 29 (non-leap year 2027 -> celebrates on 2027-02-28)
        leap_book_start = datetime(2026, 2, 1, 14, 0, 0)
        b_leap_phone = self.env['appointment.booking'].create({
            'appointment_type_id': self.birthday_type.id,
            'partner_id': self.partner_phone_only.id,
            'customer_name': 'Sita Devi',
            'customer_phone': '+919822200002',
            'customer_email': False,
            'celebrant_name': 'Sita',
            'occasion_title': 'Leap Birthday',
            'occasion_date': date(2000, 2, 29),
            'start_datetime': leap_book_start,
            'end_datetime': leap_book_start + timedelta(hours=2),
            'state': 'confirmed',
        })
        s_leap_day = self.env['appointment.booking']._cron_send_celebration_wishes(reference_date=date(2027, 2, 28))
        self.assertGreaterEqual(s_leap_day['day_sent'], 1)
        self.assertEqual(b_leap_phone.wish_last_day_year, 2027)
        self.assertTrue(self.env['sms.sms'].sudo().search([('number', '=', '+919822200002')]))

        # Toggles respected: disabling advance invite suppresses T-7 in 2028
        self.birthday_type.write({'wish_send_advance_invite': False})
        s_y2_adv = self.env['appointment.booking']._cron_send_celebration_wishes(reference_date=date(2028, 11, 5))
        self.assertEqual(b_full.wish_last_advance_year, 2027)
        self.assertEqual(s_y2_adv['advance_sent'], 0)

        # Disabling wish_send_on_day & master toggle
        self.birthday_type.write({'wish_send_on_day': False})
        self.env['appointment.booking']._cron_send_celebration_wishes(reference_date=date(2028, 11, 12))
        self.assertEqual(b_full.wish_last_day_year, 2027)

        self.birthday_type.write({
            'wish_send_advance_invite': True,
            'wish_send_on_day': True,
            'enable_anniversary_wishes': False,
        })
        self.env['appointment.booking']._cron_send_celebration_wishes(reference_date=date(2028, 11, 5))
        self.assertEqual(b_full.wish_last_advance_year, 2027)

        # Validation constraint on wish_advance_days < 1
        with self.assertRaises(ValidationError):
            self.birthday_type.write({'wish_send_advance_invite': True, 'wish_advance_days': 0})

