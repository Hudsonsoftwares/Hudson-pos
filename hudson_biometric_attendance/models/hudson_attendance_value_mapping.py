# -*- coding: utf-8 -*-
from odoo import fields, models

class HudsonAttendanceValueMapping(models.Model):
    _name = 'hudson.attendance.value.mapping'
    _description = 'Biometric Value Mapping'
    _order = 'field_mapping_id, src_value'

    field_mapping_id = fields.Many2one(
        'hudson.attendance.field.mapping',
        string='Field Mapping',
        required=True,
        ondelete='cascade',
    )
    src_value = fields.Char(
        string='Source Value',
        required=True,
        help='The value received from the device vendor API (e.g. "CHECK_IN", "1", "IN")',
    )
    target_value = fields.Selection([
        ('in', 'In'),
        ('out', 'Out'),
        ('break_in', 'Break In'),
        ('break_out', 'Break Out'),
        ('overtime_in', 'Overtime In'),
        ('overtime_out', 'Overtime Out')
    ], string='Target Value', required=True)

    _sql_constraints = [
        ('mapping_uniq', 'unique(field_mapping_id, src_value)', 'Source values must be unique per field mapping.'),
    ]
