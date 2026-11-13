# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AppointmentType(models.Model):
    _inherit = 'appointment.type'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        help="Leave empty to share this appointment type across all companies."
    )

    allowed_resource_ids = fields.Many2many(
        'appointment.resource',
        compute='_compute_allowed_resource_ids',
        help="Appointment resources linked to active POS tables with Allow Website Booking enabled."
    )

    @api.depends('company_id', 'booking_target', 'resource_ids')
    def _compute_allowed_resource_ids(self):
        Resource = self.env['appointment.resource'].sudo()
        for at in self:
            if at.booking_target != 'resources':
                at.allowed_resource_ids = [(5, 0, 0)]
                continue
            company = at.company_id or self.env.company
            own_id = at._origin.id or (at.id if isinstance(at.id, int) else False)
            at.allowed_resource_ids = Resource._get_allowed_booking_resources(
                company=company,
                exclude_appointment_type_id=own_id,
            )

    @api.constrains('resource_ids', 'booking_target', 'active')
    def _check_exclusive_resource_ids(self):
        for at in self:
            if not at.active or at.booking_target != 'resources' or not at.resource_ids:
                continue
            conflicts = self.sudo().search([
                ('id', '!=', at.id),
                ('active', '=', True),
                ('booking_target', '=', 'resources'),
                ('resource_ids', 'in', at.resource_ids.ids),
            ])
            if conflicts:
                overlap = at.resource_ids & conflicts.mapped('resource_ids')
                raise ValidationError(_(
                    "Table/Resource %(res)s is already assigned to %(atype)s. "
                    "A table given to one event/appointment type cannot be given to another.",
                    res=', '.join(overlap.mapped('name')),
                    atype=', '.join(conflicts.mapped('name')),
                ))

    @api.model_create_multi
    def create(self, vals_list):
        res = super().create(vals_list)
        self.env['appointment.type'].invalidate_model(['allowed_resource_ids'])
        self.env['appointment.resource'].invalidate_model(['allow_website_booking', 'pos_table_id'])
        return res

    def write(self, vals):
        res = super().write(vals)
        if {'resource_ids', 'booking_target', 'active', 'company_id'}.intersection(vals.keys()):
            self.env['appointment.type'].invalidate_model(['allowed_resource_ids'])
            self.env['appointment.resource'].invalidate_model(['allow_website_booking', 'pos_table_id'])
        return res


