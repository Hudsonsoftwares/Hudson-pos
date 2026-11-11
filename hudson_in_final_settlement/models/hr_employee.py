# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields, models, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    final_settlement_ids = fields.One2many(
        'final.settlement',
        'employee_id',
        string="Final Settlements"
    )
    final_settlement_count = fields.Integer(
        string="Final Settlement Count",
        compute='_compute_final_settlement_count'
    )

    def _compute_final_settlement_count(self):
        for rec in self:
            rec.final_settlement_count = len(rec.final_settlement_ids.filtered(lambda s: s.state != 'cancel'))

    def action_open_final_settlements(self):
        """Action for smart button on employee form to view final settlement."""
        self.ensure_one()
        settlements = self.final_settlement_ids.filtered(lambda s: s.state != 'cancel')
        if not settlements:
            return {
                'name': _('Final Settlement'),
                'type': 'ir.actions.act_window',
                'res_model': 'final.settlement',
                'view_mode': 'form',
                'context': {
                    'default_employee_id': self.id,
                    'default_company_id': self.company_id.id if self.company_id else False,
                },
                'target': 'current',
            }

        if len(settlements) == 1:
            return {
                'name': _('Final Settlement'),
                'type': 'ir.actions.act_window',
                'res_model': 'final.settlement',
                'res_id': settlements[0].id,
                'view_mode': 'form',
                'target': 'current',
            }

        return {
            'name': _('Final Settlements'),
            'type': 'ir.actions.act_window',
            'res_model': 'final.settlement',
            'domain': [('id', 'in', settlements.ids)],
            'view_mode': 'list,form',
            'target': 'current',
        }
