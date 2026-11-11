# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError

class HudsonAttendanceRegularization(models.Model):
    _name = 'hudson.attendance.regularization'
    _description = 'Attendance Regularization Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='employee_id.company_id',
        store=True,
        index=True,
        readonly=True,
    )
    anomaly_id = fields.Many2one(
        'hudson.attendance.anomaly',
        string='Linked Anomaly',
        ondelete='set null',
        tracking=True,
    )
    attendance_id = fields.Many2one(
        'hr.attendance',
        string='Target Attendance',
        ondelete='set null',
        tracking=True,
    )
    orig_check_in = fields.Datetime(
        string='Original Check-in',
        readonly=True,
    )
    orig_check_out = fields.Datetime(
        string='Original Check-out',
        readonly=True,
    )
    corrected_check_in = fields.Datetime(
        string='Corrected Check-in',
        required=True,
        tracking=True,
    )
    corrected_check_out = fields.Datetime(
        string='Corrected Check-out',
        tracking=True,
    )
    reason = fields.Text(
        string='Reason for Correction',
        required=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('applied', 'Applied')
    ], string='Status', default='draft', required=True, tracking=True)

    @api.onchange('attendance_id')
    def _onchange_attendance_id(self):
        if self.attendance_id:
            self.orig_check_in = self.attendance_id.check_in
            self.orig_check_out = self.attendance_id.check_out
            self.corrected_check_in = self.attendance_id.check_in
            self.corrected_check_out = self.attendance_id.check_out

    @api.onchange('anomaly_id')
    def _onchange_anomaly_id(self):
        if self.anomaly_id:
            self.employee_id = self.anomaly_id.employee_id
            if self.anomaly_id.attendance_id:
                self.attendance_id = self.anomaly_id.attendance_id

    def action_submit(self):
        self.write({'state': 'submitted'})
        self.message_post(body=_("Regularization request submitted for approval."))

    def action_approve(self):
        self.write({'state': 'approved'})
        self.message_post(body=_("Regularization request approved."))

    def action_reject(self):
        self.write({'state': 'rejected'})
        self.message_post(body=_("Regularization request rejected."))

    def action_apply(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_("Only approved requests can be applied."))
            
        vals = {
            'employee_id': self.employee_id.id,
            'check_in': self.corrected_check_in,
            'check_out': self.corrected_check_out,
        }
        
        ctx = dict(self.env.context, biometric_punch_processing=True)
        
        if self.attendance_id:
            self.attendance_id.with_context(ctx).write({
                'check_in': self.corrected_check_in,
                'check_out': self.corrected_check_out,
            })
        else:
            new_att = self.env['hr.attendance'].with_context(ctx).create(vals)
            self.write({'attendance_id': new_att.id})
            
        self.write({'state': 'applied'})
        self.message_post(body=_("Regularization changes applied to Odoo Attendances."))
