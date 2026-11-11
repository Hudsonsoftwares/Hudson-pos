# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged
from odoo.fields import Datetime
from datetime import timedelta

@tagged('post_install', '-at_install')
class TestHelpdeskTicket(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestHelpdeskTicket, cls).setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        
        cls.team = cls.env['helpdesk.management.team'].create({
            'name': 'Test Support Team',
            'auto_assignment': False,
        })
        
        cls.stage_new = cls.env['helpdesk.management.stage'].create({
            'name': 'New',
            'sequence': 1,
            'is_close': False
        })
        cls.stage_done = cls.env['helpdesk.management.stage'].create({
            'name': 'Done',
            'sequence': 10,
            'is_close': True
        })
        
        cls.project = cls.env['project.project'].create({'name': 'Test Project'})

    def test_01_ticket_creation_defaults(self):
        """ Test ticket is created with proper defaults. """
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Test Ticket',
            'team_id': self.team.id,
        })
        self.assertTrue(ticket.name, "Ticket name should be generated.")
        self.assertEqual(ticket.stage_id.name, 'New', "Default stage should be 'New'.")
        self.assertEqual(ticket.priority, '0', "Default priority should be Low ('0').")

    def test_02_stage_progression_close_date(self):
        """ Test that moving to a closed stage sets the close_date. """
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Stage Test',
            'team_id': self.team.id,
            'stage_id': self.stage_new.id,
        })
        self.assertFalse(ticket.close_date, "Close date should be empty initially.")
        
        ticket.write({'stage_id': self.stage_done.id})
        self.assertTrue(ticket.close_date, "Close date should be set when moved to a closed stage.")

    def test_03_compute_methods(self):
        """ Test count updates for tasks and field service orders. """
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Compute Test',
            'team_id': self.team.id,
        })
        
        # Test Task count
        task = self.env['project.task'].create({
            'name': 'Test Task',
            'helpdesk_ticket_id': ticket.id,
            'project_id': self.project.id,
        })
        ticket._compute_task_count()
        self.assertEqual(ticket.task_count, 1, "Task count should be 1.")

    def test_04_auto_close_cron(self):
        """ Test the auto close cron job for inactive tickets. """
        self.team.write({
            'use_auto_close': True,
            'auto_close_ticket_days': 7,
            'auto_close_stage_id': self.stage_done.id,
        })
        
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Old Ticket',
            'team_id': self.team.id,
            'stage_id': self.stage_new.id,
        })
        
        # Manually backdate the last stage change (inactivity reference)
        old_date = Datetime.now() - timedelta(days=10)
        self.env.cr.execute(
            "UPDATE helpdesk_management_ticket SET date_last_stage_update = %s WHERE id = %s",
            (old_date, ticket.id)
        )
        ticket.invalidate_recordset(['date_last_stage_update'])
        
        # Run cron
        self.env['helpdesk.management.ticket']._cron_auto_close_tickets()
        
        self.assertEqual(ticket.stage_id.id, self.stage_done.id, "Ticket should be auto-closed.")

    def test_05_integration_hooks(self):
        """ Test Livechat and WhatsApp integration hooks. """
        partner = self.env['res.partner'].create({
            'name': 'Livechat Visitor',
            'email': 'visitor@example.com',
            'phone': '+15551234567',
        })
        self.team.use_livechat = True

        # Livechat with automatic partner email matching and team routing
        lc_data = {
            'subject': 'Help with Checkout',
            'transcript': 'Customer: My payment failed.\nAgent: Looking into it.',
            'partner_email': 'visitor@example.com',
        }
        lc_ticket = self.env['helpdesk.management.ticket'].create_ticket_from_livechat(lc_data)
        self.assertTrue(lc_ticket, "Livechat ticket should be created.")
        self.assertEqual(lc_ticket.subject, 'Help with Checkout')
        self.assertEqual(lc_ticket.partner_id.id, partner.id, "Partner should be matched by email.")
        self.assertEqual(lc_ticket.team_id.id, self.team.id, "Ticket should route to livechat team.")
        
        # WhatsApp with automatic partner phone matching
        wa_data = {
            'subject': 'Order Inquiry',
            'message': 'Where is my delivery?',
            'phone': '+15551234567',
            'team_id': self.team.id,
        }
        wa_ticket = self.env['helpdesk.management.ticket'].create_ticket_from_whatsapp(wa_data)
        self.assertTrue(wa_ticket, "WhatsApp ticket should be created.")
        self.assertEqual(wa_ticket.subject, 'Order Inquiry')
        self.assertEqual(wa_ticket.partner_id.id, partner.id, "Partner should be matched by phone.")
        self.assertEqual(wa_ticket.partner_phone, '+15551234567')

    def test_06_assign_date_tracking(self):
        """ Test that assign_date is set on first assignment and not overwritten. """
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Assign Date Test',
            'team_id': self.team.id,
        })
        self.assertFalse(ticket.assign_date, "assign_date should be False initially.")

        # Assign user
        user1 = self.env.ref('base.user_admin')
        user2 = self.env.ref('base.user_demo', raise_if_not_found=False) or user1
        ticket.write({'user_id': user1.id})
        first_assign = ticket.assign_date
        self.assertTrue(first_assign, "assign_date should be recorded on first assignment.")

        # Reassign to different user (or write again)
        ticket.write({'user_id': user2.id})
        self.assertEqual(ticket.assign_date, first_assign, "assign_date should not change on reassignment.")

    def test_07_action_reply_context(self):
        """ Test action_reply returns chatter composer context with customer and subject. """
        partner = self.env['res.partner'].create({
            'name': 'Customer Test',
            'email': 'customer@example.com',
        })
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Login issue',
            'team_id': self.team.id,
            'partner_id': partner.id,
        })
        action = ticket.action_reply()
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(action.get('res_model'), 'mail.compose.message')
        ctx = action.get('context', {})
        self.assertEqual(ctx.get('default_composition_mode'), 'comment')
        self.assertEqual(ctx.get('default_subtype_xmlid'), 'mail.mt_comment')
        self.assertIn(partner.id, ctx.get('default_partner_ids', []))
        self.assertTrue(ctx.get('default_subject', '').startswith('Re:'))

    def test_08_stage_email_trigger_only_on_stage_change(self):
        """ Test stage email template is sent on stage change and not on other field writes. """
        mail_template = self.env['mail.template'].create({
            'name': 'Stage Done Template',
            'model_id': self.env.ref('helpdesk_management_pro.model_helpdesk_management_ticket').id,
            'subject': 'Ticket Done: {{ object.name }}',
            'body_html': '<p>Your ticket is completed.</p>',
        })
        self.stage_done.template_id = mail_template.id

        partner = self.env['res.partner'].create({
            'name': 'Jane Doe',
            'email': 'jane@example.com',
        })
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Stage Mail Test',
            'team_id': self.team.id,
            'stage_id': self.stage_new.id,
            'partner_id': partner.id,
        })

        # Count emails before changing priority
        msg_count_before = len(ticket.message_ids)
        ticket.write({'priority': '2'})
        self.assertEqual(len(ticket.message_ids), msg_count_before, "No stage email should send on priority change.")

        # Move to stage_done
        ticket.write({'stage_id': self.stage_done.id})
        # After moving to stage with template, message should be posted
        self.assertGreater(len(ticket.message_ids), msg_count_before, "Stage template message should be posted.")

    def test_09_auto_close_reminder_and_closure(self):
        """ Test that inactive tickets receive reminder email before being auto-closed """
        reminder_template = self.env['mail.template'].create({
            'name': 'Reminder Template',
            'model_id': self.env.ref('helpdesk_management_pro.model_helpdesk_management_ticket').id,
            'subject': 'Inactivity Reminder: {{ object.name }}',
            'body_html': '<p>Your ticket will be closed soon.</p>',
        })
        self.team.write({
            'use_auto_close': True,
            'auto_close_ticket_days': 7,
            'auto_close_stage_id': self.stage_done.id,
            'use_auto_close_reminder': True,
            'auto_close_reminder_days': 2,
            'auto_close_reminder_template_id': reminder_template.id,
        })

        partner = self.env['res.partner'].create({
            'name': 'Inactive User',
            'email': 'inactive@example.com',
        })
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Ticket Needing Reminder',
            'team_id': self.team.id,
            'stage_id': self.stage_new.id,
            'partner_id': partner.id,
        })

        # Backdate the last stage change to 5.5 days ago (between 5 and 7 days -> reminder window)
        reminder_date = Datetime.now() - timedelta(days=5, hours=12)
        self.env.cr.execute(
            "UPDATE helpdesk_management_ticket SET date_last_stage_update = %s WHERE id = %s",
            (reminder_date, ticket.id)
        )
        ticket.invalidate_recordset(['date_last_stage_update'])

        # First cron run: should send reminder and NOT close
        self.env['helpdesk.management.ticket']._cron_auto_close_tickets()
        ticket.invalidate_recordset(['auto_close_reminder_sent', 'stage_id'])
        self.assertTrue(ticket.auto_close_reminder_sent, "Reminder flag should be True after reminder sent.")
        self.assertEqual(ticket.stage_id.id, self.stage_new.id, "Ticket should NOT be closed yet.")

        # Backdate the last stage change to 8 days ago (> 7 days -> closure window)
        close_date = Datetime.now() - timedelta(days=8)
        self.env.cr.execute(
            "UPDATE helpdesk_management_ticket SET date_last_stage_update = %s WHERE id = %s",
            (close_date, ticket.id)
        )
        ticket.invalidate_recordset(['date_last_stage_update'])

        # Second cron run: should close ticket
        self.env['helpdesk.management.ticket']._cron_auto_close_tickets()
        ticket.invalidate_recordset(['stage_id'])
        self.assertEqual(ticket.stage_id.id, self.stage_done.id, "Ticket should be closed past auto_close_ticket_days.")

    def test_10_customer_portal_close(self):
        """ Test customer portal closure updates stage to closed and posts comment """
        self.team.use_closure_by_customer = True
        partner = self.env['res.partner'].create({
            'name': 'Portal Customer',
            'email': 'portal@example.com',
        })
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Portal Close Test',
            'team_id': self.team.id,
            'stage_id': self.stage_new.id,
            'partner_id': partner.id,
        })
        self.assertFalse(ticket.stage_id.is_close)

        from odoo.addons.helpdesk_management_pro.controllers.portal import HelpdeskManagementPortal
        portal_ctrl = HelpdeskManagementPortal()
        portal_ctrl._test_env = self.env

        # Simulate portal close with valid access token
        portal_ctrl.portal_my_ticket_close(ticket_id=ticket.id, access_token=ticket.access_token)
        ticket.invalidate_recordset(['stage_id', 'message_ids'])
        self.assertTrue(ticket.stage_id.is_close, "Ticket stage should be closed after portal closure.")
        chatter_bodies = [m.body for m in ticket.message_ids]
        self.assertTrue(any('closed by the customer via portal' in (b or '').lower() for b in chatter_bodies),
                        "Chatter message should be logged for customer closure.")

    def test_11_rating_gate_and_deduplication(self):
        """ Test rating endpoint respects team.use_rating and avoids duplicate ratings """
        partner = self.env['res.partner'].create({
            'name': 'Rating Customer',
            'email': 'rating@example.com',
        })
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Rating Gate Test',
            'team_id': self.team.id,
            'stage_id': self.stage_new.id,
            'partner_id': partner.id,
        })

        from odoo.addons.helpdesk_management_pro.controllers.portal import HelpdeskManagementPortal
        portal_ctrl = HelpdeskManagementPortal()
        portal_ctrl._test_env = self.env

        # 1. Team has use_rating = False
        self.team.use_rating = False
        res = portal_ctrl.helpdesk_rating(ticket_id=ticket.id, token=ticket.access_token, rating=5)
        # Should return 404
        self.assertEqual(getattr(res, 'status_code', None) or res.get('status', 404), 404)
        self.assertEqual(len(ticket.ticket_rating_ids), 0, "No rating should be created when use_rating=False.")

        # 2. Team has use_rating = True
        self.team.use_rating = True
        portal_ctrl.helpdesk_rating(ticket_id=ticket.id, token=ticket.access_token, rating=5)
        ticket.invalidate_recordset(['ticket_rating_ids'])
        self.assertEqual(len(ticket.ticket_rating_ids), 1, "Rating should be recorded.")
        self.assertEqual(ticket.ticket_rating_ids[0].rating, '5')

        # 3. Second rating submission from same ticket/token updates rather than duplicates
        portal_ctrl.helpdesk_rating(ticket_id=ticket.id, token=ticket.access_token, rating=1)
        ticket.invalidate_recordset(['ticket_rating_ids'])
        self.assertEqual(len(ticket.ticket_rating_ids), 1, "Duplicate rating should be updated, not appended.")
        self.assertEqual(ticket.ticket_rating_ids[0].rating, '1', "Rating should be updated to new value.")



    def test_receipt_email_is_queued_not_sent_during_save(self):
        """ Creating a ticket must not wait for the SMTP server: the receipt is queued and the mail
        queue cron triggered, so the email is sent in the background """
        team = self.env['helpdesk.management.team'].create({'name': 'Receipt Team', 'use_ticket_receipt': True})
        customer = self.env['res.partner'].create({'name': 'Receipt Customer', 'email': 'receipt.customer@example.com'})
        mail_cron = self.env.ref('mail.ir_cron_mail_scheduler_action')
        triggers_before = self.env['ir.cron.trigger'].search_count([('cron_id', '=', mail_cron.id)])
        ticket = self.env['helpdesk.management.ticket'].with_context(website_id=1).create({
            'subject': 'Queued receipt', 'team_id': team.id, 'partner_id': customer.id,
        })
        mails = self.env['mail.mail'].search([('model', '=', ticket._name), ('res_id', '=', ticket.id)])
        self.assertTrue(mails, "A receipt email is created")
        self.assertEqual(set(mails.mapped('state')), {'outgoing'}, "The receipt waits in the queue, it is not sent during the save")
        self.assertGreater(self.env['ir.cron.trigger'].search_count([('cron_id', '=', mail_cron.id)]), triggers_before,
                           "The mail queue is processed right away in the background")
