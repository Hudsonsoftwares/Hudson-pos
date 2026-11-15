# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import math
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_datetime

from .product_template import RENTAL_PERIOD_DAYS

RENTAL_STATUS = [
    ('draft', 'Quotation'),
    ('sent', 'Quotation Sent'),
    ('pickup', 'Reserved'),
    ('return', 'Picked-up'),
    ('returned', 'Returned'),
    ('cancel', 'Cancelled'),
]


class SaleOrder(models.Model):
    """Rental orders are sales orders holding rentable products, like in Odoo's Rental app:
    they show in both Sales and Rental, and follow Reserved -> Picked-up -> Returned."""
    _inherit = 'sale.order'

    is_rental_order = fields.Boolean(
        string='Is Rental Order', compute='_compute_is_rental_order', store=True, index=True)
    rental_start_date = fields.Datetime(string='Rental Start Date', copy=False)
    rental_end_date = fields.Datetime(string='Rental Return Date', copy=False)
    rental_status = fields.Selection(
        RENTAL_STATUS, string='Rental Status', compute='_compute_rental_status', store=True)
    has_pickable_lines = fields.Boolean(compute='_compute_rental_actions')
    has_returnable_lines = fields.Boolean(compute='_compute_rental_actions')

    # Dashboard / list flags, relative to the current time (not stored)
    is_pickup_late = fields.Boolean(compute='_compute_is_late', search='_search_is_pickup_late')
    is_return_late = fields.Boolean(compute='_compute_is_late', search='_search_is_return_late')
    is_late = fields.Boolean(string='Late', compute='_compute_is_late', search='_search_is_late')
    is_today = fields.Boolean(string='Today', compute='_compute_is_today', search='_search_is_today')

    rental_transfer_ids = fields.One2many('stock.picking', 'rental_sale_order_id', string='Rental Transfers')
    rental_transfer_count = fields.Integer(compute='_compute_rental_transfer_count')

    @api.depends('order_line.is_rental')
    def _compute_is_rental_order(self):
        for order in self:
            order.is_rental_order = any(order.order_line.mapped('is_rental'))

    @api.depends('state', 'order_line.is_rental', 'order_line.product_uom_qty',
                 'order_line.qty_delivered', 'order_line.qty_returned')
    def _compute_rental_actions(self):
        for order in self:
            lines = order.order_line.filtered('is_rental') if order.state == 'sale' else []
            order.has_pickable_lines = any(l.qty_delivered < l.product_uom_qty for l in lines)
            order.has_returnable_lines = any(l.qty_returned < l.qty_delivered for l in lines)

    @api.depends('is_rental_order', 'state', 'order_line.product_uom_qty',
                 'order_line.qty_delivered', 'order_line.qty_returned')
    def _compute_rental_status(self):
        for order in self:
            lines = order.order_line.filtered('is_rental')
            pickable = any(l.qty_delivered < l.product_uom_qty for l in lines)
            returnable = any(l.qty_returned < l.qty_delivered for l in lines)
            if not order.is_rental_order:
                order.rental_status = False
            elif order.state in ('draft', 'sent', 'cancel'):
                order.rental_status = order.state
            elif pickable:
                order.rental_status = 'pickup'
            elif returnable:
                order.rental_status = 'return'
            else:
                order.rental_status = 'returned'

    @api.depends('rental_status', 'rental_start_date', 'rental_end_date')
    def _compute_is_late(self):
        now = fields.Datetime.now()
        for order in self:
            order.is_pickup_late = bool(
                order.rental_status == 'pickup' and order.rental_start_date and order.rental_start_date < now)
            order.is_return_late = bool(
                order.rental_status == 'return' and order.rental_end_date and order.rental_end_date < now)
            order.is_late = order.is_pickup_late or order.is_return_late

    def _late_pickup_domain(self):
        return Domain([('rental_status', '=', 'pickup'), ('rental_start_date', '<', fields.Datetime.now())])

    def _late_return_domain(self):
        return Domain([('rental_status', '=', 'return'), ('rental_end_date', '<', fields.Datetime.now())])

    def _search_is_pickup_late(self, operator, value):
        return self._search_flag(operator, value, self._late_pickup_domain())

    def _search_is_return_late(self, operator, value):
        return self._search_flag(operator, value, self._late_return_domain())

    def _search_is_late(self, operator, value):
        return self._search_flag(operator, value, self._late_pickup_domain() | self._late_return_domain())

    def _today_bounds(self):
        """Start and end of the user's current day, as naive UTC datetimes."""
        try:
            tz = ZoneInfo(self.env.user.tz or 'UTC')
        except Exception:
            tz = timezone.utc
        today = datetime.now(tz).date()
        start = datetime.combine(today, time.min, tz).astimezone(timezone.utc).replace(tzinfo=None)
        return start, start + timedelta(days=1)

    def _today_domain(self):
        start, end = self._today_bounds()
        pickups = Domain([('rental_status', '=', 'pickup'),
                          ('rental_start_date', '>=', start), ('rental_start_date', '<', end)])
        returns = Domain([('rental_status', '=', 'return'),
                          ('rental_end_date', '>=', start), ('rental_end_date', '<', end)])
        return pickups | returns

    @api.depends('rental_status', 'rental_start_date', 'rental_end_date')
    def _compute_is_today(self):
        today_orders = self.filtered_domain(self._today_domain())
        for order in self:
            order.is_today = order in today_orders

    def _search_is_today(self, operator, value):
        return self._search_flag(operator, value, self._today_domain())

    def _search_flag(self, operator, value, domain):
        # Odoo normalizes boolean searches to 'in'; other operators are derived from it
        if operator != 'in':
            return NotImplemented
        if True in value and False in value:
            return Domain.TRUE
        return domain if True in value else ~domain

    @api.depends('rental_transfer_ids')
    def _compute_rental_transfer_count(self):
        for order in self:
            order.rental_transfer_count = len(order.rental_transfer_ids)

    @api.model
    def _get_rental_dashboard_domains(self):
        """Domains of the dashboard cards on the rental orders list (also used by its filters)."""
        return {
            'today': [('is_today', '=', True)],
            'pickups': [('rental_status', '=', 'pickup')],
            'returns': [('rental_status', '=', 'return')],
            'late': [('is_late', '=', True)],
            'to_confirm': [('state', 'in', ('draft', 'sent'))],
            'to_invoice': [('invoice_status', '=', 'to invoice')],
        }

    @api.model
    def retrieve_rental_dashboard(self):
        base = Domain([('is_rental_order', '=', True), ('state', '!=', 'cancel')])
        return {
            key: self.search_count(base & Domain(domain))
            for key, domain in self._get_rental_dashboard_domains().items()
        }

    # ------------------------------------------------------------------
    # Rental period
    # ------------------------------------------------------------------

    def _default_rental_period(self):
        """First rental period proposed for an order: from the next hour, for one period
        of the longest periodicity among its rented products."""
        self.ensure_one()
        start = (fields.Datetime.now() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        periods = self.order_line.filtered('is_rental').product_id.mapped('rental_periodicity')
        days = max([RENTAL_PERIOD_DAYS[p] for p in periods if p] or [1.0])
        return start, start + timedelta(days=days)

    def _set_default_rental_period(self):
        for order in self.filtered(lambda o: o.is_rental_order and not (o.rental_start_date and o.rental_end_date)):
            order.rental_start_date, order.rental_end_date = order._default_rental_period()

    @api.onchange('order_line')
    def _onchange_order_line_rental_period(self):
        if any(self.order_line.mapped('is_rental')) and not (self.rental_start_date and self.rental_end_date):
            self.rental_start_date, self.rental_end_date = self._default_rental_period()

    @api.constrains('rental_start_date', 'rental_end_date')
    def _check_rental_period(self):
        for order in self:
            if order.rental_start_date and order.rental_end_date and order.rental_end_date <= order.rental_start_date:
                raise UserError(_('The rental return date must be after the pickup date.'))

    def _action_confirm(self):
        for order in self.filtered('is_rental_order'):
            if not (order.rental_start_date and order.rental_end_date):
                raise UserError(_('Please set the rental period of %s before confirming it.', order.name))
        return super()._action_confirm()

    # ------------------------------------------------------------------
    # Pickup / Return
    # ------------------------------------------------------------------

    def _open_rental_wizard(self, status):
        self.ensure_one()
        return {
            'name': _('Validate a pickup') if status == 'pickup' else _('Validate a return'),
            'type': 'ir.actions.act_window',
            'res_model': 'rental.order.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id, 'default_status': status},
        }

    def action_open_pickup(self):
        return self._open_rental_wizard('pickup')

    def action_open_return(self):
        return self._open_rental_wizard('return')

    def action_view_rental_transfers(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_all')
        action['domain'] = [('id', 'in', self.rental_transfer_ids.ids)]
        if len(self.rental_transfer_ids) == 1:
            action['views'] = [(self.env.ref('stock.view_picking_form').id, 'form')]
            action['res_id'] = self.rental_transfer_ids.id
        return action

    # ------------------------------------------------------------------
    # eCommerce: one rental period per cart, like Odoo's Rental app
    # ------------------------------------------------------------------

    def _cart_add(self, product_id, quantity=1.0, *, rental_start_date=None, rental_end_date=None, **kwargs):
        if rental_start_date and rental_end_date and (
            (self.rental_start_date, self.rental_end_date) != (rental_start_date, rental_end_date)
        ):
            # Changing the period re-prices the rental products already in the cart
            self.write({'rental_start_date': rental_start_date, 'rental_end_date': rental_end_date})
        return super()._cart_add(product_id, quantity, **kwargs)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # Precomputed so that the standard precomputed line fields (name, price...) can depend on them
    is_rental = fields.Boolean(string='Is Rental', compute='_compute_is_rental', store=True, precompute=True)
    rental_start_date = fields.Datetime(
        string='Rental Start', compute='_compute_rental_dates', store=True, precompute=True)
    rental_end_date = fields.Datetime(
        string='Rental End', compute='_compute_rental_dates', store=True, precompute=True)
    rental_duration = fields.Float(
        string='Duration (Days)', compute='_compute_rental_duration', store=True, precompute=True)
    qty_returned = fields.Float(string='Returned', copy=False, digits='Product Unit', default=0.0)
    rental_tracking = fields.Selection(related='product_id.tracking', string='Rental Tracking')
    pickedup_lot_ids = fields.Many2many(
        'stock.lot', 'rental_sale_line_pickedup_lot_rel', 'line_id', 'lot_id',
        string='Serial Numbers', copy=False, help='Serial numbers picked up by the customer')
    returned_lot_ids = fields.Many2many(
        'stock.lot', 'rental_sale_line_returned_lot_rel', 'line_id', 'lot_id',
        string='Returned Serial Numbers', copy=False)

    @api.depends('product_id.is_rental')
    def _compute_is_rental(self):
        for line in self:
            line.is_rental = line.product_id.is_rental

    @api.depends('order_id.rental_start_date', 'order_id.rental_end_date')
    def _compute_rental_dates(self):
        for line in self:
            line.rental_start_date = line.order_id.rental_start_date
            line.rental_end_date = line.order_id.rental_end_date

    @api.depends('rental_start_date', 'rental_end_date')
    def _compute_rental_duration(self):
        for line in self:
            if line.rental_start_date and line.rental_end_date:
                delta = line.rental_end_date - line.rental_start_date
                line.rental_duration = delta.total_seconds() / 86400.0
            else:
                line.rental_duration = 0.0

    @api.depends('is_rental')
    def _compute_qty_delivered_method(self):
        super()._compute_qty_delivered_method()
        # Rented products are "delivered" when picked up, through the Pickup wizard
        for line in self.filtered('is_rental'):
            line.qty_delivered_method = 'manual'

    @api.depends('rental_start_date', 'rental_end_date')
    def _compute_name(self):
        # Extends the standard dependencies so the description shows the rental duration
        return super()._compute_name()

    def _get_rental_duration_label(self):
        """Duration of the rental in the product's periodicity, e.g. "97 Hours"."""
        self.ensure_one()
        if not (self.is_rental and self.rental_duration > 0):
            return ''
        unit = self.product_id.rental_periodicity or 'day'
        count = max(1, math.ceil(round(self.rental_duration / RENTAL_PERIOD_DAYS[unit], 6)))
        labels = {
            'hour': (_('Hour'), _('Hours')), 'day': (_('Day'), _('Days')),
            'week': (_('Week'), _('Weeks')), 'month': (_('Month'), _('Months')),
        }[unit]
        return f"{count} {labels[0] if count == 1 else labels[1]}"

    def _get_rental_pricing_description(self):
        """Rental period shown under rental lines by the standard sale/eCommerce mail templates."""
        self.ensure_one()
        if not (self.is_rental and self.rental_start_date and self.rental_end_date):
            return ''
        tz = self.order_id.partner_id.tz or self.env.user.tz or 'UTC'
        start, end = (format_datetime(self.env, d, tz=tz, dt_format='short')
                      for d in (self.rental_start_date, self.rental_end_date))
        return _("%(start)s to %(end)s", start=start, end=end)

    def _get_sale_order_line_multiline_description_sale(self):
        description = super()._get_sale_order_line_multiline_description_sale()
        if duration := self._get_rental_duration_label():
            description = "\n".join(filter(None, [description, duration]))
        return description

    @api.depends('rental_start_date', 'rental_end_date')
    def _compute_price_unit(self):
        # Extends the standard dependencies so the price follows the rental period
        return super()._compute_price_unit()

    def _get_display_price(self):
        """Rental lines are priced on their rental period instead of the pricelist."""
        if self.is_rental and self.rental_duration > 0:
            return self.product_id.product_tmpl_id.get_rental_price(self.rental_duration, 'day')
        return super()._get_display_price()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.order_id._set_default_rental_period()
        return lines

    # ------------------------------------------------------------------
    # Availability widget: rentals have no delivery order, so the stock
    # forecast is computed on the rental period instead
    # ------------------------------------------------------------------

    @api.depends('is_rental')
    def _compute_qty_to_deliver(self):
        super()._compute_qty_to_deliver()
        for line in self.filtered('is_rental'):
            # Shown until everything is picked up (there are no stock moves to follow)
            line.display_qty_widget = bool(
                line.state in ('draft', 'sent', 'sale') and line.is_storable
                and line.product_uom_id and line.qty_to_deliver > 0)

    @api.depends('is_rental', 'rental_start_date', 'rental_end_date')
    def _compute_qty_at_date(self):
        rental_lines = self.filtered(
            lambda l: l.is_rental and l.display_qty_widget and l.rental_start_date and l.rental_end_date)
        super(SaleOrderLine, self - rental_lines)._compute_qty_at_date()
        for line in rental_lines:
            available = line._get_rental_available_qty()
            line.scheduled_date = line.rental_start_date
            line.forecast_expected_date = False
            line.qty_available_today = available
            line.free_qty_today = available
            line.virtual_available_at_date = available

    def _get_rental_available_qty(self):
        """Units of the product free for this line's rental period: the stock minus what
        other confirmed rentals overlapping the period hold."""
        self.ensure_one()
        company = self.order_id.company_id or self.env.company
        product = self.product_id
        location = company._get_rental_location()
        on_hand = product.with_context(location=location.id).qty_available if location else product.qty_available
        others = self.search([
            ('product_id', '=', product.id),
            ('is_rental', '=', True),
            ('state', '=', 'sale'),
            ('id', '!=', self._origin.id),
        ])
        start, end = self.rental_start_date, self.rental_end_date
        overlapping = others.filtered(lambda l: l.rental_start_date < end and l.rental_end_date > start)
        if company.rental_use_transfers:
            # Picked-up units already left the stock: only bookings still to pick up are
            # missing, and units out on earlier rentals come back before this one starts.
            back_before = others.filtered(lambda l: l.rental_end_date and l.rental_end_date <= start)
            return (on_hand
                    + sum(l.qty_delivered - l.qty_returned for l in back_before)
                    - sum(l.product_uom_qty - l.qty_delivered for l in overlapping))
        return on_hand - sum(l.product_uom_qty - l.qty_returned for l in overlapping)

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        # Rented products leave and come back through the Pickup / Return wizards
        lines_to_launch = self.filtered(lambda l: not l.is_rental)
        return super(SaleOrderLine, lines_to_launch)._action_launch_stock_rule(previous_product_uom_qty=previous_product_uom_qty)
