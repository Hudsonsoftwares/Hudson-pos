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


class AppointmentResource(models.Model):
    _inherit = 'appointment.resource'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        help="Company to which this resource belongs."
    )


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
        for fname in ['appointment_resource_id', 'company_id']:
            if fname not in fields_list:
                fields_list.append(fname)
        return fields_list

    def _get_table_company(self):
        self.ensure_one()
        return self.company_id or (self.floor_id.pos_config_ids[:1].company_id if self.floor_id else False) or self.env.company

    def _get_default_resource_name(self):
        self.ensure_one()
        floor_name = self.floor_id.name if self.floor_id else _('Floor')
        return f"{floor_name} - Table {self.table_number}"

    def _sync_appointment_resource(self):
        """Create or update linked appointment.resource for this table with multi-company isolation."""
        Resource = self.env['appointment.resource'].sudo()
        PosConfig = self.env['pos.config'].sudo()

        for table in self:
            company = table._get_table_company()
            name = table._get_default_resource_name()
            capacity = table.seats or 1

            # Find appointment types linked to POS configs matching this table's specific company
            configs = PosConfig.search([
                ('company_id', '=', company.id),
                ('floor_ids', 'in', table.floor_id.id),
                ('use_booking', '=', True),
                ('booking_appointment_type_id', '!=', False)
            ]) if table.floor_id else PosConfig.browse()

            if not configs:
                configs = PosConfig.search([
                    ('company_id', '=', company.id),
                    ('use_booking', '=', True),
                    ('booking_appointment_type_id', '!=', False)
                ])

            # Ensure appointment types belong to this company or are globally shared (company_id False)
            app_types = configs.mapped('booking_appointment_type_id').filtered(
                lambda t: not t.company_id or t.company_id.id == company.id
            )
            app_type_ids = app_types.ids

            resource_vals = {
                'name': name,
                'capacity': capacity,
                'shareable': False,
                'active': table.active if hasattr(table, 'active') else True,
                'company_id': company.id,
            }
            if company.resource_calendar_id:
                resource_vals['opening_hours_id'] = company.resource_calendar_id.id
            if app_type_ids:
                resource_vals['appointment_type_ids'] = [(6, 0, app_type_ids)]

            if not table.appointment_resource_id:
                resource = Resource.create(resource_vals)
                table.appointment_resource_id = resource.id
            else:
                update_vals = {
                    'name': name,
                    'capacity': capacity,
                    'company_id': company.id,
                }
                if hasattr(table, 'active'):
                    update_vals['active'] = table.active
                if company.resource_calendar_id:
                    update_vals['opening_hours_id'] = company.resource_calendar_id.id
                if app_type_ids:
                    existing_types = table.appointment_resource_id.appointment_type_ids.filtered(
                        lambda t: not t.company_id or t.company_id.id == company.id
                    ).ids
                    combined_types = list(set(existing_types + app_type_ids))
                    update_vals['appointment_type_ids'] = [(6, 0, combined_types)]
                table.appointment_resource_id.sudo().write(update_vals)

    @api.model_create_multi
    def create(self, vals_list):
        tables = super().create(vals_list)
        tables._sync_appointment_resource()
        return tables

    def write(self, vals):
        res = super().write(vals)
        sync_fields = {'seats', 'table_number', 'floor_id', 'active', 'company_id'}
        if sync_fields.intersection(vals.keys()):
            for table in self:
                if not table.appointment_resource_id:
                    table._sync_appointment_resource()
                else:
                    company = table._get_table_company()
                    vals_to_update = {}
                    if 'seats' in vals:
                        vals_to_update['capacity'] = table.seats or 1
                    if 'table_number' in vals or 'floor_id' in vals:
                        vals_to_update['name'] = table._get_default_resource_name()
                    if 'active' in vals:
                        vals_to_update['active'] = table.active
                    if 'company_id' in vals or 'floor_id' in vals:
                        vals_to_update['company_id'] = company.id
                        if company.resource_calendar_id:
                            vals_to_update['opening_hours_id'] = company.resource_calendar_id.id
                    if vals_to_update:
                        table.appointment_resource_id.sudo().write(vals_to_update)
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
