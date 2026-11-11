# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _


class QualityAlert(models.Model):
    _name = 'quality.alert'
    _description = 'Quality Alert'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, id desc'

    def _default_stage(self):
        return self.env['quality.alert.stage'].search([], limit=1)

    name = fields.Char(string='Reference', default=lambda self: _('New'), copy=False, readonly=True)
    title = fields.Char(string='Title', tracking=True)

    @api.depends('name', 'title')
    def _compute_display_name(self):
        for alert in self:
            if alert.name != _('New') and alert.title:
                alert.display_name = f"{alert.name} - {alert.title}"
            elif alert.title:
                alert.display_name = alert.title
            else:
                alert.display_name = alert.name

    @api.model
    def default_get(self, fields_list):
        """Pre-fill a new alert from its originating quality check."""
        res = super().default_get(fields_list)
        check = self.env['quality.check'].browse(res.get('check_id')).exists() if res.get('check_id') else False
        if check:
            values = {
                'product_id': check.product_id.id,
                'lot_id': check.lot_id.id,
                'picking_id': check.picking_id.id,
                'production_id': check.production_id.id,
                'workorder_id': check.workorder_id.id,
                'repair_id': check.repair_id.id,
                'team_id': check.team_id.id,
                'company_id': check.company_id.id,
            }
            for fname, value in values.items():
                if fname in fields_list and value and not res.get(fname):
                    res[fname] = value
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('quality.alert') or _('New')
        return super().create(vals_list)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company)
    color = fields.Integer(string='Color Index')

    stage_id = fields.Many2one(
        'quality.alert.stage', string='Stage', default=_default_stage,
        group_expand='_read_group_stage_ids', tracking=True, ondelete='restrict')
    is_resolved = fields.Boolean(related='stage_id.done', string='Resolved', store=True)

    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Low'),
        ('2', 'High'),
        ('3', 'Critical'),
    ], default='0', string='Priority')

    kanban_state = fields.Selection([
        ('normal', 'In Progress'),
        ('blocked', 'Blocked'),
        ('done', 'Ready'),
    ], default='normal', string='Kanban State')

    product_id = fields.Many2one('product.product', string='Product', tracking=True)
    lot_id = fields.Many2one('stock.lot', string='Lot/Serial Number')

    picking_id = fields.Many2one('stock.picking', string='Transfer')
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order')
    workorder_id = fields.Many2one('mrp.workorder', string='Work Order')
    repair_id = fields.Many2one('repair.order', string='Repair Order')
    check_id = fields.Many2one('quality.check', string='Originating Check')

    team_id = fields.Many2one('quality.team', string='Quality Team', tracking=True)
    user_id = fields.Many2one('res.users', string='Responsible', tracking=True,
                               default=lambda self: self.env.user)
    tag_ids = fields.Many2many('quality.tag', string='Tags')
    description = fields.Html(string='Description')
    reason_id = fields.Many2one('quality.reason', string='Root Cause')
    corrective_action = fields.Html(string='Corrective Action')
    preventive_action = fields.Html(string='Preventive Action')
    check_name = fields.Char(related='check_id.point_id.name', string='Check Reference')

    date_assign = fields.Datetime(string='Date Assigned', default=fields.Datetime.now)
    date_close = fields.Datetime(string='Date Closed', copy=False)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        return self.env['quality.alert.stage'].search([])

    def write(self, vals):
        res = super().write(vals)
        if vals.get('stage_id'):
            stage = self.env['quality.alert.stage'].browse(vals['stage_id'])
            if stage.done:
                self.filtered(lambda a: not a.date_close).write({'date_close': fields.Datetime.now()})
        return res

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """ Override to populate the description field with the email body """
        custom_values = custom_values or {}
        if msg_dict.get('body') and not custom_values.get('description'):
            custom_values['description'] = msg_dict.get('body')
        if msg_dict.get('subject') and not custom_values.get('name'):
            custom_values['name'] = msg_dict.get('subject') or 'No Subject'
        return super().message_new(msg_dict, custom_values)

    def action_view_check(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'quality.check',
            'view_mode': 'form',
            'res_id': self.check_id.id,
        }
