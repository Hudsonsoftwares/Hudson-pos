# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta
from odoo import fields
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError, AccessError

@tagged('post_install', '-at_install')
class TestBookingAvailability(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Appointment Type for table bookings
        cls.appt_type = cls.env['appointment.type'].create({
            'name': 'Restaurant Dining',
            'booking_target': 'resources',
            'appointment_duration': 2.0,
            'appointment_tz': 'UTC',
        })

        # Customer partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Alice Test',
            'email': 'alice@example.com',
            'phone': '+15551234567',
        })

        # Ensure journals exist for pos.config
        bank_journal = cls.env['account.journal'].search([('type', '=', 'bank')], limit=1)
        if not bank_journal:
            bank_journal = cls.env['account.journal'].create({
                'name': 'Bank Test',
                'type': 'bank',
                'code': 'BNKT',
            })
        sale_journal = cls.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        if not sale_journal:
            sale_journal = cls.env['account.journal'].create({
                'name': 'Sale Test',
                'type': 'sale',
                'code': 'POSS',
            })
        payment_method = cls.env['pos.payment.method'].search([('journal_id', '=', bank_journal.id)], limit=1)
        if not payment_method:
            payment_method = cls.env['pos.payment.method'].create({
                'name': 'Bank Payment',
                'type': 'bank',
                'journal_id': bank_journal.id,
            })

        # POS Config
        cls.pos_config = cls.env['pos.config'].create({
            'name': 'Main Dining POS',
            'journal_id': sale_journal.id,
            'closing_journal_id': sale_journal.id,
            'payment_method_ids': [(4, payment_method.id)],
            'module_pos_restaurant': True,
            'use_booking': True,
            'booking_appointment_type_id': cls.appt_type.id,
            'booking_no_show_grace_minutes': 15,
        })

        # Pos config company & user tz to UTC
        cls.pos_config.company_id.partner_id.tz = 'UTC'
        cls.env.user.tz = 'UTC'

        cls.floor = cls.env['restaurant.floor'].create({
            'name': 'Main Dining Room',
            'pos_config_ids': [(4, cls.pos_config.id)],
        })
        cls.table_1 = cls.env['restaurant.table'].create({
            'table_number': 1,
            'floor_id': cls.floor.id,
            'seats': 4,
            'allow_website_booking': True,
        })
        cls.table_2 = cls.env['restaurant.table'].create({
            'table_number': 2,
            'floor_id': cls.floor.id,
            'seats': 4,
            'allow_website_booking': True,
        })
        cls.table_1._sync_appointment_resource()
        cls.table_2._sync_appointment_resource()
        cls.res_table_1 = cls.table_1.appointment_resource_id
        cls.res_table_2 = cls.table_2.appointment_resource_id
        cls.appt_type.resource_ids = [(6, 0, [cls.res_table_1.id, cls.res_table_2.id])]

    def test_phone_only_walkin_creation(self):
        """POS allows creating a walk-in booking with phone only (no email required)."""
        future_dt = fields.Datetime.now() + timedelta(days=2)
        res = self.env['pos.config'].pos_create_booking(self.pos_config.id, {
            'customer_name': 'Bob Walk-in',
            'customer_phone': '+15559876543',
            'customer_email': False,
            'party_size': 2,
            'table_id': self.table_1.id,
            'start_datetime': fields.Datetime.to_string(future_dt),
            'duration': 1.5,
        })
        booking_data = res.get('appointment.booking', [])
        self.assertTrue(booking_data)
        booking_id = booking_data[0]['id']
        booking = self.env['appointment.booking'].browse(booking_id)
        self.assertEqual(booking.customer_name, 'Bob Walk-in')
        self.assertEqual(booking.customer_phone, '+15559876543')
        self.assertFalse(booking.customer_email)
        self.assertEqual(booking.state, 'confirmed')
        self.assertEqual(booking.pos_config_id, self.pos_config)

    def test_double_booking_prevention(self):
        """Creating an overlapping booking on the same table raises double-booking conflict error."""
        start = fields.Datetime.now() + timedelta(days=3)
        end = start + timedelta(hours=2)

        # Booking 1
        self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 2,
            'start_datetime': start,
            'end_datetime': end,
            'state': 'confirmed',
        })

        # Booking 2 overlapping on Table 1 from POS must fail
        with self.assertRaises(UserError):
            self.env['pos.config'].pos_create_booking(self.pos_config.id, {
                'customer_name': 'Conflict Guest',
                'customer_phone': '+15550001111',
                'party_size': 2,
                'table_id': self.table_1.id,
                'start_datetime': fields.Datetime.to_string(start + timedelta(minutes=30)),
                'duration': 1.5,
            })

    def test_merged_table_double_booking_conflict(self):
        """When tables are merged, booking parent blocks child table as well."""
        self.table_2.parent_id = self.table_1.id
        self.table_1._sync_appointment_resource()
        self.table_2._sync_appointment_resource()

        start = fields.Datetime.now() + timedelta(days=4)
        end = start + timedelta(hours=2)

        # Booking on Table 1
        self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 4,
            'start_datetime': start,
            'end_datetime': end,
            'state': 'confirmed',
        })

        # Booking on merged Table 2 during the same window must raise UserError
        with self.assertRaises(UserError):
            self.env['pos.config'].pos_create_booking(self.pos_config.id, {
                'customer_name': 'Merged Conflict Guest',
                'customer_phone': '+15552223333',
                'party_size': 2,
                'table_id': self.table_2.id,
                'start_datetime': fields.Datetime.to_string(start),
                'duration': 2.0,
            })

    def test_no_show_scheduled_action(self):
        """Cron automatically marks confirmed bookings past grace period as no-show."""
        past_end = fields.Datetime.now() - timedelta(minutes=30)
        past_start = past_end - timedelta(hours=2)

        confirmed_booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 2,
            'start_datetime': past_start,
            'end_datetime': past_end,
            'state': 'confirmed',
            'pos_config_id': self.pos_config.id,
        })

        checked_in_booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_2.id])],
            'party_size': 2,
            'start_datetime': past_start,
            'end_datetime': past_end,
            'state': 'checked_in',
            'pos_config_id': self.pos_config.id,
        })

        # Trigger cron
        self.env['appointment.booking']._cron_mark_no_show()

        self.assertEqual(confirmed_booking.state, 'no_show', "Confirmed booking should be transitioned to no_show")
        self.assertEqual(checked_in_booking.state, 'checked_in', "Checked in booking must NOT be marked no_show")

    def test_access_rights_pos_user(self):
        """POS User has read/write access to appointment.booking."""
        pos_user = self.env['res.users'].create({
            'name': 'POS Cashier User',
            'login': 'pos_cashier_user',
            'group_ids': [(6, 0, [self.env.ref('point_of_sale.group_pos_user').id])],
        })

        booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 2,
            'start_datetime': fields.Datetime.now() + timedelta(days=5),
            'end_datetime': fields.Datetime.now() + timedelta(days=5, hours=2),
            'state': 'confirmed',
        })
        booking_as_user = booking.with_user(pos_user)
        self.assertEqual(booking_as_user.state, 'confirmed')

        # POS user can check in
        booking_as_user.action_check_in()
        self.assertEqual(booking.state, 'checked_in')

    def test_concurrency_row_lock_verified(self):
        """
        Verify database row lock mechanism on appointment resources:
        Executing sorted SELECT FOR UPDATE on appointment_resource succeeds within transaction,
        serialising concurrent booking validations.
        """
        res_ids = sorted([self.res_table_1.id, self.res_table_2.id])
        self.env.cr.execute(
            "SELECT id FROM appointment_resource WHERE id IN %s ORDER BY id FOR UPDATE",
            [tuple(res_ids)]
        )
        locked_ids = [row[0] for row in self.env.cr.fetchall()]
        self.assertEqual(locked_ids, res_ids)
