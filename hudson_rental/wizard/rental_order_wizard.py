# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class RentalOrderWizard(models.TransientModel):
    """Validate the pickup or the return of the rented products of an order."""
    _name = 'rental.order.wizard'
    _description = 'Pickup / Return of Rented Products'

    order_id = fields.Many2one('sale.order', required=True, ondelete='cascade')
    status = fields.Selection([('pickup', 'Pickup'), ('return', 'Return')], required=True)
    line_ids = fields.One2many('rental.order.wizard.line', 'wizard_id', string='Lines')
    has_tracked_lines = fields.Boolean(compute='_compute_has_tracked_lines')
    is_late = fields.Boolean(compute='_compute_is_late')

    @api.depends('order_id', 'status')
    def _compute_is_late(self):
        now = fields.Datetime.now()
        for wizard in self:
            date = wizard.order_id.rental_start_date if wizard.status == 'pickup' else wizard.order_id.rental_end_date
            wizard.is_late = bool(date and date < now)

    @api.depends('line_ids.tracking')
    def _compute_has_tracked_lines(self):
        for wizard in self:
            wizard.has_tracked_lines = any(wizard.line_ids.mapped('tracking'))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order = self.env['sale.order'].browse(res.get('order_id'))
        status = res.get('status')
        if order and status:
            lines = []
            for line in order.order_line.filtered('is_rental'):
                if status == 'pickup':
                    qty = line.product_uom_qty - line.qty_delivered
                    lots = self.env['stock.lot']  # chosen by the user
                else:
                    qty = line.qty_delivered - line.qty_returned
                    # By default everything still out comes back
                    lots = line.pickedup_lot_ids - line.returned_lot_ids
                if qty > 0:
                    lines.append((0, 0, {'order_line_id': line.id, 'qty': qty, 'lot_ids': [(6, 0, lots.ids)]}))
            res['line_ids'] = lines
        return res

    def action_apply(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: not l.uom_id.is_zero(l.qty))
        if not lines:
            raise UserError(_('There is nothing to %s.', self._action_label()))
        for line in lines:
            line._check_quantity_and_lots()

        order = self.order_id
        if self.status == 'pickup':
            for line in lines:
                line.order_line_id.qty_delivered += line.qty
                line.order_line_id.pickedup_lot_ids |= line.lot_ids
        else:
            for line in lines:
                line.order_line_id.qty_returned += line.qty
                line.order_line_id.returned_lot_ids |= line.lot_ids
            self._add_delay_costs(lines, fields.Datetime.now())
        self._create_transfer(lines)
        title = _('Picked up') if self.status == 'pickup' else _('Returned')
        details = ', '.join(
            f'{l.qty:g} {l.product_id.display_name}' + (f" ({', '.join(l.lot_ids.mapped('name'))})" if l.lot_ids else '')
            for l in lines)
        order.message_post(body=f'{title}: {details}')
        return {'type': 'ir.actions.act_window_close'}

    def _action_label(self):
        return _('pick up') if self.status == 'pickup' else _('return')

    def _add_delay_costs(self, lines, return_date):
        """Late returns add a delay cost line on the order, like Odoo's Rental app."""
        order = self.order_id
        if not order.rental_end_date or return_date <= order.rental_end_date:
            return
        company = order.company_id
        delay = return_date - order.rental_end_date
        product = company._get_rental_delay_product()
        if not product:
            return
        for line in lines:
            cost = company._compute_rental_delay_cost(delay, extra_day=line.product_id.late_fee_per_day) * line.qty
            if cost > 0:
                self.env['sale.order.line'].create({
                    'order_id': order.id,
                    'product_id': product.id,
                    'name': _('Late return of %(product)s (%(hours)s hours late)',
                              product=line.product_id.display_name,
                              hours=round(delay.total_seconds() / 3600.0, 1)),
                    'product_uom_qty': 1,
                    'price_unit': cost,
                })

    def _create_transfer(self, lines):
        """With Rental Transfers, pickups and returns also move the stock (with their serials)."""
        order = self.order_id
        company = order.company_id
        if not company.rental_use_transfers:
            return
        stored_lines = lines.filtered(lambda l: l.product_id.is_storable)
        if not stored_lines:
            return
        location = company._get_rental_location()
        customer_location = order.partner_shipping_id.property_stock_customer
        if self.status == 'pickup':
            picking_type = company._get_rental_picking_type('outgoing')
            source, destination = location, customer_location
        else:
            picking_type = company._get_rental_picking_type('incoming')
            source, destination = customer_location, location
        if not (location and picking_type):
            raise UserError(_('Rental Transfers need a warehouse for company %s.', company.name))
        picking = self.env['stock.picking'].create({
            'partner_id': order.partner_shipping_id.id,
            'origin': order.name,
            'rental_sale_order_id': order.id,
            'picking_type_id': picking_type.id,
            'location_id': source.id,
            'location_dest_id': destination.id,
            'move_ids': [(0, 0, {
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'uom_id': line.uom_id.id,
                'location_id': source.id,
                'location_dest_id': destination.id,
            }) for line in stored_lines],
        })
        picking.action_confirm()
        picking.action_assign()
        for move, line in zip(picking.move_ids, stored_lines):
            if line.lot_ids:
                move.lot_ids = line.lot_ids
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()


