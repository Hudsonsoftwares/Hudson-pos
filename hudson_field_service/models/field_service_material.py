# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.addons.base.models.res_partner import _tz_get

class FieldServiceMaterial(models.Model):
    _name = 'field.service.material'
    _description = 'Field Service Material'
    _order = 'name'

    name = fields.Char(string='Name', required=True)
    employee_id = fields.Many2one('hr.employee', string='Assigned To')
    role_ids = fields.Many2many('fs.planning.role', string='Roles')
    default_role_id = fields.Many2one('fs.planning.role', string='Default Role')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    resource_calendar_id = fields.Many2one('resource.calendar', string='Working Time')
    tz = fields.Selection(
        _tz_get, string='Timezone', required=True,
        default=lambda self: self.env.context.get('tz') or self.env.user.tz or 'UTC'
    )
    color = fields.Integer(string='Color Index')

    def action_open_material_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Material'),
            'res_model': 'field.service.material',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }
