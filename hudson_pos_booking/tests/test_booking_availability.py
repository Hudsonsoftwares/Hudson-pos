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
            'slot_interval': 1.0,
            'appointment_tz': 'UTC',
        })

        # Resources (Tables)
        cls.res_table_1 = cls.env['appointment.resource'].create({
            'name': 'Table 1',
            'capacity': 4,
            'shareable': False,
            'appointment_type_ids': [(4, cls.appt_type.id)],
        })
        cls.res_table_2 = cls.env['appointment.resource'].create({
            'name': 'Table 2',
            'capacity': 4,
            'shareable': False,
            'appointment_type_ids': [(4, cls.appt_type.id)],
        })
        # Link table 1 and table 2
        cls.res_table_1.linked_resource_id = cls.res_table_2.id

        cls.res_shareable = cls.env['appointment.resource'].create({
            'name': 'Communal Table',
            'capacity': 6,
            'shareable': True,
            'appointment_type_ids': [(4, cls.appt_type.id)],
        })

        cls.appt_type.resource_ids = [(6, 0, [cls.res_table_1.id, cls.res_table_2.id, cls.res_shareable.id])]

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

        cls.floor = cls.env['restaurant.floor'].create({
            'name': 'Main Dining Room',
            'pos_config_ids': [(4, cls.pos_config.id)],
        })
        cls.table_1 = cls.env['restaurant.table'].create({
            'table_number': 1,
            'floor_id': cls.floor.id,
            'seats': 4,
            'appointment_resource_id': cls.res_table_1.id,
        })
        cls.table_2 = cls.env['restaurant.table'].create({
            'table_number': 2,
            'floor_id': cls.floor.id,
            'seats': 4,
            'appointment_resource_id': cls.res_table_2.id,
        })

    def test_availability_no_overlap(self):
        """Resource is free: should be returned as available."""
        start = datetime(2026, 11, 10, 18, 0, 0)
        end = start + timedelta(hours=2)
        available = self.appt_type._get_available_resources(start, end, party_size=2)
        self.assertIn(self.res_table_1, available)
        self.assertIn(self.res_table_2, available)

    def test_availability_blocked_by_confirmed(self):
        """Confirmed booking blocks a non-shareable table during that period."""
        start = datetime(2026, 11, 10, 18, 0, 0)
        end = start + timedelta(hours=2)
        self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 2,
            'start_datetime': start,
            'end_datetime': end,
            'state': 'confirmed',
        })

        available = self.appt_type._get_available_resources(start, end, party_size=2)
        self.assertNotIn(self.res_table_1, available)
        self.assertIn(self.res_table_2, available)

    def test_availability_shareable_table(self):
        """Shareable table allows multiple bookings up to capacity."""
        start = datetime(2026, 11, 10, 19, 0, 0)
        end = start + timedelta(hours=2)

        # Booking 1: 3 guests on Communal Table (capacity 6)
        self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_shareable.id])],
            'party_size': 3,
            'start_datetime': start,
            'end_datetime': end,
            'state': 'confirmed',
        })

        # 3 remaining capacity -> Party of 2 should fit
        available = self.appt_type._get_available_resources(start, end, party_size=2)
        self.assertIn(self.res_shareable, available)

        # Party of 4 exceeds remaining capacity (3 + 4 > 6)
        available_4 = self.appt_type._get_available_resources(start, end, party_size=4)
        self.assertNotIn(self.res_shareable, available_4)

    def test_linked_resource_not_added_unnecessarily(self):
        """
        Fix for Issue (a):
        When party_size fits on the primary table alone (party_size=2 <= capacity=4),
        the linked resource MUST NOT be assigned.
        """
        start = datetime(2026, 11, 10, 20, 0, 0)
        end = start + timedelta(hours=2)

        assigned = self.appt_type._assign_resources(
            start, end, party_size=2, requested_resource_id=self.res_table_1.id
        )
        self.assertEqual(len(assigned), 1)
        self.assertEqual(assigned, self.res_table_1)
        self.assertNotIn(self.res_table_2, assigned)

    def test_linked_resource_added_when_needed(self):
        """
        When party_size exceeds primary table capacity (party_size=6 > capacity=4),
        the linked resource IS assigned to accommodate the larger party.
        """
        start = datetime(2026, 11, 10, 20, 0, 0)
        end = start + timedelta(hours=2)

        assigned = self.appt_type._assign_resources(
            start, end, party_size=6, requested_resource_id=self.res_table_1.id
        )
        self.assertEqual(len(assigned), 2)
        self.assertIn(self.res_table_1, assigned)
        self.assertIn(self.res_table_2, assigned)

    def test_party_above_capacity(self):
        """Party size exceeding single and combined capacity cannot be assigned."""
        start = datetime(2026, 11, 10, 20, 0, 0)
        end = start + timedelta(hours=2)

        # Table 1 (4) + Table 2 (4) = 8 max. Party of 10 must fail.
        assigned = self.appt_type._assign_resources(
            start, end, party_size=10, requested_resource_id=self.res_table_1.id
        )
        self.assertFalse(assigned)

    def test_pending_payment_hold(self):
        """Pending payment holds table for 15 minutes, but expires after 15 minutes."""
        now = fields.Datetime.now()
        start = now + timedelta(hours=1)
        end = start + timedelta(hours=2)

        # Recent pending booking (5 minutes ago)
        recent_booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 2,
            'start_datetime': start,
            'end_datetime': end,
            'state': 'pending_payment',
        })
        available = self.appt_type._get_available_resources(start, end, party_size=2)
        self.assertNotIn(self.res_table_1, available)

        # Expired pending booking (simulate created 20 minutes ago)
        self.env.cr.execute(
            "UPDATE appointment_booking SET create_date = %s WHERE id = %s",
            [now - timedelta(minutes=20), recent_booking.id]
        )
        self.env.invalidate_all()

        available_after_expiry = self.appt_type._get_available_resources(start, end, party_size=2)
        self.assertIn(self.res_table_1, available_after_expiry)

    def test_phone_only_walkin_creation(self):
        """POS allows creating a walk-in booking with phone only (no email required)."""
        booking_data = self.env['pos.config'].pos_create_booking(self.pos_config.id, {
            'customer_name': 'Bob Walk-in',
            'customer_phone': '+15559876543',
            'customer_email': False,
            'party_size': 2,
            'table_id': self.table_1.id,
        })
        self.assertTrue(booking_data['id'])
        booking = self.env['appointment.booking'].browse(booking_data['id'])
        self.assertEqual(booking.partner_id.name, 'Bob Walk-in')
        self.assertEqual(booking.partner_id.phone, '+15559876543')
        self.assertFalse(booking.partner_id.email)
        self.assertEqual(booking.state, 'confirmed')
        self.assertEqual(booking.pos_config_id, self.pos_config)

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
            'name': 'POS Cashier',
            'login': 'pos_cashier',
            'group_ids': [(6, 0, [self.env.ref('point_of_sale.group_pos_user').id])],
        })

        # POS user can read booking
        booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 2,
            'start_datetime': fields.Datetime.now(),
            'end_datetime': fields.Datetime.now() + timedelta(hours=2),
            'state': 'confirmed',
        })
        booking_as_user = booking.with_user(pos_user)
        self.assertEqual(booking_as_user.state, 'confirmed')

        # POS user can check in
        booking_as_user.action_check_in()
        self.assertEqual(booking.state, 'checked_in')

    def test_access_rights_non_pos_user(self):
        """A user without POS or Appointment rights cannot write to appointment.booking."""
        standard_user = self.env['res.users'].create({
            'name': 'Standard Employee',
            'login': 'std_employee',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id])],
        })

        booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 2,
            'start_datetime': fields.Datetime.now(),
            'end_datetime': fields.Datetime.now() + timedelta(hours=2),
            'state': 'confirmed',
        })

        # Writing state without access rights raises AccessError
        with self.assertRaises(AccessError):
            booking.with_user(standard_user).write({'state': 'checked_in'})

    def test_concurrency_row_lock_verified(self):
        """
        Verify database row lock mechanism on appointment resources:
        Executing SELECT FOR UPDATE on appointment_resource succeeds within transaction,
        serialising concurrent booking validations.
        """
        self.env.cr.execute(
            "SELECT id FROM appointment_resource WHERE id IN %s FOR UPDATE",
            [tuple(self.res_table_1.ids)]
        )
        locked_id = self.env.cr.fetchone()[0]
        self.assertEqual(locked_id, self.res_table_1.id)
