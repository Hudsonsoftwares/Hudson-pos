# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from collections import defaultdict
from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

import pytz

from odoo import api, fields, models, _
from odoo.fields import Domain
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.intervals import Intervals


class FsPlanningSlot(models.Model):
    _name = 'fs.planning.slot'
    _description = 'Field Service Planning Slot'
    _order = 'date_start asc, resource_id asc'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']
    # Employee, project, sales order, template... of the shift's company
    _check_company_auto = True

    # Dates are required, except on the open shifts of a sales order still to
    # schedule (side panel of the schedule).
    _dates_set_or_to_schedule = models.Constraint(
        'CHECK((date_start IS NOT NULL AND date_end IS NOT NULL) OR sale_line_id IS NOT NULL)',
        "Set the start and end dates of the shift.",
    )

    name = fields.Char(string='Description')
    active = fields.Boolean(default=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('published', 'Published'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    resource_id = fields.Many2one(
        'hr.employee',
        string='Resource',
        ondelete='cascade',
        index=True,
        check_company=True,
    )
    role_id = fields.Many2one(
        'fs.planning.role',
        string='Role',
        ondelete='restrict',
        index=True,
    )
    color = fields.Integer(
        related='role_id.color',
        string='Color',
        readonly=True,
    )
    # Required, except on the shifts of a sales order to schedule (see
    # _dates_set_or_to_schedule).
    date_start = fields.Datetime(
        string='Start Date',
        index=True,
    )
    date_end = fields.Datetime(
        string='End Date',
        index=True,
    )
    allocated_hours = fields.Float(
        string='Allocated Time',
        compute='_compute_allocated_hours',
        store=True,
        readonly=False,
        help='Working time of the shift: its duration minus the break. '
             'On a shift to schedule (no dates), the hours to plan.',
    )
    break_hours = fields.Float(
        string='Break',
        default=0.0,
    )
    shift_status = fields.Selection(
        [
            ('draft', 'Draft'),
            ('scheduled', 'Scheduled'),
        ],
        string='Shift Status',
        compute='_compute_shift_status',
        help='Draft: not published yet. Scheduled: published to the resource.',
    )
    
    project_id = fields.Many2one(
        'project.project',
        string='Project',
        ondelete='set null',
        check_company=True,
    )
    task_id = fields.Many2one(
        'project.task',
        string='Task',
        domain="[('project_id', '=?', project_id)]",
        ondelete='set null',
        check_company=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        ondelete='set null',
        check_company=True,
    )
    sale_line_id = fields.Many2one(
        'sale.order.line',
        string='Sales Order Item',
        ondelete='set null',
        index='btree_not_null',
        copy=False,
        check_company=True,
        help='Service sold whose hours are planned by this shift (Plan Services on the product).',
    )
    is_to_plan = fields.Boolean(
        string='To Plan',
        compute='_compute_is_to_plan',
        search='_search_is_to_plan',
        help='Open shift of a sales order: hours sold not assigned to an employee yet.',
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        ondelete='set null',
        check_company=True,
    )

    shift_template_id = fields.Many2one(
        'fs.shift.template',
        string='Template',
        ondelete='set null',
        check_company=True,
    )
    available_template_ids = fields.Many2many(
        'fs.shift.template',
        compute='_compute_available_template_ids',
        help='Templates offered on the shift: those of its role (without role: of the '
             'roles of its resource), and the templates without role (offered to everyone).',
    )
    request_to_switch = fields.Boolean(
        string='Replacement Requested',
        copy=False,
        tracking=True,
        help='The resource asked to be replaced on this shift: other employees can take it.',
    )
    # Shifts of the same employee at the same time (alert on the form, with
    # suggestions of other employees / nearest free days)
    conflict_count = fields.Integer(string='Conflicts', compute='_compute_conflicts')
    conflict_warning = fields.Char(string='Conflicting Shifts', compute='_compute_conflicts')
    conflict_suggestions = fields.Json(
        string='Suggestions', compute='_compute_conflict_suggestions',
        help='Where the shift could go instead (see _get_reassign_suggestions)')
    # Replacement requested: employees of the role who could take the shift
    replacement_suggestions = fields.Json(
        string='Replacements', compute='_compute_replacement_suggestions',
        help='Employees with the role of the shift free at that time, or on the nearest free day.',
    )
    is_planning_manager = fields.Boolean(compute='_compute_is_planning_manager')
    is_own_shift = fields.Boolean(compute='_compute_shift_changes')
    can_request_switch = fields.Boolean(compute='_compute_shift_changes')
    can_self_unassign = fields.Boolean(compute='_compute_shift_changes')
    can_take_shift = fields.Boolean(compute='_compute_shift_changes')
    template_creation = fields.Boolean(
        string='Save as Template',
        copy=False,
        help='Create a shift template with the hours, role and project of this shift.',
    )
    note = fields.Text(string='Note')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        compute='_compute_company_id',
        store=True,
        readonly=False,
        precompute=True,
        required=True,
        help="The company of the shift's employee.",
    )

    @api.depends('resource_id')
    def _compute_company_id(self):
        for slot in self:
            slot.company_id = slot.resource_id.company_id or slot.company_id or self.env.company

    @api.depends('resource_id', 'role_id', 'company_id')
    def _compute_available_template_ids(self):
        templates = self.env['fs.shift.template'].search([])
        for slot in self:
            role = slot.role_id._origin
            resource = slot.resource_id._origin

            def offered(template):
                if template.company_id and template.company_id != slot.company_id:
                    return False
                if not template.role_id:
                    return True  # templates without role: for every shift
                if role:
                    return template.role_id == role
                if resource:
                    return resource in template.role_id.resource_ids
                return True  # shift without role nor resource: all templates

            slot.available_template_ids = templates.filtered(offered)

    @api.depends('date_start', 'date_end', 'break_hours')
    def _compute_allocated_hours(self):
        for slot in self:
            if slot.date_start and slot.date_end:
                delta = slot.date_end - slot.date_start
                slot.allocated_hours = max(delta.total_seconds() / 3600.0 - slot.break_hours, 0.0)
            elif not slot.sale_line_id:
                slot.allocated_hours = 0.0
            # else: a shift to schedule keeps its hours

    @api.depends('resource_id', 'sale_line_id')
    def _compute_is_to_plan(self):
        for slot in self:
            slot.is_to_plan = bool(slot.sale_line_id) and not slot.resource_id

    def _search_is_to_plan(self, operator, value):
        if operator in ('=', '!='):
            positive = bool(value) == (operator == '=')
        elif operator in ('in', 'not in'):
            positive = (True in value) == (operator == 'in')
        else:
            return NotImplemented
        to_plan = Domain('sale_line_id', '!=', False) & Domain('resource_id', '=', False)
        return to_plan if positive else ~to_plan

    @api.depends('state')
    def _compute_shift_status(self):
        for slot in self:
            slot.shift_status = 'scheduled' if slot.state == 'published' else 'draft'

    @api.depends('resource_id', 'state', 'request_to_switch', 'date_end')
    @api.depends_context('uid')
    @api.depends_context('uid')
    def _compute_is_planning_manager(self):
        self.is_planning_manager = self.env.user.has_group('hudson_planning.group_planning_manager')

    def _compute_shift_changes(self):
        mode = self._get_shift_change_mode()
        now = fields.Datetime.now()
        for slot in self:
            own = bool(slot.resource_id.user_id) and slot.resource_id.user_id == self.env.user
            usable = slot.state == 'published' and bool(slot.id) and (not slot.date_end or slot.date_end > now)
            slot.is_own_shift = own
            slot.can_request_switch = usable and own and mode == 'switch' and not slot.request_to_switch
            slot.can_self_unassign = usable and own and mode == 'unassign'
            slot.can_take_shift = usable and slot.request_to_switch and not own and bool(self.env.user.employee_id)

    @api.model
    def _get_shift_change_mode(self):
        return self.env['ir.config_parameter'].sudo().get_str('hudson_planning.employee_unavailabilities', 'switch')

    @api.constrains('break_hours', 'date_start', 'date_end')
    def _check_break_hours(self):
        for slot in self:
            if slot.break_hours < 0:
                raise ValidationError(_('The break cannot be negative.'))
            if slot.date_start and slot.date_end and slot.break_hours * 3600 > (slot.date_end - slot.date_start).total_seconds():
                raise ValidationError(_('The break cannot be longer than the shift.'))

    @api.constrains('date_start', 'date_end', 'sale_line_id')
    def _check_dates(self):
        for slot in self:
            if bool(slot.date_start) != bool(slot.date_end) or (not slot.date_start and not slot.sale_line_id):
                raise ValidationError(_('Set the start and end dates of the shift.'))
            if slot.date_start and slot.date_end and slot.date_start > slot.date_end:
                raise ValidationError(_('Start date must be before end date.'))

    # Conflicts (an employee with two shifts at the same time) are not blocked,
    # like Odoo: the shift form shows them with suggestions, the schedule
    # flags them, and the user decides. Automatic planning (Auto Plan, Copy
    # previous) avoids them (_is_free_for).

    @api.model
    def _is_free_for(self, employee, date_start, date_end, exclude=None):
        """Whether ``employee`` has no shift between the two datetimes."""
        domain = [
            ('resource_id', '=', employee.id),
            ('date_start', '<', date_end),
            ('date_end', '>', date_start),
        ]
        if exclude:
            domain.append(('id', 'not in', exclude.ids))
        # sudo: shifts hidden by the record rules still make the employee busy.
        return not self.sudo().search_count(domain, limit=1)

    def _get_conflicting_slots(self):
        """Shifts of the employee of this shift at the same time: an employee
        cannot do two things at once. Also for a shift being edited (form)."""
        self.ensure_one()
        employee = self.resource_id._origin or self.resource_id
        if not employee or not self.date_start or not self.date_end:
            return self.env['fs.planning.slot']
        domain = [
            ('resource_id', '=', employee.id),
            ('date_start', '<', self.date_end),
            ('date_end', '>', self.date_start),
        ]
        if self._origin.id:
            domain.append(('id', '!=', self._origin.id))
        # sudo: a conflict must be detected even when the other slot is
        # hidden from the current user by record rules.
        return self.env['fs.planning.slot'].sudo().search(domain, order='date_start').filtered(self._conflicts_with)

    def _get_conflict_label(self):
        """e.g. "Maintenance Technician (4 Nov 08:00 - 16:00)" """
        self.ensure_one()
        start = fields.Datetime.context_timestamp(self, self.date_start)
        end = fields.Datetime.context_timestamp(self, self.date_end)
        when = '%s - %s' % (start.strftime('%d %b %H:%M'),
                            end.strftime('%H:%M') if start.date() == end.date() else end.strftime('%d %b %H:%M'))
        return '%s (%s)' % (self.role_id.display_name or self.name or _("Shift"), when)

    @api.depends('resource_id', 'date_start', 'date_end')
    def _compute_conflicts(self):
        for slot in self:
            conflicts = slot._get_conflicting_slots()
            slot.conflict_count = len(conflicts)
            labels = [c._get_conflict_label() for c in conflicts[:3]]
            if len(conflicts) > 3:
                labels.append(_("and %s more", len(conflicts) - 3))
            slot.conflict_warning = ', '.join(labels) or False

    @api.depends('resource_id', 'role_id', 'date_start', 'date_end', 'break_hours', 'conflict_count')
    def _compute_conflict_suggestions(self):
        for slot in self:
            slot.conflict_suggestions = slot._get_reassign_suggestions() if slot.conflict_count else []

    @api.depends('resource_id', 'role_id', 'date_start', 'date_end', 'break_hours', 'request_to_switch')
    @api.depends_context('uid')
    def _compute_replacement_suggestions(self):
        is_manager = self.env.user.has_group('hudson_planning.group_planning_manager')
        for slot in self:
            requested = slot.request_to_switch and slot.resource_id and is_manager
            slot.replacement_suggestions = slot._get_reassign_suggestions(include_current=False) if requested else []

    def _get_reassign_suggestions(self, limit=6, days=30, include_current=True):
        """Where the shift could go instead: employees having the role of the
        shift, free at the same time (working that day, no time off, no other
        shift), else on the nearest free day; and its employee on their nearest
        free day (unless ``include_current`` is False: replacements).

        :return: list of ``{'employee_id', 'employee_name', 'date_start',
            'date_end', 'days', 'same_employee'}`` (UTC datetimes as strings)
        """
        self.ensure_one()
        if not self.date_start or not self.date_end:
            return []
        Employee = self.env['hr.employee'].sudo()
        current = (self.resource_id._origin or self.resource_id).sudo()
        role = (self.role_id._origin or self.role_id).sudo()
        if not role and current:
            role = current._get_default_planning_role()
        company = self.company_id._origin or self.company_id or self.env.company
        candidates = role.resource_ids if role else Employee.search([('company_id', 'in', [company.id, False])])
        candidates = candidates.filtered(lambda e: e.active and e.company_id in (company, self.env['res.company']))
        if include_current:
            employees = (candidates | current) if current else candidates
        else:
            employees = candidates - current
        if not employees:
            return []

        duration = self.date_end - self.date_start
        # Working time needed: the shift without its break (at least half, as Auto Plan)
        needed = max(duration.total_seconds() - (self.break_hours or 0.0) * 3600, 0) / 2
        window_start = self.date_start
        window_end = self.date_start + timedelta(days=days) + duration
        others = self.env['fs.planning.slot'].sudo().search([
            ('resource_id', 'in', employees.ids),
            ('date_start', '<', window_end),
            ('date_end', '>', window_start),
        ] + ([('id', '!=', self._origin.id)] if self._origin.id else []))
        busy = defaultdict(list)
        for other in others:
            busy[other.resource_id.id].append((other.date_start, other.date_end))

        suggestions = []
        for employee in employees:
            same = employee == current
            calendar = employee.resource_calendar_id
            work, leaves = None, []
            if calendar:
                tz = ZoneInfo(employee.tz or self.env.user.tz or 'UTC')
                begin, stop = window_start.replace(tzinfo=UTC), window_end.replace(tzinfo=UTC)
                per_tz = {tz: employee.resource_id}
                work = [(b.astimezone(UTC).replace(tzinfo=None), e.astimezone(UTC).replace(tzinfo=None))
                        for b, e, _r in calendar._work_intervals_batch(begin, stop, resources_per_tz=per_tz)[employee.resource_id.id]]
                leaves = [(b.astimezone(UTC).replace(tzinfo=None), e.astimezone(UTC).replace(tzinfo=None))
                          for b, e, _r in calendar._leave_intervals_batch(begin, stop, resources_per_tz=per_tz)[employee.resource_id.id]]
            for offset in range(1 if same else 0, days + 1):
                start = self.date_start + timedelta(days=offset)
                end = start + duration
                if any(b < end and e > start for b, e in busy[employee.id] + leaves):
                    continue
                if work is not None:
                    worked = sum(max((min(e, end) - max(b, start)).total_seconds(), 0) for b, e in work)
                    if worked < needed or not worked:
                        continue
                suggestions.append({
                    'employee_id': employee.id,
                    'employee_name': employee.name,
                    'date_start': fields.Datetime.to_string(start),
                    'date_end': fields.Datetime.to_string(end),
                    'days': offset,
                    'same_employee': same,
                })
                break
        # The same time first, then the nearest days; other employees first.
        suggestions.sort(key=lambda s: (s['days'], s['same_employee'], s['employee_name'] or ''))
        return suggestions[:limit]

    def _conflicts_with(self, other):
        """Whether ``other`` (an overlapping slot of the same resource) blocks ``self``.

        Hook for modules that add slot types which may legitimately overlap.
        """
        return True

    # -------------------------------------------------------------------------
    # MAP VIEW
    # -------------------------------------------------------------------------

    # Customers geolocated per map load (each lookup calls the geocoding service)
    _MAP_GEOLOCATE_LIMIT = 20

    @api.model
    def get_map_view_data(self, domain, group_by, offset=0, limit=80):
        """Data of the map view (``fs_map``): the shifts of the page, located at
        their customer, and grouped like the side panel.

        :param group_by: group bys of the search view; the side panel groups
            by the first one (by resource if none)
        """
        domain = Domain(domain or [])
        slots = self.search(domain, offset=offset, limit=limit, order='date_start, id')
        total = self.search_count(domain)
        group_field = (group_by[0] if group_by else 'resource_id').split(':')[0]
        if group_field not in self._fields:
            group_field = 'resource_id'
        field = self._fields[group_field]

        # sudo: the address of the customers of the shifts the user may see
        partners = slots.partner_id.sudo()
        self._map_geolocate(partners.filtered(lambda p: not (p.partner_latitude or p.partner_longitude)))

        groups = {}
        records = []
        for slot in slots:
            key, label = self._map_group_of(slot, field)
            groups.setdefault(key, {'key': key, 'name': label})
            partner = slot.partner_id.sudo()
            located = bool(partner and (partner.partner_latitude or partner.partner_longitude))
            records.append({
                'id': slot.id,
                'name': slot._get_schedule_slot_values()['label'] or slot.display_name,
                'partner_name': partner.display_name or '',
                'address': partner._display_address(without_name=True).replace('\n', ', ').strip(', ') if partner else '',
                'latitude': partner.partner_latitude if located else False,
                'longitude': partner.partner_longitude if located else False,
                'date_start': fields.Datetime.to_string(slot.date_start),
                'date_end': fields.Datetime.to_string(slot.date_end),
                'state': slot.state,
                'group_key': key,
            })
        ordered = sorted(groups.values(), key=lambda g: (g['key'] is False, (g['name'] or '').lower()))
        return {
            'records': records,
            'groups': ordered,
            'group_field': group_field,
            'group_field_string': field.string,
            'total': total,
        }

    @api.model
    def _map_group_of(self, slot, field):
        value = slot[field.name]
        if field.type == 'many2one':
            if not value:
                return False, _("Open Shifts") if field.name == 'resource_id' else _("None")
            return value.id, value.display_name
        if field.type == 'selection':
            return value, dict(field._description_selection(self.env)).get(value, value)
        if field.type in ('date', 'datetime'):
            day = fields.Date.to_string(fields.Datetime.context_timestamp(slot, value).date() if field.type == 'datetime' and value else value)
            return day or False, day or _("None")
        return value or False, str(value) if value else _("None")

    @api.model
    def _map_geolocate(self, partners):
        """Locate customers without coordinates (base_geolocalize), a few per load."""
        if not partners or not hasattr(partners, 'geo_localize'):
            return
        for partner in partners[:self._MAP_GEOLOCATE_LIMIT]:
            if not (partner.street or partner.city or partner.zip):
                continue
            try:
                with self.env.cr.savepoint():
                    partner.geo_localize()
            except Exception:  # noqa: BLE001 - an unreachable geocoder must not break the map
                continue

    # -------------------------------------------------------------------------
    # SCHEDULE VIEW
    # -------------------------------------------------------------------------

    @api.model
    def get_schedule_data(self, date_from, date_to):
        """Data for the planning schedule client action."""
        slots = self.search([
            ('date_start', '>=', date_from),
            ('date_start', '<', date_to),
        ])
        return {
            'slots': slots.read(self._get_schedule_fields()),
        }

    @api.model
    def _get_schedule_fields(self):
        return ['id', 'name', 'resource_id', 'role_id', 'sale_order_id', 'date_start', 'date_end', 'state', 'partner_id', 'allocated_hours', 'request_to_switch']

    @api.model
    def get_schedule_view_data(self, domain, group_by, date_from, date_to):
        """Data of the schedule view (``fs_schedule``) for a period.

        :param domain: domain of the search view
        :param group_by: group bys of the search view; the rows are the groups
            of the first one (no group by: a single row). With two group bys
            (e.g. Role > Resources), the rows of the second one are shown under
            a collapsible header per group of the first one.
        :param date_from, date_to: UTC bounds of the period
        :return: ``rows``: list of rows, each ``{'type': 'row', 'key', 'name',
            'values': {field: value}, ...}``, preceded with two group bys by
            their header ``{'type': 'group', 'key', 'name', ...}``
        """
        period = Domain('date_start', '<', date_to) & Domain('date_end', '>', date_from)
        full_domain = Domain(domain or []) & period
        slots = self.search(full_domain)
        group_fields = [g for g in (group_by or []) if g.split(':')[0] in self._fields][:2]
        start = fields.Datetime.to_datetime(date_from)
        end = fields.Datetime.to_datetime(date_to)

        if len(group_fields) == 2:
            rows, row_of_slot = self._schedule_nested_rows(domain, full_domain, group_fields)
        else:
            rows, row_of_slot = self._schedule_rows(domain, full_domain, group_fields[0] if group_fields else False, slots)

        # Shifts of an employee at the same time as another of their shifts
        busy = defaultdict(list)
        for other in self.sudo().search([('resource_id', 'in', slots.resource_id.ids),
                                         ('date_start', '<', date_to), ('date_end', '>', date_from)]):
            busy[other.resource_id.id].append(other)

        planned = dict.fromkeys(rows, 0.0)
        slot_values = []
        for slot, values in zip(slots, slots.read(self._get_schedule_fields())):
            key = row_of_slot.get(slot.id, False)
            values.update(slot._get_schedule_slot_values())
            values['row_key'] = key
            values['has_conflict'] = any(
                other.id != slot.id and other.date_start < slot.date_end and other.date_end > slot.date_start
                and slot._conflicts_with(other)
                for other in busy.get(slot.resource_id.id, [])
            )
            slot_values.append(values)
            duration = (slot.date_end - slot.date_start).total_seconds()
            overlap = (min(slot.date_end, end) - max(slot.date_start, start)).total_seconds()
            if duration > 0:
                planned[key] = planned.get(key, 0.0) + slot.allocated_hours * max(overlap, 0) / duration

        # Avatar, capacity... of the rows of employees
        resource_field = next((g for g in group_fields if g.split(':')[0] == 'resource_id'), False)
        if resource_field:
            employee_rows = {}
            for row in rows.values():
                employee_id = row.get('values', {}).get('resource_id')
                if employee_id:
                    employee_rows.setdefault(employee_id, []).append(row)
            info = {employee_id: {} for employee_id in employee_rows}
            self._add_schedule_resource_info(info, start, end)
            for employee_id, employee_info in info.items():
                for row in employee_rows[employee_id]:
                    row.update(employee_info)

        for key, row in rows.items():
            row['planned_hours'] = planned.get(key, 0.0)
        return {
            'rows': self._schedule_ordered_rows(rows, nested=len(group_fields) == 2),
            'slots': slot_values,
            'to_plan': self._get_schedule_to_plan(date_from, date_to),
            'group_field': group_fields[0] if group_fields else False,
            'group_fields': group_fields,
        }

    @api.model
    def _schedule_rows(self, domain, full_domain, group_field, slots):
        """Rows of the schedule grouped by one field (or not grouped)."""
        rows = {}
        row_of_slot = {}
        if not group_field:
            rows[False] = {'type': 'row', 'key': False, 'name': _("Shifts"), 'values': {}}
            return rows, dict.fromkeys(slots.ids, False)
        fname = group_field.split(':')[0]
        field = self._fields[fname]
        for group in self.formatted_read_group(full_domain, [group_field], ['id:array_agg']):
            key, label = self._schedule_row_key(field, group[group_field])
            rows[key] = {'type': 'row', 'key': key, 'name': label, 'values': {fname: key}}
            for slot_id in group['id:array_agg']:
                row_of_slot[slot_id] = key
        if not domain and fname in ('resource_id', 'role_id'):
            # No filter: every resource (role) is shown, even without shifts.
            for key, label in self._schedule_all_rows(fname):
                rows.setdefault(key, {'type': 'row', 'key': key, 'name': label, 'values': {fname: key}})
        if fname in ('resource_id', 'role_id'):
            rows.setdefault(False, {'type': 'row', 'key': False, 'name': self._schedule_row_key(field, False)[1],
                                    'values': {fname: False}})
        return rows, row_of_slot

    @api.model
    def _schedule_nested_rows(self, domain, full_domain, group_fields):
        """Rows of the schedule grouped by two fields: a header per group of
        the first field, the groups of the second one under it.

        ... > Resources (e.g. Role, Project): under each group, its open
        shifts and its employees. Role > Resources: the employees having the
        role, also without shifts (when there is no filter).
        """
        (group1, group2) = group_fields
        name1, name2 = group1.split(':')[0], group2.split(':')[0]
        field1, field2 = self._fields[name1], self._fields[name2]

        def leaf_key(key1, key2):
            return f'{key1}|{key2}'

        rows = {}
        row_of_slot = {}

        def add_header(key1, label1):
            header_key = f'group|{key1}'
            if header_key not in rows:
                rows[header_key] = {'type': 'group', 'key': header_key, 'name': label1,
                                    'group_value': key1, 'has_slots': False}
            return rows[header_key]

        def add_leaf(key1, label1, key2, label2):
            header = add_header(key1, label1)
            key = leaf_key(key1, key2)
            if key not in rows:
                rows[key] = {'type': 'row', 'key': key, 'name': label2, 'group_key': header['key'],
                             'values': {name1: key1, name2: key2}}
            return rows[key]

        for group in self.formatted_read_group(full_domain, [group1, group2], ['id:array_agg']):
            key1, label1 = self._schedule_row_key(field1, group[group1])
            key2, label2 = self._schedule_row_key(field2, group[group2])
            leaf = add_leaf(key1, label1, key2, label2)
            rows[leaf['group_key']]['has_slots'] = True
            for slot_id in group['id:array_agg']:
                row_of_slot[slot_id] = leaf['key']

        if name2 == 'resource_id':
            open_label = self._schedule_row_key(field2, False)[1]
            if name1 == 'role_id' and not domain:
                # No filter: every role, with its employees.
                visible = dict(self._schedule_all_rows('resource_id'))
                for role in self.env['fs.planning.role'].search([]):
                    add_header(role.id, role.display_name)
                    for employee in role.resource_ids.filtered(lambda e: e.id in visible):
                        add_leaf(role.id, role.display_name, employee.id, employee.name)
            for header in [r for r in rows.values() if r['type'] == 'group']:
                # Open shifts of each role / project... (also "Undefined Role",
                # "None", once they have shifts)
                add_leaf(header['group_value'], header['name'], False, open_label)
        return rows, row_of_slot

    @api.model
    def _schedule_ordered_rows(self, rows, nested=False):
        """Rows in display order: "None" first, then by name (with two
        group bys: each header followed by its rows), with the header totals."""
        def order(row):
            value = row['group_value'] if row['type'] == 'group' else row['key']
            if nested and row['type'] == 'row':
                value = row['values'][list(row['values'])[1]]
            return (value is not False, (row['name'] or '').lower())

        if not nested:
            return sorted(rows.values(), key=order)
        ordered = []
        for header in sorted((r for r in rows.values() if r['type'] == 'group'), key=order):
            children = sorted((r for r in rows.values() if r.get('group_key') == header['key']), key=order)
            header['planned_hours'] = sum(child['planned_hours'] for child in children)
            capacities = [child['capacity_hours'] for child in children if child.get('capacity_hours') is not None]
            if capacities:
                header['capacity_hours'] = sum(capacities)
            header['child_count'] = len(children)
            ordered.append(header)
            ordered.extend(children)
        return ordered

    @api.model
    def _schedule_row_key(self, field, value):
        """(key, label) of a row from a formatted_read_group value."""
        if isinstance(value, (list, tuple)):
            return value[0], value[1]
        if value is False or value is None:
            if field.name == 'resource_id':
                return False, _("Open Shifts")
            if field.name == 'role_id':
                return False, _("Undefined Role")
            if field.name == 'project_id':
                return False, _("No Project")
            return False, _("None")
        if field.type == 'selection':
            return value, dict(field._description_selection(self.env)).get(value, value)
        return value, str(value)

    @api.model
    def _schedule_all_rows(self, fname):
        if fname == 'resource_id':
            if not self.env.user.has_group('hudson_planning.group_planning_manager'):
                # Employees only see their own planning
                return [(e.id, e.name) for e in self.env.user.employee_ids]
            employees = self.env['hr.employee'].search([('company_id', 'in', self.env.companies.ids + [False])])
            return [(e.id, e.name) for e in employees]
        return [(r.id, r.name) for r in self.env['fs.planning.role'].search([])]

    @api.model
    def _add_schedule_resource_info(self, rows, start, end):
        """Avatar, job, capacity and days off of the resources of the period."""
        employees = self.env['hr.employee'].browse([k for k in rows if k]).exists()
        utc_start = pytz.utc.localize(start)
        utc_end = pytz.utc.localize(end)
        work_data = employees._get_work_days_data_batch(utc_start, utc_end, compute_leaves=True)
        for employee in employees:
            row = rows[employee.id]
            calendar = employee.resource_calendar_id
            work_days = set(calendar.attendance_ids.mapped('dayofweek')) if calendar else {'0', '1', '2', '3', '4'}
            tz = pytz.timezone(employee.tz or self.env.user.tz or 'UTC')
            days_off = []
            day = utc_start.astimezone(tz).date()
            while day < utc_end.astimezone(tz).date():
                if str(day.weekday()) not in work_days:
                    days_off.append(fields.Date.to_string(day))
                day += timedelta(days=1)
            if calendar:
                for leave_start, leave_end, _leave in calendar._leave_intervals_batch(
                        utc_start, utc_end, resources_per_tz={tz: employee.resource_id})[employee.resource_id.id]:
                    day = leave_start.astimezone(tz).date()
                    while day <= leave_end.astimezone(tz).date():
                        days_off.append(fields.Date.to_string(day))
                        day += timedelta(days=1)
            row.update({
                'avatar': f'/web/image/hr.employee.public/{employee.id}/avatar_128',
                'job_title': employee.job_title or '',
                'capacity_hours': work_data.get(employee.id, {}).get('hours', 0.0),
                'days_off': sorted(set(days_off)),
            })

    def _get_schedule_slot_values(self):
        """Extra values of a shift in the schedule view (label, color...)."""
        self.ensure_one()
        return {
            'label': self.name or self.partner_id.display_name or self.role_id.display_name or '',
            'color': self.role_id.color or 0,
            'is_job': False,
        }

    @api.model
    def _get_schedule_to_plan(self, date_from, date_to):
        """Side panel of the schedule: work still to be planned, dragged onto
        the schedule to plan it (see ``action_plan_from_schedule``).

        Base: the open shifts of the sales orders without dates (an open shift
        of the same role was already waiting when they were generated).

        :return: list of ``{'ref': 'model,id', 'name', 'hours'}``
        """
        slots = self.search([
            ('sale_line_id', '!=', False), ('date_start', '=', False),
            ('company_id', 'in', self.env.companies.ids),
        ], order='sale_order_id, id')
        return [{
            'ref': f'fs.planning.slot,{slot.id}',
            'name': slot._get_to_schedule_label(),
            'hours': slot.allocated_hours,
        } for slot in slots]

    def _get_to_schedule_label(self):
        self.ensure_one()
        # sudo: planners without sales rights plan the orders too.
        order = self.sudo().sale_order_id
        minutes = round(self.allocated_hours * 60)
        duration = '%d:%02d' % divmod(minutes, 60) if minutes % 60 else '%d' % (minutes // 60)
        return _(
            "%(order)s - %(name)s (%(role)s, %(hours)sh)",
            order=' - '.join(filter(None, [order.name, order.partner_id.display_name])),
            name=self.name or self.sudo().sale_line_id.product_id.display_name,
            role=self.role_id.display_name or _("no role"),
            hours=duration,
        )

    @api.model
    def action_plan_from_schedule(self, ref, group_field, row_key, date_start, date_end):
        """Schedule a shift of a sales order dropped from the side panel: it
        covers its hours of working time from where it is dropped, as an open
        shift (Open Shifts row) or the shift of the employee of the row."""
        model, _sep, res_id = ref.partition(',')
        if model != 'fs.planning.slot':
            raise UserError(_("This cannot be planned from the schedule."))
        self._check_planning_manager()
        slot = self.browse(int(res_id)).exists()
        if not slot or slot.date_start:
            raise UserError(_("This shift has already been scheduled."))
        start, end, breaks = self._get_work_span(fields.Datetime.to_datetime(date_start), slot.allocated_hours, slot.company_id)
        vals = {'date_start': start, 'date_end': end, 'break_hours': breaks}
        if group_field == 'resource_id':
            vals['resource_id'] = row_key or False
        elif group_field in ('role_id', 'project_id', 'task_id') and row_key:
            vals[group_field] = row_key
        slot.write(vals)
        return True

    # -------------------------------------------------------------------------
    # SALES ORDERS: open shifts of the services sold (Plan Services)
    # -------------------------------------------------------------------------

    @api.model
    def _get_work_span(self, start, hours, company):
        """Interval covering ``hours`` of the company's working time from
        ``start`` (naive UTC): ``(start, end, break_hours)``, the start moved to
        the first working moment and the time off work counted as break."""
        calendar = company.resource_calendar_id
        if calendar and hours > 0:
            tz = ZoneInfo(self.env.user.tz or 'UTC')
            begin = start.replace(tzinfo=UTC)
            horizon = begin + timedelta(days=int(hours // 4) + 14)
            work = calendar._work_intervals_batch(begin, horizon, resources_per_tz={tz: self.env['resource.resource']})[False]
            first, left = None, hours
            for b, e, _records in work:
                b, e = b.astimezone(UTC).replace(tzinfo=None), e.astimezone(UTC).replace(tzinfo=None)
                first = first or b
                duration = (e - b).total_seconds() / 3600
                if duration >= left - 1e-6:
                    end = b + timedelta(minutes=round(left * 60))
                    return first, end, max(round((end - first).total_seconds() / 3600 - hours, 4), 0.0)
                left -= duration
        return start, start + timedelta(minutes=round(max(hours, 0.0) * 60)), 0.0

    def _set_open_shift_hours(self, hours):
        """Make the open shift cover ``hours`` of working time from its start."""
        self.ensure_one()
        if not self.date_start:
            # To schedule: no dates yet.
            self.allocated_hours = hours
            return
        start, end, breaks = self._get_work_span(self.date_start, hours, self.company_id)
        self.write({'date_start': start, 'date_end': end, 'break_hours': breaks})

    def _blocks_sale_planning(self, other):
        """Whether the shift ``other`` makes its resource unavailable to plan
        the hours of ``self`` (a shift to plan)."""
        return True

    def _get_free_work_blocks(self, employee, date_from, date_to):
        """Free working time of ``employee`` (open shift: of the company)
        between two naive UTC datetimes: its working schedule minus its time
        off and its shifts.

        :return: list of blocks, one per day and run of free time, each a list
            of naive UTC ``(start, end)`` (several intervals: e.g. around lunch)
        """
        self.ensure_one()
        utc = UTC
        start, end = date_from.replace(tzinfo=utc), date_to.replace(tzinfo=utc)
        if employee:
            calendar = employee.resource_calendar_id or employee.company_id.resource_calendar_id
            if not calendar:
                return []
            tz = ZoneInfo(employee.tz or self.env.user.tz or 'UTC')
            work = calendar._work_intervals_batch(start, end, resources_per_tz={tz: employee.resource_id})[employee.resource_id.id]
            # sudo: shifts hidden by the record rules still make the resource busy.
            others = self.sudo().search([
                ('resource_id', '=', employee.id), ('id', '!=', self.id),
                ('date_start', '<', date_to), ('date_end', '>', date_from),
            ]).filtered(self._blocks_sale_planning)
            busy = [(o.date_start.replace(tzinfo=utc), o.date_end.replace(tzinfo=utc)) for o in others]
            work = work - Intervals([(b, e, self.env['fs.planning.slot']) for b, e in busy])
        else:
            calendar = self.company_id.resource_calendar_id or self.env.company.resource_calendar_id
            if not calendar:
                return []
            tz = ZoneInfo(self.env.user.tz or 'UTC')
            work = calendar._work_intervals_batch(start, end, resources_per_tz={tz: self.env['resource.resource']})[False]
            busy = []

        blocks = []
        last_day = last_end = None
        for begin, stop, _records in work:
            begin, stop = begin.astimezone(utc), stop.astimezone(utc)
            day = begin.astimezone(tz).date()
            # Same day and no shift in between (e.g. lunch): one shift with a break.
            if blocks and day == last_day and not any(b < begin and e > last_end for b, e in busy):
                blocks[-1].append((begin, stop))
            else:
                blocks.append([(begin, stop)])
            last_day, last_end = day, stop
        return [[(b.replace(tzinfo=None), e.replace(tzinfo=None)) for b, e in block] for block in blocks]

    def _prepare_planned_shift_values(self, employee, date_start, date_end, break_hours):
        """Values of a shift planning (part of) the hours of a shift to plan."""
        self.ensure_one()
        return {
            'name': self.name,
            'sale_line_id': self.sale_line_id.id,
            'sale_order_id': self.sale_order_id.id,
            'role_id': self.role_id.id,
            'project_id': self.project_id.id,
            'task_id': self.task_id.id,
            'note': self.note,
            'company_id': self.company_id.id,
            'resource_id': employee.id,
            'date_start': date_start,
            'date_end': date_end,
            'break_hours': break_hours,
            'state': 'draft',
        }

    def _plan_hours(self, employee, date_from, date_to, extra_vals=None):
        """Assign the hours of this open shift of a sales order to ``employee``,
        in their free working time between two naive UTC datetimes: one shift
        per day. The hours that do not fit stay in this open shift (deleted
        once all is planned).

        :return: the created shifts
        """
        self.ensure_one()
        remaining = self.allocated_hours
        vals_list = []
        for block in self._get_free_work_blocks(employee, date_from, date_to):
            if remaining < 1 / 60:
                break
            worked = 0.0
            end = block[0][0]
            for begin, stop in block:
                take = min((stop - begin).total_seconds() / 3600, remaining - worked)
                take = round(take * 60) / 60  # whole minutes
                if take <= 0:
                    break
                end = begin + timedelta(hours=take)
                worked += take
            if worked < 1 / 60:
                continue
            breaks = max(round((end - block[0][0]).total_seconds() / 3600 - worked, 4), 0.0)
            vals = self._prepare_planned_shift_values(employee, block[0][0], end, breaks)
            vals.update(extra_vals or {})
            vals_list.append(vals)
            remaining -= worked
        if not vals_list:
            return self.browse()
        shifts = self.create(vals_list)
        # What was planned is not open anymore.
        left = self.allocated_hours - sum(shifts.mapped('allocated_hours'))
        if left < 1 / 60:
            self.unlink()
        else:
            self._set_open_shift_hours(left)
        return shifts

    @api.model
    def _auto_plan_sale_shifts(self, domain, date_from, date_to):
        """Plan the hours of the sales orders over the period, on the employees
        having the role of the service (the least planned first), in their free
        working time.

        :return: (number of shifts to plan, hours planned)
        """
        date_from = max(fields.Datetime.to_datetime(date_from), fields.Datetime.now().replace(second=0, microsecond=0))
        date_to = fields.Datetime.to_datetime(date_to)
        # Open shifts of the period and before, and those to schedule (no dates).
        to_plan = self.search(Domain(domain or []) & Domain('is_to_plan', '=', True)
                              & (Domain('date_start', '<', date_to) | Domain('date_start', '=', False)),
                              order='date_start, id')
        if date_from >= date_to:
            return len(to_plan), 0.0
        planned = defaultdict(float)
        for slot in self.search([('resource_id', '!=', False), ('date_start', '<', date_to), ('date_end', '>', date_from)]):
            planned[slot.resource_id.id] += slot.allocated_hours
        total = 0.0
        for slot in to_plan:
            # Only the employees with the role of the service.
            candidates = slot.role_id.resource_ids.filtered(
                lambda e: e.company_id in (slot.company_id, self.env['res.company']))
            for employee in candidates.sorted(lambda e: (planned[e.id], e.name or '')):
                if not slot.exists():
                    break
                try:
                    with self.env.cr.savepoint():
                        shifts = slot._plan_hours(employee, date_from, date_to)
                except (ValidationError, UserError):
                    continue
                hours = sum(shifts.mapped('allocated_hours'))
                planned[employee.id] += hours
                total += hours
        return len(to_plan), total

    # -------------------------------------------------------------------------
    # SCHEDULE ACTIONS (Publish, Copy previous, Auto plan)
    # -------------------------------------------------------------------------

    @api.model
    def _check_planning_manager(self):
        if not self.env.user.has_group('hudson_planning.group_planning_manager'):
            raise AccessError(_("Only Planning administrators can do this."))

    @api.model
    def action_publish_period(self, domain, date_from, date_to):
        """Publish the draft shifts of the period."""
        self._check_planning_manager()
        slots = self.search(Domain(domain or []) & Domain([
            ('state', '=', 'draft'), ('date_start', '<', date_to), ('date_end', '>', date_from),
        ]))
        slots.action_publish()
        return len(slots)

    def _can_copy_to_next_period(self):
        """Whether the shift is repeated by "Copy previous week"."""
        self.ensure_one()
        return True

    @api.model
    def action_copy_previous_period(self, domain, date_from, date_to, previous_from):
        """Copy the shifts of the previous period into this one, as drafts.

        A shift whose resource is not available anymore becomes an open shift.
        """
        self._check_planning_manager()
        delta = fields.Datetime.to_datetime(date_from) - fields.Datetime.to_datetime(previous_from)
        previous = self.search(Domain(domain or []) & Domain([
            ('date_start', '>=', previous_from), ('date_start', '<', date_from),
        ])).filtered(lambda s: s._can_copy_to_next_period())
        copied = self.browse()
        for slot in previous:
            vals = {
                'date_start': slot.date_start + delta,
                'date_end': slot.date_end + delta,
                'state': 'draft',
                'request_to_switch': False,
            }
            if self.search_count([
                ('resource_id', '=', slot.resource_id.id),
                ('date_start', '=', vals['date_start']),
                ('date_end', '=', vals['date_end']),
            ]):
                continue  # already copied
            if slot.resource_id and not self._is_free_for(slot.resource_id, vals['date_start'], vals['date_end']):
                # The employee is busy then: an open shift instead.
                vals['resource_id'] = False
            copied |= slot.copy(vals)
        return len(copied)

    @api.model
    def action_auto_plan(self, domain, date_from, date_to):
        """Assign the open shifts of the period to available resources: having
        the shift's role, working that day and not booked, the least planned first."""
        self._check_planning_manager()
        # The open shifts of the sales orders are split on the employees
        # (see _auto_plan_sale_shifts).
        open_slots = self.search(Domain(domain or []) & Domain([
            ('resource_id', '=', False), ('sale_line_id', '=', False),
            ('date_start', '<', date_to), ('date_end', '>', date_from),
        ]))
        all_employees = self.env['hr.employee'].search([('company_id', 'in', self.env.companies.ids + [False])])
        planned = defaultdict(float)
        for slot in self.search([('resource_id', '!=', False), ('date_start', '<', date_to), ('date_end', '>', date_from)]):
            planned[slot.resource_id.id] += slot.allocated_hours
        assigned = 0
        for slot in open_slots:
            candidates = (slot.role_id.resource_ids or all_employees).filtered(
                lambda e: not slot.company_id or e.company_id in (slot.company_id, self.env['res.company']))
            for employee in candidates.sorted(lambda e: planned[e.id]):
                if not employee._is_available_for_slot(slot) or not self._is_free_for(employee, slot.date_start, slot.date_end):
                    continue
                try:
                    with self.env.cr.savepoint():
                        slot.write({'resource_id': employee.id})
                except (ValidationError, UserError):
                    continue
                planned[employee.id] += slot.allocated_hours
                assigned += 1
                break
        sale_to_plan, sale_hours = self._auto_plan_sale_shifts(domain, date_from, date_to)
        return {'assigned': assigned, 'open': len(open_slots), 'sale_to_plan': sale_to_plan, 'sale_hours': sale_hours}

    def get_popover_data(self):
        """Summary of the shift shown when it is clicked on the schedule.

        ``actions`` are buttons calling a method of the shift; modules add
        their own (see ``_get_popover_actions``).
        """
        self.ensure_one()
        lines = []
        partner = self.partner_id
        if partner:
            address = partner._display_address(without_name=True).strip()
            lines.append({'icon': 'person', 'text': f"{partner.display_name}\n{address}" if address else partner.display_name})
            if partner.phone:
                lines.append({'icon': 'call', 'text': partner.phone})
        for icon, record in (('folder', self.project_id), ('task_alt', self.task_id),
                             ('shopping_cart', self.sale_order_id), ('badge', self.role_id)):
            if record:
                lines.append({'icon': icon, 'text': record.display_name})
        if self.note:
            lines.append({'icon': 'sticky_note_2', 'text': self.note})
        return {
            'id': self.id,
            'name': self.name or '',
            'date_start': fields.Datetime.to_string(self.date_start),
            'date_end': fields.Datetime.to_string(self.date_end),
            'allocated_hours': self.allocated_hours,
            'state': self.state,
            'resource_id': self.resource_id.id,
            'resource_name': self.resource_id.name or '',
            'lines': lines,
            'priority': False,
            'conflict_count': self.conflict_count,
            'actions': self._get_popover_actions(),
            'can_delete': self.env.user.has_group('hudson_planning.group_planning_manager'),
        }

    def _get_popover_actions(self):
        """Buttons of the schedule popover: ``{'method', 'string'}``, plus
        ``'geolocate': True`` to pass the browser location to the method."""
        return []

    # -------------------------------------------------------------------------
    # TEMPLATES
    # -------------------------------------------------------------------------

    def _get_slot_tz(self):
        self.ensure_one()
        return pytz.timezone(self.resource_id.tz or self.env.user.tz or 'UTC')

    @api.onchange('shift_template_id')
    def _onchange_shift_template_id(self):
        template = self.shift_template_id
        if not template:
            return
        tz = self._get_slot_tz()
        day = fields.Datetime.context_timestamp(self.with_context(tz=tz.zone), self.date_start).date() \
            if self.date_start else fields.Date.context_today(self)
        self.date_start, self.date_end = template._get_interval(day, tz, self.resource_id.resource_calendar_id)
        if template.role_id:
            self.role_id = template.role_id
        if template.project_id:
            self.project_id = template.project_id
        if template.task_id:
            self.task_id = template.task_id

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._add_default_role(vals) if 'role_id' not in vals or not vals['role_id'] else vals
                     for vals in vals_list]
        slots = super().create(vals_list)
        slots.filtered('template_creation')._create_shift_template()
        return slots

    def _get_employee_writable_fields(self):
        """Fields employees may change on their shifts: the planning itself
        (resource, dates, state...) is the administrators'."""
        return set()

    def _check_employee_write(self, vals):
        if self.env.su or self.env.user.has_group('hudson_planning.group_planning_manager'):
            return
        forbidden = set(vals) - self._get_employee_writable_fields()
        if forbidden:
            fields_desc = ', '.join(sorted(self._fields[f].string for f in forbidden if f in self._fields))
            raise AccessError(_("Only Planning administrators can change the planning (%s).", fields_desc))

    def write(self, vals):
        self._check_employee_write(vals)
        if vals.get('resource_id') and 'role_id' not in vals:
            # Shifts without role assigned (e.g. dropped on an employee): the
            # employee's default role.
            no_role = self.filtered(lambda s: not s.role_id)
            role_vals = self._add_default_role(vals)
            if no_role and role_vals is not vals:
                if no_role != self:
                    (self - no_role).write(vals)
                    return no_role.write(role_vals)
                vals = role_vals
        # A shift with a replacement request given to someone else (by a planning
        # administrator): the request is settled.
        replaced = {}
        if 'resource_id' in vals and 'request_to_switch' not in vals:
            replaced = {slot: slot.resource_id for slot in self
                        if slot.request_to_switch and slot.resource_id.id != (vals['resource_id'] or False)}
        res = super().write(vals)
        for slot, previous in replaced.items():
            if not slot.exists():
                # e.g. the shift of an extra technician of a job: removed with them
                continue
            # sudo: employees may no longer read the shift once replaced
            slot.sudo().request_to_switch = False
            if slot.resource_id:
                body = _("%(user)s gave this shift to %(new)s, replacing %(old)s.",
                         user=self.env.user.name, new=slot.resource_id.name, old=previous.name)
            else:
                body = _("%(user)s moved this shift to the open shifts, replacing %(old)s.",
                         user=self.env.user.name, old=previous.name)
            slot.sudo().message_post(body=body)
        if vals.get('template_creation'):
            self.filtered('template_creation')._create_shift_template()
        # The open shifts of a sales order are not regenerated when its shifts
        # are moved, resized or deleted (like Odoo): only when the order is
        # confirmed or its quantities change (sale.order.line).
        return res

    def _create_shift_template(self):
        """Save the hours, role and project of the shifts as templates (once)."""
        Template = self.env['fs.shift.template']
        for slot in self.filtered('date_start'):
            tz = slot._get_slot_tz()
            start = pytz.utc.localize(slot.date_start).astimezone(tz)
            end = pytz.utc.localize(slot.date_end).astimezone(tz)
            vals = {
                'start_time': start.hour + start.minute / 60.0,
                'end_time': end.hour + end.minute / 60.0,
                'duration_days': max((end.date() - start.date()).days + (1 if end.time() > start.time() else 0), 1),
                'role_id': slot.role_id.id,
                'project_id': slot.project_id.id,
                'task_id': slot.task_id.id,
                'company_id': slot.company_id.id,
                **slot._get_shift_template_extra_values(),
            }
            template = Template.search([(f, '=', v) for f, v in vals.items()], limit=1) or Template.create(vals)
            super(FsPlanningSlot, slot).write({'template_creation': False, 'shift_template_id': template.id})

    def _get_shift_template_extra_values(self):
        """Values saved on the template created from the shift ("Save as Template")."""
        return {}

    @api.onchange('project_id')
    def _onchange_project_id(self):
        """Fetch the customer and sales order of the project."""
        project = self.project_id
        if self.task_id and self.task_id.project_id != project:
            self.task_id = False
        if not project:
            return
        if project.partner_id:
            self.partner_id = project.partner_id
        # sale_project: project sold through a sales order
        if 'sale_order_id' in project._fields and project.sale_order_id:
            self.sale_order_id = project.sale_order_id

    @api.onchange('task_id')
    def _onchange_task_id(self):
        """Fetch the project, customer and sales order of the task."""
        task = self.task_id
        if not task:
            return
        if task.project_id and task.project_id != self.project_id:
            self.project_id = task.project_id
            self._onchange_project_id()
        if task.partner_id:
            self.partner_id = task.partner_id
        # sale_project: task sold through a sales order line
        if 'sale_line_id' in task._fields and task.sale_line_id:
            self.sale_order_id = task.sale_line_id.order_id

    @api.onchange('resource_id')
    def _onchange_resource_id_role(self):
        """The role of the shift is the default role of its employee, unless
        it is already one of their roles."""
        employee = self.resource_id._origin.sudo()
        if not employee or (self.role_id and self.role_id._origin in employee.planning_role_ids):
            return
        role = employee._get_default_planning_role()
        if role:
            self.role_id = role

    @api.model
    def _add_default_role(self, vals):
        """Values of a shift assigned without role: the employee's default role."""
        if vals.get('resource_id') and not vals.get('role_id'):
            role = self.env['hr.employee'].sudo().browse(vals['resource_id'])._get_default_planning_role()
            if role:
                return dict(vals, role_id=role.id)
        return vals

    @api.onchange('role_id')
    def _onchange_role_id(self):
        if self.role_id and self.resource_id:
            if self.resource_id not in self.role_id.resource_ids:
                self.resource_id = False

    # -------------------------------------------------------------------------
    # SHIFT CHANGES (Settings > Shift Changes)
    # -------------------------------------------------------------------------

    def action_request_switch(self):
        """Ask to be replaced: the shift is offered to the other employees."""
        for slot in self:
            if not slot.can_request_switch:
                raise UserError(_("You can only ask for a replacement on your own upcoming published shifts."))
            # sudo: employees cannot write on shifts; checked above
            slot.sudo().request_to_switch = True
            slot.message_post(body=_("%s asked for a replacement on this shift.", self.env.user.name))
        return True

    def action_cancel_switch(self):
        for slot in self:
            if not (slot.is_own_shift or self.env.user.has_group('hudson_planning.group_planning_manager')):
                raise UserError(_("Only the employee of the shift can cancel the replacement request."))
            slot.sudo().request_to_switch = False
        return True

    def action_self_unassign(self):
        """Remove yourself from the shift, which becomes an open shift."""
        for slot in self:
            if not slot.can_self_unassign:
                raise UserError(_("You can only remove yourself from your own upcoming published shifts."))
            # sudo: employees may not write on the shift anymore once unassigned.
            slot.sudo().write({'resource_id': False, 'request_to_switch': False})
            slot.sudo().message_post(body=_("%s removed themselves from this shift.", self.env.user.name))
        return True

    def action_take_shift(self):
        """Take a shift whose employee asked for a replacement."""
        employee = self.env.user.employee_id
        for slot in self:
            if not slot.can_take_shift:
                raise UserError(_("This shift is not offered for replacement."))
            previous = slot.resource_id
            # sudo: the shift belongs to another employee; the overlap check still applies.
            slot.sudo().write({'resource_id': employee.id, 'request_to_switch': False})
            slot.sudo().message_post(body=_(
                "%(new)s replaced %(old)s on this shift.", new=employee.name, old=previous.name,
            ))
        return True

    def action_publish(self):
        self.write({'state': 'published'})
        return True

    def action_unpublish(self):
        self.write({'state': 'draft'})


