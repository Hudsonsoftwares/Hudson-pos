# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    eco_ids = fields.One2many('mrp.eco', 'product_tmpl_id', string='ECOs')
    eco_count = fields.Integer('# ECOs', compute='_compute_eco_count')

    def _compute_eco_count(self):
        counts = dict(self.env['mrp.eco']._read_group(
            [('product_tmpl_id', 'in', self.ids)], ['product_tmpl_id'], ['__count']))
        for product in self:
            product.eco_count = counts.get(product, 0)

    def action_view_ecos(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('hudson_plm.mrp_eco_action_main')
        action['domain'] = [('product_tmpl_id', '=', self.id)]
        action['context'] = {'default_product_tmpl_id': self.id}
        return action
