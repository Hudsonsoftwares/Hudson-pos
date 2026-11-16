# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


EXCEPTION_TYPES = [
    ('late', 'Late check-in'),
    ('early_in', 'Early check-in'),
    ('no_show', 'No-show'),
    ('missed_check_out', 'Missed check-out'),
    ('location_mismatch', 'Location mismatch'),
    ('identity_low_confidence', 'Low match confidence'),
    ('geofence_violation', 'Geofence violation'),
    ('liveness_fail', 'Liveness failure'),
    ('duplicate_check_in', 'Duplicate check-in'),
    ('manual', 'Manual'),
]

SEVERITIES = [
    ('info', 'Info'),
    ('warning', 'Warning'),
    ('critical', 'Critical'),
]


class EhHrAttendanceException(models.Model):
    _name = 'eh.hr.attendance.exception'
    _description = 'Attendance Exception'
    _inherit = ['mail.thread']
    _order = 'occurred_on desc, id desc'

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    attendance_id = fields.Many2one(
        'hr.attendance',
        string='Related attendance',
        ondelete='set null',
        index=True,
    )
    exception_type = fields.Selection(
        EXCEPTION_TYPES,
        string='Type',
        required=True,
        tracking=True,
        index=True,
    )
    severity = fields.Selection(
        SEVERITIES,
        string='Severity',
        required=True,
        default='warning',
        tracking=True,
        index=True,
    )
    occurred_on = fields.Datetime(
        string='Occurred on',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
    )
    description = fields.Text(string='Description')
    resolved = fields.Boolean(default=False, tracking=True, index=True)
    resolved_by = fields.Many2one('res.users', string='Resolved by', tracking=True)
    resolved_on = fields.Datetime(string='Resolved on', tracking=True)
    resolution_notes = fields.Text(string='Resolution notes')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.depends('employee_id', 'exception_type', 'occurred_on')
    def _compute_name(self):
        types = dict(self._fields['exception_type'].selection)
        for record in self:
            who = record.employee_id.name or ''
            label = types.get(record.exception_type, '')
            stamp = fields.Datetime.to_string(record.occurred_on) if record.occurred_on else ''
            record.name = ' / '.join(part for part in (who, label, stamp) if part) or _('Exception')

    def action_resolve(self):
        for record in self:
            if record.resolved:
                continue
            record.write({
                'resolved': True,
                'resolved_by': self.env.user.id,
                'resolved_on': fields.Datetime.now(),
            })

    def action_reopen(self):
        for record in self:
            if not record.resolved:
                continue
            record.write({
                'resolved': False,
                'resolved_by': False,
                'resolved_on': False,
            })

    @api.model
    def raise_exception(self, employee, exception_type, severity='warning', occurred_on=None, description=None, attendance=None):
        """Public API for any module to log an exception consistently.

        Returns the created record.
        """
        if not employee:
            raise UserError(_("An employee is required to raise an exception."))
        vals = {
            'employee_id': employee.id if hasattr(employee, 'id') else employee,
            'exception_type': exception_type,
            'severity': severity,
            'occurred_on': occurred_on or fields.Datetime.now(),
            'description': description or '',
        }
        if attendance:
            vals['attendance_id'] = attendance.id if hasattr(attendance, 'id') else attendance
        record = self.sudo().create(vals)
        self.env['eh.hr.kiosk.event'].sudo().log(
            'exception_raised',
            employee_id=record.employee_id.id,
            notes=description,
            ref_model='eh.hr.attendance.exception',
            ref_id=record.id,
        )
        return record
