# -*- coding: utf-8 -*-
from odoo import fields, models

class HudsonAttendanceFieldMapping(models.Model):
    _name = 'hudson.attendance.field.mapping'
    _description = 'Biometric Field Mapping'
    _order = 'device_id, target_field'

    device_id = fields.Many2one(
        'hudson.attendance.device',
        string='Device',
        required=True,
        ondelete='cascade',
    )
    src_path = fields.Char(
        string='Source JSON Path',
        required=True,
        help='Dot-notation path to extract value from JSON payload (e.g. data.employeeId)',
    )
    target_field = fields.Selection([
        ('employee_code', 'Employee Code'),
        ('punch_time', 'Punch Time'),
        ('punch_type', 'Punch Type'),
        ('external_uid', 'External Unique ID')
    ], string='Target Field', required=True)

    value_mapping_ids = fields.One2many(
        'hudson.attendance.value.mapping',
        'field_mapping_id',
        string='Value Mappings',
    )

    _sql_constraints = [
        ('device_target_uniq', 'unique(device_id, target_field)', 'A target field mapping must be unique per device.'),
    ]
