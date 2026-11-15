# -*- coding: utf-8 -*-
from odoo import models, fields, api

CHANGE_TYPES = [
    ('add', 'Add'),
    ('remove', 'Remove'),
    ('update', 'Update')
]


class MrpEcoBomChange(models.Model):
    _name = 'mrp.eco.bom.change'
    _description = 'ECO BoM Changes'
    _order = 'change_type, product_id'

    eco_id = fields.Many2one('mrp.eco', string='ECO', required=True, ondelete='cascade', index=True)
    change_type = fields.Selection(CHANGE_TYPES, string='Type', required=True)

    product_id = fields.Many2one('product.product', string='Components', required=True)
    uom_id = fields.Many2one('uom.uom', related='product_id.uom_id', string='Unit of Measure')

    old_qty = fields.Float('Old Quantity', default=0.0)
    new_qty = fields.Float('New Quantity', default=0.0)

    quantity_diff = fields.Float('Quantity', compute='_compute_diffs', store=True)
    cost_diff = fields.Monetary('BoM Cost', compute='_compute_diffs', store=True, currency_field='currency_id')

    currency_id = fields.Many2one('res.currency', related='eco_id.company_id.currency_id')

    # Reporting helpers
    eco_type_id = fields.Many2one(related='eco_id.type_id', string='ECO Type', store=True)
    product_tmpl_id = fields.Many2one(related='eco_id.product_tmpl_id', string='Product', store=True)
    company_id = fields.Many2one(related='eco_id.company_id', store=True)

    @api.depends('new_qty', 'old_qty', 'product_id', 'product_id.standard_price')
    def _compute_diffs(self):
        for record in self:
            record.quantity_diff = record.new_qty - record.old_qty
            record.cost_diff = record.quantity_diff * record.product_id.standard_price


class MrpEcoRoutingChange(models.Model):
    _name = 'mrp.eco.routing.change'
    _description = 'ECO Operation Changes'
    _order = 'change_type, workcenter_id, operation_name'

    eco_id = fields.Many2one('mrp.eco', string='ECO', required=True, ondelete='cascade', index=True)
    change_type = fields.Selection(CHANGE_TYPES, string='Type', required=True)

    operation_name = fields.Char('Operation', required=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center', required=True)

    old_duration = fields.Float('Old Duration (min)', default=0.0)
    new_duration = fields.Float('New Duration (min)', default=0.0)

    duration_diff = fields.Float('Duration (min)', compute='_compute_diffs', store=True)
    cost_diff = fields.Monetary('Operation Cost', compute='_compute_diffs', store=True, currency_field='currency_id')

    currency_id = fields.Many2one('res.currency', related='eco_id.company_id.currency_id')

    # Reporting helpers
    eco_type_id = fields.Many2one(related='eco_id.type_id', string='ECO Type', store=True)
    product_tmpl_id = fields.Many2one(related='eco_id.product_tmpl_id', string='Product', store=True)
    company_id = fields.Many2one(related='eco_id.company_id', store=True)

    @api.depends('new_duration', 'old_duration', 'workcenter_id', 'workcenter_id.costs_hour')
    def _compute_diffs(self):
        for record in self:
            record.duration_diff = record.new_duration - record.old_duration
            record.cost_diff = record.duration_diff / 60.0 * record.workcenter_id.costs_hour
