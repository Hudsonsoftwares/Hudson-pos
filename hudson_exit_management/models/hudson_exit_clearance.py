# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HudsonExitClearance(models.Model):
    """
    Department Clearance Checklist Item for Employee Offboarding.
    Tracks IT, Finance, Admin, and HR sign-offs.
    """
    _name = 'hudson.exit.clearance'
    _description = 'Department Exit Clearance'
    _order = 'sequence, id'

    resignation_id = fields.Many2one(
        'hr.resignation',
        string='Resignation',
        required=True,
        ondelete='cascade'
    )
    sequence = fields.Integer(string='Sequence', default=10)
    department_type = fields.Selection([
        ('it', 'IT & Infrastructure'),
        ('finance', 'Finance & Accounts'),
        ('admin', 'Administration & Facilities'),
        ('hr', 'Human Resources'),
        ('other', 'Other Department'),
    ], string='Department', required=True, default='it')

    name = fields.Char(string='Clearance Area', required=True)
    description = fields.Text(string='Checklist Items / Instructions')
    responsible_user_id = fields.Many2one(
        'res.users',
        string='Cleared By'
    )
    clearance_date = fields.Date(string='Clearance Date')
    state = fields.Selection([
        ('pending', 'Pending'),
        ('cleared', 'Cleared'),
        ('rejected', 'Issues / Hold'),
    ], string='Status', default='pending', required=True)
    remarks = fields.Text(string='Comments / Pending Items')

    def action_mark_cleared(self):
        for rec in self:
            rec.write({
                'state': 'cleared',
                'responsible_user_id': self.env.user.id,
                'clearance_date': fields.Date.today()
            })

    def action_mark_rejected(self):
        for rec in self:
            rec.write({
                'state': 'rejected',
                'responsible_user_id': self.env.user.id,
                'clearance_date': fields.Date.today()
            })

    def action_reset_pending(self):
        for rec in self:
            rec.write({
                'state': 'pending',
                'responsible_user_id': False,
                'clearance_date': False
            })
