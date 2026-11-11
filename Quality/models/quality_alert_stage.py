# -*- coding: utf-8 -*-
from odoo import fields, models  # pyrefly: ignore [missing-import]


class QualityAlertStage(models.Model):
    _name = 'quality.alert.stage'
    _description = 'Quality Alert Stage'
    _order = 'sequence, id'

    name = fields.Char(string='Stage Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    fold = fields.Boolean(
        string='Folded',
        help='Columns folded in the kanban view will be hidden by default.')
    done = fields.Boolean(
        string='Alert Processed',
        help='Alerts reaching a stage flagged as done are considered closed/resolved.')
    team_ids = fields.Many2many('quality.team', string='Teams')
    active = fields.Boolean(default=True)
