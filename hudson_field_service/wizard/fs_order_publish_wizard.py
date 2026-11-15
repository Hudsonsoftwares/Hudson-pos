# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _

class FsOrderPublishWizard(models.TransientModel):
    _name = 'fs.order.publish.wizard'
    _description = 'Publish Field Service Order Validation Wizard'

    order_ids = fields.Many2many('field.service.order', string='Orders to Publish')
    warning_message = fields.Text(string='Warning', readonly=True)

    def action_proceed_anyway(self):
        self.ensure_one()
        # Force publish the orders, bypassing the check
        self.order_ids.filtered(lambda o: not o.is_published)._publish_orders()
        return {'type': 'ir.actions.act_window_close'}
