# -*- coding: utf-8 -*-
from odoo import fields, models

class HudsonAttendanceEmployeeMapping(models.Model):
    _name = 'hudson.attendance.employee.mapping'
    _description = 'Biometric Employee Mapping'
    _order = 'device_id, external_employee_code'

    device_id = fields.Many2one(
        'hudson.attendance.device',
        string='Device',
        ondelete='cascade',
    )
    external_employee_code = fields.Char(
        string='External Employee Code',
        required=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Odoo Employee',
        required=True,
        ondelete='cascade',
    )

    _sql_constraints = [
        ('device_ext_uniq', 'unique(device_id, external_employee_code)', 'The external employee code must be unique per device.'),
    ]
