# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests import TransactionCase, tagged
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError

@tagged('post_install', '-at_install')
class TestHelpdeskTeam(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestHelpdeskTeam, cls).setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        
        cls.team = cls.env['helpdesk.management.team'].create({
            'name': 'Operations Team',
            'auto_assignment': False,
        })
        
        cls.user_1 = cls.env['res.users'].create({
            'name': 'Team Member 1',
            'login': 'member_1@test.com',
        })
        cls.user_2 = cls.env['res.users'].create({
            'name': 'Team Member 2',
            'login': 'member_2@test.com',
        })

    def test_01_team_assignment_method(self):
        """ Test team assignment configuration. """
        self.team.write({
            'auto_assignment': True,
            'assignment_method': 'random',
            'member_ids': [(6, 0, [self.user_1.id, self.user_2.id])]
        })
        self.assertTrue(self.team.auto_assignment, "Auto assignment should be enabled.")
        self.assertEqual(self.team.assignment_method, 'random', "Assignment method should be random.")
        self.assertEqual(len(self.team.member_ids), 2, "Team should have 2 members.")

    def test_02_team_visibility(self):
        """ Test team visibility configuration. """
        self.team.write({
            'visibility': 'invited',
            'message_follower_ids': [(0, 0, {'res_model': 'helpdesk.management.team', 'partner_id': self.user_1.partner_id.id})]
        })
        self.assertEqual(self.team.visibility, 'invited', "Visibility should be set to invited.")

    def test_03_dashboard_metrics_structure(self):
        """ Test get_dashboard_metrics() contract and structure matches OWL component expectations """
        metrics = self.env['helpdesk.management.team'].get_dashboard_metrics()
        expected_keys = [
            'my_tickets', 'high_priority', 'urgent', 'open_tickets',
            'avg_open_hours', 'hp_avg_open_hours', 'urg_avg_open_hours',
            'failed_tickets', 'hp_failed_tickets', 'urg_failed_tickets',
            'closed_tickets', 'sla_success_rate', 'sla_success_rate_7d',
            'average_rating', 'average_rating_7d', 'today', 'avg_last_7_days',
            'target_closed', 'target_success', 'target_rating',
        ]
        for key in expected_keys:
            self.assertIn(key, metrics, f"Dashboard metrics missing expected key '{key}'")

    def test_03b_dashboard_targets(self):
        """ Daily targets are per user, unset (0) by default, saved in database and clamped to their range """
        agent = self.env['res.users'].create({
            'name': 'Helpdesk Agent',
            'login': 'helpdesk_agent@test.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('helpdesk_management_pro.group_helpdesk_user').id])],
        })
        Team = self.env['helpdesk.management.team'].with_user(agent)
        metrics = Team.get_dashboard_metrics()
        self.assertEqual(
            (metrics['target_closed'], metrics['target_success'], metrics['target_rating']), (0, 0.0, 0.0),
            "A new user should have no dashboard target set")

        self.assertEqual(Team.set_dashboard_target('closed', 7.6), 7)
        self.assertEqual(Team.set_dashboard_target('success', 150), 100.0)
        self.assertEqual(Team.set_dashboard_target('rating', -2), 0.0)
        self.assertEqual(Team.set_dashboard_target('rating', 4.2), 4.2)
        metrics = Team.get_dashboard_metrics()
        self.assertEqual(
            (metrics['target_closed'], metrics['target_success'], metrics['target_rating']), (7, 100.0, 4.2))
        self.assertEqual(agent.helpdesk_target_closed, 7)
        self.assertEqual(self.env.user.helpdesk_target_closed, 0, "Targets of other users are not changed")
        with self.assertRaises(ValueError):
            Team.set_dashboard_target('unknown', 1)

    def test_04_multi_company_ticket_isolation(self):
        """ Test ticket multi-company record isolation """
        company_2 = self.env['res.company'].create({'name': 'Secondary Support Corp'})
        ticket_c1 = self.env['helpdesk.management.ticket'].create({
            'subject': 'Company 1 Ticket',
            'company_id': self.env.company.id,
            'team_id': self.team.id,
        })
        team_c2 = self.env['helpdesk.management.team'].create({
            'name': 'Company 2 Team',
            'company_id': company_2.id,
        })
        ticket_c2 = self.env['helpdesk.management.ticket'].create({
            'subject': 'Company 2 Ticket',
            'company_id': company_2.id,
            'team_id': team_c2.id,
        })

        self.user_1.write({
            'company_ids': [(6, 0, [self.env.company.id])],
            'company_id': self.env.company.id,
            'group_ids': [(4, self.env.ref('helpdesk_management_pro.group_helpdesk_user').id)],
        })
        self.team.write({
            'member_ids': [(4, self.user_1.id)],
        })

        # When searching with a user belonging to company 1, company 2 tickets should be isolated by multi-company rule
        tickets_c1 = self.env['helpdesk.management.ticket'].with_user(self.user_1).search([])
        self.assertIn(ticket_c1, tickets_c1)
        self.assertNotIn(ticket_c2, tickets_c1)

    def test_05_timesheet_and_rating_tabs(self):
        """ Test timesheet logging, total_time accumulation, and rating computation """
        self.team.use_helpdesk_timesheet = True
        self.team.use_rating = True
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Timesheet Ticket',
            'team_id': self.team.id,
        })
        self.assertTrue(ticket.use_helpdesk_timesheet)
        self.assertTrue(ticket.use_rating)

        # Log timesheet entries
        self.env['helpdesk.management.ticket.time'].create({
            'ticket_id': ticket.id,
            'description': 'Initial diagnosis',
            'duration': 1.5,
        })
        self.env['helpdesk.management.ticket.time'].create({
            'ticket_id': ticket.id,
            'description': 'Resolution implementation',
            'duration': 2.0,
        })
        ticket.invalidate_recordset(['time_ids', 'total_time'])
        self.assertEqual(ticket.total_time, 3.5, "Total time should equal sum of durations")

        # Log ratings
        self.env['helpdesk.management.ticket.rating'].create({
            'ticket_id': ticket.id,
            'rating': '5',
            'feedback': 'Great service!',
        })
        self.env['helpdesk.management.ticket.rating'].create({
            'ticket_id': ticket.id,
            'rating': '3',
            'feedback': 'Average speed',
        })
        ticket.invalidate_recordset(['ticket_rating_ids', 'average_rating'])
        self.assertEqual(ticket.average_rating, 4.0, "Average rating should be computed correctly")

    def test_06_dashboard_settings_opens_team_form(self):
        """ The Settings entry of a dashboard card opens the settings form of that team """
        action = self.team.action_open_team_settings()
        self.assertEqual(action['res_model'], 'helpdesk.management.team')
        self.assertEqual(action['res_id'], self.team.id)
        self.assertEqual(action['views'][0][1], 'form')

    def test_07_team_tickets_action_shows_team_name(self):
        """ Opening the tickets of a team (kanban card, Tickets button) titles the view with the team name """
        other_team = self.env['helpdesk.management.team'].create({'name': 'Other Team'})
        ticket = self.env['helpdesk.management.ticket'].create({'subject': 'Team ticket', 'team_id': self.team.id})
        self.env['helpdesk.management.ticket'].create({'subject': 'Other ticket', 'team_id': other_team.id})

        action = self.team.action_view_tickets()
        self.assertEqual(action['name'], 'Operations Team')
        self.assertEqual(action['display_name'], 'Operations Team')
        self.assertEqual(action['res_model'], 'helpdesk.management.ticket')
        self.assertEqual(action['context']['default_team_id'], self.team.id)
        self.assertEqual(self.env['helpdesk.management.ticket'].search(action['domain']), ticket)

    def test_08_dashboard_performance_figures(self):
        """ "My Performance" sends the raw figures compared to the daily targets (colouring) """
        Team = self.env['helpdesk.management.team']
        before = Team.get_dashboard_metrics()['performance']
        self.assertIsNone(before['rating_today'], "No rating: nothing to compare, no colour")
        closed_stage = self.env['helpdesk.management.stage'].search([('is_close', '=', True)], limit=1)
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Closed today', 'team_id': self.team.id, 'user_id': self.env.uid})
        ticket.stage_id = closed_stage
        perf = Team.get_dashboard_metrics()['performance']
        self.assertEqual(perf['closed_today'], before['closed_today'] + 1)
        self.assertEqual(perf['closed_7d'], round((before['closed_7d'] * 7 + 1) / 7.0, 1))
