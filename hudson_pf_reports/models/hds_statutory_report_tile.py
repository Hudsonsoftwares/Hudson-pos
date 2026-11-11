# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class HdsStatutoryReportTile(models.Model):
    _name = 'hds.statutory.report.tile'
    _description = 'Statutory Report Hub Tile'
    _order = 'section, sequence, id'

    name = fields.Char(string='Report Title', required=True, translate=True)
    description = fields.Char(string='Description', translate=True)
    icon = fields.Char(string='FontAwesome Icon', default='fa-file-text-o', help="FontAwesome CSS class, e.g. fa-file-export")

    section = fields.Selection([
        ('filing', 'Statutory Filing'),
        ('contribution', 'Contribution'),
        ('analysis', 'Analysis'),
        ('compliance', 'Compliance & Audit'),
    ], string='Section', required=True, default='filing')

    featured = fields.Boolean(string='Featured / Mandatory Filing', default=False)
    action_id = fields.Many2one('ir.actions.actions', string='Report Action', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    country_code = fields.Char(string='Country Code', default='IN', required=True, index=True)

    def action_open_report(self):
        self.ensure_one()
        if not self.action_id:
            return {'type': 'ir.actions.act_window_close'}
        action_type = self.action_id.type
        return self.env[action_type].browse(self.action_id.id).read()[0]
