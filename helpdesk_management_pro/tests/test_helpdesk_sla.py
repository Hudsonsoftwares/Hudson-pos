# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError
# pyrefly: ignore [missing-import]
from odoo import fields

from unittest.mock import patch
from datetime import datetime, timedelta

class TestHelpdeskSLA(TransactionCase):
    # ... (setup is fine) ...
    def setUp(self):
        super(TestHelpdeskSLA, self).setUp()
        self.old_tz = self.env.company.tz
        self.env.company.tz = 'UTC'
        
        self.team = self.env['helpdesk.management.team'].create({
            'name': 'Support Team',
            'use_sla': True,
        })
        self.stage_new = self.env['helpdesk.management.stage'].create({
            'name': 'New',
            'team_ids': [(4, self.team.id)]
        })
        self.stage_progress = self.env['helpdesk.management.stage'].create({
            'name': 'In Progress',
            'team_ids': [(4, self.team.id)]
        })
        self.stage_wait = self.env['helpdesk.management.stage'].create({
            'name': 'Waiting for Customer',
            'team_ids': [(4, self.team.id)]
        })
        self.stage_solved = self.env['helpdesk.management.stage'].create({
            'name': 'Solved',
            'team_ids': [(4, self.team.id)],
            'is_close': True
        })
        
        # 40 Hours a week calendar
        self.calendar = self.env['resource.calendar'].create({
            'name': 'Standard 40 Hours',
            'attendance_ids': [
                (0, 0, {'dayofweek': '0', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'dayofweek': '0', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'}),
                (0, 0, {'dayofweek': '1', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'dayofweek': '1', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'}),
                (0, 0, {'dayofweek': '2', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'dayofweek': '2', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'}),
                (0, 0, {'dayofweek': '3', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'dayofweek': '3', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'}),
                (0, 0, {'dayofweek': '4', 'hour_from': 8, 'hour_to': 12, 'day_period': 'morning'}),
                (0, 0, {'dayofweek': '4', 'hour_from': 13, 'hour_to': 17, 'day_period': 'afternoon'}),
            ],
        })
        self.team.resource_calendar_id = self.calendar.id
        
        self.sla_policy = self.env['helpdesk.management.sla'].create({
            'name': 'First Response',
            'team_id': self.team.id,
            'stage_id': self.stage_progress.id,
            'target_hours': 4.0,
            'domain': "[('priority', '=', '0')]",
            'exclude_stage_ids': [(4, self.stage_wait.id)]
        })

    def tearDown(self):
        self.env.company.tz = self.old_tz
        super(TestHelpdeskSLA, self).tearDown()

    def _mock_now(self, dt_str):
        return datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')

    def test_sla_creation_normal_working_hours(self):
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:00:00')):
            ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Test Ticket',
                'team_id': self.team.id,
                'stage_id': self.stage_new.id,
                'priority': '0'
            })
            self.assertEqual(len(ticket.sla_status_ids), 1)
            sla_status = ticket.sla_status_ids[0]
            self.assertEqual(sla_status.status, 'ongoing')
            self.assertEqual(fields.Datetime.to_string(sla_status.deadline), '2026-09-07 12:00:00')

    def test_sla_creation_weekend(self):
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-05 10:00:00')):
            ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Test Weekend',
                'team_id': self.team.id,
                'stage_id': self.stage_new.id,
                'priority': '0'
            })
            sla_status = ticket.sla_status_ids[0]
            # 4 hours from Saturday -> Monday 12 PM
            self.assertEqual(fields.Datetime.to_string(sla_status.deadline), '2026-09-07 12:00:00')

    def test_excluded_stage_pause(self):
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:00:00')):
            ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Test Pause',
                'team_id': self.team.id,
                'stage_id': self.stage_new.id,
                'priority': '0'
            })
            
        sla_status = ticket.sla_status_ids[0]
        
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 09:00:00')):
            ticket.write({'stage_id': self.stage_wait.id})
            
        self.assertTrue(sla_status.is_paused)
        
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 11:00:00')):
            ticket.write({'stage_id': self.stage_new.id})
            
        self.assertFalse(sla_status.is_paused)
        # 2 hours paused. Old deadline was 12:00. New should be 15:00 (12:00 + 2h + 1h lunch).
        self.assertEqual(fields.Datetime.to_string(sla_status.deadline), '2026-09-07 15:00:00')

    def test_target_reached_before_deadline(self):
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:00:00')):
            ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Test Reach',
                'team_id': self.team.id,
                'stage_id': self.stage_new.id,
                'priority': '0'
            })
        
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 10:00:00')):
            ticket.write({'stage_id': self.stage_progress.id})
            
        self.assertEqual(ticket.sla_status_ids[0].status, 'reached')

    def test_target_reached_after_deadline(self):
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:00:00')):
            ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Test Fail',
                'team_id': self.team.id,
                'stage_id': self.stage_new.id,
                'priority': '0'
            })
            
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 13:00:00')):
            ticket.write({'stage_id': self.stage_progress.id})
            
        self.assertEqual(ticket.sla_status_ids[0].status, 'failed')

    def test_priority_change_cancellation(self):
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:00:00')):
            ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Test Priority Change',
                'team_id': self.team.id,
                'stage_id': self.stage_new.id,
                'priority': '0'
            })
            
        sla_status = ticket.sla_status_ids[0]
        self.assertEqual(sla_status.status, 'ongoing')
        
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 09:00:00')):
            ticket.write({'priority': '1'})
            
        self.assertEqual(sla_status.status, 'cancelled')

    def test_team_use_sla_gate(self):
        """ Test that when team.use_sla is False, no SLAs are computed """
        self.team.use_sla = False
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:00:00')):
            ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Test No SLA',
                'team_id': self.team.id,
                'stage_id': self.stage_new.id,
                'priority': '0'
            })
        self.assertEqual(len(ticket.sla_status_ids), 0, "No SLA status should be created when team.use_sla=False.")

    def test_sla_target_type_assign(self):
        """ Test SLA with target_type == 'assign' reaches when assigned before deadline """
        sla_assign = self.env['helpdesk.management.sla'].create({
            'name': 'Assign Time SLA',
            'team_id': self.team.id,
            'stage_id': self.stage_progress.id,
            'target_type': 'assign',
            'target_hours': 2.0,
            'domain': "[('priority', '=', '0')]",
        })
        user = self.env.ref('base.user_admin')
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:00:00')):
            ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Test Assign SLA',
                'team_id': self.team.id,
                'stage_id': self.stage_new.id,
                'priority': '0'
            })
        assign_status = ticket.sla_status_ids.filtered(lambda s: s.sla_id == sla_assign)
        self.assertTrue(assign_status)
        self.assertEqual(assign_status.status, 'ongoing')

        # Assign user at 09:00 (before 10:00 deadline)
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 09:00:00')):
            ticket.write({'user_id': user.id})

        self.assertEqual(assign_status.status, 'reached', "Assign target SLA should be reached when user is assigned.")

    def test_kanban_state_waiting_customer_pause(self):
        """ Test that setting kanban_state to 'waiting_customer' pauses the SLA timer """
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:00:00')):
            ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Test Kanban State Pause',
                'team_id': self.team.id,
                'stage_id': self.stage_new.id,
                'priority': '0'
            })
        sla_status = ticket.sla_status_ids[0]
        self.assertFalse(sla_status.is_paused)

        # Set waiting for customer at 09:00
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 09:00:00')):
            ticket.write({'kanban_state': 'waiting_customer'})
        self.assertTrue(sla_status.is_paused, "SLA should be paused when ticket is waiting for customer.")

        # Resume to normal at 11:00 (2h pause)
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 11:00:00')):
            ticket.write({'kanban_state': 'normal'})
        self.assertFalse(sla_status.is_paused, "SLA should resume when ticket returns to normal.")
        self.assertEqual(fields.Datetime.to_string(sla_status.deadline), '2026-09-07 15:00:00')


    def test_sla_tag_and_customer_criteria(self):
        """ SLA with tags/customers only applies to tickets having all tags and a matching customer """
        tag_vip = self.env['helpdesk.management.tag'].create({'name': 'VIP'})
        company = self.env['res.partner'].create({'name': 'Acme', 'is_company': True})
        contact = self.env['res.partner'].create({'name': 'Acme Contact', 'parent_id': company.id})
        sla_vip = self.env['helpdesk.management.sla'].create({
            'name': 'VIP Customers',
            'team_id': self.team.id,
            'stage_id': self.stage_progress.id,
            'target_hours': 2.0,
            'tag_ids': [(4, tag_vip.id)],
            'partner_ids': [(4, company.id)],
        })
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:00:00')):
            ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Test Tags',
                'team_id': self.team.id,
                'stage_id': self.stage_new.id,
                'partner_id': contact.id,
                'priority': '0',
            })
        self.assertNotIn(sla_vip, ticket.sla_tag_ids.sla_id, "SLA must not apply without the required tag.")

        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:30:00')):
            ticket.write({'tag_ids': [(4, tag_vip.id)]})
        self.assertIn(sla_vip, ticket.sla_tag_ids.sla_id, "SLA must apply once the ticket has the tag and a contact of the customer.")
        self.assertEqual(ticket.sla_tag_ids.filtered(lambda s: s.sla_id == sla_vip).display_name, 'VIP Customers')

        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 09:00:00')):
            ticket.write({'tag_ids': [(5, 0, 0)]})
        self.assertNotIn(sla_vip, ticket.sla_tag_ids.sla_id, "SLA must be removed when the tag is removed.")

    def test_sla_reached_by_later_stage_and_reopened(self):
        """ A later stage reaches the SLA; moving back before the target reopens it """
        self.stage_new.sequence = 1
        self.stage_progress.sequence = 2
        self.stage_wait.sequence = 3
        self.stage_solved.sequence = 4
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:00:00')):
            ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Test Later Stage',
                'team_id': self.team.id,
                'stage_id': self.stage_new.id,
                'priority': '0',
            })
            sla_status = ticket.sla_status_ids[0]
            self.assertEqual(sla_status.color, 0)

        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 09:00:00')):
            ticket.write({'stage_id': self.stage_solved.id})
        self.assertEqual(sla_status.status, 'reached')
        self.assertEqual(sla_status.color, 10)

        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 09:30:00')):
            ticket.write({'stage_id': self.stage_new.id})
        self.assertEqual(sla_status.status, 'ongoing')
        self.assertIn(sla_status, ticket.sla_tag_ids)

    def test_excluded_stage_does_not_reach_sla(self):
        """ An excluded (pause) stage placed after the target stage pauses the SLA instead of reaching it """
        self.stage_new.sequence = 1
        self.stage_progress.sequence = 2
        self.stage_wait.sequence = 3
        self.stage_solved.sequence = 4
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:00:00')):
            ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Test Hold', 'team_id': self.team.id, 'stage_id': self.stage_new.id, 'priority': '0',
            })
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 09:00:00')):
            ticket.write({'stage_id': self.stage_wait.id})
            sla_status = ticket.sla_status_ids[0]
            self.assertEqual(sla_status.status, 'ongoing', "Entering an excluded stage must not reach the SLA.")
            self.assertTrue(sla_status.is_paused)
            self.assertEqual(ticket.sla_status, 'on_track', "A paused SLA keeps the ticket on track.")

        # Reached, then put on hold: the SLA stays reached
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 09:30:00')):
            ticket.write({'stage_id': self.stage_progress.id})
            ticket.write({'stage_id': self.stage_wait.id})
        self.assertEqual(sla_status.status, 'reached')

    def test_failed_policy_breaches_ticket_and_report(self):
        """ A failed policy breaches the ticket even while another policy is ongoing, and the
        SLA Status Analysis reports each policy with its live status """
        sla_solve = self.env['helpdesk.management.sla'].create({
            'name': 'Solve', 'team_id': self.team.id, 'stage_id': self.stage_solved.id, 'target_hours': 40.0,
        })
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 08:00:00')):
            failed_ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'Late', 'team_id': self.team.id, 'stage_id': self.stage_new.id, 'priority': '0',
            })
            ok_ticket = self.env['helpdesk.management.ticket'].create({
                'subject': 'On time', 'team_id': self.team.id, 'stage_id': self.stage_new.id, 'priority': '0',
            })
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 09:00:00')):
            ok_ticket.write({'stage_id': self.stage_progress.id})
        with patch.object(fields.Datetime, 'now', return_value=self._mock_now('2026-09-07 13:00:00')):
            self.env['helpdesk.management.ticket']._cron_update_sla_status()
            first_response = failed_ticket.sla_status_ids.filtered(lambda s: s.sla_id == self.sla_policy)
            self.assertEqual(first_response.status, 'failed')
            self.assertEqual(failed_ticket.sla_status, 'breached',
                             "A failed policy breaches the ticket even though 'Solve' is still ongoing.")

        self.env.flush_all()
        Report = self.env['helpdesk.management.sla.report']
        lines = Report.search([('ticket_id', 'in', (failed_ticket | ok_ticket).ids)])
        status_by_key = {(l.ticket_id, l.sla_id): l.status for l in lines}
        self.assertEqual(status_by_key[(failed_ticket, self.sla_policy)], 'failed')
        self.assertEqual(status_by_key[(ok_ticket, self.sla_policy)], 'reached')
        # 'Solve' is ongoing in the records, but its deadline (one week after 2026-09-07) is long past now
        self.assertEqual(status_by_key[(ok_ticket, sla_solve)], 'failed', "Overdue SLAs are reported as failed live.")

        rate = Report._read_group([('ticket_id', 'in', (failed_ticket | ok_ticket).ids), ('sla_id', '=', self.sla_policy.id)],
                                  aggregates=['success_rate:avg'])[0][0]
        self.assertEqual(rate, 50.0)