class AppointmentResource(models.Model):
    _inherit = 'appointment.resource'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        help="Company to which this resource belongs."
    )
    pos_table_id = fields.Many2one(
        'restaurant.table',
        string='POS Table',
        compute='_compute_pos_table_booking_info',
    )
    allow_website_booking = fields.Boolean(
        string='Allow Website Booking',
        compute='_compute_pos_table_booking_info',
        inverse='_inverse_allow_website_booking',
        search='_search_allow_website_booking',
        help="Whether this resource/table is allowed for website & event booking.",
    )

    @api.depends_context('allowed_company_ids')
    def _compute_pos_table_booking_info(self):
        tables = self.env['restaurant.table'].sudo().with_context(active_test=False).search([
            ('appointment_resource_id', 'in', self.ids),
        ])
        table_by_res_id = {t.appointment_resource_id.id: t for t in tables}
        for resource in self:
            table = table_by_res_id.get(resource.id)
            resource.pos_table_id = table
            if table:
                resource.allow_website_booking = bool(
                    table.active and table.allow_website_booking and table._get_active_booking_configs()
                )
            else:
                resource.allow_website_booking = bool(resource.active)

    def _inverse_allow_website_booking(self):
        tables = self.env['restaurant.table'].sudo().with_context(active_test=False).search([
            ('appointment_resource_id', 'in', self.ids),
        ])
        table_by_res_id = {t.appointment_resource_id.id: t for t in tables}
        for resource in self:
            table = table_by_res_id.get(resource.id)
            if table:
                table.write({'allow_website_booking': bool(resource.allow_website_booking)})

    @api.model
    def _search_allow_website_booking(self, operator, value):
        if operator != 'in':
            return NotImplemented
        val_set = set(value)
        want_true = True in val_set
        want_false = False in val_set
        if want_true and want_false:
            return []
        if not want_true and not want_false:
            return [('id', '=', 0)]
        all_tables = self.env['restaurant.table'].sudo().with_context(active_test=False).search([
            ('appointment_resource_id', '!=', False),
        ])
        all_linked_res_ids = all_tables.mapped('appointment_resource_id').ids
        allowed_res_ids = all_tables.filtered(
            lambda t: t.active and t.allow_website_booking and bool(t._get_active_booking_configs())
        ).mapped('appointment_resource_id').ids
        if want_true:
            return [
                '|',
                ('id', 'in', allowed_res_ids),
                '&', ('id', 'not in', all_linked_res_ids), ('active', '=', True),
            ]
        return [
            '|',
            '&', ('id', 'in', all_linked_res_ids), ('id', 'not in', allowed_res_ids),
            '&', ('id', 'not in', all_linked_res_ids), ('active', '=', False),
        ]

    @api.model
    def _get_allowed_booking_resources(self, company=None, exclude_appointment_type_id=False, include_allocated=False):
        company = company or self.env.company
        Table = self.env['restaurant.table'].sudo()
        enabled_tables = Table.search([
            ('allow_website_booking', '=', True),
            ('active', '=', True),
            ('appointment_resource_id', '!=', False),
            ('floor_id.active', '=', True),
            '|', ('company_id', '=', False), ('company_id', '=', company.id),
        ]).filtered(lambda t: bool(t._get_active_booking_configs()))
        resources = enabled_tables.mapped('appointment_resource_id').filtered(
            lambda r: r.active and (not r.company_id or r.company_id == company)
        )
        if not include_allocated and resources:
            other_domain = [
                ('active', '=', True),
                ('booking_target', '=', 'resources'),
                ('resource_ids', 'in', resources.ids),
            ]
            if exclude_appointment_type_id and isinstance(exclude_appointment_type_id, int):
                other_domain.append(('id', '!=', exclude_appointment_type_id))
            taken_res = self.env['appointment.type'].sudo().search(other_domain).mapped('resource_ids')
            resources = resources - taken_res
        return resources

    @api.model
    def _apply_allowed_table_domain(self, domain):
        domain_list = list(domain or [])
        booking_target_ctx = self.env.context.get('appointment_booking_target') == 'resources'
        closing_type_ctx = self.env.context.get('appointment_closing_type') == 'resources'
        if booking_target_ctx or closing_type_ctx:
            has_id_filter = any(isinstance(term, (list, tuple)) and len(term) >= 2 and term[0] == 'id' for term in domain_list)
            if not has_id_filter:
                if booking_target_ctx:
                    exclude_at_id = self.env.context.get('active_appointment_type_id') or False
                    allowed_res_ids = self._get_allowed_booking_resources(
                        exclude_appointment_type_id=exclude_at_id,
                    ).ids
                else:
                    allowed_res_ids = self._get_allowed_booking_resources(include_allocated=True).ids
                domain_list = domain_list + [('id', 'in', allowed_res_ids)]
        return domain_list

    @api.model
    @api.readonly
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        domain = self._apply_allowed_table_domain(domain)
        return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **read_kwargs):
        domain = self._apply_allowed_table_domain(domain)
        return super().search_read(domain=domain, fields=fields, offset=offset, limit=limit, order=order, **read_kwargs)

    @api.model
    @api.readonly
    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        domain = self._apply_allowed_table_domain(domain)
        return super().web_search_read(domain=domain, specification=specification, offset=offset, limit=limit, order=order, count_limit=count_limit)


class RestaurantFloor(models.Model):
    _inherit = 'restaurant.floor'

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_table_sync') and {'pos_config_ids', 'active', 'name'}.intersection(vals.keys()):
            self.with_context(active_test=False).mapped('table_ids')._sync_appointment_resource()
        return res

    def unlink(self):
        resources = self.with_context(active_test=False).mapped('table_ids.appointment_resource_id')
        res = super().unlink()
        if resources:
            app_types = self.env['appointment.type'].sudo().with_context(active_test=False).search([
                ('resource_ids', 'in', resources.ids)
            ])
            if app_types:
                unlink_cmds = [(3, r.id) for r in resources]
                for at in app_types:
                    at.with_context(skip_table_sync=True).write({'resource_ids': unlink_cmds})
            Booking = self.env['appointment.booking'].sudo()
            for resource in resources:
                if resource.exists():
                    if Booking.search([('resource_ids', 'in', [resource.id])], limit=1):
                        resource.sudo().write({'active': False})
                    else:
                        resource.sudo().unlink()
        return res


