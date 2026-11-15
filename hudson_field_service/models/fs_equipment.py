# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class FsEquipment(models.Model):
    """Customer equipment serviced by field service jobs (Settings > Equipment)."""
    _name = 'fs.equipment'
    _description = 'Customer Equipment'
    _inherit = ['mail.thread']
    _order = 'partner_id, name'

    name = fields.Char(string='Equipment', required=True, tracking=True)
    active = fields.Boolean(default=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, index=True, tracking=True)
    manufacturer_id = fields.Many2one('res.partner', string='Manufacturer')
    model = fields.Char(string='Model')
    serial_number = fields.Char(string='Serial Number', tracking=True, copy=False)
    location = fields.Char(string='Location', help='Where the equipment is installed at the customer.')
    note = fields.Html(string='Note')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    # Settings > Maintenance Contracts
    contract_reference = fields.Char(string='Maintenance Contract', tracking=True)
    contract_end_date = fields.Date(string='Covered Until', tracking=True)
    under_contract = fields.Boolean(
        string='Under Contract',
        compute='_compute_under_contract',
        search='_search_under_contract',
        help='The equipment is covered by a running maintenance contract.',
    )

    order_ids = fields.Many2many(
        'field.service.order',
        'field_service_order_equipment_rel',
        'equipment_id',
        'order_id',
        string='Interventions',
    )
    order_count = fields.Integer(string='Interventions Count', compute='_compute_order_count')

    _serial_number_uniq = models.Constraint(
        'UNIQUE(serial_number, company_id)',
        'Another equipment already has this serial number.',
    )

    @api.depends('contract_end_date')
    def _compute_under_contract(self):
        today = fields.Date.context_today(self)
        for equipment in self:
            equipment.under_contract = bool(equipment.contract_end_date) and equipment.contract_end_date >= today

    def _search_under_contract(self, operator, value):
        if operator not in ('=', '!='):
            return NotImplemented
        today = fields.Date.context_today(self)
        covered = [('contract_end_date', '>=', today)]
        return covered if (operator == '=') == bool(value) else ['!', *covered]

    @api.depends('order_ids')
    def _compute_order_count(self):
        for equipment in self:
            equipment.order_count = len(equipment.order_ids)

    @api.depends('name', 'serial_number')
    def _compute_display_name(self):
        for equipment in self:
            equipment.display_name = f'{equipment.name} ({equipment.serial_number})' if equipment.serial_number else equipment.name

    def action_view_interventions(self):
        """Intervention history of the equipment."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Interventions'),
            'res_model': 'field.service.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.order_ids.ids)],
            'context': {'default_partner_id': self.partner_id.id, 'default_equipment_ids': [self.id]},
        }
