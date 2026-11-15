# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class FsPlanningRole(models.Model):
    _name = 'fs.planning.role'
    _description = 'Field Service Planning Role'
    _order = 'sequence asc, name asc'

    name = fields.Char(string='Role', required=True, translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string='Color', default=0)
    resource_ids = fields.Many2many(
        'hr.employee',
        'fs_planning_role_employee_rel',
        'role_id',
        'employee_id',
        string='Resources',
        help='Employees who can perform this role.',
    )
    product_ids = fields.One2many(
        'product.template',
        'planning_role_id',
        string='Services',
        help='Services whose sales orders generate shifts for this role (Plan Services).',
    )
    slot_count = fields.Integer(
        string='Shifts',
        compute='_compute_slot_count',
    )

    @api.depends('name')
    def _compute_slot_count(self):
        slot_data = self.env['fs.planning.slot'].read_group(
            [('role_id', 'in', self.ids)],
            ['role_id'],
            ['role_id'],
        )
        slot_map = {d['role_id'][0]: d['role_id_count'] for d in slot_data}
        for role in self:
            role.slot_count = slot_map.get(role.id, 0)
