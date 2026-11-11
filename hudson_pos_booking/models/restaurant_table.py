# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class AppointmentType(models.Model):
    _inherit = 'appointment.type'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        help="Leave empty to share this appointment type across all companies."
    )

    def write(self, vals):
        if 'resource_ids' in vals and not self.env.context.get('skip_table_sync'):
            for at in self:
                old_res_ids = set(at.resource_ids.ids)
                res = super(AppointmentType, at).write(vals)
                new_res_ids = set(at.resource_ids.ids)
                Table = self.env['restaurant.table'].sudo()
                comp_domain = [('company_id', 'in', (at.company_id.id, False))] if at.company_id else []
                # Newly added resources -> enable website booking for their tables
                added_ids = list(new_res_ids - old_res_ids)
                if added_ids:
                    Table.search(comp_domain + [
                        ('appointment_resource_id', 'in', added_ids),
                        ('allow_website_booking', '=', False)
                    ]).with_context(skip_table_sync=True).write({'allow_website_booking': True})
                # Removed resources -> disable website booking only for tables that were actually removed from this appointment type
                removed_ids = list(old_res_ids - new_res_ids)
                if removed_ids:
                    Table.search(comp_domain + [
                        ('appointment_resource_id', 'in', removed_ids),
                        ('allow_website_booking', '=', True)
                    ]).with_context(skip_table_sync=True).write({'allow_website_booking': False})
            return True
        return super().write(vals)


class AppointmentResource(models.Model):
    _inherit = 'appointment.resource'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        help="Company to which this resource belongs."
    )

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **read_kwargs):
        if domain is None:
            domain = []
        if self.env.context.get('appointment_booking_target') == 'resources' or self.env.context.get('appointment_closing_type') == 'resources':
            has_id_filter = any(isinstance(term, (list, tuple)) and term[0] == 'id' for term in domain)
            if not has_id_filter:
                Table = self.env['restaurant.table'].sudo()
                company = self.env.company
                enabled_tables = Table.search([
                    ('allow_website_booking', '=', True),
                    ('active', '=', True),
                    ('appointment_resource_id', '!=', False),
                    '|', ('company_id', '=', False), ('company_id', '=', company.id)
                ])
                allowed_res_ids = enabled_tables.mapped('appointment_resource_id').ids
                domain = list(domain) + [('id', 'in', allowed_res_ids)]
        return super().search_read(domain=domain, fields=fields, offset=offset, limit=limit, order=order, **read_kwargs)


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

    def _get_default_resource_name(self):
        self.ensure_one()
        floor_name = self.floor_id.name if self.floor_id else _('Floor')
        return f"{floor_name} - Table {self.table_number}"

    def _sync_appointment_resource(self):
        """Create or update linked appointment.resource for this table with multi-company isolation."""
        if self.env.context.get('skip_table_sync'):
            return
        Resource = self.env['appointment.resource'].sudo()
        PosConfig = self.env['pos.config'].sudo()
        AppType = self.env['appointment.type'].sudo()

        for table in self:
            company = table._get_table_company()
            name = table._get_default_resource_name()
            capacity = table.seats or 1

            # Find appointment types linked to POS configs matching this table's specific company
            configs = PosConfig.search([
                ('company_id', '=', company.id),
                ('use_booking', '=', True),
                ('booking_appointment_type_id', '!=', False)
            ])
            app_types = configs.mapped('booking_appointment_type_id').filtered(
                lambda t: not t.company_id or t.company_id.id == company.id
            )
            if not app_types:
                app_types = AppType.search([
                    ('name', 'ilike', 'Table Booking'),
                    '|', ('company_id', '=', False), ('company_id', '=', company.id)
                ])

            # Sync linked resources from Odoo's native merged tables (parent_id & children)
            native_merged = (table.get_merged_and_linked_tables() - table)
            linked_resources = native_merged.mapped('appointment_resource_id')

            resource_vals = {
                'name': name,
                'capacity': capacity,
                'shareable': False,
                'active': table.active if hasattr(table, 'active') else True,
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
                }
                if hasattr(table, 'active'):
                    update_vals['active'] = table.active
                if company.resource_calendar_id:
                    update_vals['opening_hours_id'] = company.resource_calendar_id.id
                if linked_resources:
                    update_vals['linked_resource_ids'] = [(6, 0, linked_resources.ids)]
                else:
                    update_vals['linked_resource_ids'] = [(5, 0, 0)]
                resource.write(update_vals)

            # Direct sync with appointment types
            for at in app_types:
                if table.allow_website_booking and (not hasattr(table, 'active') or table.active):
                    if resource.id not in at.resource_ids.ids:
                        at.with_context(skip_table_sync=True).write({'resource_ids': [(4, resource.id)]})
                else:
                    if resource.id in at.resource_ids.ids:
                        at.with_context(skip_table_sync=True).write({'resource_ids': [(3, resource.id)]})

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
        self._sync_appointment_resource()
        return self.appointment_resource_id
