# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models
import ast

class QualityTeam(models.Model):
    _name = 'quality.team'
    _description = 'Quality Team'
    _inherit = ['mail.alias.mixin', 'mail.thread']
    _order = 'sequence, name'

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Color Index')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)
    user_id = fields.Many2one(
        'res.users', string='Team Leader', tracking=True)
    member_ids = fields.Many2many(
        'res.users', string='Members')

    check_ids = fields.One2many('quality.check', 'team_id', string='Quality Checks')
    alert_ids = fields.One2many('quality.alert', 'team_id', string='Quality Alerts')

    check_count = fields.Integer(compute='_compute_counts')
    alert_count = fields.Integer(compute='_compute_counts')
    failed_check_count = fields.Integer(compute='_compute_counts')

    @api.depends('check_ids.quality_state', 'alert_ids')
    def _compute_counts(self):
        for team in self:
            if not team.id:
                team.check_count = 0
                team.failed_check_count = 0
                team.alert_count = 0
                continue
            team.check_count = self.env['quality.check'].search_count([('team_id', '=', team.id), ('quality_state', '=', 'none')])
            team.failed_check_count = self.env['quality.check'].search_count([('team_id', '=', team.id), ('quality_state', '=', 'fail')])
            team.alert_count = self.env['quality.alert'].search_count([('team_id', '=', team.id)])

    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get('quality.alert').id
        if self.id:
            values['alias_defaults'] = defaults = ast.literal_eval(self.alias_defaults or "{}")
            defaults['team_id'] = self.id
        return values

    def action_view_checks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'Quality.action_quality_check')
        action['domain'] = [('team_id', '=', self.id)]
        action['context'] = {'default_team_id': self.id, 'search_default_to_do': 1}
        return action

    def action_view_alerts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'Quality.action_quality_alert')
        action['domain'] = [('team_id', '=', self.id)]
        action['context'] = {'default_team_id': self.id}
        return action
