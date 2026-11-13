# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import os
import uuid
import xml.etree.ElementTree as ET
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

        cls.bank_payment_method = payment_method
        cls.dish_product = cls.env['product.product'].create({
            'name': 'Hudson Test Pasta',
            'type': 'consu',
            'available_in_pos': True,
            'lst_price': 25.0,
            'taxes_id': [(5, 0, 0)],
        })

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

    def test_orphaned_floor_table_excluded_and_detach_unlinks(self):
        """Tables on orphaned floors (no active booking pos.config) are never exposed to website booking."""
        orphaned_floor = self.env['restaurant.floor'].create({
            'name': 'Orphaned Default Floor',
            'pos_config_ids': [(5, 0, 0)],
        })
        orphaned_table = self.env['restaurant.table'].create({
            'table_number': 99,
            'floor_id': orphaned_floor.id,
            'seats': 1,
            'allow_website_booking': True,
        })
        self.assertNotIn(orphaned_table.appointment_resource_id, self.appt_type.resource_ids)

        # Attach a temporary floor to pos_config -> table creates synced resource (never auto-allocated)
        # and becomes selectable in allowed_resource_ids; once manually assigned, detaching floor unlinks it.
        temp_floor = self.env['restaurant.floor'].create({
            'name': 'Temp Patio',
            'pos_config_ids': [(4, self.pos_config.id)],
        })
        temp_table = self.env['restaurant.table'].create({
            'table_number': 88,
            'floor_id': temp_floor.id,
            'seats': 4,
            'allow_website_booking': True,
        })
        self.assertTrue(temp_table.appointment_resource_id)
        self.assertNotIn(temp_table.appointment_resource_id, self.appt_type.resource_ids)
        self.assertIn(temp_table.appointment_resource_id, self.appt_type.allowed_resource_ids)

        # Client manually configures temp_table onto appt_type, then detaches floor -> unlinked again
        self.appt_type.write({'resource_ids': [(4, temp_table.appointment_resource_id.id)]})
        self.assertIn(temp_table.appointment_resource_id, self.appt_type.resource_ids)

        # Detaching the floor from POS config must unlink its resources from Table Booking
        self.pos_config.write({'floor_ids': [(3, temp_floor.id)]})
        self.assertNotIn(temp_table.appointment_resource_id, self.appt_type.resource_ids)
        self.assertNotIn(temp_table.appointment_resource_id, self.appt_type.allowed_resource_ids)

    def test_cleanup_rescues_trapped_booking_and_pos_domain_tz(self):
        """Cleanup rescues trapped orphaned-floor bookings onto active POS floor tables and loads multi-day/local TZ bookings."""
        orphaned_floor = self.env['restaurant.floor'].create({
            'name': 'My Company',
            'pos_config_ids': [(5, 0, 0)],
        })
        orphaned_table = self.env['restaurant.table'].create({
            'table_number': 77,
            'floor_id': orphaned_floor.id,
            'seats': 1,
            'allow_website_booking': True,
        })
        orphaned_table.with_context(force_create_resource=True)._sync_appointment_resource()
        orphan_res = orphaned_table.appointment_resource_id
        self.appt_type.with_context(skip_table_sync=True).write({'resource_ids': [(4, orphan_res.id)]})

        # Simulate blank company partner TZ and IST appointment_tz as on fresh DBs
        self.pos_config.company_id.partner_id.tz = False
        self.env.user.tz = False
        self.appt_type.appointment_tz = 'Asia/Calcutta'

        start_utc = datetime.utcnow().replace(hour=7, minute=0, second=0, microsecond=0) + timedelta(days=5)
        end_utc = start_utc + timedelta(hours=2)
        trapped_booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'customer_name': 'Trapped Guest',
            'resource_ids': [(6, 0, [orphan_res.id])],
            'party_size': 1,
            'start_datetime': start_utc,
            'end_datetime': end_utc,
            'state': 'confirmed',
        })

        self.env['restaurant.table']._cleanup_orphaned_tables_and_rescue_bookings()

        self.assertNotIn(orphan_res, self.appt_type.resource_ids)
        self.assertTrue(trapped_booking.table_ids)
        self.assertNotIn(orphaned_table, trapped_booking.table_ids)
        self.assertIn(trapped_booking.table_ids[0].floor_id, self.pos_config.floor_ids)

        # Verify _load_pos_data_domain includes this multi-day rescued booking
        domain = self.env['appointment.booking']._load_pos_data_domain({'pos.config': self.pos_config})
        loaded = self.env['appointment.booking'].search(domain)
        self.assertIn(trapped_booking, loaded)

        # Verify _get_pos_booking_data formats time in appointment_tz (07:00 UTC -> 12:30 IST) and carries full schema fields
        payload = trapped_booking._get_pos_booking_data(self.pos_config)
        self.assertEqual(payload['start_time_str'], '12:30')
        self.assertEqual(payload['end_time_str'], '14:30')
        self.assertEqual(payload['resource_ids'], trapped_booking.resource_ids.ids)
        self.assertIn('guest_details', payload)
        self.assertIn('write_date', payload)

        # Restore TZ for sibling tests if run out of order
        self.appt_type.appointment_tz = 'UTC'
        self.pos_config.company_id.partner_id.tz = 'UTC'
        self.env.user.tz = 'UTC'

    def _open_pos_session(self):
        if not self.pos_config.current_session_id:
            self.pos_config.open_ui()
        return self.pos_config.current_session_id

    def _build_sync_order_payload(
        self,
        session,
        table,
        *,
        order_uuid=None,
        state='draft',
        booking=None,
        lines=None,
        amount_total=None,
        amount_paid=None,
        payment_ids=None,
        is_refund=False,
    ):
        order_uuid = order_uuid or str(uuid.uuid4())
        if lines is None:
            price = self.dish_product.lst_price
            lines = [[0, 0, {
                'name': self.dish_product.display_name,
                'price_unit': price,
                'product_id': self.dish_product.id,
                'price_subtotal': price,
                'price_subtotal_incl': price,
                'qty': 1,
                'tax_ids': [],
                'uuid': str(uuid.uuid4()),
            }]]
        if amount_total is None:
            amount_total = sum(cmd[2].get('price_subtotal_incl', 0.0) for cmd in lines if len(cmd) > 2)
        if payment_ids is None:
            if state == 'paid' and abs(amount_total) > 0.0001 and not is_refund:
                payment_ids = [[0, 0, {
                    'amount': amount_total,
                    'payment_method_id': self.bank_payment_method.id,
                    'payment_date': fields.Datetime.to_string(fields.Datetime.now()),
                    'uuid': str(uuid.uuid4()),
                }]]
            else:
                payment_ids = []
        if amount_paid is None:
            amount_paid = sum(cmd[2].get('amount', 0.0) for cmd in payment_ids if len(cmd) > 2)
        payload = {
            'name': f'Order {order_uuid[:8]}',
            'uuid': order_uuid,
            'session_id': session.id,
            'table_id': table.id if table else False,
            'partner_id': self.partner.id,
            'user_id': self.env.uid,
            'date_order': fields.Datetime.to_string(fields.Datetime.now()),
            'fiscal_position_id': False,
            'pricelist_id': session.config_id.pricelist_id.id if session.config_id.pricelist_id else False,
            'to_invoice': False,
            'state': state,
            'is_refund': is_refund,
            'amount_tax': 0.0,
            'amount_total': amount_total,
            'amount_paid': amount_paid,
            'amount_return': 0.0,
            'lines': lines,
            'payment_ids': payment_ids,
        }
        if booking is not None:
            payload['booking_id'] = booking.id if booking else False
        return payload

    def test_auto_release_on_pos_order_paid_via_sync_from_ui(self):
        """Validating POS payment via sync_from_ui automatically releases the table & checks out the booking."""
        session = self._open_pos_session()
        now = fields.Datetime.now()
        booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 2,
            'start_datetime': now - timedelta(minutes=30),
            'end_datetime': now + timedelta(minutes=90),
            'state': 'checked_in',
            'pos_config_id': self.pos_config.id,
        })

        # Create a draft order for this booking plus an empty stale phantom draft on the same table
        draft_uuid = str(uuid.uuid4())
        empty_uuid = str(uuid.uuid4())
        price = self.dish_product.lst_price
        draft_lines = [[0, 0, {
            'name': self.dish_product.display_name,
            'price_unit': price,
            'product_id': self.dish_product.id,
            'price_subtotal': price,
            'price_subtotal_incl': price,
            'qty': 1,
            'tax_ids': [],
            'uuid': str(uuid.uuid4()),
        }]]
        self.env['pos.order'].sync_from_ui([
            self._build_sync_order_payload(session, self.table_1, order_uuid=draft_uuid, state='draft', booking=booking, lines=draft_lines),
        ])
        empty_payload = self._build_sync_order_payload(session, self.table_1, order_uuid=empty_uuid, state='draft', lines=[], amount_total=0.0)
        empty_payload['company_id'] = session.company_id.id
        empty_order = self.env['pos.order'].create(empty_payload)
        self.assertEqual(empty_order.state, 'draft')

        # Validate payment via sync_from_ui -> triggers _process_saved_order -> action_pos_order_paid
        self.env['pos.order'].sync_from_ui([
            self._build_sync_order_payload(session, self.table_1, order_uuid=draft_uuid, state='paid', booking=booking, lines=draft_lines),
        ])
        paid_order = self.env['pos.order'].search([('uuid', '=', draft_uuid)], limit=1)
        self.assertEqual(paid_order.state, 'paid')
        self.assertEqual(booking.state, 'checked_out', "Booking must automatically transition to checked_out on payment")
        self.assertLessEqual(booking.end_datetime, fields.Datetime.now() + timedelta(seconds=5))
        self.assertEqual(empty_order.state, 'cancel', "Empty orphan draft order on the table must be cancelled cleanly")

    def test_auto_release_zero_amount_prepaid_booking(self):
        """A $0 prepaid POS order still runs action_pos_order_paid and auto-releases the table."""
        session = self._open_pos_session()
        now = fields.Datetime.now()
        booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 2,
            'start_datetime': now - timedelta(minutes=15),
            'end_datetime': now + timedelta(minutes=105),
            'state': 'checked_in',
            'pos_config_id': self.pos_config.id,
        })
        zero_lines = [[0, 0, {
            'price_unit': self.dish_product.lst_price,
            'discount': 100.0,
            'product_id': self.dish_product.id,
            'price_subtotal': 0.0,
            'price_subtotal_incl': 0.0,
            'qty': 1,
            'tax_ids': [],
            'customer_note': f'Prepaid Online (Booking #{booking.id})',
            'uuid': str(uuid.uuid4()),
        }]]
        order_uuid = str(uuid.uuid4())
        self.env['pos.order'].sync_from_ui([
            self._build_sync_order_payload(
                session,
                self.table_1,
                order_uuid=order_uuid,
                state='paid',
                booking=booking,
                lines=zero_lines,
                amount_total=0.0,
                amount_paid=0.0,
                payment_ids=[],
            ),
        ])
        paid_order = self.env['pos.order'].search([('uuid', '=', order_uuid)], limit=1)
        self.assertEqual(paid_order.state, 'paid')
        self.assertEqual(booking.state, 'checked_out', "$0 prepaid order validation must auto-checkout booking")

    def test_auto_release_unlinked_order_and_merged_tables(self):
        """Payment auto-links & releases early checked-in bookings and merged child-table bookings."""
        session = self._open_pos_session()
        now = fields.Datetime.now()

        # Part A: Early check-in >30 min before scheduled start_datetime, paid via unlinked POS order
        early_start = now + timedelta(hours=2)
        early_booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 2,
            'start_datetime': early_start,
            'end_datetime': early_start + timedelta(hours=2),
            'state': 'checked_in',
            'pos_config_id': self.pos_config.id,
        })
        early_uuid = str(uuid.uuid4())
        self.env['pos.order'].sync_from_ui([
            self._build_sync_order_payload(session, self.table_1, order_uuid=early_uuid, state='paid', booking=False),
        ])
        early_order = self.env['pos.order'].search([('uuid', '=', early_uuid)], limit=1)
        self.assertEqual(early_order.booking_id, early_booking)
        self.assertEqual(early_booking.state, 'checked_out')
        self.assertEqual(early_booking.end_datetime, early_start + timedelta(minutes=1))

        # Part B: Merged tables (table_2 merged into root table_1), booking sitting on child table_2
        self.table_2.parent_id = self.table_1.id
        merged_booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_2.id])],
            'party_size': 4,
            'start_datetime': now - timedelta(minutes=10),
            'end_datetime': now + timedelta(minutes=110),
            'state': 'checked_in',
            'pos_config_id': self.pos_config.id,
        })
        merged_uuid = str(uuid.uuid4())
        self.env['pos.order'].sync_from_ui([
            self._build_sync_order_payload(session, self.table_1, order_uuid=merged_uuid, state='paid', booking=False),
        ])
        self.assertEqual(merged_booking.state, 'checked_out', "Paying merged root table must release child table booking")

    def test_walkin_payment_preserves_future_confirmed_booking(self):
        """Paying a walk-in order on a table must NEVER check out an upcoming confirmed reservation."""
        session = self._open_pos_session()
        now = fields.Datetime.now()
        future_booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 2,
            'start_datetime': now + timedelta(hours=2),
            'end_datetime': now + timedelta(hours=4),
            'state': 'confirmed',
            'pos_config_id': self.pos_config.id,
        })
        walkin_uuid = str(uuid.uuid4())
        self.env['pos.order'].sync_from_ui([
            self._build_sync_order_payload(session, self.table_1, order_uuid=walkin_uuid, state='paid', booking=False),
        ])
        walkin_order = self.env['pos.order'].search([('uuid', '=', walkin_uuid)], limit=1)
        self.assertFalse(walkin_order.booking_id)
        self.assertEqual(future_booking.state, 'confirmed')

        # Also verify fallback RPC pos_release_table never auto-closes future confirmed bookings when booking_id=False
        self.env['pos.config'].pos_release_table(self.pos_config.id, self.table_1.id, booking_id=False)
        self.assertEqual(future_booking.state, 'confirmed')

    def test_split_order_defers_auto_release_and_refund_does_not_release(self):
        """Split bills release only on the last open bill; refund orders never release an active booking."""
        session = self._open_pos_session()
        now = fields.Datetime.now()
        split_booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_1.id])],
            'party_size': 4,
            'start_datetime': now - timedelta(minutes=20),
            'end_datetime': now + timedelta(minutes=100),
            'state': 'checked_in',
            'pos_config_id': self.pos_config.id,
        })

        bill_1_uuid = str(uuid.uuid4())
        bill_2_uuid = str(uuid.uuid4())
        unit_price = self.dish_product.lst_price
        bill_1_lines = [[0, 0, {
            'name': self.dish_product.display_name,
            'price_unit': unit_price,
            'product_id': self.dish_product.id,
            'price_subtotal': unit_price,
            'price_subtotal_incl': unit_price,
            'qty': 1,
            'tax_ids': [],
            'uuid': str(uuid.uuid4()),
        }]]
        bill_2_lines = [[0, 0, {
            'name': self.dish_product.display_name,
            'price_unit': unit_price,
            'product_id': self.dish_product.id,
            'price_subtotal': unit_price,
            'price_subtotal_incl': unit_price,
            'qty': 1,
            'tax_ids': [],
            'uuid': str(uuid.uuid4()),
        }]]
        self.env['pos.order'].sync_from_ui([
            self._build_sync_order_payload(session, self.table_1, order_uuid=bill_1_uuid, state='draft', booking=split_booking, lines=bill_1_lines),
        ])
        bill_2_payload = self._build_sync_order_payload(session, self.table_1, order_uuid=bill_2_uuid, state='draft', booking=split_booking, lines=bill_2_lines)
        bill_2_payload['company_id'] = session.company_id.id
        bill_2 = self.env['pos.order'].create(bill_2_payload)
        self.assertTrue(bool(bill_2.lines))

        # Pay first split bill -> second draft still has lines, so booking stays checked_in
        self.env['pos.order'].sync_from_ui([
            self._build_sync_order_payload(session, self.table_1, order_uuid=bill_1_uuid, state='paid', booking=split_booking, lines=bill_1_lines),
        ])
        bill_1 = self.env['pos.order'].search([('uuid', '=', bill_1_uuid)], limit=1)
        self.assertEqual(bill_1.state, 'paid')
        self.assertEqual(split_booking.state, 'checked_in', "Booking must stay checked_in while a split bill remains open")

        # Pay second (last) split bill -> booking now checks out automatically
        self.env['pos.order'].sync_from_ui([
            self._build_sync_order_payload(session, self.table_1, order_uuid=bill_2_uuid, state='paid', booking=split_booking, lines=bill_2_lines),
        ])
        self.assertEqual(bill_2.state, 'paid')
        self.assertEqual(split_booking.state, 'checked_out', "Booking must auto-release once the last split bill is paid")

        # Refund order guard on table_2
        active_booking = self.env['appointment.booking'].create({
            'appointment_type_id': self.appt_type.id,
            'partner_id': self.partner.id,
            'resource_ids': [(6, 0, [self.res_table_2.id])],
            'party_size': 2,
            'start_datetime': now - timedelta(minutes=10),
            'end_datetime': now + timedelta(minutes=110),
            'state': 'checked_in',
            'pos_config_id': self.pos_config.id,
        })
        price = -self.dish_product.lst_price
        refund_lines = [[0, 0, {
            'price_unit': self.dish_product.lst_price,
            'product_id': self.dish_product.id,
            'price_subtotal': price,
            'price_subtotal_incl': price,
            'qty': -1,
            'tax_ids': [],
            'uuid': str(uuid.uuid4()),
        }]]
        refund_payments = [[0, 0, {
            'amount': price,
            'payment_method_id': self.bank_payment_method.id,
            'payment_date': fields.Datetime.to_string(now),
            'uuid': str(uuid.uuid4()),
        }]]
        self.env['pos.order'].sync_from_ui([
            self._build_sync_order_payload(
                session,
                self.table_2,
                order_uuid=str(uuid.uuid4()),
                state='paid',
                booking=active_booking,
                lines=refund_lines,
                amount_total=price,
                amount_paid=price,
                payment_ids=refund_payments,
                is_refund=True,
            ),
        ])
        self.assertEqual(active_booking.state, 'checked_in', "A refund POS order must never check out an active guest")

    def test_no_custom_release_buttons_in_pos_templates_and_js(self):
        """Custom Release/Release Table buttons and manual handlers must stay completely removed."""
        mod_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        xml_paths = [
            os.path.join(mod_root, 'static', 'src', 'xml', 'floor_plan_booking_badge.xml'),
            os.path.join(mod_root, 'static', 'src', 'xml', 'booking_screen.xml'),
        ]
        for path in xml_paths:
            with open(path, encoding='utf-8') as f:
                raw_xml = f.read()
            self.assertNotIn('Table Released', raw_xml, f"'Table Released' UI tag must not appear in {path}")
            self.assertNotIn('pos-released-tag', raw_xml, f"'pos-released-tag' must not appear in {path}")
            tree = ET.parse(path)
            for btn in tree.getroot().iter('button'):
                btn_text = ' '.join(''.join(btn.itertext()).split()).lower()
                btn_attrs = ' '.join(f'{k}={v}' for k, v in btn.attrib.items()).lower()
                self.assertNotIn('release', btn_text, f"Custom release button text found in {path}: {btn_text}")
                self.assertNotIn('releasetable', btn_attrs, f"releaseTable action found in {path}: {btn_attrs}")
                self.assertNotIn('releasebookingtable', btn_attrs, f"releaseBookingTable found in {path}")
                self.assertNotIn('releasemodaltable', btn_attrs, f"releaseModalTable found in {path}")

        js_paths = [
            os.path.join(mod_root, 'static', 'src', 'js', 'booking_screen.js'),
            os.path.join(mod_root, 'static', 'src', 'js', 'pos_store_patch.js'),
        ]
        for path in js_paths:
            with open(path, encoding='utf-8') as f:
                src = f.read()
            self.assertNotIn('releaseBookingTable(', src)
            self.assertNotIn('releaseModalTable(', src)
            self.assertNotIn('releaseTable(', src)
