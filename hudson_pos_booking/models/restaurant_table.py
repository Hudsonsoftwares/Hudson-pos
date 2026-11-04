# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class RestaurantTable(models.Model):
    _inherit = 'restaurant.table'

    appointment_resource_id = fields.Many2one(
        'appointment.resource',
        string='Appointment Resource',
        ondelete='set null',
        copy=False,
        help="Linked appointment resource representing this table in the booking system."
    )

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
        """Include appointment_resource_id in POS data loading for restaurant.table."""
        fields_list = super()._load_pos_data_fields(config)
        if 'appointment_resource_id' not in fields_list:
            fields_list.append('appointment_resource_id')
        return fields_list

    @api.model_create_multi
    def create(self, vals_list):
        tables = super().create(vals_list)
        for table in tables:
            if table.appointment_resource_id and table.seats:
                table.appointment_resource_id.sudo().write({'capacity': table.seats})
        return tables

    def write(self, vals):
        res = super().write(vals)
        if 'seats' in vals or 'appointment_resource_id' in vals:
            for table in self:
                if table.appointment_resource_id and table.seats:
                    # Sync table seats to resource capacity (one source of truth: restaurant.table)
                    table.appointment_resource_id.sudo().write({'capacity': table.seats})
        return res

    def action_create_appointment_resource(self):
        """Helper to automatically generate and link an appointment resource for this table."""
        self.ensure_one()
        if self.appointment_resource_id:
            return

        name = f"{self.floor_id.name or 'Floor'} - Table {self.table_number}"
        resource = self.env['appointment.resource'].create({
            'name': name,
            'capacity': self.seats or 1,
            'shareable': False,
        })
        self.appointment_resource_id = resource.id
        return resource
