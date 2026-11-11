# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests import TransactionCase, tagged
# pyrefly: ignore [missing-import]
from odoo.fields import Datetime
from datetime import timedelta

@tagged('post_install', '-at_install')
class TestAutoAssignment(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super(TestAutoAssignment, cls).setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        
        # Create users
        cls.user_1 = cls.env['res.users'].create({
            'name': 'Agent One',
            'login': 'agent_1@test.com',
        })
        cls.user_2 = cls.env['res.users'].create({
            'name': 'Agent Two',
            'login': 'agent_2@test.com',
        })
        cls.user_3 = cls.env['res.users'].create({
            'name': 'Agent Three',
            'login': 'agent_3@test.com',
        })
        
        # Create tag mapping
        cls.tag_hardware = cls.env['helpdesk.management.tag'].create({
            'name': 'Hardware',
            'user_ids': [(6, 0, [cls.user_1.id, cls.user_2.id])]
        })
        cls.tag_software = cls.env['helpdesk.management.tag'].create({
            'name': 'Software',
            'user_ids': [(6, 0, [cls.user_3.id])]
        })
        
        # Create Team
        cls.team = cls.env['helpdesk.management.team'].create({
            'name': 'Support Team',
            'auto_assignment': True,
            'assignment_method': 'random',
            'member_ids': [(6, 0, [cls.user_1.id, cls.user_2.id, cls.user_3.id])]
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

    def test_01_random_assignment_total_tickets(self):
        """ Test random (Equal number of total tickets) """
        self.team.assignment_method = 'random'
        
        # Give user_1 and user_2 some tickets
        self.env['helpdesk.management.ticket'].create([
            {'subject': 'T1', 'team_id': self.team.id, 'user_id': self.user_1.id},
            {'subject': 'T2', 'team_id': self.team.id, 'user_id': self.user_1.id},
            {'subject': 'T3', 'team_id': self.team.id, 'user_id': self.user_2.id},
        ])
        
        # user_3 has 0 tickets, should be assigned next
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'T4',
            'team_id': self.team.id,
        })
        self.assertEqual(ticket.user_id, self.user_3, "Should assign to user with least total tickets (user_3)")
        
        # Now user_2 and user_3 have 1 ticket, user_1 has 2. Next should be user_2 or user_3.
        ticket2 = self.env['helpdesk.management.ticket'].create({
            'subject': 'T5',
            'team_id': self.team.id,
        })
        self.assertIn(ticket2.user_id.id, [self.user_2.id, self.user_3.id], "Should assign to user_2 or user_3")

    def test_02_balanced_assignment_open_tickets(self):
        """ Test balanced (Equal number of open tickets) """
        self.team.assignment_method = 'balanced'
        
        # user_1 has 2 open tickets, user_2 has 1 closed ticket (0 open)
        self.env['helpdesk.management.ticket'].create([
            {'subject': 'T1', 'team_id': self.team.id, 'user_id': self.user_1.id, 'stage_id': self.stage_new.id},
            {'subject': 'T2', 'team_id': self.team.id, 'user_id': self.user_1.id, 'stage_id': self.stage_new.id},
            {'subject': 'T3', 'team_id': self.team.id, 'user_id': self.user_2.id, 'stage_id': self.stage_done.id},
            {'subject': 'T4', 'team_id': self.team.id, 'user_id': self.user_3.id, 'stage_id': self.stage_new.id},
        ])
        
        # user_2 has 0 open tickets, should be assigned
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'T5',
            'team_id': self.team.id,
        })
        self.assertEqual(ticket.user_id, self.user_2, "Should assign to user with least open tickets (user_2)")

    def test_03_tags_assignment(self):
        """ Test dispatch based on tags """
        self.team.assignment_method = 'tags'
        
        # Tag Hardware maps to user_1, user_2
        # Give user_1 2 open tickets, user_2 0 open tickets
        self.env['helpdesk.management.ticket'].create([
            {'subject': 'T1', 'team_id': self.team.id, 'user_id': self.user_1.id, 'stage_id': self.stage_new.id},
            {'subject': 'T2', 'team_id': self.team.id, 'user_id': self.user_1.id, 'stage_id': self.stage_new.id},
        ])
        
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'HW Issue',
            'team_id': self.team.id,
            'tag_ids': [(6, 0, [self.tag_hardware.id])]
        })
        # Between user_1 and user_2, user_2 has fewer open tickets
        self.assertEqual(ticket.user_id, self.user_2, "Should assign to user_2 based on tags and least open tickets")

    def test_04_tags_assignment_no_match(self):
        """ Test tags assignment with no matching tag/user """
        self.team.assignment_method = 'tags'
        
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'No Tag Issue',
            'team_id': self.team.id,
        })
        self.assertFalse(ticket.user_id, "Ticket should remain unassigned if no matching tag users")

    def test_05_manual_assignment_override(self):
        """ Test manual assignment does not get overwritten """
        self.team.assignment_method = 'random'
        
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Manual',
            'team_id': self.team.id,
            'user_id': self.user_3.id
        })
        self.assertEqual(ticket.user_id, self.user_3, "Manual assignment should be preserved")
        self.assertTrue(ticket.is_manually_assigned, "Flag should be set")

    def test_06_unavailability(self):
        """ Test skipping unavailable users """
        self.team.assignment_method = 'random'
        
        # Ensure user_3 is normally chosen first (lowest count)
        self.env['helpdesk.management.ticket'].create([
            {'subject': 'T1', 'team_id': self.team.id, 'user_id': self.user_1.id},
            {'subject': 'T2', 'team_id': self.team.id, 'user_id': self.user_2.id},
        ])
        
        # Make user_3 unavailable by creating a leave
        calendar = self.env['resource.calendar'].create({'name': 'Test Cal'})
        resource = self.env['resource.resource'].create({
            'name': 'User 3 Resource',
            'user_id': self.user_3.id,
            'calendar_id': calendar.id,
        })
        self.user_3.resource_ids = [(4, resource.id)]
        
        now = Datetime.now()
        self.env['resource.calendar.leaves'].create({
            'name': 'Sick Leave',
            'resource_id': resource.id,
            'calendar_id': calendar.id,
            'date_from': now - timedelta(hours=1),
            'date_to': now + timedelta(hours=8),
        })
        
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'T3',
            'team_id': self.team.id,
        })
        
        self.assertNotEqual(ticket.user_id, self.user_3, "Should skip user_3 because they are on leave")
        self.assertIn(ticket.user_id.id, [self.user_1.id, self.user_2.id], "Should assign to user_1 or user_2")
