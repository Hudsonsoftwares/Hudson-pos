# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

import logging
import math
from datetime import timedelta

import requests
from markupsafe import Markup

from odoo import Command, api, fields, models, _
from odoo.fields import Domain
from odoo.tools import float_compare, format_date, format_datetime
from odoo.tools.image import image_data_uri
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class FieldServiceOrder(models.Model):
    _name = 'field.service.order'
    _description = 'Field Service Order'
    _inherit = ['portal.mixin', 'mail.thread', 'mail.activity.mixin', 'fs.features.mixin', 'product.catalog.mixin']
    _order = 'priority desc, date_planned asc, id desc'
    # Technicians, customer, project, sales order, equipment... of the job's company
    _check_company_auto = True

    # -------------------------------------------------------------------------
    # FIELDS
    # -------------------------------------------------------------------------

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        index='trigram',
    )
    title = fields.Char(string='Title', required=True, tracking=True)
    description = fields.Html(string='Description', sanitize_attributes=False)
    active = fields.Boolean(default=True)

    # Stage & State
    stage_id = fields.Many2one(
        'field.service.stage',
        string='Stage',
        tracking=True,
        index=True,
        default=lambda self: self._default_stage_id(),
        group_expand='_read_group_stage_ids',
        ondelete='restrict',
    )
    state = fields.Selection([
        ('new', 'New'),
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('paused', 'Paused'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='new', required=True, tracking=True, copy=False)
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Low'),
        ('2', 'High'),
        ('3', 'Urgent'),
    ], default='0', string='Priority', tracking=True)
    color = fields.Integer(string='Color Index')

    # Project Integration (Optional)
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        tracking=True,
        help='Optional: Link this field service order to a project.',
        check_company=True,
    )
    

    task_id = fields.Many2one(
        'project.task',
        string='Project Task',
        tracking=True,
        domain="[('project_id', '=?', project_id)]",
        help='Optional: Link this field service order to a specific project task.',
        check_company=True,
    )

    # Customer
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        tracking=True,
        index=True,
        required=True,
        check_company=True,
    )
    partner_phone = fields.Char(
        string='Phone',
        compute='_compute_partner_info',
        store=True,
        readonly=False,
    )
    partner_email = fields.Char(
        string='Email',
        compute='_compute_partner_info',
        store=True,
        readonly=False,
    )
    partner_address = fields.Char(
        string='Service Address',
        compute='_compute_partner_info',
        store=True,
        readonly=False,
        required=True,
        help='Location where the service will be performed.',
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Primary Technician',
        tracking=True,
        index=True,
        group_expand='_read_group_employee_ids',
        default=lambda self: self.env.user.employee_id,
        check_company=True,
    )
    extra_employee_ids = fields.Many2many(
        'hr.employee',
        'field_service_order_extra_employees_rel',
        'order_id',
        'employee_id',
        string='Extra Assignees',
        tracking=True,
        help="Additional technicians assigned to this job.",
        check_company=True,
    )
    material_ids = fields.Many2many(
        'field.service.material',
        string='Materials',
        tracking=True,
        help="Materials assigned to this job.",
        check_company=True,
    )
    team_leader_employee_id = fields.Many2one(
        'hr.employee',
        string='Team Leader',
        tracking=True,
        check_company=True,
    )

    # Scheduling
    date_planned = fields.Datetime(
        string='Start Date',
        tracking=True,
        index=True,
    )
    date_deadline = fields.Datetime(
        string='End Date',
        tracking=True,
    )
    duration_planned = fields.Float(
        string='Total Scheduled Time (Hours)',
        compute='_compute_duration_planned',
        store=True,
        readonly=False,
        help='Estimated total duration from start to finish.',
    )
    rest_time_planned = fields.Float(
        string='Planned Rest Time (Hours)',
        help='Expected rest or non-working time during the shift.',
        default=0.0,
    )
    duration_working_planned = fields.Float(
        string='Planned Working Time (Hours)',
        compute='_compute_duration_working',
        store=True,
        help='Total scheduled time minus planned rest time.',
    )

    # Planning Integration
    role_id = fields.Many2one(
        'fs.planning.role',
        string='Planning Role',
        tracking=True,
        help='Role required for this job. Used to suggest technicians and to colour the job in Planning.',
    )
    planning_slot_ids = fields.One2many(
        'fs.planning.slot',
        'field_service_order_id',
        string='Planning Shifts',
    )
    planning_warning = fields.Text(
        string='Planning Warnings',
        compute='_compute_planning_availability',
    )
    available_employee_ids = fields.Many2many(
        'hr.employee',
        string='Available Technicians',
        compute='_compute_planning_availability',
        help='Technicians (with the required role, if any) who are on shift and free during the planned time.',
    )

    # Timer & Actual Duration
    date_start = fields.Datetime(string='Actual Start', readonly=True, copy=False)
    date_end = fields.Datetime(string='Actual End', readonly=True, copy=False)
    timer_start = fields.Datetime(
        string='Timer Started At',
        readonly=True,
        copy=False,
        help='Timestamp when the current timer session was started.',
    )
    active_timer_ids = fields.One2many(
        'field.service.active.timer',
        'order_id',
        string='Active Timers'
    )
    is_timer_running = fields.Boolean(
        string='Timer Running',
        compute='_compute_is_timer_running',
        store=False,
    )
    can_start_work = fields.Boolean(
        string='Can Start',
        compute='_compute_can_start_work',
        help='The job is published and the current user is one of its technicians.',
    )
    last_paused_time = fields.Datetime(
        string='Last Paused Time',
        readonly=True,
        copy=False,
        help='Timestamp when the order was last paused.',
    )
    rest_time_actual = fields.Float(
        string='Actual Rest Time (Hours)',
        readonly=True,
        copy=False,
        default=0.0,
        help='Total accumulated time spent in paused state.',
    )
    start_latitude = fields.Float(string='Start Latitude', digits=(16, 5), copy=False)
    start_longitude = fields.Float(string='Start Longitude', digits=(16, 5), copy=False)
    duration_actual = fields.Float(
        string='Actual Duration (Hours)',
        compute='_compute_duration_actual',
        store=True,
        help='Total time spent from all timesheet entries.',
    )

    # Live Location (updated in real-time by technician's device)
    current_latitude = fields.Float(
        string='Current Latitude',
        digits=(16, 5),
        copy=False,
        help='Most recent GPS latitude reported by the technician\'s device.',
    )
    current_longitude = fields.Float(
        string='Current Longitude',
        digits=(16, 5),
        copy=False,
        help='Most recent GPS longitude reported by the technician\'s device.',
    )
    last_location_update = fields.Datetime(
        string='Location Last Updated',
        readonly=True,
        copy=False,
    )

    # Timesheets
    timesheet_ids = fields.One2many(
        'field.service.timesheet',
        'order_id',
        string='Time Entries',
    )
    total_time_spent = fields.Float(
        string='Total Time Spent',
        compute='_compute_duration_actual',
        store=True,
    )
    timesheet_count = fields.Integer(
        string='Timesheet Count',
        compute='_compute_timesheet_count',
    )

    # Products
    product_line_ids = fields.One2many(
        'field.service.product.line',
        'order_id',
        string='Products Used',
    )
    
    picking_ids = fields.One2many(
        'stock.picking',
        'fs_order_id',
        string='Delivery Orders'
    )
    picking_count = fields.Integer(
        string='Delivery Orders Count',
        compute='_compute_picking_count'
    )

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for order in self:
            order.picking_count = len(order.picking_ids)
    image_ids = fields.Many2many(
        'ir.attachment',
        string="Images",
        help="Upload images related to this service order."
    )
    service_image_ids = fields.One2many(
        'field.service.image',
        'order_id',
        string='Service Images'
    )
    total_products_amount = fields.Float(
        string='Products Total',
        compute='_compute_total_products_amount',
        store=True,
        digits='Product Price',
    )

    # Invoice & Sale Order
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        tracking=True,
        copy=False,
        check_company=True,
    )
    sale_order_count = fields.Integer(
        string='Sale Orders',
        compute='_compute_sale_order_count',
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
        tracking=True,
        copy=False,
        readonly=True,
        check_company=True,
    )
    invoice_status = fields.Selection([
        ('not_invoiced', 'Not Invoiced'),
        ('invoiced', 'Invoiced'),
    ], string='Invoice Status', default='not_invoiced', compute='_compute_invoice_status', store=True)
    quotation_count = fields.Integer(compute='_compute_sale_stats', string='Quotations')
    sale_order_confirmed = fields.Boolean(compute='_compute_sale_stats', string='Sales Order Confirmed')
    delivery_count = fields.Integer(compute='_compute_delivery_stats', string='Deliveries')
    delivery_done_count = fields.Integer(compute='_compute_delivery_stats', string='Deliveries Done')
    product_count = fields.Integer(compute='_compute_product_count', string='Products Count')
    photo_count = fields.Integer(compute='_compute_photo_count', string='Photos Count')

    # Tags
    tag_ids = fields.Many2many(
        'field.service.tag',
        string='Tags',
    )

    # Company
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )

    # Worksheet & Signature
    worksheet_template_id = fields.Many2one(
        'fs.worksheet.template',
        string='Worksheet',
        default=lambda self: self.env['fs.worksheet.template'].search(
            [('company_id', 'in', [self.env.company.id, False])], limit=1),
        tracking=True,
        help='Worksheet the technician fills in during the intervention.',
        check_company=True,
    )
    # The fields of the worksheet are defined on its template
    worksheet_properties = fields.Properties(
        string='Worksheet Fields',
        definition='worksheet_template_id.worksheet_definition',
        copy=False,
    )
    notes = fields.Text(string='Internal Notes')

    # Settings > Equipment / Maintenance Contracts
    equipment_ids = fields.Many2many(
        'fs.equipment',
        'field_service_order_equipment_rel',
        'order_id',
        'equipment_id',
        string='Equipment',
        domain="[('partner_id', 'child_of', partner_id)]",
        tracking=True,
        check_company=True,
    )
    under_warranty = fields.Boolean(
        string='Under Warranty',
        compute='_compute_under_warranty',
        store=True,
        readonly=False,
        tracking=True,
        help='The intervention is covered by a warranty or maintenance contract: it is not invoiced.',
    )

    # Settings > Travel Fees
    travel_sale_line_id = fields.Many2one('sale.order.line', string='Travel Fee Line', copy=False, readonly=True)
    sale_line_id = fields.Many2one(
        'sale.order.line', string='Service Sold', copy=False, readonly=True, index='btree_not_null',
        help='Service of the sales order this job was generated for (Worksheet on the product).',
    )
    travel_distance = fields.Float(
        string='Travel Distance (km)',
        compute='_compute_travel',
        store=True,
        readonly=False,
        help='One-way distance from the company to the customer.',
    )
    travel_duration = fields.Float(
        string='Travel Time',
        compute='_compute_travel',
        store=True,
        readonly=False,
        help='Round-trip travel time to the customer, in hours. Invoiced when Travel Fees are enabled.',
    )
    worksheet_notes = fields.Html(
        string='Work Performed',
        sanitize_attributes=False,
        help='Details of the work performed during the service visit.',
    )
    # Signed by the customer only, on the portal (see action_send_report)
    customer_signature = fields.Binary(
        string='Customer Signature',
        copy=False,
        readonly=True,
    )
    customer_signed_by = fields.Char(
        string='Signed By',
        copy=False,
        readonly=True,
    )
    customer_signed_date = fields.Datetime(
        string='Signed Date',
        copy=False,
        readonly=True,
    )

    # Customer Rating (stored directly on the order)
    customer_rating = fields.Selection([
        ('1', '😞 Poor'),
        ('2', '😐 Below Average'),
        ('3', '🙂 Average'),
        ('4', '😊 Good'),
        ('5', '😁 Excellent'),
    ], string='Customer Rating', copy=False, tracking=True)
    rating_note = fields.Text(
        string='Rating Notes',
        copy=False,
        help='Additional feedback from the customer.',
    )
    survey_input_id = fields.Many2one(
        'survey.user_input',
        string='Survey Response',
        readonly=True,
        copy=False,
        help='The survey invitation sent to the customer upon order completion.',
    )
    is_published = fields.Boolean(
        string="Published", default=False, tracking=True,
        help="If true, the shift is published and visible to the technician."
    )

    # Computed display fields
    total_amount = fields.Float(
        string='Total Amount',
        compute='_compute_total_amount',
        store=True,
        digits='Product Price',
    )
    hourly_rate = fields.Float(
        string='Hourly Rate',
        compute='_compute_hourly_rate',
        store=False,
    )

    # -------------------------------------------------------------------------
    # DEFAULT METHODS
    # -------------------------------------------------------------------------

    def _default_stage_id(self):
        return self.env['field.service.stage'].search([], order='sequence, id', limit=1)

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        """Always show all stages in Kanban view."""
        return self.env['field.service.stage'].search([])

    @api.model
    def _read_group_employee_ids(self, employees, domain):
        """Always show all active employees in Kanban view."""
        return self.env['hr.employee'].search([])

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends('partner_id')
    def _compute_partner_info(self):
        for order in self:
            if order.partner_id:
                order.partner_phone = order.partner_id.phone
                order.partner_email = order.partner_id.email
                order.partner_address = order.partner_id.contact_address
            else:
                order.partner_phone = False
                order.partner_email = False
                order.partner_address = False

    def _compute_access_url(self):
        super()._compute_access_url()
        for order in self:
            order.access_url = f'/my/field_service/{order.id}'

    @api.depends('is_published', 'employee_id.user_id', 'extra_employee_ids.user_id')
    @api.depends_context('uid')
    def _compute_can_start_work(self):
        for order in self:
            order.can_start_work = not order._get_start_work_error()

    def _get_start_work_error(self):
        """Why the current user cannot start (or resume) the job, if they cannot.

        A saved job is only planned: it is started once published, and only
        by the technicians assigned to it.
        """
        self.ensure_one()
        if not self.is_published:
            return _("This job is not published yet. Publish it so that the technician can start it.")
        if self.env.user not in (self.employee_id | self.extra_employee_ids).user_id:
            return _("Only the technicians assigned to this job can start it.")
        return False

    def _check_can_start_work(self):
        error = self._get_start_work_error()
        if error:
            raise UserError(error)

    @api.depends('active_timer_ids.user_id')
    def _compute_is_timer_running(self):
        for order in self:
            order.is_timer_running = any(t.user_id == self.env.user for t in order.active_timer_ids)

    @api.depends('date_planned', 'date_deadline')
    def _compute_duration_planned(self):
        for order in self:
            if order.date_planned and order.date_deadline:
                diff = order.date_deadline - order.date_planned
                order.duration_planned = max(0.0, diff.total_seconds() / 3600.0)
            else:
                order.duration_planned = 0.0

    @api.depends('duration_planned', 'rest_time_planned')
    def _compute_duration_working(self):
        for order in self:
            order.duration_working_planned = max(0.0, order.duration_planned - order.rest_time_planned)

    @api.depends('timesheet_ids.duration')
    def _compute_duration_actual(self):
        for order in self:
            total = sum(order.timesheet_ids.mapped('duration'))
            order.duration_actual = total
            order.total_time_spent = total

    @api.depends('timesheet_ids')
    def _compute_timesheet_count(self):
        for order in self:
            order.timesheet_count = len(order.timesheet_ids)

    @api.depends('product_line_ids.price_subtotal')
    def _compute_total_products_amount(self):
        for order in self:
            order.total_products_amount = sum(order.product_line_ids.mapped('price_subtotal'))

    def _get_quotations(self):
        """Quotations of the job: its own sales order until it is confirmed."""
        self.ensure_one()
        return self.env['sale.order'].search([
            '|', ('id', '=', self.sale_order_id.id), ('origin', '=', self.name),
            ('state', 'in', ('draft', 'sent')),
        ]) if self.id else self.env['sale.order']

    @api.depends('sale_order_id.state')
    def _compute_sale_stats(self):
        for order in self:
            order.quotation_count = len(order._get_quotations())
            order.sale_order_confirmed = order.sale_order_id.state == 'sale'

    def _get_deliveries(self):
        """Transfers of the job's products: its own and those of its sales order lines."""
        self.ensure_one()
        pickings = self.picking_ids
        lines = self._get_sale_lines()
        if 'move_ids' in lines._fields:
            pickings |= lines.sudo().move_ids.picking_id.with_env(self.env)
        return pickings.filtered(lambda p: p.state != 'cancel')

    def _compute_delivery_stats(self):
        for order in self:
            deliveries = order._get_deliveries() if order.id else order.picking_ids
            order.delivery_count = len(deliveries)
            order.delivery_done_count = len(deliveries.filtered(lambda p: p.state == 'done'))

    @api.depends('product_line_ids')
    def _compute_product_count(self):
        for order in self:
            order.product_count = len(order.product_line_ids)

    @api.depends('service_image_ids')
    def _compute_photo_count(self):
        for order in self:
            order.photo_count = len(order.service_image_ids)

    @api.depends('sale_order_id')
    def _compute_sale_order_count(self):
        for order in self:
            order.sale_order_count = 1 if order.sale_order_id else 0

    @api.depends(
        'invoice_id.state',
        'product_line_ids.sale_order_line_id.product_uom_qty',
        'product_line_ids.sale_order_line_id.qty_invoiced',
        'travel_sale_line_id.product_uom_qty',
        'travel_sale_line_id.qty_invoiced',
    )
    def _compute_invoice_status(self):
        precision = self.env['decimal.precision'].precision_get('Product Unit')
        for order in self:
            # Billed through a sales order: invoiced once all of the job's own
            # lines are, whatever else is on the (project's) order.
            lines = order._get_sale_lines().filtered('product_uom_qty')
            if lines:
                invoiced = all(
                    float_compare(line.qty_invoiced, line.product_uom_qty, precision_digits=precision) >= 0
                    for line in lines
                )
            else:
                invoiced = bool(order.invoice_id) and order.invoice_id.state != 'cancel'
            order.invoice_status = 'invoiced' if invoiced else 'not_invoiced'

    def _compute_hourly_rate(self):
        default_rate = self.env['ir.config_parameter'].sudo().get_param(
            'hudson_field_service.default_hourly_rate', default='0.0'
        )
        try:
            rate = float(default_rate)
        except (ValueError, TypeError):
            rate = 0.0
        for order in self:
            order.hourly_rate = rate

    @api.depends('total_products_amount', 'total_time_spent', 'hourly_rate')
    def _compute_total_amount(self):
        for order in self:
            time_cost = order.total_time_spent * order.hourly_rate
            order.total_amount = order.total_products_amount + time_cost

    @api.constrains('employee_id', 'extra_employee_ids', 'date_planned', 'duration_planned')
    def _check_planning_collision(self):
        # With the Planning integration on, collisions are checked on the
        # synced planning slots, which also covers shifts from Planning.
        if self._is_planning_sync_enabled():
            return
        for order in self:
            if not order.date_planned or not order.duration_planned:
                continue
            
            assignee_ids = []
            if order.employee_id:
                assignee_ids.append(order.employee_id.id)
            if order.extra_employee_ids:
                assignee_ids.extend(order.extra_employee_ids.ids)
                
            if not assignee_ids:
                continue
                
            order_end = order.date_planned + timedelta(hours=order.duration_planned)
            
            domain = [
                ('id', '!=', order.id),
                ('state', 'not in', ('done', 'cancelled')),
                ('date_planned', '!=', False),
                '|', ('employee_id', 'in', assignee_ids), ('extra_employee_ids', 'in', assignee_ids),
            ]
            
            overlapping = self.search(domain)
            for other in overlapping:
                other_end = other.date_planned + timedelta(hours=other.duration_planned)
                if order.date_planned < other_end and order_end > other.date_planned:
                    other_assignee_ids = set(other.extra_employee_ids.ids)
                    if other.employee_id:
                        other_assignee_ids.add(other.employee_id.id)
                    conflict_users = set(assignee_ids) & other_assignee_ids
                    user_names = ", ".join(self.env['hr.employee'].browse(list(conflict_users)).mapped('name'))
                    raise ValidationError(_("Planning Collision! The following assignees are already booked during this time: %s") % user_names)

    @api.depends('equipment_ids.contract_end_date', 'date_planned')
    def _compute_under_warranty(self):
        enabled = self._fs_feature('fs_equipment') and self._fs_feature('fs_maintenance_contracts')
        for order in self:
            if not enabled:
                order.under_warranty = order.under_warranty
                continue
            day = (order.date_planned or fields.Datetime.now()).date()
            order.under_warranty = any(
                e.contract_end_date and e.contract_end_date >= day for e in order.equipment_ids
            )

    # Average road speed used to estimate travel time without Mapbox (km/h).
    _TRAVEL_SPEED = 50.0

    @api.depends('partner_id.partner_latitude', 'partner_id.partner_longitude', 'company_id')
    def _compute_travel(self):
        for order in self:
            origin = order.company_id.partner_id
            target = order.partner_id
            if not (origin.partner_latitude and origin.partner_longitude
                    and target.partner_latitude and target.partner_longitude):
                order.travel_distance = order.travel_distance or 0.0
                order.travel_duration = order.travel_duration or 0.0
                continue
            route = self._get_route(
                (origin.partner_latitude, origin.partner_longitude),
                (target.partner_latitude, target.partner_longitude),
            )
            order.travel_distance = route['distance']
            order.travel_duration = round(2 * route['duration'], 2)

    @api.model
    def _get_route(self, start, end):
        """One-way route between two (lat, lon): {'distance': km, 'duration': hours}.

        Uses Mapbox driving directions when a token is set (Settings > Mapbox),
        otherwise the straight-line distance at an average road speed.
        """
        token = self.env['ir.config_parameter'].sudo().get_str('hudson_field_service.fs_mapbox_token')
        if token:
            try:
                response = requests.get(
                    'https://api.mapbox.com/directions/v5/mapbox/driving/'
                    f'{start[1]},{start[0]};{end[1]},{end[0]}',
                    params={'access_token': token, 'overview': 'false'},
                    timeout=10,
                )
                response.raise_for_status()
                route = response.json()['routes'][0]
                return {'distance': round(route['distance'] / 1000.0, 2), 'duration': route['duration'] / 3600.0}
            except Exception as e:  # noqa: BLE001 - fall back on the estimate
                _logger.warning("Mapbox directions failed, using straight-line estimate: %s", e)
        lat1, lon1, lat2, lon2 = map(math.radians, (*start, *end))
        a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        distance = 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return {'distance': round(distance, 2), 'duration': distance / self._TRAVEL_SPEED}

    # -------------------------------------------------------------------------
    # ONCHANGE METHODS
    # -------------------------------------------------------------------------

    @api.onchange('worksheet_template_id')
    def _onchange_worksheet_template_id(self):
        """Show the fields of the new worksheet right away (values start empty)."""
        if self.worksheet_template_id != self._origin.worksheet_template_id:
            self.worksheet_properties = {}

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """Clear task when project changes."""
        if self.task_id and self.task_id.project_id != self.project_id:
            self.task_id = False

    @api.onchange('task_id')
    def _onchange_task_id(self):
        """
        When a task is assigned, automatically inherit the project, and — most
        importantly — detect the originating Sale Order from the project so that
        materials added to this FS order are billed to that SO.
        """
        if not self.task_id:
            return

        # Auto-fill project from task
        if self.task_id.project_id and not self.project_id:
            self.project_id = self.task_id.project_id

        if self.sale_order_id:
            return  # Already set — don't override

        project = self.task_id.project_id
        if not project:
            return

        # Method 1: Our custom sale_order_id field on project.project
        project_so = getattr(project, 'sale_order_id', False)
        if project_so:
            self.sale_order_id = project_so
            return

        # Method 2: sale_timesheet integration — task has sale_line_id
        task_line = getattr(self.task_id, 'sale_line_id', False)
        if task_line and task_line.order_id:
            self.sale_order_id = task_line.order_id
            return

    # -------------------------------------------------------------------------
    # CRUD OVERRIDES
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('field.service.order') or _('New')
        orders = super().create(vals_list)
        orders.with_context(fs_skip_slot_sync=True)._remove_primary_from_extra_technicians()
        orders._grant_technician_access()
        if not self.env.context.get('fs_skip_slot_sync'):
            orders._sync_planning_slots()
        return orders

    _CUSTOMER_SIGNATURE_FIELDS = ('customer_signature', 'customer_signed_by', 'customer_signed_date')

    # Who does the job, when and for whom: planned by the administrators
    _PLANNING_MANAGER_FIELDS = {
        'employee_id', 'extra_employee_ids', 'date_planned', 'date_deadline', 'duration_planned',
        'rest_time_planned', 'is_published', 'active', 'role_id', 'partner_id', 'company_id',
    }

    @api.onchange('employee_id')
    def _onchange_employee_id_planning(self):
        """The primary technician is not also an extra one; the role of the
        job is the default role of its technician."""
        employee = self.employee_id._origin
        if not employee:
            return
        if employee in self.extra_employee_ids._origin:
            self.extra_employee_ids = self.extra_employee_ids.filtered(lambda e: e._origin != employee)
        if not self.role_id or self.role_id._origin not in employee.sudo().planning_role_ids:
            role = employee.sudo()._get_default_planning_role()
            if role:
                self.role_id = role

    @api.onchange('extra_employee_ids')
    def _onchange_extra_employee_ids(self):
        employee = self.employee_id._origin
        if employee and employee in self.extra_employee_ids._origin:
            self.extra_employee_ids = self.extra_employee_ids.filtered(lambda e: e._origin != employee)

    def _grant_technician_access(self):
        """Technicians assigned to a job get Field Service / User rights, to
        start it (timer, location), fill the worksheet... from their shift:
        like Odoo, field service work is done by Field Service users. The
        rights cover only their own published jobs."""
        group = self.env.ref('hudson_field_service.group_field_service_user', raise_if_not_found=False)
        if not group:
            return
        for order in self:
            users = (order.employee_id | order.extra_employee_ids).sudo().user_id.filtered(
                lambda u: not u.share and group not in u.all_group_ids)
            if not users:
                continue
            # sudo: planners assign technicians without managing user rights.
            users.sudo().write({'group_ids': [(4, group.id)]})
            order.sudo().message_post(body=_(
                "Field Service access given to %s to work on their jobs.", ', '.join(users.mapped('name'))))

    def _remove_primary_from_extra_technicians(self):
        """The primary technician is never also an extra technician (e.g. the
        shift of an extra technician moved to the primary one)."""
        for order in self:
            if order.employee_id and order.employee_id in order.extra_employee_ids:
                order.write({'extra_employee_ids': [Command.unlink(order.employee_id.id)]})

    def write(self, vals):
        if not self.env.context.get('fs_customer_signing') and any(f in vals for f in self._CUSTOMER_SIGNATURE_FIELDS):
            raise UserError(_("The report can only be signed by the customer, from the link sent by email."))
        if (not self.env.su and self._PLANNING_MANAGER_FIELDS & vals.keys()
                and not self.env.user.has_group('hudson_planning.group_planning_manager')):
            raise AccessError(_("Only Planning administrators can change who does the job, when, and for whom."))
        # Auto-transition to scheduled when user and date are set
        result = super().write(vals)
        if 'employee_id' in vals or 'date_planned' in vals:
            for order in self:
                if order.state == 'new' and order.employee_id and order.date_planned:
                    order.state = 'scheduled'
        if 'employee_id' in vals or 'extra_employee_ids' in vals:
            self._remove_primary_from_extra_technicians()
            self._grant_technician_access()
        # fs_skip_slot_sync: the job is being created from its shift, which
        # syncs once created (e.g. the quotation of products set at creation).
        if self._PLANNING_SYNC_FIELDS & vals.keys() and not self.env.context.get('fs_skip_slot_sync'):
            self._sync_planning_slots()
        return result

    # -------------------------------------------------------------------------
    # PLANNING SYNC
    # -------------------------------------------------------------------------

    # Order fields that are mirrored on the planning slots.
    _PLANNING_SYNC_FIELDS = {
        'employee_id', 'extra_employee_ids', 'date_planned', 'date_deadline', 'duration_planned',
        'state', 'active', 'is_published', 'name', 'title', 'role_id', 'partner_id',
        'project_id', 'task_id', 'sale_order_id', 'company_id', 'rest_time_planned',
    }

    @api.model
    def _is_planning_sync_enabled(self):
        return self.env['ir.config_parameter'].sudo().get_bool('hudson_field_service.fs_planning_enabled', True)

    def _get_planning_interval(self):
        """Return the planned (start, end) of the job, or (False, False)."""
        self.ensure_one()
        start = self.date_planned
        end = self.date_deadline
        if not end and start and self.duration_planned:
            end = start + timedelta(hours=self.duration_planned)
        if not start or not end or end <= start:
            return False, False
        return start, end

    def _get_assignees(self):
        self.ensure_one()
        return self.employee_id | self.extra_employee_ids

    def _prepare_planning_slot_values(self):
        self.ensure_one()
        start, end = self._get_planning_interval()
        return {
            'name': f'{self.name} - {self.title}' if self.title else self.name,
            'date_start': start,
            'date_end': end,
            'role_id': self.role_id.id,
            'partner_id': self.partner_id.id,
            'project_id': self.project_id.id,
            'task_id': self.task_id.id,
            'sale_order_id': self.sale_order_id.id,
            'company_id': self.company_id.id,
            'break_hours': self.rest_time_planned,
            'state': 'published' if self.is_published else 'draft',
        }

    def _sync_planning_slots(self):
        """Mirror each order as one planning slot per assigned technician; a
        planned order without technician is one open shift (an open job, e.g.
        after its technician unassigned themselves), to assign from the schedule."""
        if not self._is_planning_sync_enabled():
            return
        Slot = self.env['fs.planning.slot'].sudo().with_context(fs_slot_sync=True, active_test=False)
        no_one = self.env['hr.employee']
        for order in self:
            existing = Slot.search([('field_service_order_id', '=', order.id)])
            start, end = order._get_planning_interval()
            planned = bool(start and order.active and order.state != 'cancelled')
            assignees = order._get_assignees() if planned else no_one
            # The resources of the shifts: the technicians, or no one (open shift)
            targets = list(assignees) or ([no_one] if planned else [])

            slot_by_employee = {}
            to_remove = Slot
            for slot in existing:
                wanted = slot.resource_id in assignees if slot.resource_id else (planned and not assignees)
                if wanted and slot.resource_id.id not in slot_by_employee:
                    slot_by_employee[slot.resource_id.id] = slot
                else:
                    to_remove |= slot
            # Free the technicians that were unassigned before re-checking overlaps.
            to_remove.unlink()

            vals = order._prepare_planning_slot_values()
            for employee in targets:
                slot = slot_by_employee.get(employee.id)
                if not slot:
                    Slot.create(dict(vals, resource_id=employee.id, field_service_order_id=order.id))
                    continue
                # Only write what changed, so unrelated order updates (timer,
                # location...) don't re-run the overlap check on legacy data.
                changed = {}
                for fname, value in vals.items():
                    current = slot[fname]
                    if slot._fields[fname].type == 'many2one':
                        current = current.id
                    if current != value:
                        changed[fname] = value
                if changed:
                    slot.write(changed)

    @api.model
    def _resync_all_planning_slots(self):
        """Rebuild (or remove, if the integration is off) the slots of all orders."""
        if not self._is_planning_sync_enabled():
            self.env['fs.planning.slot'].sudo().with_context(fs_slot_sync=True, active_test=False).search([
                ('field_service_order_id', '!=', False),
            ]).unlink()
            return
        # force_generate: existing data may already overlap; don't block on it.
        orders = self.sudo().with_context(active_test=False, force_generate=True).search([])
        orders._sync_planning_slots()

    @api.depends('employee_id', 'extra_employee_ids', 'date_planned', 'date_deadline', 'duration_planned', 'role_id', 'state')
    def _compute_planning_availability(self):
        Slot = self.env['fs.planning.slot'].sudo()
        Employee = self.env['hr.employee']
        sync_enabled = self._is_planning_sync_enabled()
        for order in self:
            order.planning_warning = False
            order.available_employee_ids = Employee
            start, end = order._get_planning_interval()
            if not sync_enabled or not start or order.state in ('done', 'cancelled'):
                continue

            candidates = order.role_id.resource_ids or Employee.search([
                ('company_id', 'in', [order.company_id.id, False]),
            ])
            assignees = order._get_assignees()
            employees = candidates | assignees
            # Any other shift or job of a technician at that time is a conflict:
            # a technician cannot do two things at once.
            slots = Slot.search([
                ('resource_id', 'in', employees.ids),
                ('date_start', '<', end),
                ('date_end', '>', start),
            ])
            if order._origin:
                slots = slots.filtered(lambda s: s.field_service_order_id != order._origin)

            def fmt(dt):
                return fields.Datetime.context_timestamp(order, dt).strftime('%Y-%m-%d %H:%M')

            warnings = []
            available = Employee
            for employee in employees:
                emp_slots = slots.filtered(lambda s: s.resource_id == employee)
                conflicts = emp_slots
                has_role = not order.role_id.resource_ids or employee in order.role_id.resource_ids

                if employee in candidates and not conflicts:
                    available |= employee
                if employee not in assignees:
                    continue
                for conflict in conflicts:
                    warnings.append(_(
                        "%(employee)s is already booked on %(booking)s (%(start)s - %(end)s).",
                        employee=employee.name,
                        booking=conflict._get_booking_label(),
                        start=fmt(conflict.date_start),
                        end=fmt(conflict.date_end),
                    ))
                if not has_role:
                    warnings.append(_("%(employee)s does not have the role %(role)s.", employee=employee.name, role=order.role_id.name))
            order.planning_warning = '\n'.join(warnings) or False
            order.available_employee_ids = available

    @api.model
    def get_board_shifts(self, date_from, date_to):
        """Planning shifts (not jobs) shown as availability on the Field Service board."""
        if not self._is_planning_sync_enabled():
            return []
        Slot = self.env['fs.planning.slot']
        if self.env.user.has_group('hudson_planning.group_planning_manager'):
            # sudo: dispatchers need to see shifts without Planning access rights.
            Slot = Slot.sudo()
        shifts = Slot.search([
            ('field_service_order_id', '=', False),
            ('resource_id', '!=', False),
            ('date_start', '<', date_to),
            ('date_end', '>', date_from),
            ('company_id', 'in', self.env.companies.ids),
        ])
        return shifts.read(['id', 'name', 'resource_id', 'role_id', 'date_start', 'date_end', 'allocated_hours', 'partner_id'])

    def _publish_orders(self):
        """Publish the orders, notify the primary technician and confirm to the customer."""
        template = self.env.ref('hudson_field_service.mail_template_field_service_publish', raise_if_not_found=False)
        confirmation = self._get_confirmation_template()
        for order in self:
            order.is_published = True
            if template and order.employee_id and (order.employee_id.work_contact_id or order.employee_id.user_id.partner_id):
                template.send_mail(order.id, force_send=False)
            if confirmation and order.partner_id.email:
                confirmation.send_mail(order.id, force_send=False)
                order.message_post(body=_("Confirmation email sent to %s.", order.partner_id.email))

    @api.model
    def _get_confirmation_template(self):
        """Settings > Confirmation Email: template sent to the customer on publish, if enabled."""
        ICP = self.env['ir.config_parameter'].sudo()
        if not ICP.get_bool('hudson_field_service.fs_confirmation_email', True):
            return self.env['mail.template']
        template = self.env['mail.template'].browse(ICP.get_int('hudson_field_service.fs_confirmation_template_id')).exists()
        return template or self.env.ref('hudson_field_service.mail_template_fs_shift_confirmation', raise_if_not_found=False) \
            or self.env['mail.template']

    # -------------------------------------------------------------------------
    # SALE ORDER SYNC
    # -------------------------------------------------------------------------

    def _get_sale_lines(self):
        """Sales order lines billing this job (products and travel)."""
        self.ensure_one()
        return (self.product_line_ids.sale_order_line_id | self.travel_sale_line_id).exists()

    def _get_project_sale_order(self):
        """Sales order the job's task or project is sold on, if any."""
        self.ensure_one()
        task_line = getattr(self.task_id, 'sale_line_id', False)
        sale_order = (task_line and task_line.order_id) or self.project_id.sale_order_id
        return sale_order.filtered(lambda so: so.state != 'cancel')

    def _get_billing_sale_order(self):
        """Sales order the job's products are billed on, created if needed.

        The job's own sales order, else the one of its project or task, else
        a new quotation (Settings > Bill products through a sales order).
        """
        self.ensure_one()
        # sudo: technicians bill their job without sales rights.
        sale_order = self.sudo().sale_order_id.filtered(lambda so: so.state != 'cancel') or self.sudo()._get_project_sale_order()
        auto_so = self.env['ir.config_parameter'].sudo().get_bool('hudson_field_service.fs_auto_sale_order', True)
        if not sale_order and auto_so and self.partner_id:
            # sudo: technicians bill their job without sales rights.
            sale_order = self.env['sale.order'].sudo().with_company(self.company_id).create({
                'partner_id': self.partner_id.id,
                'company_id': self.company_id.id,
                'origin': self.name,
                'note': _('Auto-created from Field Service Order %s', self.name),
            })
            self.message_post(body=_("Quotation %s created.", sale_order._get_html_link()))
        if sale_order != self.sale_order_id:
            self.sudo().write({'sale_order_id': sale_order.id})
        return sale_order

    def _sync_sale_orders(self):
        for order in self:
            order._sync_products_to_sale_order()

    def _sync_products_to_sale_order(self):
        """Bill the job's products (and travel) through a sales order.

        Each product line is mirrored by a sales order line. Lines already
        invoiced keep their price: added quantities and products make the
        order "to invoice" again for the difference only, so a posted or paid
        invoice is never billed twice.
        """
        self.ensure_one()
        if not self._fs_feature('fs_billing') or self.under_warranty:
            return
        travel_product = self._get_travel_product()
        if not self.product_line_ids and not travel_product:
            return
        sale_order = self._get_billing_sale_order()
        if not sale_order:
            return

        # sudo: technicians bill their job without sales rights; a locked
        # (confirmed) order is reopened just for the job's lines.
        sale_order = sale_order.sudo()
        locked = sale_order.locked
        if locked:
            sale_order.action_unlock()
        SaleLine = self.env['sale.order.line'].sudo()
        for fs_line in self.product_line_ids:
            so_line = fs_line.sale_order_line_id.sudo().exists()
            if so_line.order_id != sale_order:
                so_line = SaleLine
            if so_line and so_line.product_id == fs_line.product_id:
                vals = {'product_uom_qty': fs_line.quantity}
                if not so_line.qty_invoiced:
                    vals['price_unit'] = fs_line.price_unit
                vals = {f: v for f, v in vals.items() if so_line[f] != v}
                if vals:
                    so_line.write(vals)
                continue
            if so_line:
                # Product replaced: the old line is cancelled (credited if invoiced).
                so_line.product_uom_qty = 0
            so_line = SaleLine.create({
                'order_id': sale_order.id,
                'product_id': fs_line.product_id.id,
                'name': fs_line.description or fs_line.product_id.display_name,
                'product_uom_qty': fs_line.quantity,
                'price_unit': fs_line.price_unit,
                'product_uom_id': (fs_line.uom_id or fs_line.product_id.uom_id).id,
            })
            fs_line.sudo().write({'sale_order_line_id': so_line.id})

        # ── Settings > Travel Fees: round-trip travel time ──────────────────
        if travel_product:
            travel_vals = {
                'product_uom_qty': self.travel_duration,
                'name': _('Travel to %(customer)s (%(distance)s km)', customer=self.partner_id.display_name, distance=self.travel_distance),
            }
            travel_line = self.travel_sale_line_id.sudo().exists()
            if travel_line and travel_line.order_id == sale_order:
                travel_line.write(travel_vals)
            else:
                line = SaleLine.create(dict(travel_vals, order_id=sale_order.id, product_id=travel_product.id))
                self.sudo().write({'travel_sale_line_id': line.id})

        if self.state == 'done':
            self._deliver_sale_lines()
        if locked:
            sale_order.action_lock()

    def _deliver_sale_lines(self):
        """Once the job is done, its quotation is confirmed and what was used
        is delivered, so that it can be invoiced."""
        self.ensure_one()
        sale_order = self.sale_order_id.sudo()
        if not sale_order or not self._get_sale_lines():
            return
        if sale_order.state in ('draft', 'sent'):
            sale_order.action_confirm()
        if sale_order.state != 'sale':
            return
        for fs_line in self.product_line_ids:
            so_line = fs_line.sale_order_line_id.sudo().exists()
            if so_line.qty_delivered_method == 'manual' and so_line.qty_delivered != fs_line.quantity:
                so_line.qty_delivered = fs_line.quantity
        travel_line = self.travel_sale_line_id.sudo().exists()
        if travel_line.qty_delivered_method == 'manual' and travel_line.qty_delivered != travel_line.product_uom_qty:
            travel_line.qty_delivered = travel_line.product_uom_qty
        self._validate_sale_deliveries()

    def _validate_sale_deliveries(self):
        """Validate the job's moves in the transfers of its sales order (sale_stock):
        what the technician used is delivered, the rest of the transfer is
        kept as a backorder."""
        lines = self._get_sale_lines().sudo()
        if 'move_ids' not in lines._fields:
            return
        moves = lines.move_ids.filtered(lambda m: m.state not in ('done', 'cancel') and m.picking_id)
        for picking in moves.picking_id:
            job_moves = moves.filtered(lambda m: m.picking_id == picking)
            for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
                if move in job_moves:
                    move.quantity = move.product_uom_qty
                    move.picked = True
                else:
                    move.quantity = 0
                    move.picked = False
            picking._action_done()

    def _get_travel_product(self):
        """Product invoicing the travel time, when travel fees apply to this job."""
        self.ensure_one()
        travel_fees = self._fs_feature('fs_billing') and self._fs_feature('fs_travel_fees')
        if not travel_fees or self.under_warranty or not self.travel_duration:
            return self.env['product.product']
        ICP = self.env['ir.config_parameter'].sudo()
        product = self.env['product.product'].browse(ICP.get_int('hudson_field_service.fs_travel_product_id')).exists()
        if not product:
            # Created on first use rather than as module data: modules loaded
            # after this one (e.g. website_sale) add required product columns
            # that are unknown while this module's data is loaded.
            product = self.env['product.product'].sudo().create({
                'name': self.env._("Travel Fees"),
                'type': 'service',
                'list_price': 30.0,
                'uom_id': self.env.ref('uom.product_uom_hour').id,
                'sale_ok': True,
                'purchase_ok': False,
            })
            ICP.set_int('hudson_field_service.fs_travel_product_id', product.id)
        return product

    # -------------------------------------------------------------------------
    # ACTION METHODS — TIMER
    # -------------------------------------------------------------------------
    def _format_location_message(self, event_label, latitude, longitude):
        """Format a rich chatter message with coordinates and a map button."""
        map_url = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
        return Markup(
            f'<div style="padding: 8px 0;">'
            f'<b>📍 {event_label}</b><br/>'
            f'<span style="color: #666;">Coordinates: {latitude:.6f}, {longitude:.6f}</span><br/>'
            f'<a href="{map_url}" target="_blank" '
            f'style="display: inline-block; margin-top: 4px; padding: 4px 12px; '
            f'background-color: #017e84; color: white; border-radius: 4px; '
            f'text-decoration: none; font-size: 13px; font-weight: bold; '
            f'box-shadow: 0 1px 3px rgba(0,0,0,0.15);">'
            f'<i class="fa fa-map-marker"></i> Open in Google Maps</a>'
            f'</div>'
        )


    def _check_sign_in_radius(self, latitude, longitude):
        """Settings > Geolocation > Radius Sign In: start work only at the customer's."""
        ICP = self.env['ir.config_parameter'].sudo()
        if not (self._fs_feature('fs_geolocation') and ICP.get_bool('hudson_field_service.fs_radius_validation')):
            return
        partner = self.partner_id
        if not (partner.partner_latitude and partner.partner_longitude):
            return
        if not (latitude and longitude):
            raise UserError(_("Your location is required to start this job. Allow location access in your browser."))
        radius = ICP.get_float('hudson_field_service.fs_location_radius', 500.0) or 500.0
        distance = self._distance_km((latitude, longitude), (partner.partner_latitude, partner.partner_longitude))
        if distance * 1000 > radius:
            raise UserError(_(
                "You are %(distance)s m away from the customer: you can only start the job within %(radius)s m.",
                distance=round(distance * 1000), radius=round(radius),
            ))

    @api.model
    def _distance_km(self, start, end):
        lat1, lon1, lat2, lon2 = map(math.radians, (*start, *end))
        a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def action_start_timer_with_location(self, latitude=0.0, longitude=0.0):
        self.ensure_one()
        if self.state not in ('new', 'scheduled', 'in_progress', 'paused'):
            raise UserError(_("You can only start an active order."))
        self._check_can_start_work()
        if self.is_timer_running:
            raise UserError(_("Timer is already running for you."))
            
        self._check_sign_in_radius(latitude, longitude)

        now = fields.Datetime.now()
        
        self.env['field.service.active.timer'].create({
            'order_id': self.id,
            'user_id': self.env.user.id,
            'start_time': now,
            'current_latitude': latitude,
            'current_longitude': longitude,
        })
        
        self.write({
            'state': 'in_progress',
            'date_start': now if not self.date_start else self.date_start,
        })
        return True

    def action_update_current_location(self, latitude=0.0, longitude=0.0):
        """
        Called periodically by the frontend to update the technician's live
        position on the map.  Only writes if the values have actually changed
        (avoids unnecessary DB writes on every poll).
        """
        self.ensure_one()
        if not latitude or not longitude:
            return True
        if (abs(self.current_latitude - latitude) > 0.00001
                or abs(self.current_longitude - longitude) > 0.00001):
            self.write({
                'current_latitude': latitude,
                'current_longitude': longitude,
                'last_location_update': fields.Datetime.now(),
            })
        return True

    def action_log_location(self, latitude=0.0, longitude=0.0, event_label="Location Logged"):
        """Called by the frontend widget to log location in chatter."""
        self.ensure_one()
        if latitude and longitude:
            self.write({
                'start_latitude': latitude,
                'start_longitude': longitude,
                'current_latitude': latitude,
                'current_longitude': longitude,
                'last_location_update': fields.Datetime.now(),
            })
            self.message_post(body=self._format_location_message(
                event_label, latitude, longitude
            ))
        return True

    def action_pause_timer(self):
        self.ensure_one()
        if not self.is_timer_running:
            raise UserError(_("Timer is not running for you."))
        return self._open_stop_wizard(action='pause')

    def _create_stock_deduction(self):
        """Create and validate a stock.picking for materials used if enabled."""
        self.ensure_one()
        IrConfigParam = self.env['ir.config_parameter'].sudo()
        if IrConfigParam.get_param('hudson_field_service.fs_stock_deduction') != 'True':
            return
            
        picking_type_id = int(IrConfigParam.get_param('hudson_field_service.fs_default_picking_type_id', 0))
        if not picking_type_id:
            return
            
        # sudo: technicians complete their jobs without inventory rights
        Picking = self.env['stock.picking'].sudo().with_company(self.company_id)
        picking_type = Picking.env['stock.picking.type'].browse(picking_type_id).exists()
        if picking_type.company_id and picking_type.company_id != self.company_id:
            # The configured operation type is another company's: use this company's deliveries
            picking_type = Picking.env['stock.picking.type'].search([
                ('code', '=', 'outgoing'), ('company_id', '=', self.company_id.id),
            ], limit=1)
        if not picking_type:
            return

        # Get storable or consumable products
        def delivered_by_sale_order(line):
            # Delivered by the sales order's own transfer (sale_stock)
            so_line = line.sale_order_line_id.sudo()
            return 'move_ids' in so_line._fields and bool(so_line.move_ids)

        valid_lines = self.product_line_ids.filtered(
            lambda l: l.product_id.type in ['product', 'consu'] and l.quantity > 0 and not delivered_by_sale_order(l)
        )
        if not valid_lines:
            return
            
        vehicle = self.employee_id.sudo().fs_vehicle_location_id
        if vehicle.company_id and vehicle.company_id != self.company_id:
            vehicle = vehicle.browse()
        picking = Picking.create({
            'partner_id': self.partner_id.id,
            'picking_type_id': picking_type.id,
            # Settings > Stock by Vehicle: parts come from the technician's vehicle
            'location_id': (vehicle or picking_type.default_location_src_id).id,
            'location_dest_id': picking_type.default_location_dest_id.id or self.partner_id.property_stock_customer.id,
            'fs_order_id': self.id,
            'origin': self.name,
        })
        
        move_vals = []
        for line in valid_lines:
            move_vals.append({
                'description_picking': line.description or line.product_id.name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity,
                'uom_id': line.uom_id.id or line.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': picking.location_id.id,
                'location_dest_id': picking.location_dest_id.id,
            })
            
        Picking.env['stock.move'].create(move_vals)
        picking.action_confirm()
        picking.action_assign()
        # Automatically validate the transfer
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()

    def action_stop_timer(self):
        self.ensure_one()
        if not self.is_timer_running:
            raise UserError(_("Timer is not running for you."))
        return self._open_stop_wizard(action='stop')

    def action_resume_timer(self):
        """Fallback resume without location."""
        self.ensure_one()
        if self.state != 'paused':
            raise UserError(_("You can only resume a paused order."))
        if self.is_timer_running:
            raise UserError(_("Timer is already running."))
        self._check_can_start_work()
        
        now = fields.Datetime.now()
        vals = {
            'state': 'in_progress',
        }
        if self.last_paused_time:
            elapsed_rest = (now - self.last_paused_time).total_seconds() / 3600.0
            vals['rest_time_actual'] = self.rest_time_actual + elapsed_rest
            vals['last_paused_time'] = False
            
        self.write(vals)
        return True

    def action_resume_timer_with_location(self, latitude=0.0, longitude=0.0):
        return self.action_start_timer_with_location(latitude, longitude)

    def _open_stop_wizard(self, action='pause'):
        active_timer = self.env['field.service.active.timer'].search([
            ('order_id', '=', self.id),
            ('user_id', '=', self.env.user.id)
        ], limit=1)
        
        now = fields.Datetime.now()
        elapsed = (now - active_timer.start_time).total_seconds() / 3600.0 if active_timer else 0.0
        return {
            'name': _('Stop Timer'),
            'type': 'ir.actions.act_window',
            'res_model': 'field.service.stop.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_duration': round(elapsed, 2),
                'default_start_time': active_timer.start_time if active_timer else False,
                'default_end_time': now,
                'default_action_type': action,
            }
        }

    # -------------------------------------------------------------------------
    # ACTION METHODS — WORKFLOW
    # -------------------------------------------------------------------------

    def action_view_rating(self):
        return True

    def action_mark_done(self):
        """Complete the job: its products are billed and delivered."""
        self.ensure_one()
        # If timer is running, stop it first
        if self.is_timer_running:
            return self._open_stop_wizard(action='stop')
        # sudo: the timers of the other technicians are private to them
        if self.env['field.service.active.timer'].sudo().search_count([('order_id', '=', self.id)]):
            raise UserError(_("Other technicians are still working. All timers must be stopped before completing the job."))

        self.write({
            'state': 'done',
            'date_end': fields.Datetime.now(),
        })

        # Move to the closing stage if one exists
        close_stage = self.env['field.service.stage'].search([('is_close', '=', True)], limit=1)
        if close_stage:
            self.stage_id = close_stage

        # Bill the products: the quotation is confirmed and its deliveries validated
        self._sync_products_to_sale_order()
        self._create_stock_deduction()

        # Send customer satisfaction survey if enabled
        self._send_rating_survey()

    def _send_rating_survey(self):
        """
        Send the satisfaction survey to the customer if the feature is enabled
        and the order has a customer with an email address.
        """
        IrConfig = self.env['ir.config_parameter'].sudo()
        if IrConfig.get_param('hudson_field_service.fs_customer_ratings', 'False') != 'True':
            return
        if not self.partner_id or not self.partner_id.email:
            return

        # Resolve the survey to use
        survey_id_param = IrConfig.get_param('hudson_field_service.fs_rating_survey_id', False)
        survey = False
        if survey_id_param and str(survey_id_param).isdigit():
            survey = self.env['survey.survey'].browse(int(survey_id_param)).exists()
        if not survey:
            # Fall back to the default survey shipped with the module
            survey = self.env.ref(
                'hudson_field_service.field_service_satisfaction_survey',
                raise_if_not_found=False,
            )
        if not survey:
            return

        # Create a unique survey input (token) for this customer
        survey_input = survey.sudo()._create_answer(
            partner=self.partner_id,
            check_attempts=False,
        )
        self.sudo().survey_input_id = survey_input

        # Send the rating email
        template = self.env.ref(
            'hudson_field_service.mail_template_fs_rating',
            raise_if_not_found=False,
        )
        if template:
            template.sudo().send_mail(self.id, force_send=True)
            self.message_post(
                body=_("Customer Satisfaction Survey sent to %s.") % self.partner_id.email,
                message_type='notification'
            )

    def action_cancel(self):
        """Cancel the field service order."""
        self.ensure_one()
        if self.is_timer_running:
            raise UserError(_("You must stop the timer before cancelling."))
        self.write({'state': 'cancelled'})

    def action_unschedule(self):
        """Take a job that has not started off the schedule: its dates and
        technicians are cleared (removing its shifts), the job itself is kept."""
        self.ensure_one()
        if not self.env.user.has_group('hudson_field_service.group_field_service_manager'):
            raise UserError(_("Only field service administrators can unschedule a job."))
        if self.state not in ('new', 'scheduled'):
            raise UserError(_("Only jobs that have not started can be unscheduled."))
        self.write({
            'date_planned': False,
            'date_deadline': False,
            'employee_id': False,
            'extra_employee_ids': [Command.clear()],
            'is_published': False,
            'state': 'new',
        })
        self.message_post(body=_("Unscheduled from the planning."))

    def action_reset_to_new(self):
        """Reset a cancelled/done order back to new."""
        self.ensure_one()
        self.write({
            'state': 'new',
            'date_start': False,
            'date_end': False,
            'is_published': False,
        })
        new_stage = self.env['field.service.stage'].search([], order='sequence, id', limit=1)
        if new_stage:
            self.stage_id = new_stage

    def action_publish_order(self):
        """Publish the order, making it visible to the technician and sending an email.
           Validates overlaps and working hours before publishing."""
        
        # Collect warnings
        warnings = []
        for order in self:
            if not order.date_planned or not order.date_deadline:
                continue
            
            # Check overlap for employees
            domain = [
                ('id', '!=', order.id),
                ('date_planned', '<', order.date_deadline),
                ('date_deadline', '>', order.date_planned),
                ('is_published', '=', True),
            ]
            if order.employee_id:
                emp_domain = domain + [('employee_id', '=', order.employee_id.id)]
                overlapping = self.env['field.service.order'].search(emp_domain, limit=1)
                if overlapping:
                    warnings.append(f"Employee {order.employee_id.name} is double-booked with '{overlapping.name}'.")
            
            # Check overlap for materials
            if order.material_ids:
                for mat in order.material_ids:
                    mat_domain = domain + [('material_ids', 'in', [mat.id])]
                    overlapping = self.env['field.service.order'].search(mat_domain, limit=1)
                    if overlapping:
                        warnings.append(f"Material {mat.name} is double-booked with '{overlapping.name}'.")
                        
            # Check working hours (duration > standard)
            if order.employee_id and order.employee_id.resource_calendar_id:
                # Roughly check hours per day
                hours = order.employee_id.resource_calendar_id.hours_per_day or 8.0
                if order.duration_planned > hours:
                    warnings.append(f"Order '{order.name}' exceeds the daily working hours ({hours}h) for {order.employee_id.name}.")

        if warnings:
            # Open wizard
            wizard = self.env['fs.order.publish.wizard'].create({
                'order_ids': [(6, 0, self.ids)],
                'warning_message': "\n".join(warnings)
            })
            return {
                'name': _('Validation Warnings'),
                'type': 'ir.actions.act_window',
                'res_model': 'fs.order.publish.wizard',
                'res_id': wizard.id,
                'view_mode': 'form',
                'target': 'new',
            }
            
        # Proceed with normal publish
        self.filtered(lambda o: not o.is_published)._publish_orders()


    # -------------------------------------------------------------------------
    # ACTION METHODS — INVOICE
    # -------------------------------------------------------------------------

    def action_create_invoice(self):
        """
        Open the invoice creation flow.

        - If linked to a Sale Order: sync products first, then invoice what is
          left to invoice on that SO (see _invoice_sale_order).
        - If standalone (no SO): fall back to our custom wizard.
        """
        self.ensure_one()
        if not self._fs_feature('fs_billing'):
            raise UserError(_('Billing is disabled in the settings.'))
        if self.under_warranty:
            raise UserError(_('This intervention is under warranty: it is not invoiced.'))
        if self.invoice_status == 'invoiced':
            raise UserError(_('This order is already invoiced!'))
        if not self.partner_id:
            raise UserError(_('Please set a customer before creating an invoice.'))

        # Route through the sales order when the job's products are billed on one
        self._sync_products_to_sale_order()
        if self.sale_order_id:
            return self._invoice_sale_order()

        # Standalone: use our custom wizard
        return {
            'name': _('Create Invoice'),
            'type': 'ir.actions.act_window',
            'res_model': 'field.service.create.invoice.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_include_time': True,
                'default_include_products': True,
            },
        }

    def _invoice_sale_order(self):
        """Invoice what is left to invoice on the job's sales order.

        A draft invoice of the order is completed instead of creating another
        one. Posted or paid invoices are never modified: products added since
        go on a new invoice for the difference only, as Odoo does for any
        sales order (a reduced quantity is credited).
        """
        self.ensure_one()
        self._deliver_sale_lines()
        # sudo: the job's technician may invoice without accounting rights.
        sale_order = self.sale_order_id.sudo()
        lines = sale_order._get_invoiceable_lines(final=True)
        draft = sale_order.invoice_ids.filtered(lambda m: m.state == 'draft' and m.move_type == 'out_invoice')[:1]
        if draft:
            lines = lines.filtered(lambda l: not l.display_type and not l.is_downpayment)
            if lines:
                sequence = max(draft.invoice_line_ids.mapped('sequence'), default=0)
                draft.write({'invoice_line_ids': [
                    Command.create(line._prepare_invoice_line(sequence=sequence + i))
                    for i, line in enumerate(lines, start=1)
                ]})
            invoice = draft
        elif lines:
            invoice = sale_order._create_invoices(final=True)[:1]
        else:
            invoice = self._get_sale_lines().invoice_lines.move_id.filtered(lambda m: m.state != 'cancel')[-1:]
            if not invoice:
                raise UserError(_(
                    "There is nothing to invoice on %s yet: products invoiced on delivered "
                    "quantities are invoiced once they are delivered.", sale_order.display_name,
                ))
        self.sudo().invoice_id = invoice
        return self.action_view_invoice()

    def action_view_invoice(self):
        """Open the linked invoice."""
        self.ensure_one()
        if self.invoice_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': self.invoice_id.id,
                'target': 'current',
            }

    def action_view_sale_order(self):
        """Open the linked sale order."""
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_('No sale order is linked to this field service order.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.sale_order_id.id,
            'target': 'current',
        }

    def action_send_report(self):
        """Email the report to the customer.

        Until the customer has signed it, the email asks them to review and
        sign it online: the report is never signed on the technician's device.
        """
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_("The report can be sent once the job is completed."))
        if not self.partner_id.email:
            raise UserError(_("Set an email address on the customer %s to send the report.", self.partner_id.display_name))
        if self.customer_signature or not self._fs_feature('fs_customer_signature'):
            template = self.env.ref('hudson_field_service.mail_template_field_service_report', raise_if_not_found=False)
        else:
            template = self.env.ref('hudson_field_service.mail_template_fs_signature_request', raise_if_not_found=False)

        ctx = {
            'default_model': 'field.service.order',
            'default_res_ids': self.ids,
            'default_template_id': template.id if template else False,
            'default_use_template': bool(template),
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
            'force_email': True,
        }
        return {
            'name': _('Send Report'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'view_id': False,
            'target': 'new',
            'context': ctx,
        }

    # -------------------------------------------------------------------------
    # ACTION METHODS — NAVIGATION
    # -------------------------------------------------------------------------

    def action_view_timesheets(self):
        """Open related timesheets."""
        self.ensure_one()
        return {
            'name': _('Time Entries'),
            'type': 'ir.actions.act_window',
            'res_model': 'field.service.timesheet',
            'view_mode': 'list,form',
            'domain': [('order_id', '=', self.id)],
            'context': {'default_order_id': self.id},
        }

    def action_view_project_task(self):
        """Navigate to the linked project task."""
        self.ensure_one()
        if self.task_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'project.task',
                'view_mode': 'form',
                'res_id': self.task_id.id,
                'target': 'current',
            }

    # -------------------------------------------------------------------------
    # HELPER METHODS
    # -------------------------------------------------------------------------

    def _format_duration(self, hours):
        """Format hours as HH:MM string."""
        h = int(hours)
        m = int((hours - h) * 60)
        return f'{h:02d}:{m:02d}'

    def action_view_pickings(self):
        self.ensure_one()
        deliveries = self._get_deliveries()
        action = {
            'name': _('Deliveries'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'domain': [('id', 'in', deliveries.ids)],
            'context': {'create': False},
        }
        if len(deliveries) == 1:
            return dict(action, view_mode='form', views=[(False, 'form')], res_id=deliveries.id)
        return dict(action, view_mode='list,form', views=[(False, 'list'), (False, 'form')])

    def action_view_quotations(self):
        self.ensure_one()
        quotations = self._get_quotations()
        action = {
            'name': _('Quotations'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'domain': [('id', 'in', quotations.ids)],
            # New quotations for the job's customer, listed here (origin)
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_origin': self.name,
                'default_company_id': self.company_id.id,
            },
            'help': _('<p class="o_view_nocontent_smiling_face">Create a new quotation</p>'
                      '<p>Quote additional work or products to %s.</p>', self.partner_id.display_name),
        }
        if len(quotations) == 1:
            return dict(action, view_mode='form', views=[(False, 'form')], res_id=quotations.id)
        return dict(action, view_mode='list,form', views=[(False, 'list'), (False, 'form')])

    def action_fsm_view_products(self):
        """Product catalog: products used on site are added to the job (and billed)."""
        self.ensure_one()
        return self.with_context(child_field='product_line_ids').action_add_from_catalog()

    def action_customer_preview(self):
        """The job's report as the customer sees it on the portal."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.get_portal_url(),
            'target': 'self',
        }

    def _get_worksheet_report_sections(self):
        """The filled in worksheet, for the report: [(group title, [(label, type, value)])].

        Empty fields are left out; the value is a display string, or the image
        data URI of signatures.
        """
        self.ensure_one()
        properties = self.read(['worksheet_properties'])[0]['worksheet_properties'] or []
        sections = []
        title, lines = False, []
        for prop in properties:
            if prop['type'] == 'separator':
                if lines:
                    sections.append((title, lines))
                title, lines = prop.get('string'), []
                continue
            value = prop.get('value')
            if prop['type'] == 'boolean':
                value = _('Yes') if value else _('No')
            elif value in (False, None, '', []):
                continue
            elif prop['type'] == 'many2one':
                value = value[1]
            elif prop['type'] == 'many2many':
                value = ', '.join(v[1] for v in value)
            elif prop['type'] == 'tags':
                labels = {tag[0]: tag[1] for tag in prop.get('tags') or []}
                value = ', '.join(labels.get(v, v) for v in value)
            elif prop['type'] == 'selection':
                value = dict(prop.get('selection') or []).get(value, value)
            elif prop['type'] == 'date':
                value = format_date(self.env, value)
            elif prop['type'] == 'datetime':
                value = format_datetime(self.env, value)
            elif prop['type'] == 'signature':
                value = image_data_uri(value.encode() if isinstance(value, str) else value)
            elif prop['type'] != 'html':
                value = '%s %s' % (value, prop['suffix']) if prop.get('suffix') else str(value)
            lines.append((prop.get('string'), prop['type'], value))
        if lines:
            sections.append((title, lines))
        return sections

    def _get_signature_url(self):
        """Portal link (with access token) opening the report on its signature."""
        self.ensure_one()
        return self.get_base_url() + self.get_portal_url(query_string='sign=true', anchor='signature')

    # -------------------------------------------------------------------------
    # PRODUCT CATALOG
    # -------------------------------------------------------------------------

    def _get_product_catalog_domain(self):
        return super()._get_product_catalog_domain() & Domain('sale_ok', '=', True)

    def _get_action_add_from_catalog_extra_context(self):
        return {**super()._get_action_add_from_catalog_extra_context(), 'order_id': self.id}

    def _is_readonly(self):
        self.ensure_one()
        return self.state == 'cancelled'

    def _show_prices(self):
        return self._fs_feature('fs_billing')

    def action_get_directions(self):
        self.ensure_one()
        if not self.partner_id:
            return
        # Create Google Maps URL
        import urllib.parse
        address = []
        if self.partner_id.street: address.append(self.partner_id.street)
        if self.partner_id.city: address.append(self.partner_id.city)
        if self.partner_id.zip: address.append(self.partner_id.zip)
        if self.partner_id.country_id: address.append(self.partner_id.country_id.name)
        address_str = ', '.join(address)
        if not address_str:
            address_str = self.partner_id.name
            
        url = 'https://www.google.com/maps/dir/?api=1&destination=' + urllib.parse.quote(address_str)
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }


class FieldServiceImage(models.Model):
    _name = 'field.service.image'
    _description = 'Field Service Image'
    _order = 'id desc'

    order_id = fields.Many2one(
        'field.service.order',
        string='Order',
        required=True,
        ondelete='cascade',
    )
    image = fields.Image(
        string='Image',
        required=True,
        max_width=1920,
        max_height=1920,
    )
    name = fields.Char(
        string='Description',
    )
    include_in_report = fields.Boolean(
        string='Include in Report',
        default=True,
        help='Whether to show this image in the printed service report and customer portal.',
    )
