# -*- coding: utf-8 -*-
from odoo import fields, models, api, _

class HudsonAttendanceAnomaly(models.Model):
    _name = 'hudson.attendance.anomaly'
    _description = 'Attendance Anomaly'
    _order = 'detection_time desc, id desc'

    name = fields.Char(
        string='Title',
        required=True,
    )
    anomaly_type = fields.Selection([
        ('missing_punch', 'Missing Punch'),
        ('duplicate_punch', 'Duplicate Punch'),
        ('unmapped_employee', 'Unmapped Employee'),
        ('invalid_sequence', 'Invalid Sequence'),
        ('late_arrival', 'Late Arrival'),
        ('early_departure', 'Early Departure'),
        ('unusual_hours', 'Unusual Working Hours')
    ], string='Anomaly Type', required=True)

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='employee_id.company_id',
        store=True,
        index=True,
        readonly=True,
    )
    attendance_id = fields.Many2one(
        'hr.attendance',
        string='Attendance Record',
        ondelete='cascade',
    )
    raw_punch_id = fields.Many2one(
        'hudson.attendance.raw.punch',
        string='Raw Punch Log',
        ondelete='cascade',
    )
    detection_time = fields.Datetime(
        string='Detection Time',
        default=fields.Datetime.now,
        required=True,
    )
    description = fields.Text(
        string='Description',
    )