class RentalOrderWizardLine(models.TransientModel):
    _name = 'rental.order.wizard.line'
    _description = 'Pickup / Return Line'

    wizard_id = fields.Many2one('rental.order.wizard', required=True, ondelete='cascade')
    status = fields.Selection(related='wizard_id.status')
    order_line_id = fields.Many2one('sale.order.line', required=True, ondelete='cascade')
    product_id = fields.Many2one(related='order_line_id.product_id')
    tracking = fields.Selection(related='product_id.tracking')
    uom_id = fields.Many2one(related='order_line_id.product_uom_id')
    qty_reserved = fields.Float(related='order_line_id.product_uom_qty', string='Reserved')
    qty_delivered = fields.Float(related='order_line_id.qty_delivered', string='Picked-up')
    qty_returned = fields.Float(related='order_line_id.qty_returned', string='Returned')
    qty_max = fields.Float(compute='_compute_qty_max')
    qty = fields.Float(string='Quantity', digits='Product Unit')
    lot_ids = fields.Many2many(
        'stock.lot', 'rental_wizard_line_lot_rel', 'wizard_line_id', 'lot_id', string='Serial Numbers',
        domain="[('id', 'in', allowed_lot_ids)]")
    allowed_lot_ids = fields.Many2many(
        'stock.lot', 'rental_wizard_line_allowed_lot_rel', 'wizard_line_id', 'lot_id',
        compute='_compute_allowed_lot_ids')

    @api.depends('status', 'qty_reserved', 'qty_delivered', 'qty_returned')
    def _compute_qty_max(self):
        for line in self:
            if line.status == 'pickup':
                line.qty_max = line.qty_reserved - line.qty_delivered
            else:
                line.qty_max = line.qty_delivered - line.qty_returned

    @api.depends('status', 'product_id', 'order_line_id.pickedup_lot_ids', 'order_line_id.returned_lot_ids')
    def _compute_allowed_lot_ids(self):
        for line in self:
            if not line.tracking:
                line.allowed_lot_ids = False
            elif line.status == 'return':
                # Only what this order picked up and did not bring back yet
                line.allowed_lot_ids = line.order_line_id.pickedup_lot_ids - line.order_line_id.returned_lot_ids
            else:
                line.allowed_lot_ids = line._get_pickeable_lots()

    def _get_pickeable_lots(self):
        """Serials of the product that are not out with another customer (and, with
        Rental Transfers, that are in stock in the rental location)."""
        self.ensure_one()
        company = self.wizard_id.order_id.company_id
        lots = self.env['stock.lot'].search([
            ('product_id', '=', self.product_id.id),
            ('company_id', 'in', [company.id, False]),
        ])
        rented_lines = self.env['sale.order.line'].search([
            ('product_id', '=', self.product_id.id),
            ('is_rental', '=', True),
            ('state', '=', 'sale'),
            ('pickedup_lot_ids', '!=', False),
        ])
        out = rented_lines.pickedup_lot_ids - rented_lines.returned_lot_ids
        lots -= out
        if company.rental_use_transfers and self.product_id.is_storable:
            location = company._get_rental_location()
            quants = self.env['stock.quant'].search([
                ('product_id', '=', self.product_id.id),
                ('location_id', 'child_of', location.id),
                ('lot_id', 'in', lots.ids),
                ('quantity', '>', 0),
            ])
            lots = quants.lot_id
        return lots

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        if self.tracking == 'serial' and self.lot_ids:
            self.qty = len(self.lot_ids)

    def _check_quantity_and_lots(self):
        self.ensure_one()
        action = self.wizard_id._action_label()
        if self.uom_id.compare(self.qty, self.qty_max) > 0:
            raise UserError(_('You can\'t %(action)s more than %(qty)s %(product)s.',
                              action=action, qty=self.qty_max, product=self.product_id.display_name))
        if self.tracking == 'serial' and len(self.lot_ids) != self.qty:
            raise UserError(_('Please select %(qty)s serial number(s) to %(action)s %(product)s.',
                              qty=int(self.qty), action=action, product=self.product_id.display_name))
        if self.lot_ids - self.allowed_lot_ids:
            raise UserError(_('Serial numbers %(lots)s can\'t be used to %(action)s %(product)s.',
                              lots=', '.join((self.lot_ids - self.allowed_lot_ids).mapped('name')),
                              action=action, product=self.product_id.display_name))
