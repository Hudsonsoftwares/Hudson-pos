# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests import TransactionCase, new_test_user, tagged
# pyrefly: ignore [missing-import]
from odoo.fields import Datetime
from datetime import timedelta


@tagged('post_install', '-at_install')
class TestHelpdeskAuditFixes(TransactionCase):
    """ Regression tests for the behaviours aligned on the standard (Enterprise) helpdesk. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.Ticket = cls.env['helpdesk.management.ticket']
        cls.team = cls.env['helpdesk.management.team'].create({'name': 'Audit Team', 'auto_assignment': False})
        cls.stage_new = cls.env['helpdesk.management.stage'].create({'name': 'Audit New', 'sequence': 0})
        cls.stage_done = cls.env['helpdesk.management.stage'].create({'name': 'Audit Done', 'sequence': 90, 'is_close': True})
        cls.customer_a = cls.env['res.partner'].create({'name': 'Customer A', 'email': 'a@example.com', 'phone': '111'})
        cls.customer_b = cls.env['res.partner'].create({'name': 'Customer B', 'email': 'b@example.com', 'phone': '222'})

    def test_email_alias_creates_ticket(self):
        """ The email subject is the ticket subject (not its number) and the sender is the customer. """
        ticket = self.Ticket.with_context(default_team_id=self.team.id).message_new({
            'subject': 'Printer is broken',
            'email_from': '"Bob Sender" <bob.sender@example.com>',
            'body': '<p>It does not print anymore.</p>',
        })
        self.assertEqual(ticket.subject, 'Printer is broken')
        self.assertNotEqual(ticket.name, 'Printer is broken', "The ticket number comes from the sequence.")
        self.assertEqual(ticket.team_id, self.team)
        self.assertEqual(ticket.partner_id.email, 'bob.sender@example.com')
        self.assertEqual(ticket.partner_email, 'bob.sender@example.com')
        self.assertIn(ticket.partner_id, ticket.message_partner_ids, "The customer follows the ticket.")

    def test_customer_change_updates_contact_details(self):
        ticket = self.Ticket.create({'subject': 'Contact', 'team_id': self.team.id, 'partner_id': self.customer_a.id})
        self.assertEqual(ticket.partner_email, 'a@example.com')
        ticket.partner_id = self.customer_b
        self.assertEqual(ticket.partner_email, 'b@example.com', "The email of the previous customer must not be kept.")
        self.assertEqual(ticket.partner_phone, '222')
        self.assertIn(self.customer_b, ticket.message_partner_ids)

    def test_ticket_starts_in_its_team_stage(self):
        other_team = self.env['helpdesk.management.team'].create({'name': 'Other Team'})
        own_stage = self.env['helpdesk.management.stage'].create({
            'name': 'Other Team Intake', 'sequence': -1, 'team_ids': [(4, other_team.id)]})
        ticket = self.Ticket.create({'subject': 'Stage', 'team_id': self.team.id})
        self.assertNotEqual(ticket.stage_id, own_stage, "A stage of another team must not be used.")
        other_ticket = self.Ticket.create({'subject': 'Stage', 'team_id': other_team.id})
        self.assertEqual(other_ticket.stage_id, own_stage)

    def test_assign_date_kept_on_multi_write(self):
        user = self.env.ref('base.user_admin')
        old_date = Datetime.now() - timedelta(days=3)
        assigned = self.Ticket.create({'subject': 'Assigned', 'team_id': self.team.id, 'user_id': user.id,
                                       'assign_date': old_date})
        unassigned = self.Ticket.create({'subject': 'Unassigned', 'team_id': self.team.id})
        (assigned | unassigned).write({'user_id': user.id})
        self.assertEqual(assigned.assign_date, old_date, "The first assignment date must be kept.")
        self.assertTrue(unassigned.assign_date)

    def test_close_date_kept_between_closing_stages(self):
        cancelled = self.env['helpdesk.management.stage'].create({'name': 'Audit Cancelled', 'sequence': 91, 'is_close': True})
        ticket = self.Ticket.create({'subject': 'Close', 'team_id': self.team.id, 'stage_id': self.stage_new.id})
        ticket.stage_id = self.stage_done
        closed_on = ticket.close_date
        self.assertTrue(closed_on)
        ticket.stage_id = cancelled
        self.assertEqual(ticket.close_date, closed_on)
        ticket.stage_id = self.stage_new
        self.assertFalse(ticket.close_date, "Reopening clears the close date.")

    def test_no_reassignment_on_edit(self):
        """ Like the standard helpdesk, tickets are dispatched on creation / team change only. """
        agent = new_test_user(self.env, login='audit_agent', groups='helpdesk_management_pro.group_helpdesk_user')
        self.team.write({'auto_assignment': True, 'member_ids': [(6, 0, agent.ids)]})
        ticket = self.Ticket.create({'subject': 'Dispatch', 'team_id': self.team.id})
        self.assertEqual(ticket.user_id, agent)
        self.assertFalse(ticket.is_manually_assigned, "An automatic assignment is not a manual one.")
        ticket.user_id = False
        ticket.priority = '2'
        self.assertFalse(ticket.user_id, "Editing the ticket must not reassign it.")

    def test_sla_reapplies_after_priority_reverted(self):
        sla = self.env['helpdesk.management.sla'].create({
            'name': 'Urgent', 'team_id': self.team.id, 'priority': '3',
            'stage_id': self.stage_done.id, 'target_hours': 4.0,
        })
        ticket = self.Ticket.create({'subject': 'SLA', 'team_id': self.team.id, 'priority': '3'})
        self.assertEqual(ticket.sla_status_ids.filtered(lambda s: s.sla_id == sla).status, 'ongoing')
        ticket.priority = '0'
        self.assertEqual(ticket.sla_status_ids.filtered(lambda s: s.sla_id == sla).status, 'cancelled')
        ticket.priority = '3'
        self.assertEqual(ticket.sla_status_ids.filtered(lambda s: s.sla_id == sla).status, 'ongoing',
                         "The policy applies again once the ticket matches it again.")

    def test_rating_request_needs_customer_ratings(self):
        rating_template = self.env.ref('helpdesk_management_pro.mail_template_ticket_review')
        self.stage_done.template_id = rating_template
        ticket = self.Ticket.create({'subject': 'Rating', 'team_id': self.team.id,
                                     'stage_id': self.stage_new.id, 'partner_id': self.customer_a.id})
        self.team.use_rating = False
        count = len(ticket.message_ids)
        ticket.stage_id = self.stage_done
        self.assertEqual(len(ticket.message_ids), count, "No rating request when the team does not collect ratings.")

        ticket.stage_id = self.stage_new
        self.team.use_rating = True
        ticket.stage_id = self.stage_done
        self.assertGreater(len(ticket.message_ids), count, "The rating request is sent and logged in the chatter.")

    def test_auto_close_reminder_does_not_restart_inactivity(self):
        self.team.write({
            'use_auto_close': True, 'auto_close_ticket_days': 7, 'auto_close_stage_id': self.stage_done.id,
            'use_auto_close_reminder': True, 'auto_close_reminder_days': 2,
        })
        ticket = self.Ticket.create({'subject': 'Idle', 'team_id': self.team.id, 'stage_id': self.stage_new.id,
                                     'partner_id': self.customer_a.id})
        self.env.cr.execute("UPDATE helpdesk_management_ticket SET date_last_stage_update = %s WHERE id = %s",
                            (Datetime.now() - timedelta(days=6), ticket.id))
        ticket.invalidate_recordset(['date_last_stage_update'])
        self.Ticket._cron_auto_close_tickets()
        self.assertTrue(ticket.auto_close_reminder_sent)
        # One more day without stage change: closed, although the reminder flag was just written
        self.env.cr.execute("UPDATE helpdesk_management_ticket SET date_last_stage_update = %s WHERE id = %s",
                            (Datetime.now() - timedelta(days=8), ticket.id))
        ticket.invalidate_recordset(['date_last_stage_update'])
        self.Ticket._cron_auto_close_tickets()
        self.assertEqual(ticket.stage_id, self.stage_done)

    def test_dashboard_counts_my_tickets(self):
        me = self.env.user
        other = new_test_user(self.env, login='audit_other', groups='helpdesk_management_pro.group_helpdesk_user')
        Team = self.env['helpdesk.management.team']
        before = Team.get_dashboard_metrics()['my_tickets']
        self.Ticket.create({'subject': 'Mine', 'team_id': self.team.id, 'user_id': me.id, 'stage_id': self.stage_new.id})
        self.Ticket.create({'subject': 'Not mine', 'team_id': self.team.id, 'user_id': other.id, 'stage_id': self.stage_new.id})
        self.assertEqual(Team.get_dashboard_metrics()['my_tickets'], before + 1)

    def test_ticket_access_rules(self):
        """ Portal customers only see (read-only) their tickets; private teams are restricted to their members. """
        portal_user = new_test_user(self.env, login='audit_portal', groups='base.group_portal')
        agent = new_test_user(self.env, login='audit_agent2', groups='helpdesk_management_pro.group_helpdesk_user')
        private_team = self.env['helpdesk.management.team'].create({
            'name': 'Private Team', 'visibility_member_type': 'internal'})
        own_ticket = self.Ticket.create({'subject': 'Own', 'team_id': self.team.id, 'partner_id': portal_user.partner_id.id})
        other_ticket = self.Ticket.create({'subject': 'Other', 'team_id': self.team.id, 'partner_id': self.customer_a.id})
        private_ticket = self.Ticket.create({'subject': 'Private', 'team_id': private_team.id})

        portal_tickets = self.Ticket.with_user(portal_user).search([('id', 'in', (own_ticket | other_ticket).ids)])
        self.assertEqual(portal_tickets, own_ticket, "A customer must not see the tickets of other customers.")
        self.assertFalse(own_ticket.with_user(portal_user).has_access('write'), "Customers cannot edit tickets directly.")

        agent_tickets = self.Ticket.with_user(agent).search([('id', 'in', (other_ticket | private_ticket).ids)])
        self.assertEqual(agent_tickets, other_ticket, "Tickets of private teams are restricted to their members.")
        private_team.member_ids = agent
        self.assertTrue(private_ticket.with_user(agent).has_access('read'))

    def _overdue_ticket(self, **vals):
        """ Ticket whose SLA deadline passed, before the SLA cron refreshed its stored sla_status. """
        self.env['helpdesk.management.sla'].search([('team_id', '=', self.team.id)]).unlink()
        self.env['helpdesk.management.sla'].create({
            'name': 'Overdue', 'team_id': self.team.id, 'stage_id': self.stage_done.id, 'target_hours': 1.0})
        ticket = self.Ticket.create(dict({'subject': 'Overdue', 'team_id': self.team.id,
                                          'stage_id': self.stage_new.id}, **vals))
        # Time passing: the deadline is behind us while nothing recomputed the stored status
        self.env.cr.execute("UPDATE helpdesk_management_sla_status SET deadline = %s WHERE ticket_id = %s",
                            (Datetime.now() - timedelta(hours=2), ticket.id))
        self.env.invalidate_all()
        self.assertNotEqual(ticket.sla_status, 'breached', "Precondition: the stored status is not refreshed yet.")
        return ticket

    def test_dashboard_failed_sla_is_live(self):
        Team = self.env['helpdesk.management.team']
        before = Team.get_dashboard_metrics()
        ticket = self._overdue_ticket(user_id=self.env.uid, priority='3')
        metrics = Team.get_dashboard_metrics()
        self.assertEqual(metrics['failed_tickets'], before['failed_tickets'] + 1)
        self.assertEqual(metrics['urg_failed_tickets'], before['urg_failed_tickets'] + 1)
        # The list opened from the figure contains exactly the counted tickets
        self.assertIn(ticket, self.Ticket.search(metrics['domains']['urg_failed']))
        self.assertEqual(self.Ticket.search_count(metrics['domains']['failed']), metrics['failed_tickets'])

    def test_team_card_failed_sla_is_live(self):
        ticket = self._overdue_ticket()
        self.team.invalidate_recordset(['failed_ticket_count'])
        self.assertEqual(self.team.failed_ticket_count, 1)
        self.assertIn(ticket, self.Ticket.search(self.team.action_view_failed_tickets()['domain']))

    def test_dashboard_periods_follow_user_timezone(self):
        from unittest.mock import patch
        self.env.user.tz = 'Asia/Kolkata'
        Team = self.env['helpdesk.management.team']
        # 01:00 in Kolkata is 19:30 UTC of the previous day
        with patch.object(Datetime, 'now', return_value=Datetime.to_datetime('2026-10-28 19:30:00')):
            today, last_7_days = Team._get_dashboard_periods()
        self.assertEqual(today, Datetime.to_datetime('2026-10-28 18:30:00'), "Today starts at local midnight.")
        self.assertEqual(last_7_days, Datetime.to_datetime('2026-10-22 18:30:00'), "7 days, today included.")