class RestaurantTable(models.Model):
    _inherit = 'restaurant.table'

    appointment_resource_id = fields.Many2one(
        'appointment.resource',
        string='Appointment Resource',
        ondelete='set null',
        copy=False,
        check_company=True,
        help="Linked appointment resource representing this table in the booking system."
    )
    allow_website_booking = fields.Boolean(
        string='Allow Website Booking',
        default=True,
        help="If enabled, this table is open for online reservation via website appointment."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        compute='_compute_company_id',
        store=True,
        readonly=False,
        default=lambda self: self.env.company,
        index=True,
        help="Company associated with this restaurant table."
    )

    @api.depends('floor_id', 'floor_id.pos_config_ids.company_id')
    def _compute_company_id(self):
        for table in self:
            pos_configs = table.floor_id.pos_config_ids if table.floor_id else False
            if pos_configs and pos_configs[:1].company_id:
                table.company_id = pos_configs[:1].company_id
            elif not table.company_id:
                table.company_id = self.env.company

    @api.constrains('appointment_resource_id')
    def _check_unique_appointment_resource(self):
        for table in self:
            if table.appointment_resource_id:
                other = self.search([
                    ('appointment_resource_id', '=', table.appointment_resource_id.id),
                    ('id', '!=', table.id)
                ], limit=1)
                if other:
                    raise ValidationError(_("An appointment resource can only be linked to one restaurant table at a time."))

    @api.model
    def _load_pos_data_fields(self, config):
        """Include appointment_resource_id and company_id in POS data loading for restaurant.table."""
        fields_list = super()._load_pos_data_fields(config)
        for fname in ['appointment_resource_id', 'company_id', 'allow_website_booking']:
            if fname not in fields_list:
                fields_list.append(fname)
        return fields_list

    def get_merged_and_linked_tables(self):
        """
        Return recordset of all tables that are physically merged or linked with this table.
        Traverses Odoo native parent_id up to the root parent, finds all children and descendants,
        and includes any tables connected via appointment.resource linked_resource_ids.
        """
        all_tables = self.env['restaurant.table'].browse()
        for table in self:
            all_tables |= table
            # 1. Follow Odoo native parent_id up to root
            curr = table
            visited = {table.id}
            while curr.parent_id and curr.parent_id.id not in visited:
                visited.add(curr.parent_id.id)
                curr = curr.parent_id
                all_tables |= curr
            root = curr

            # 2. Find all descendants of root (Odoo native merged tables)
            descendants = self.search([('parent_id', '=', root.id)])
            all_tables |= descendants
            for child in descendants:
                all_tables |= self.search([('parent_id', '=', child.id)])

            # 3. Tables linked via appointment.resource.linked_resource_ids
            if table.appointment_resource_id:
                res = table.appointment_resource_id
                linked_res = res.linked_resource_ids if hasattr(res, 'linked_resource_ids') else self.env['appointment.resource']
                rev_res = self.env['appointment.resource'].search([('linked_resource_ids', 'in', res.ids)])
                all_res = linked_res | rev_res
                if all_res:
                    all_tables |= self.search([('appointment_resource_id', 'in', all_res.ids)])

        return all_tables

    def _get_table_company(self):
        self.ensure_one()
        return self.company_id or (self.floor_id.pos_config_ids[:1].company_id if self.floor_id else False) or self.env.company

    def _get_active_booking_configs(self):
        """Return active restaurant POS configs with Table Booking enabled serving this table's active floor."""
        self.ensure_one()
        if not self.floor_id or not self.floor_id.active:
            return self.env['pos.config']
        return self.floor_id.pos_config_ids.sudo().filtered(
            lambda c: c.active and c.module_pos_restaurant and c.use_booking
        )

    def _get_default_resource_name(self):
        self.ensure_one()
        floor_name = self.floor_id.name if self.floor_id else _('Floor')
        return f"{floor_name} - Table {self.table_number}"

    def _sync_appointment_resource(self):
        """Create or update linked appointment.resource for eligible POS booking tables with floor/config isolation."""
        if self.env.context.get('skip_table_sync'):
            return
        Resource = self.env['appointment.resource'].sudo()
        AppType = self.env['appointment.type'].sudo().with_context(active_test=False)
        force_create = bool(self.env.context.get('force_create_resource'))

        for table in self:
            company = table._get_table_company()
            active_configs = table._get_active_booking_configs()
            is_table_active = table.active if hasattr(table, 'active') else True
            is_eligible_for_website = bool(active_configs and is_table_active and table.allow_website_booking)

            # Avoid polluting appointment.resource for orphaned default floors / non-booking POS tables
            if not table.appointment_resource_id and not active_configs and not force_create:
                continue

            name = table._get_default_resource_name()
            capacity = table.seats or 1

            # Sync linked resources from Odoo's native merged tables (parent_id & children)
            native_merged = (table.get_merged_and_linked_tables() - table)
            linked_resources = native_merged.mapped('appointment_resource_id')

            resource_vals = {
                'name': name,
                'capacity': capacity,
                'shareable': False,
                'active': is_table_active,
                'company_id': company.id,
            }
            if linked_resources:
                resource_vals['linked_resource_ids'] = [(6, 0, linked_resources.ids)]
            if company.resource_calendar_id:
                resource_vals['opening_hours_id'] = company.resource_calendar_id.id

            if not table.appointment_resource_id:
                resource = Resource.create(resource_vals)
                table.with_context(skip_table_sync=True).appointment_resource_id = resource.id
            else:
                resource = table.appointment_resource_id.sudo()
                update_vals = {
                    'name': name,
                    'capacity': capacity,
                    'company_id': company.id,
                    'active': is_table_active,
                }
                if company.resource_calendar_id:
                    update_vals['opening_hours_id'] = company.resource_calendar_id.id
                if linked_resources:
                    update_vals['linked_resource_ids'] = [(6, 0, linked_resources.ids)]
                else:
                    update_vals['linked_resource_ids'] = [(5, 0, 0)]
                resource.write(update_vals)

            # Never auto-allocate resources onto appointment.type by default (client adds them per appointment type).
            # Still unlink from any appointment.type where this table is no longer eligible (website booking disabled,
            # archived, detached floor, or company mismatch).
            existing_app_types = AppType.search([('resource_ids', 'in', [resource.id])])
            if is_eligible_for_website:
                stale_app_types = existing_app_types.filtered(
                    lambda at: at.company_id and at.company_id.id != company.id
                )
            else:
                stale_app_types = existing_app_types
            for stale_at in stale_app_types:
                stale_at.with_context(skip_table_sync=True).write({'resource_ids': [(3, resource.id)]})
        self.env['appointment.type'].invalidate_model(['allowed_resource_ids'])
        self.env['appointment.resource'].invalidate_model(['allow_website_booking', 'pos_table_id'])

    @api.model_create_multi
    def create(self, vals_list):
        tables = super().create(vals_list)
        tables._sync_appointment_resource()
        return tables

    def write(self, vals):
        tables_to_sync = self
        if 'parent_id' in vals:
            for t in self:
                tables_to_sync |= t.get_merged_and_linked_tables()

        res = super().write(vals)

        if not self.env.context.get('skip_table_sync'):
            sync_fields = {'seats', 'table_number', 'floor_id', 'active', 'company_id', 'allow_website_booking', 'parent_id', 'parent_side'}
            if sync_fields.intersection(vals.keys()):
                if 'parent_id' in vals:
                    for t in self:
                        tables_to_sync |= t.get_merged_and_linked_tables()
                for table in tables_to_sync:
                    table._sync_appointment_resource()
        return res

    def unlink(self):
        resources = self.mapped('appointment_resource_id')
        res = super().unlink()
        if resources:
            app_types = self.env['appointment.type'].sudo().with_context(active_test=False).search([
                ('resource_ids', 'in', resources.ids)
            ])
            if app_types:
                unlink_cmds = [(3, r.id) for r in resources]
                for at in app_types:
                    at.with_context(skip_table_sync=True).write({'resource_ids': unlink_cmds})
        for resource in resources:
            if resource.exists():
                bookings = self.env['appointment.booking'].sudo().search([('resource_ids', 'in', [resource.id])], limit=1)
                if bookings:
                    resource.sudo().write({'active': False})
                else:
                    resource.sudo().unlink()
        return res

    def action_create_appointment_resource(self):
        """Helper to automatically generate and link an appointment resource for this table."""
        self.ensure_one()
        self.with_context(force_create_resource=True)._sync_appointment_resource()
        return self.appointment_resource_id

    @api.model
    def _cleanup_orphaned_tables_and_rescue_bookings(self):
        """
        Re-sync all restaurant tables so orphaned/unlinked floors never expose website
        appointment resources, and reassign any active/upcoming bookings trapped on
        orphaned floor tables onto free tables on active booking POS floors.
        """
        Table = self.env['restaurant.table'].sudo().with_context(active_test=False)
        AppType = self.env['appointment.type'].sudo().with_context(active_test=False)
        Booking = self.env['appointment.booking'].sudo()
        PosConfig = self.env['pos.config'].sudo()

        all_tables = Table.search([])
        all_tables._sync_appointment_resource()

        # Defensive sweep in case any table-backed resource lingered in appointment.type.resource_ids
        table_by_res = {
            t.appointment_resource_id.id: t
            for t in all_tables
            if t.appointment_resource_id
        }
        for at in AppType.search([('booking_target', '=', 'resources')]):
            stale_ids = []
            for res in at.resource_ids:
                tbl = table_by_res.get(res.id)
                if tbl and (not tbl.active or not tbl.allow_website_booking or not tbl._get_active_booking_configs()):
                    stale_ids.append(res.id)
            if stale_ids:
                at.with_context(skip_table_sync=True).write({
                    'resource_ids': [(3, rid) for rid in stale_ids]
                })

        # Rescue active/upcoming bookings trapped on orphaned tables without active booking configs
        orphaned_tables = all_tables.filtered(lambda t: t.appointment_resource_id and not t._get_active_booking_configs())
        if not orphaned_tables:
            return {'unlinked_resources': 0, 'rescued_bookings': 0}

        orphaned_res_ids = orphaned_tables.mapped('appointment_resource_id').ids
        trapped_bookings = Booking.search([
            ('state', 'in', ('confirmed', 'checked_in', 'pending_payment')),
            ('appointment_type_id.booking_target', '=', 'resources'),
            '|',
            ('table_ids', 'in', orphaned_tables.ids),
            ('resource_ids', 'in', orphaned_res_ids),
        ], order='start_datetime asc, id asc')

        rescued = 0
        for booking in trapped_bookings:
            company_id = booking.company_id.id or self.env.company.id
            active_configs = PosConfig.search([
                ('active', '=', True),
                ('module_pos_restaurant', '=', True),
                ('use_booking', '=', True),
                ('company_id', 'in', (company_id, False)),
            ])
            matching_configs = active_configs.filtered(
                lambda c: c.booking_appointment_type_id == booking.appointment_type_id
            ) or active_configs
            candidate_tables = matching_configs.mapped('floor_ids').filtered('active').mapped('table_ids').filtered('active')
            if not candidate_tables:
                continue

            party_size = booking.party_size or 1
            # Prefer smallest fitting website-bookable table first; fall back to any active floor table
            sorted_candidates = sorted(
                candidate_tables,
                key=lambda t: (
                    0 if t.allow_website_booking else 1,
                    0 if (t.seats or 1) >= party_size else 1,
                    abs((t.seats or 1) - party_size),
                    t.id,
                )
            )
            chosen = False
            for cand in sorted_candidates:
                if not cand.appointment_resource_id:
                    cand.with_context(force_create_resource=True)._sync_appointment_resource()
                if not cand.appointment_resource_id:
                    continue
                related_tables = cand.get_merged_and_linked_tables()
                blocked_res = related_tables.mapped('appointment_resource_id').ids
                conflict = Booking.search([
                    ('id', '!=', booking.id),
                    ('state', 'in', ('confirmed', 'checked_in', 'pending_payment')),
                    ('resource_ids', 'in', blocked_res),
                    ('start_datetime', '<', booking.end_datetime),
                    ('end_datetime', '>', booking.start_datetime),
                ], limit=1)
                if not conflict:
                    chosen = cand
                    break

            if chosen and chosen.appointment_resource_id:
                try:
                    booking.write({'resource_ids': [(6, 0, [chosen.appointment_resource_id.id])]})
                    rescued += 1
                    _logger.info(
                        "hudson_pos_booking: Reassigned orphaned booking #%s to table %s (%s).",
                        booking.id, chosen.display_name, chosen.appointment_resource_id.name
                    )
                except Exception as err:
                    _logger.warning(
                        "hudson_pos_booking: Could not reassign orphaned booking #%s: %s",
                        booking.id, err
                    )
        return {'rescued_bookings': rescued}
