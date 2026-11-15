# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import math
from datetime import timezone
from zoneinfo import ZoneInfo

from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rental_location_id = fields.Many2one(
        'stock.location',
        string='Rental Location',
        related='company_id.rental_location_id',
        readonly=False,
        help='Location where rental products are stored'
    )
    rental_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Rental Picking Type',
        related='company_id.rental_picking_type_id',
        readonly=False,
        help='Picking type for rental deliveries'
    )
    rental_late_fee_product_id = fields.Many2one(
        'product.product',
        string='Delay Product',
        related='company_id.rental_late_fee_product_id',
        readonly=False,
        help='Product used to invoice delay costs'
    )
    rental_extra_hour = fields.Float(
        string='Per Hour', related='company_id.rental_extra_hour', readonly=False)
    rental_extra_day = fields.Float(
        string='Per Day', related='company_id.rental_extra_day', readonly=False)
    rental_min_extra_hour = fields.Integer(
        string='Apply after', related='company_id.rental_min_extra_hour', readonly=False)
    rental_calendar_id = fields.Many2one(
        'resource.calendar',
        string='Availabilities',
        related='company_id.rental_calendar_id',
        readonly=False,
        help='Days during which pickup and return are possible.'
    )
    rental_use_transfers = fields.Boolean(
        string='Rental Transfers',
        related='company_id.rental_use_transfers',
        readonly=False,
        help="Activate to use stock deliveries and receipts for rental orders."
    )
    # Quotation templates ship with sale_management, which this module depends on
    module_sale_management = fields.Boolean(string='Quotation Templates')


class Company(models.Model):
    _inherit = 'res.company'

    rental_location_id = fields.Many2one('stock.location', string='Rental Location')
    rental_picking_type_id = fields.Many2one('stock.picking.type', string='Rental Picking Type')
    rental_late_fee_product_id = fields.Many2one('product.product', string='Delay Product')
    rental_deposit_product_id = fields.Many2one('product.product', string='Deposit Product')
    rental_auto_invoice = fields.Boolean(string='Auto Create Invoice', default=False)
    rental_require_deposit = fields.Boolean(string='Require Security Deposit', default=True)
    rental_extra_hour = fields.Float(string='Delay Cost Per Hour')
    rental_extra_day = fields.Float(string='Delay Cost Per Day')
    rental_min_extra_hour = fields.Integer(
        string='Delay Cost Tolerance (Hours)', default=2,
        help='Delay costs only apply when the return is late by more than this number of hours')
    rental_calendar_id = fields.Many2one(
        'resource.calendar', string='Rental Availabilities',
        help='Days during which pickup and return are possible. Leave empty to allow every day.')
    rental_use_transfers = fields.Boolean(string='Rental Transfers', default=False)

    def _get_rental_warehouse(self):
        self.ensure_one()
        return self.env['stock.warehouse'].search([('company_id', '=', self.id)], limit=1)

    def _get_rental_location(self):
        """Stock location rented products leave from and come back to."""
        self.ensure_one()
        return self.rental_location_id or self._get_rental_warehouse().lot_stock_id

    def _get_rental_picking_type(self, code='outgoing'):
        self.ensure_one()
        if code == 'outgoing' and self.rental_picking_type_id:
            return self.rental_picking_type_id
        warehouse = self._get_rental_warehouse()
        return warehouse.out_type_id if code == 'outgoing' else warehouse.in_type_id

    def _get_rental_delay_product(self):
        self.ensure_one()
        return self.rental_late_fee_product_id or self.env.ref(
            'hudson_rental.product_late_fee', raise_if_not_found=False)

    def _is_rental_day_available(self, dt):
        """Whether pickups/returns are possible at ``dt`` (naive UTC) per the availabilities."""
        self.ensure_one()
        calendar = self.rental_calendar_id
        if not calendar or not dt:
            return True
        tz_name = self.partner_id.tz or self.env.user.tz or 'UTC'
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = timezone.utc
        local_date = dt.replace(tzinfo=timezone.utc).astimezone(tz).date()
        return calendar._works_on_date(local_date)

    def _compute_rental_delay_cost(self, delay, extra_day=0.0):
        """Delay cost of one unit returned ``delay`` (timedelta) late.

        Nothing is charged within the tolerance; beyond it, every full day is charged at
        the daily rate and every started remaining hour at the hourly rate."""
        self.ensure_one()
        delay_hours = delay.total_seconds() / 3600.0
        if delay_hours <= max(self.rental_min_extra_hour, 0):
            return 0.0
        days = int(delay_hours // 24)
        remaining_hours = delay_hours - days * 24
        hours = math.ceil(round(remaining_hours, 6))
        return days * (extra_day or self.rental_extra_day) + hours * self.rental_extra_hour
