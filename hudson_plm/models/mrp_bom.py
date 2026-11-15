# -*- coding: utf-8 -*-
from odoo import models, fields, api

class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    version = fields.Integer('Version', default=1, copy=False)
    eco_count = fields.Integer('ECO Count', compute='_compute_eco_count')
    version_count = fields.Integer('Version Count', compute='_compute_version_count')

    def write(self, vals):
        res = super().write(vals)
        if {'bom_line_ids', 'operation_ids'} & set(vals):
            # Keep the change tabs of open ECOs in sync with their BoMs (sudo: MRP users
            # without PLM rights may edit BoMs too)
            ecos = self.env['mrp.eco'].sudo().search([
                '|', ('bom_id', 'in', self.ids), ('new_bom_id', 'in', self.ids),
                ('is_applied', '=', False),
            ])
            ecos._compute_eco_changes()
        return res

    def _compute_version_count(self):
        for bom in self:
            bom.version_count = self.env['mrp.bom'].with_context(active_test=False).search_count([
                ('product_tmpl_id', '=', bom.product_tmpl_id.id)
            ])
    
    def _compute_eco_count(self):
        for bom in self:
            ecos = self.env['mrp.eco'].search(['|', ('bom_id', '=', bom.id), ('new_bom_id', '=', bom.id)])
            bom.eco_count = len(ecos)

    def action_view_ecos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'ECOs',
            'res_model': 'mrp.eco',
            'view_mode': 'list,form',
            'domain': ['|', ('bom_id', '=', self.id), ('new_bom_id', '=', self.id)],
            'context': {'default_bom_id': self.id, 'default_product_tmpl_id': self.product_tmpl_id.id},
        }

    def action_view_versions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Version History',
            'res_model': 'mrp.bom',
            'view_mode': 'list,form',
            'domain': [('product_tmpl_id', '=', self.product_tmpl_id.id)],
            'context': {
                'default_product_tmpl_id': self.product_tmpl_id.id,
                'active_test': False,
            },
        }

    def action_restore_version(self):
        for bom in self:
            # Find currently active BoMs for this product and archive them
            active_boms = self.env['mrp.bom'].search([
                ('product_tmpl_id', '=', bom.product_tmpl_id.id),
                ('id', '!=', bom.id)
            ])
            active_boms.write({'active': False})
            # Unarchive this selected version
            bom.write({'active': True})
