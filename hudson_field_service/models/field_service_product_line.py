# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class FieldServiceProductLine(models.Model):
    _name = 'field.service.product.line'
    _description = 'Field Service Product Line'
    _inherit = ['product.catalog.line.mixin']
    _order = 'sequence, id'
    _check_company_auto = True

    order_id = fields.Many2one(
        'field.service.order',
        string='Field Service Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        check_company=True,
    )
    company_id = fields.Many2one(related='order_id.company_id', store=True, index=True)
    description = fields.Char(
        string='Description',
        compute='_compute_description',
        store=True,
        readonly=False,
    )
    quantity = fields.Float(
        string='Quantity',
        default=1.0,
        required=True,
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        compute='_compute_uom_id',
        store=True,
        readonly=False,
    )
    price_unit = fields.Float(
        string='Unit Price',
        compute='_compute_price_unit',
        store=True,
        readonly=False,
        digits='Product Price',
    )
    price_subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_price_subtotal',
        store=True,
        digits='Product Price',
    )

    # ── Sale Order Line tracking ───────────────────────────────────────────────
    sale_order_line_id = fields.Many2one(
        'sale.order.line',
        string='Sale Order Line',
        readonly=True,
        copy=False,
        ondelete='set null',
        help=(
            'The Sale Order line that was auto-created or linked for this product. '
            'This keeps the FS product and the SO line in sync.'
        ),
    )

    @api.depends('product_id')
    def _compute_description(self):
        for line in self:
            if line.product_id:
                line.description = line.product_id.display_name
            else:
                line.description = False

    @api.depends('product_id')
    def _compute_uom_id(self):
        for line in self:
            line.uom_id = line.product_id.uom_id if line.product_id else False

    @api.depends('product_id')
    def _compute_price_unit(self):
        for line in self:
            line.price_unit = line.product_id.lst_price if line.product_id else 0.0

    @api.depends('quantity', 'price_unit')
    def _compute_price_subtotal(self):
        for line in self:
            line.price_subtotal = line.quantity * line.price_unit

    # Every change of the products is billed on the job's sales order,
    # whether made on the job or from the product catalog.

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.order_id._sync_sale_orders()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('fs_skip_sale_sync') and vals.keys() & {'product_id', 'quantity', 'price_unit', 'uom_id', 'description'}:
            self.order_id._sync_sale_orders()
        return res

    def unlink(self):
        """Remove the linked SO line, or cancel its quantity once delivered or invoiced."""
        so_lines = self.sale_order_line_id.sudo().exists()
        orders = self.order_id
        res = super().unlink()
        for so_line in so_lines:
            if so_line.qty_delivered == 0 and so_line.qty_invoiced == 0 and so_line.state != 'sale':
                so_line.unlink()
                continue
            sale_order = so_line.order_id
            locked = sale_order.locked
            if locked:
                sale_order.action_unlock()
            so_line.product_uom_qty = 0
            if locked:
                sale_order.action_lock()
        orders.exists()._sync_sale_orders()
        return res

    # Product catalog

    @api.model
    def _get_quantity_field(self):
        return 'quantity'

    @api.model
    def _get_product_uom_field(self):
        return 'uom_id'

    def _get_catalog_unit_price(self, parent_record, **kwargs):
        return self[:1].price_unit
