# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError


class FsPlanningSlot(models.Model):
    """A planning shift with a customer is a field service job.

    Setting a customer on a shift creates a ``field.service.order`` behind it;
    the job's tools (timer, products, photos, worksheet, invoicing...) are then
    available directly on the shift. An order is planned as one shift per
    assigned technician, kept in sync by ``field.service.order._sync_planning_slots()``.
    """
    _inherit = ['fs.planning.slot', 'fs.features.mixin']

    # Shift field -> order field, pushed to the order when a job's shift is edited.
    _FS_SCHEDULE_FIELDS = {
        'date_start': 'date_planned',
        'date_end': 'date_deadline',
        'partner_id': 'partner_id',
        'role_id': 'role_id',
        'project_id': 'project_id',
        'task_id': 'task_id',
        'sale_order_id': 'sale_order_id',
        'company_id': 'company_id',
        'break_hours': 'rest_time_planned',
    }
    # Job fields shown on the shift: shift field -> order field.
    _FS_JOB_FIELDS = {
        'fs_title': 'title',
        'fs_partner_phone': 'partner_phone',
        'fs_partner_address': 'partner_address',
        'fs_extra_employee_ids': 'extra_employee_ids',
        'fs_material_ids': 'material_ids',
        'fs_priority': 'priority',
        'fs_tag_ids': 'tag_ids',
        'fs_description': 'description',
        'fs_timesheet_ids': 'timesheet_ids',
        'fs_service_image_ids': 'service_image_ids',
        'fs_product_line_ids': 'product_line_ids',
        'fs_worksheet_notes': 'worksheet_notes',
        'fs_worksheet_template_id': 'worksheet_template_id',
        'fs_worksheet_properties': 'worksheet_properties',
        'fs_equipment_ids': 'equipment_ids',
        'fs_under_warranty': 'under_warranty',
    }
    # Required order fields: never emptied from the shift form.
    _FS_REQUIRED_JOB_FIELDS = ('title', 'partner_address')

    field_service_order_id = fields.Many2one(
        'field.service.order',
        string='Field Service Job',
        ondelete='cascade',
        index=True,
        readonly=True,
        copy=False,
    )
    field_service_state = fields.Selection(
        related='field_service_order_id.state',
        string='Job Status',
    )
    shift_status = fields.Selection(
        selection_add=[
            ('in_progress', 'In Progress'),
            ('done', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
    )
    fs_project_planning = fields.Boolean(
        string='Project Planning',
        compute='_compute_fs_project_planning',
        help='Settings > Project Planning: plan shifts and jobs on projects and tasks.',
    )
    is_field_service = fields.Boolean(
        string='Is a Field Service Job',
        compute='_compute_is_field_service',
        help='Shifts with a customer are field service jobs.',
    )

    # Editable job details (writes are forwarded to the order, see _write_job_values)
    fs_title = fields.Char(related='field_service_order_id.title', string='Job Title', readonly=False)
    fs_partner_phone = fields.Char(related='field_service_order_id.partner_phone', string='Phone', readonly=False)
    fs_partner_address = fields.Char(related='field_service_order_id.partner_address', string='Service Address', readonly=False)
    fs_extra_employee_ids = fields.Many2many(related='field_service_order_id.extra_employee_ids', string='Extra Technicians', readonly=False)
    fs_material_ids = fields.Many2many(related='field_service_order_id.material_ids', string='Materials', readonly=False)
    fs_primary_employee_id = fields.Many2one(related='field_service_order_id.employee_id', string='Primary Technician')
    fs_is_extra_shift = fields.Boolean(
        compute='_compute_fs_is_extra_shift',
        help='Shift of an extra technician of the job (not of its primary technician).',
    )
    fs_priority = fields.Selection(related='field_service_order_id.priority', string='Priority', readonly=False, store=True)
    fs_tag_ids = fields.Many2many(related='field_service_order_id.tag_ids', string='Tags', readonly=False)
    fs_description = fields.Html(related='field_service_order_id.description', string='Job Description', readonly=False)
    fs_timesheet_ids = fields.One2many(related='field_service_order_id.timesheet_ids', string='Time Entries', readonly=False)
    fs_service_image_ids = fields.One2many(related='field_service_order_id.service_image_ids', string='Photos', readonly=False)
    fs_product_line_ids = fields.One2many(related='field_service_order_id.product_line_ids', string='Products', readonly=False)
    fs_worksheet_notes = fields.Html(related='field_service_order_id.worksheet_notes', string='Work Performed', readonly=False)
    fs_customer_signature = fields.Binary(related='field_service_order_id.customer_signature', string='Customer Signature', readonly=True)
    fs_customer_signed_by = fields.Char(related='field_service_order_id.customer_signed_by', string='Signed By', readonly=True)
    fs_customer_signed_date = fields.Datetime(related='field_service_order_id.customer_signed_date', string='Signed On', readonly=True)
    fs_worksheet_template_id = fields.Many2one(related='field_service_order_id.worksheet_template_id', string='Worksheet', readonly=False, store=True)
    fs_partner_city = fields.Char(related='partner_id.city', string='City', store=True)
    fs_worksheet_properties = fields.Properties(
        related='field_service_order_id.worksheet_properties',
        definition='fs_worksheet_template_id.worksheet_definition',
        string='Worksheet Fields',
        readonly=False,
    )
    fs_equipment_ids = fields.Many2many(related='field_service_order_id.equipment_ids', string='Equipment', readonly=False)
    fs_under_warranty = fields.Boolean(related='field_service_order_id.under_warranty', string='Under Warranty', readonly=False)

    # Read-only job information
    fs_is_timer_running = fields.Boolean(related='field_service_order_id.is_timer_running', string='Timer Running')
    fs_can_start_work = fields.Boolean(related='field_service_order_id.can_start_work', string='Can Start')
    fs_date_start = fields.Datetime(related='field_service_order_id.date_start', string='Actual Start')
    fs_date_end = fields.Datetime(related='field_service_order_id.date_end', string='Actual End')
    fs_total_time_spent = fields.Float(related='field_service_order_id.total_time_spent', string='Time Spent')
    fs_total_products_amount = fields.Float(related='field_service_order_id.total_products_amount', string='Products Total')
    fs_total_amount = fields.Float(related='field_service_order_id.total_amount', string='Total Amount')
    fs_invoice_status = fields.Selection(related='field_service_order_id.invoice_status', string='Invoice Status')
    fs_invoice_id = fields.Many2one(related='field_service_order_id.invoice_id', string='Invoice')
    fs_timesheet_count = fields.Integer(related='field_service_order_id.timesheet_count', string='Time Entries Count')
    fs_picking_count = fields.Integer(related='field_service_order_id.picking_count', string='Deliveries')
    fs_customer_rating = fields.Selection(related='field_service_order_id.customer_rating', string='Rating')
    fs_quotation_count = fields.Integer(related='field_service_order_id.quotation_count', string='Quotations')
    fs_sale_order_confirmed = fields.Boolean(related='field_service_order_id.sale_order_confirmed')
    fs_delivery_count = fields.Integer(related='field_service_order_id.delivery_count', string='Deliveries')
    fs_delivery_done_count = fields.Integer(related='field_service_order_id.delivery_done_count', string='Done')
    fs_product_count = fields.Integer(related='field_service_order_id.product_count', string='Products')
    fs_photo_count = fields.Integer(related='field_service_order_id.photo_count', string='Photos')

    def _compute_fs_project_planning(self):
        enabled = self.env['ir.config_parameter'].sudo().get_bool('hudson_field_service.fs_project_planning', True)
        for slot in self:
            slot.fs_project_planning = enabled

    @api.depends('partner_id')
    def _compute_is_field_service(self):
        enabled = self.env['field.service.order']._is_planning_sync_enabled()
        for slot in self:
            slot.is_field_service = enabled and bool(slot.partner_id)

    @api.depends('state', 'field_service_state')
    def _compute_shift_status(self):
        super()._compute_shift_status()
        job_status = {'in_progress': 'in_progress', 'paused': 'in_progress', 'done': 'done', 'cancelled': 'cancelled'}
        for slot in self.filtered('field_service_order_id'):
            slot.shift_status = job_status.get(slot.field_service_state, slot.shift_status)

    @api.depends('resource_id', 'field_service_order_id.employee_id', 'field_service_order_id.extra_employee_ids')
    def _compute_fs_is_extra_shift(self):
        for slot in self:
            order = slot.sudo().field_service_order_id
            slot.fs_is_extra_shift = bool(order) and bool(slot.resource_id) \
                and slot.resource_id != order.employee_id and slot.resource_id in order.extra_employee_ids

    @api.onchange('resource_id', 'fs_extra_employee_ids')
    def _onchange_resource_id_extra_technicians(self):
        """The (primary) technician of the job is not also one of its extra
        technicians. Shifts of the extra technicians list them all."""
        if self._origin.fs_is_extra_shift:
            return
        resource = self.resource_id._origin
        if resource and resource in self.fs_extra_employee_ids._origin:
            # Onchange records: compare the real employees.
            self.fs_extra_employee_ids = self.fs_extra_employee_ids.filtered(lambda e: e._origin != resource)

    @api.onchange('partner_id')
    def _onchange_partner_id_field_service(self):
        """Fetch the customer's phone number; a new job gets the default worksheet."""
        if not self.partner_id:
            return
        if self.partner_id != self.field_service_order_id.partner_id:
            # Optional: stays empty when the customer has no number.
            self.fs_partner_phone = self.partner_id.phone
        if not self.fs_worksheet_template_id:
            self.fs_worksheet_template_id = self.env['field.service.order'].default_get(
                ['worksheet_template_id']).get('worksheet_template_id')

    def _get_shift_template_extra_values(self):
        return {**super()._get_shift_template_extra_values(), 'worksheet_template_id': self.fs_worksheet_template_id.id}

    @api.onchange('shift_template_id')
    def _onchange_shift_template_id(self):
        super()._onchange_shift_template_id()
        if self.shift_template_id.worksheet_template_id:
            self.fs_worksheet_template_id = self.shift_template_id.worksheet_template_id

    @api.onchange('fs_worksheet_template_id')
    def _onchange_fs_worksheet_template_id(self):
        # Show the fields of the new worksheet right away (values start empty)
        if self.fs_worksheet_template_id != self._origin.fs_worksheet_template_id:
            self.fs_worksheet_properties = {}

    # -------------------------------------------------------------------------
    # CONFLICTS
    # -------------------------------------------------------------------------

    def _is_open_job(self):
        return bool(self.field_service_order_id) and self.field_service_state not in ('done', 'cancelled')

    def _is_booked_shift(self):
        """A shift reserved for specific work, as opposed to plain availability."""
        return not self.field_service_order_id and bool(
            self.partner_id or self.project_id or self.task_id or self.sale_order_id
        )

    def _blocks_field_service_job(self):
        return self._is_open_job() or self._is_booked_shift()

    # An employee cannot do two things at once: a job conflicts with any other
    # shift or job of the technician at the same time (no _conflicts_with
    # exception for jobs inside plain shifts anymore).

    def _get_conflict_label(self):
        if not self.field_service_order_id:
            return super()._get_conflict_label()
        order = self.sudo().field_service_order_id
        label = super()._get_conflict_label()
        # "FS-00012 - Title (4 Nov 08:00 - 16:00)"
        return ' - '.join(filter(None, [order.name, order.title])) + label[label.rfind(' ('):]

    def _get_booking_label(self):
        """Human readable label of what the slot is booked for."""
        self.ensure_one()
        if self.field_service_order_id:
            return self.field_service_order_id.display_name
        work = self.task_id or self.project_id or self.sale_order_id or self.partner_id
        if work:
            return _("a shift for %s", work.display_name)
        return self.name or _("another shift")

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    def _fs_enabled(self):
        return not self.env.context.get('fs_slot_sync') and self.env['field.service.order']._is_planning_sync_enabled()

    @api.model
    def _pop_job_values(self, vals):
        """Remove the job fields from ``vals``, returned as order values."""
        return {self._FS_JOB_FIELDS[f]: vals.pop(f) for f in list(vals) if f in self._FS_JOB_FIELDS}

    @api.model
    def _prepare_field_service_order_values(self, vals, job_vals):
        partner = self.env['res.partner'].browse(vals['partner_id'])
        order_vals = {
            'title': vals.get('name') or partner.display_name,
            'partner_address': partner.contact_address or partner.display_name,
            # The primary technician defaults to the current user on orders; a
            # shift without resource is an open job.
            'employee_id': vals.get('resource_id') or False,
            'is_published': vals.get('state') == 'published',
        }
        for slot_field, order_field in self._FS_SCHEDULE_FIELDS.items():
            if vals.get(slot_field):
                order_vals[order_field] = vals[slot_field]
        # An empty worksheet on a new job keeps the default one.
        keep = self._FS_REQUIRED_JOB_FIELDS + ('worksheet_template_id',)
        order_vals.update({k: v for k, v in job_vals.items() if v or k not in keep})
        return order_vals

    @api.model_create_multi
    def create(self, vals_list):
        # The role of a job comes from its order: set it before creating it.
        vals_list = [self._add_default_role(vals) for vals in vals_list]
        if not self._fs_enabled():
            for vals in vals_list:
                self._pop_job_values(vals)
            return super().create(vals_list)

        Order = self.env['field.service.order']
        orders = Order
        for vals in vals_list:
            job_vals = self._pop_job_values(vals)
            if vals.get('partner_id') and not vals.get('field_service_order_id'):
                # sudo: planners may book a job for a customer without having
                # field service rights themselves.
                order = Order.sudo().with_context(fs_skip_slot_sync=True).create(
                    self._prepare_field_service_order_values(vals, job_vals)
                )
                vals['field_service_order_id'] = order.id
                orders |= order
        slots = super().create(vals_list)
        # Name, state... of the shifts follow the order.
        orders.sudo()._sync_planning_slots()
        return slots

    def _get_employee_writable_fields(self):
        # Technicians fill in their jobs; the technicians of a job are planned
        # by the administrators.
        return super()._get_employee_writable_fields() | (set(self._FS_JOB_FIELDS) - {'fs_extra_employee_ids'})

    def write(self, vals):
        self._check_employee_write(vals)
        if vals.get('resource_id') and 'role_id' not in vals:
            # The role of a job comes from its order: set it before the job
            # values are pushed to the order.
            no_role = self.filtered(lambda s: not s.role_id)
            role_vals = self._add_default_role(vals)
            if no_role and role_vals is not vals:
                if no_role != self:
                    (self - no_role).write(vals)
                    return no_role.write(role_vals)
                vals = role_vals
        if 'resource_id' in vals and not vals['resource_id'] and 'partner_id' not in vals and self._fs_enabled():
            # A job has no shift without technician (see
            # field.service.order._sync_planning_slots): unassigning the only
            # technician of the job of a service sold (e.g. moved to Open
            # Shifts) makes it an open shift of the sales order again, at the
            # same time, removing the job (refused once work is recorded).
            back_to_open = self.filtered(
                lambda s: s.sale_line_id and s.field_service_order_id and s.resource_id
                and s.field_service_order_id._get_assignees() == s.resource_id)
            if back_to_open:
                for slot in back_to_open:
                    line = slot.sudo().sale_line_id
                    slot.write({**vals, 'partner_id': False,
                                'name': (line.name or '').split('\n')[0] or line.product_id.display_name})
                rest = self - back_to_open
                return rest.write(vals) if rest else True
        if vals.get('resource_id') and not vals.get('partner_id') and self._fs_enabled():
            # Assigning an open shift of a service with a worksheet (e.g.
            # dropped on a technician): it becomes a job for the customer.
            sale_jobs = self.filtered(lambda s: not s.resource_id and not s.partner_id and s._is_field_service_sale_shift())
            if sale_jobs:
                for slot in sale_jobs:
                    slot.write({**vals, **slot._get_sale_job_values()})
                rest = self - sale_jobs
                return rest.write(vals) if rest else True
        if not self._fs_enabled():
            self._pop_job_values(vals)
            return super().write(vals)

        job_vals = self._pop_job_values(vals)

        # Removing the customer turns a job back into a plain shift.
        if 'partner_id' in vals and not vals['partner_id']:
            self.filtered('field_service_order_id')._detach_field_service_order()

        # Setting a customer on a plain shift creates its job.
        if vals.get('partner_id'):
            for slot in self.filtered(lambda s: not s.field_service_order_id):
                slot_vals = {f: slot._convert_to_write({f: slot[f]})[f] for f in ('name', 'resource_id', 'state', *self._FS_SCHEDULE_FIELDS)}
                slot_vals.update(vals)
                order = self.env['field.service.order'].sudo().with_context(fs_skip_slot_sync=True).create(
                    self._prepare_field_service_order_values(slot_vals, {})
                )
                super(FsPlanningSlot, slot.with_context(fs_slot_sync=True)).write({'field_service_order_id': order.id})

        jobs = self.filtered('field_service_order_id')
        old_resources = {slot: slot.resource_id for slot in jobs}
        res = super().write(vals)

        if jobs:
            jobs._push_schedule_to_orders(vals, old_resources)
            jobs._write_job_values(job_vals)
            if 'state' in vals:
                # sudo: planners publish from the schedule without
                # necessarily having write access on field service orders.
                orders = jobs.field_service_order_id.sudo()
                if vals['state'] == 'published':
                    orders.filtered(lambda o: not o.is_published)._publish_orders()
                else:
                    orders.filtered('is_published').write({'is_published': False})
        return res

    def _push_schedule_to_orders(self, vals, old_resources):
        """Forward schedule changes made on job shifts to their orders."""
        order_vals = {self._FS_SCHEDULE_FIELDS[f]: vals[f] for f in vals if f in self._FS_SCHEDULE_FIELDS}
        for order in self.field_service_order_id:
            values = dict(order_vals)
            if 'resource_id' in vals:
                new = self.env['hr.employee'].browse(vals['resource_id'])
                for slot in self.filtered(lambda s: s.field_service_order_id == order):
                    old = old_resources[slot]
                    if old == new:
                        continue
                    if old == order.employee_id or not old:
                        values['employee_id'] = new.id
                    else:
                        values['extra_employee_ids'] = [(3, old.id), (4, new.id)] if new else [(3, old.id)]
            if values:
                order.sudo().write(values)

    def _write_job_values(self, job_vals):
        job_vals = {k: v for k, v in job_vals.items() if v or k not in self._FS_REQUIRED_JOB_FIELDS}
        if job_vals:
            # Once per order: x2many commands must not be applied twice.
            self.field_service_order_id.write(job_vals)

    def _has_field_service_progress(self):
        order = self.field_service_order_id
        return order.state in ('in_progress', 'paused', 'done') or bool(order.timesheet_ids or order.invoice_id)

    def _detach_field_service_order(self):
        """Turn job shifts back into plain shifts, deleting their (unstarted) job."""
        for slot in self:
            if slot._has_field_service_progress():
                raise UserError(_(
                    "The customer cannot be removed: work has already been recorded on %s.",
                    slot.field_service_order_id.display_name,
                ))
        orders = self.field_service_order_id
        Slot = self.sudo().with_context(fs_slot_sync=True)
        (orders.planning_slot_ids - self).sudo().with_context(fs_slot_sync=True).unlink()
        super(FsPlanningSlot, Slot.browse(self.ids)).write({'field_service_order_id': False})
        orders.sudo().unlink()

    def unlink(self):
        if self.env.context.get('fs_slot_sync'):
            return super().unlink()
        orders_to_delete = self.env['field.service.order']
        extras_to_remove = defaultdict(lambda: self.env['hr.employee'])
        for slot in self.filtered('field_service_order_id'):
            order = slot.field_service_order_id
            if slot.resource_id and slot.resource_id in order.extra_employee_ids and slot.resource_id != order.employee_id:
                # Deleting an extra technician's shift unassigns them.
                extras_to_remove[order] |= slot.resource_id
            elif slot._has_field_service_progress():
                raise UserError(_(
                    "This shift cannot be deleted: work has already been recorded on %s. Cancel the job instead.",
                    order.display_name,
                ))
            else:
                orders_to_delete |= order
        res = super(FsPlanningSlot, self.with_context(fs_slot_sync=True)).unlink()
        for order, employees in extras_to_remove.items():
            if order not in orders_to_delete:
                order.sudo().write({'extra_employee_ids': [(3, e.id) for e in employees]})
        orders_to_delete.sudo().unlink()
        return res

    # -------------------------------------------------------------------------
    # JOB ACTIONS (forwarded to the order)
    # -------------------------------------------------------------------------

    def _job(self):
        self.ensure_one()
        if not self.field_service_order_id:
            raise UserError(_("Set a customer and save the shift to plan a field service job."))
        return self.field_service_order_id

    def action_start_timer_with_location(self, latitude=0.0, longitude=0.0):
        return self._job().action_start_timer_with_location(latitude, longitude)

    def action_resume_timer_with_location(self, latitude=0.0, longitude=0.0):
        return self._job().action_resume_timer_with_location(latitude, longitude)

    def action_update_current_location(self, latitude=0.0, longitude=0.0):
        return self._job().action_update_current_location(latitude, longitude)

    def action_log_location(self, latitude=0.0, longitude=0.0, event_label="Location Logged"):
        return self._job().action_log_location(latitude, longitude, event_label)

    def action_stop_timer(self):
        return self._job().action_stop_timer()

    def action_pause_timer(self):
        return self._job().action_pause_timer()

    def action_mark_done(self):
        return self._job().action_mark_done()

    def action_get_directions(self):
        return self._job().action_get_directions()

    def action_create_invoice(self):
        return self._job().action_create_invoice()

    def action_view_invoice(self):
        return self._job().action_view_invoice()

    def action_send_report(self):
        return self._job().action_send_report()

    def action_view_timesheets(self):
        return self._job().action_view_timesheets()

    def action_view_pickings(self):
        return self._job().action_view_pickings()

    def action_view_sale_order(self):
        return self._job().action_view_sale_order()

    def action_view_quotations(self):
        return self._job().action_view_quotations()

    def action_fsm_view_products(self):
        return self._job().action_fsm_view_products()

    def action_customer_preview(self):
        return self._job().action_customer_preview()


    def _check_job_not_started(self, action):
        started = self.filtered(lambda s: s.field_service_state in ('in_progress', 'paused', 'done'))
        if started:
            raise UserError(_(
                "%(action)s is not possible: the job %(job)s has already been started.",
                action=action, job=started[0].field_service_order_id.display_name,
            ))

    def action_unpublish(self):
        self._check_job_not_started(_("Unpublishing"))
        return super().action_unpublish()

    def action_request_switch(self):
        self._check_job_not_started(_("Asking for a replacement"))
        return super().action_request_switch()

    def action_self_unassign(self):
        """On a job, the technician leaves the job: their shift is removed (an
        extra technician), or becomes the open shift of the job (the only one),
        so the message goes on the job."""
        self._check_job_not_started(_("Unassigning yourself"))
        jobs = self.filtered('field_service_order_id')
        for slot in jobs:
            if not slot.can_self_unassign:
                raise UserError(_("You can only remove yourself from your own upcoming published shifts."))
            order = slot.sudo().field_service_order_id
            # sudo: employees may not write on the shift anymore once unassigned.
            slot.sudo().write({'resource_id': False, 'request_to_switch': False})
            order.message_post(body=_("%s removed themselves from this job.", self.env.user.name))
        return super(FsPlanningSlot, self - jobs).action_self_unassign()

    # -------------------------------------------------------------------------
    # SCHEDULE VIEW
    # -------------------------------------------------------------------------

    @api.model
    def _get_schedule_fields(self):
        return super()._get_schedule_fields() + ['field_service_order_id', 'field_service_state']

    def _get_schedule_slot_values(self):
        values = super()._get_schedule_slot_values()
        order = self.field_service_order_id
        if order:
            values.update(
                is_job=True,
                label=' - '.join(filter(None, [order.partner_id.display_name, order.title])) or order.name,
            )
        return values

    def _can_copy_to_next_period(self):
        # Jobs are planned for their customer: they are not repeated.
        return super()._can_copy_to_next_period() and not self.field_service_order_id

    @api.model
    def _get_schedule_to_plan(self, date_from, date_to):
        items = super()._get_schedule_to_plan(date_from, date_to)
        if not self.env.user.has_group('hudson_field_service.group_field_service_user'):
            return items
        orders = self.env['field.service.order'].search([
            ('date_planned', '=', False),
            ('state', 'not in', ('done', 'cancelled')),
            ('company_id', 'in', self.env.companies.ids),
        ], order='priority desc, id')
        return items + [{
            'ref': f'field.service.order,{order.id}',
            'name': ' - '.join(filter(None, [order.partner_id.display_name, order.title])) or order.name,
            'hours': order.duration_planned or 1.0,
        } for order in orders]

    @api.model
    def action_plan_from_schedule(self, ref, group_field, row_key, date_start, date_end):
        model, _sep, res_id = ref.partition(',')
        if model != 'field.service.order':
            return super().action_plan_from_schedule(ref, group_field, row_key, date_start, date_end)
        order = self.env['field.service.order'].browse(int(res_id)).exists()
        if not order:
            raise UserError(_("This job does not exist anymore."))
        vals = {'date_planned': date_start, 'date_deadline': date_end}
        if group_field == 'resource_id':
            if not row_key:
                raise UserError(_("Drop the job on a resource to plan it."))
            vals['employee_id'] = row_key
        elif group_field in ('role_id', 'project_id', 'task_id', 'sale_order_id', 'partner_id') and row_key:
            vals[group_field] = row_key
        if 'employee_id' not in vals and not order.employee_id:
            raise UserError(_("Group the schedule by resource and drop the job on a technician to plan it."))
        order.write(vals)
        return True

    # -------------------------------------------------------------------------
    # SALES ORDERS: services with a worksheet are field service jobs
    # -------------------------------------------------------------------------

    def _is_field_service_sale_shift(self):
        """Shift of a service with a worksheet: assigned, it is a job."""
        self.ensure_one()
        return self._fs_enabled() and bool(self.sudo().sale_line_id.product_id.worksheet_template_id)

    def _get_sale_job_values(self):
        """Values making a shift of a service with a worksheet a job for the
        customer of its sales order (see create / write)."""
        self.ensure_one()
        line = self.sudo().sale_line_id
        order = line.order_id
        return {
            'partner_id': (order.partner_shipping_id or order.partner_id).id,
            'fs_title': self.name or line.product_id.display_name,
            'fs_worksheet_template_id': line.product_id.worksheet_template_id.id,
        }

    def _prepare_planned_shift_values(self, employee, date_start, date_end, break_hours):
        vals = super()._prepare_planned_shift_values(employee, date_start, date_end, break_hours)
        if self._is_field_service_sale_shift():
            vals.update(self._get_sale_job_values())
        return vals

    def get_popover_data(self):
        data = super().get_popover_data()
        if not self.field_service_order_id or not self.env.user.has_group('hudson_field_service.group_field_service_user'):
            return data
        order = self.field_service_order_id
        lines = data['lines']
        if order.partner_phone:
            # The job's contact number rather than the customer's.
            lines = [line for line in lines if line['icon'] != 'call']
            lines.insert(1, {'icon': 'call', 'text': order.partner_phone})
        if order.worksheet_template_id and self._fs_feature('fs_worksheets'):
            lines.append({'icon': 'build', 'text': order.worksheet_template_id.display_name})
        data.update(lines=lines, priority=order.priority, job_state=order.state)
        return data

    def _get_popover_actions(self):
        actions = super()._get_popover_actions()
        order = self.field_service_order_id
        if not order or not self.env.user.has_group('hudson_field_service.group_field_service_user'):
            return actions
        actions.append({'method': 'action_get_directions', 'string': _("Navigate")})
        if order.state in ('new', 'scheduled') and not order.is_timer_running and order.can_start_work:
            actions.append({'method': 'action_start_timer_with_location', 'string': _("Start"),
                            'geolocate': self._fs_feature('fs_geolocation')})
        # The technician's timer, like Odoo: pause / stop it, or resume it.
        if order.state in ('in_progress', 'paused') and order.can_start_work:
            if order.is_timer_running:
                actions.append({'method': 'action_pause_timer', 'string': _("Pause")})
                actions.append({'method': 'action_stop_timer', 'string': _("Stop")})
            else:
                actions.append({'method': 'action_resume_timer_with_location', 'string': _("Resume"),
                                'geolocate': self._fs_feature('fs_geolocation')})
        if order.state in ('new', 'scheduled') and self.env.user.has_group('hudson_field_service.group_field_service_manager'):
            actions.append({'method': 'action_unschedule', 'string': _("Unschedule")})
        return actions

    def action_unschedule(self):
        return self._job().action_unschedule()

    # -------------------------------------------------------------------------
    # MAPS
    # -------------------------------------------------------------------------

    @api.model
    def get_job_map_data(self, date_from, date_to, my_only=False):
        """Field service jobs between two UTC datetimes, located at their customer."""
        domain = [
            ('field_service_order_id', '!=', False),
            ('date_start', '<', date_to),
            ('date_end', '>', date_from),
        ]
        if my_only:
            domain.append(('resource_id.user_id', '=', self.env.uid))
        jobs = []
        # The search applies the access rules (employees: their own jobs);
        # sudo: planners see where jobs are without field service rights.
        for slot in self.search(domain, order='date_start, id').sudo():
            order = slot.field_service_order_id
            if order.state == 'cancelled':
                continue
            partner = order.partner_id
            jobs.append({
                'id': slot.id,
                'order_name': order.name,
                'title': order.title or '',
                'state': order.state,
                'resource_id': slot.resource_id.id or 0,
                'resource_name': slot.resource_id.name or _('Unassigned'),
                'date_start': fields.Datetime.to_string(slot.date_start),
                'date_end': fields.Datetime.to_string(slot.date_end),
                'partner_name': partner.display_name or '',
                'address': order.partner_address or '',
                'phone': order.partner_phone or '',
                'latitude': partner.partner_latitude,
                'longitude': partner.partner_longitude,
            })
        return jobs

    @api.model
    def get_mapbox_token(self):
        """Settings > Mapbox: public token used by the maps for driving routes."""
        return self.env['ir.config_parameter'].sudo().get_str('hudson_field_service.fs_mapbox_token')

    @api.model
    def action_locate_customers(self, slot_ids):
        """Geolocate the customers of the given job shifts that have no coordinates yet."""
        # Only the jobs the user may see
        partners = self.search([('id', 'in', slot_ids)]).sudo().field_service_order_id.partner_id.filtered(
            lambda p: not (p.partner_latitude and p.partner_longitude)
        )
        partners.geo_localize()
        return len(partners.filtered(lambda p: p.partner_latitude and p.partner_longitude))
