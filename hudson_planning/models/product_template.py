# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    planning_enabled = fields.Boolean(
        string='Plan Services',
        help="If enabled, a shift will automatically be generated for the selected role when "
             "confirming the Sales Order. With the 'auto plan' feature, only employees with this "
             "role will be automatically assigned shifts for Sales Orders containing this service. "
             "The system will consider employee availability and the remaining time to be planned. "
             "You can also manually schedule open shifts for your Sales Order or assign them to "
             "any employee you prefer.",
    )
    planning_role_id = fields.Many2one(
        'fs.planning.role',
        string='Planning Role',
        ondelete='restrict',
        help='Role of the shifts generated for this service when its Sales Order is confirmed.',
    )

    @api.constrains('planning_enabled', 'planning_role_id', 'type')
    def _check_planning_service(self):
        for product in self.filtered('planning_enabled'):
            if product.type != 'service':
                raise ValidationError(_("Only services can be planned: %s is not a service.", product.display_name))
            if not product.planning_role_id:
                raise ValidationError(_("Set the role to plan %s as.", product.display_name))

    @api.onchange('type')
    def _onchange_type_planning(self):
        if self.type != 'service':
            self.planning_enabled = False

    @api.onchange('planning_enabled')
    def _onchange_planning_enabled(self):
        if not self.planning_enabled:
            self.planning_role_id = False
