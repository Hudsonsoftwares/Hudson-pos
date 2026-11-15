# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FieldServiceCreateInvoiceWizard(models.TransientModel):
    _name = 'field.service.create.invoice.wizard'
    _description = 'Create Invoice from Field Service'

    order_id = fields.Many2one(
        'field.service.order',
        string='Field Service Order',
        required=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
    )
    include_time = fields.Boolean(
        string='Include Time Charges',
        default=True,
        help='Add a line item for the time spent on this service order.',
    )
    hourly_rate = fields.Float(
        string='Hourly Rate',
        default=lambda self: float(
            self.env['ir.config_parameter'].sudo().get_param(
                'hudson_field_service.default_hourly_rate', '50.0'
            )
        ),
    )
    time_amount = fields.Float(
        string='Time Amount',
        compute='_compute_time_amount',
    )
    include_products = fields.Boolean(
        string='Include Products',
        default=True,
        help='Add line items for the products used during this service order.',
    )
    products_amount = fields.Float(
        string='Products Amount',
        compute='_compute_products_amount',
    )
    total_amount = fields.Float(
        string='Total Invoice Amount',
        compute='_compute_total_amount',
    )

    @api.depends('order_id', 'hourly_rate', 'include_time')
    def _compute_time_amount(self):
        for wizard in self:
            if wizard.include_time and wizard.order_id:
                amount = 0.0
                for line in wizard.order_id.timesheet_ids:
                    cost = line.employee_id.hourly_cost if hasattr(line.employee_id, 'hourly_cost') and line.employee_id.hourly_cost else wizard.hourly_rate
                    amount += line.duration * cost
                wizard.time_amount = amount
            else:
                wizard.time_amount = 0.0

    @api.depends('order_id', 'include_products')
    def _compute_products_amount(self):
        for wizard in self:
            if wizard.include_products and wizard.order_id:
                wizard.products_amount = wizard.order_id.total_products_amount
            else:
                wizard.products_amount = 0.0

    @api.depends('time_amount', 'products_amount')
    def _compute_total_amount(self):
        for wizard in self:
            wizard.total_amount = wizard.time_amount + wizard.products_amount

    def action_create_invoice(self):
        """
        Create a customer invoice from the field service order.

        If the order is linked to a Sale Order, this wizard should not be called
        (the SO-based flow is used instead).  This method handles the standalone
        case only.
        """
        self.ensure_one()
        order = self.order_id

        # Safety: if SO exists, redirect to SO-based flow
        if order.sale_order_id:
            return order.action_create_invoice()

        if not self.partner_id:
            raise UserError(_('Please set a customer.'))

        invoice_lines = []

        # Add time charge lines per employee
        if self.include_time and order.timesheet_ids:
            time_product = False
            time_template = self.env.ref(
                'hudson_field_service.product_field_service_time',
                raise_if_not_found=False,
            )
            if time_template:
                time_product = time_template.product_variant_id
                
            time_by_emp = {}
            for line in order.timesheet_ids:
                emp = line.employee_id
                if emp not in time_by_emp:
                    cost = emp.hourly_cost if hasattr(emp, 'hourly_cost') and emp.hourly_cost else self.hourly_rate
                    time_by_emp[emp] = {'duration': 0.0, 'cost': cost}
                time_by_emp[emp]['duration'] += line.duration
                
            for emp, data in time_by_emp.items():
                if data['duration'] > 0:
                    emp_name = emp.name if emp else _('Unknown Technician')
                    invoice_lines.append((0, 0, {
                        'name': _('Field Service Time - %s - %s [%s hours]') % (
                            order.title, emp_name, round(data['duration'], 2)
                        ),
                        'quantity': data['duration'],
                        'price_unit': data['cost'],
                        'product_id': time_product.id if time_product else False,
                    }))

        # Add product lines
        if self.include_products:
            for line in order.product_line_ids:
                invoice_lines.append((0, 0, {
                    'name': line.description or line.product_id.display_name,
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                    'price_unit': line.price_unit,
                    'product_uom_id': line.uom_id.id if line.uom_id else False,
                }))

        # Settings > Travel Fees: round-trip travel time
        travel_product = order._get_travel_product()
        if travel_product:
            invoice_lines.append((0, 0, {
                'name': _('Travel to %(customer)s (%(distance)s km)', customer=order.partner_id.display_name, distance=order.travel_distance),
                'product_id': travel_product.id,
                'quantity': order.travel_duration,
                'price_unit': travel_product.lst_price,
            }))

        if not invoice_lines:
            raise UserError(_('Nothing to invoice. Add time entries or products first.'))

        # Create the invoice
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_origin': order.name,
            'invoice_line_ids': invoice_lines,
            'company_id': order.company_id.id,
        })

        # Link invoice to the order
        order.write({
            'invoice_id': invoice.id,
        })

        # Post a message on the order
        order.message_post(
            body=_('Invoice %s created for amount %s.') % (
                invoice.name or _('Draft'), self.total_amount
            ),
        )

        # Open the created invoice
        return {
            'name': _('Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': invoice.id,
            'target': 'current',
        }
