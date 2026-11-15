# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _action_confirm(self):
        res = super()._action_confirm()
        # sudo: salespeople confirm orders without field service rights.
        self.order_line.sudo()._field_service_job_generation()
        return res

    def _action_cancel(self):
        res = super()._action_cancel()
        # Jobs of the services sold not started yet are not needed anymore.
        jobs = self.order_line.sudo().with_context(active_test=False).field_service_order_ids
        jobs.filtered(lambda j: j.state == 'new' and not j.date_planned and not j.timesheet_ids).unlink()
        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    field_service_order_ids = fields.One2many('field.service.order', 'sale_line_id', string='Field Service Jobs')

    def _is_field_service_job_line(self):
        """Service with a worksheet but not planned through shifts (Plan
        Services): one job to schedule per line, like a task per service."""
        self.ensure_one()
        product = self.product_id
        return (not self.display_type and self.state == 'sale' and product.type == 'service'
                and bool(product.worksheet_template_id) and not product.planning_enabled
                and self.product_uom_qty > 0)

    def _prepare_field_service_job_values(self):
        self.ensure_one()
        order = self.order_id
        partner = order.partner_shipping_id or order.partner_id
        return {
            'title': (self.name or '').split('\n')[0] or self.product_id.display_name,
            'partner_id': partner.id,
            'partner_address': partner.contact_address or partner.display_name,
            'partner_phone': partner.phone or order.partner_id.phone,
            # A job to schedule: no technician, no date.
            'employee_id': False,
            'sale_order_id': order.id,
            'sale_line_id': self.id,
            'worksheet_template_id': self.product_id.worksheet_template_id.id,
            'duration_planned': self._planning_hours_sold(),
            'company_id': order.company_id.id,
            'project_id': self.project_id.id if 'project_id' in self._fields else False,
        }

    def _field_service_job_generation(self):
        Order = self.env['field.service.order'].sudo()
        for line in self:
            if not line._is_field_service_job_line():
                continue
            if line.with_context(active_test=False).field_service_order_ids:
                continue
            Order.with_company(line.order_id.company_id).create(line._prepare_field_service_job_values())
