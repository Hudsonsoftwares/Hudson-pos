# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHelpdeskStage(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.Stage = cls.env['helpdesk.management.stage']
        cls.team = cls.env['helpdesk.management.team'].create({'name': 'Stage Team', 'auto_assignment': False})

    def test_default_team_from_context(self):
        stage = self.Stage.with_context(default_team_id=self.team.id).create({'name': 'Team Stage'})
        self.assertEqual(stage.team_ids, self.team)

    def test_ticket_count_and_open_tickets(self):
        stage = self.Stage.create({'name': 'Counted', 'sequence': 0, 'team_ids': [(6, 0, self.team.ids)]})
        self.env['helpdesk.management.ticket'].create([
            {'subject': 'T1', 'team_id': self.team.id, 'stage_id': stage.id},
            {'subject': 'T2', 'team_id': self.team.id, 'stage_id': stage.id},
        ])
        self.assertEqual(stage.ticket_count, 2)
        self.assertEqual(stage.action_open_tickets()['domain'], [('stage_id', '=', stage.id)])

    def test_archived_stage_not_proposed(self):
        stage = self.Stage.create({'name': 'Archived', 'sequence': -1, 'team_ids': [(6, 0, self.team.ids)]})
        stage.action_archive()
        ticket = self.env['helpdesk.management.ticket'].create({'subject': 'T', 'team_id': self.team.id})
        self.assertNotEqual(ticket.stage_id, stage)
        groups = self.env['helpdesk.management.ticket'].with_context(default_team_id=self.team.id)._read_group_stage_ids(
            self.Stage, [])
        self.assertNotIn(stage, groups)
