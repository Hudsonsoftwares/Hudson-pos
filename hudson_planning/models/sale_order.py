# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from datetime import timedelta

from odoo import api, fields, models
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    planning_slot_ids = fields.One2many('fs.planning.slot', 'sale_order_id', string='Shifts')
    planning_slot_count = fields.Integer(compute='_compute_planning_hours', string='Shifts Count')
    planning_hours_planned = fields.Float(compute='_compute_planning_hours', string='Planned Hours')
    planning_hours_to_plan = fields.Float(compute='_compute_planning_hours', string='Hours to Plan')

    @api.depends('order_line.planning_hours_planned', 'order_line.planning_hours_to_plan', 'planning_slot_ids')
    def _compute_planning_hours(self):
        for order in self:
            # sudo: salespeople see how much of their orders is planned.
            order.planning_slot_count = len(order.sudo().planning_slot_ids)
            order.planning_hours_planned = sum(order.order_line.mapped('planning_hours_planned'))
            order.planning_hours_to_plan = sum(order.order_line.mapped('planning_hours_to_plan'))

    def _action_confirm(self):
        res = super()._action_confirm()
        # sudo: salespeople confirm orders without being planning administrators.
        self.order_line.sudo()._planning_slot_generation()
        return res

    def _action_cancel(self):
        res = super()._action_cancel()
        # Shifts not planned yet are not needed anymore; planned ones are
        # kept, the planner decides what to do with them.
        self.order_line.sudo().with_context(planning_slot_generation=True)._get_slots_to_plan().unlink()
        return res

    def action_view_planning(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('hudson_planning.action_fs_schedule_by_sale_order')
        slots = self.sudo().planning_slot_ids
        action['context'] = {'search_default_group_resource': 1}
        dated = slots.filtered('date_start')
        if dated:
            # Open on the first shift of the order.
            action['context']['initial_date'] = fields.Datetime.to_string(min(dated.mapped('date_start')))
        if slots.filtered('resource_id'):
            # The shifts of the order; while all are open shifts, all the
            # resources are shown to assign them.
            action['context']['search_default_sale_order_id'] = self.id
        return action


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    planning_slot_ids = fields.One2many('fs.planning.slot', 'sale_line_id', string='Shifts')
    planning_hours_planned = fields.Float(
        compute='_compute_planning_hours', string='Planned Hours',
        help='Hours of the shifts of this line assigned to employees.',
    )
    planning_hours_to_plan = fields.Float(
        compute='_compute_planning_hours', string='Hours to Plan',
        help='Hours of the open shifts of this line, still to assign.',
    )

    @api.depends('planning_slot_ids.allocated_hours', 'planning_slot_ids.resource_id')
    def _compute_planning_hours(self):
        for line in self:
            slots = line.sudo().planning_slot_ids
            line.planning_hours_planned = sum(slots.filtered('resource_id').mapped('allocated_hours'))
            line.planning_hours_to_plan = sum(slots.filtered(lambda s: not s.resource_id).mapped('allocated_hours'))

    def _is_planned_service(self):
        self.ensure_one()
        return (not self.display_type and self.product_id.planning_enabled
                and bool(self.product_id.planning_role_id) and self.state == 'sale')

    def _planning_hours_sold(self):
        """Ordered quantity, in hours (a quantity not in a time unit is taken as hours)."""
        self.ensure_one()
        uom_hour = self.env.ref('uom.product_uom_hour', raise_if_not_found=False)
        uom = self.product_uom_id
        if not uom or not uom_hour or uom == uom_hour or not uom._has_common_reference(uom_hour):
            return self.product_uom_qty
        return uom._compute_quantity(self.product_uom_qty, uom_hour, raise_if_failure=False)

    def _get_slots_to_plan(self):
        """Open shifts of the line: its hours not assigned to anyone yet."""
        return self.planning_slot_ids.filtered(lambda s: not s.resource_id)

    def _prepare_open_shift_values(self, date_start, date_end, break_hours, hours=0.0):
        """Values of an open shift of the line; without dates, a shift "to
        schedule" of ``hours``."""
        self.ensure_one()
        order = self.order_id
        vals = {
            'name': self.name.split('\n')[0] if self.name else self.product_id.display_name,
            'sale_line_id': self.id,
            'sale_order_id': order.id,
            'role_id': self.product_id.planning_role_id.id,
            'company_id': order.company_id.id,
            'project_id': self.project_id.id if 'project_id' in self._fields else False,
            'date_start': date_start,
            'date_end': date_end,
            'break_hours': break_hours,
            'resource_id': False,
        }
        if not date_start:
            vals['allocated_hours'] = hours
        return vals

    def _get_open_shift_start(self):
        """Start of a new open shift: the order's delivery date, at the
        earliest now (next half hour)."""
        self.ensure_one()
        now = fields.Datetime.now().replace(second=0, microsecond=0)
        start = now + timedelta(minutes=(30 - now.minute % 30) % 30)
        commitment = self.order_id.commitment_date
        if commitment and commitment > start:
            start = commitment
        return start

    def _prepare_new_open_shift_values(self, hours):
        """A new open shift for the role of the service, at the next working
        time. When an open shift of the same role is already waiting then, it
        has no dates: it is listed in the side panel of the schedule ("to
        schedule"), to drag on the schedule or to plan with Auto Plan."""
        self.ensure_one()
        Slot = self.env['fs.planning.slot'].sudo()
        start, end, breaks = Slot._get_work_span(self._get_open_shift_start(), hours, self.order_id.company_id)
        busy = Slot.search_count([
            ('resource_id', '=', False),
            ('sale_line_id', '!=', False),
            ('role_id', '=', self.product_id.planning_role_id.id),
            ('date_start', '<', end),
            ('date_end', '>', start),
        ], limit=1)
        if busy:
            return self._prepare_open_shift_values(False, False, 0.0, hours=hours)
        return self._prepare_open_shift_values(start, end, breaks)

    def _planning_slot_generation(self):
        """Keep the open shifts of each planned service at the hours sold that
        are not assigned to an employee yet: generated when the order is
        confirmed, as one open shift for the role of the service, spread over
        the working hours of the company."""
        Slot = self.env['fs.planning.slot'].sudo().with_context(
            planning_slot_generation=True, mail_create_nolog=True, tracking_disable=True)
        for line in self:
            if not line._is_planned_service():
                continue
            slots = line.sudo().planning_slot_ids.with_context(planning_slot_generation=True)
            open_slots = slots.filtered(lambda s: not s.resource_id)
            assigned = sum((slots - open_slots).mapped('allocated_hours'))
            remaining = max(line._planning_hours_sold() - assigned, 0.0)
            diff = remaining - sum(open_slots.mapped('allocated_hours'))
            # Last: the latest open shift, those to schedule (no dates) after.
            by_date = open_slots.sorted(lambda s: (not s.date_start, s.date_start or fields.Datetime.now(), s.id))
            if float_compare(diff, 0.0, precision_digits=2) > 0 and open_slots:
                # More hours to plan: on the last open shift.
                last = by_date[-1]
                last._set_open_shift_hours(last.allocated_hours + diff)
            elif float_compare(diff, 0.0, precision_digits=2) > 0:
                Slot.create(line._prepare_new_open_shift_values(diff))
            elif float_compare(diff, 0.0, precision_digits=2) < 0:
                # Fewer hours to plan: remove them from the last open shifts.
                excess = -diff
                for slot in reversed(by_date):
                    if float_compare(slot.allocated_hours, excess, precision_digits=2) <= 0:
                        excess -= slot.allocated_hours
                        slot.unlink()
                    else:
                        slot._set_open_shift_hours(slot.allocated_hours - excess)
                        break
                    if float_compare(excess, 0.0, precision_digits=2) <= 0:
                        break

    def write(self, vals):
        res = super().write(vals)
        if 'product_uom_qty' in vals or 'product_uom_id' in vals:
            # Sold hours of a confirmed order changed: so do the hours to plan.
            self.sudo().filtered(lambda l: l.state == 'sale')._planning_slot_generation()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_slots_to_plan(self):
        self.sudo().with_context(planning_slot_generation=True)._get_slots_to_plan().unlink()
