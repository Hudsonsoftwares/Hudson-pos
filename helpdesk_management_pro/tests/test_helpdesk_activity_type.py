# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestHelpdeskActivityType(TransactionCase):

    def test_manager_creates_ticket_activity_type(self):
        manager = new_test_user(self.env, login='hd_activity_manager',
                                groups='helpdesk_management_pro.group_helpdesk_manager')
        action = self.env.ref('helpdesk_management_pro.helpdesk_management_pro_action_activity_types')
        ActivityType = self.env['mail.activity.type'].with_user(manager).with_context(**eval(action.context))
        activity_type = ActivityType.create({'name': 'Call Customer', 'delay_count': 2})
        self.assertEqual(activity_type.res_model, 'helpdesk.management.ticket')

        team = self.env['helpdesk.management.team'].create({'name': 'Activity Team', 'auto_assignment': False})
        ticket = self.env['helpdesk.management.ticket'].create({'subject': 'Activity', 'team_id': team.id})
        activity = ticket.activity_schedule(activity_type_id=activity_type.id)
        self.assertEqual(activity.activity_type_id, activity_type)
        self.assertIn(activity_type, self.env['mail.activity.type'].search(eval(action.domain)))
