# -*- coding: utf-8 -*-
from odoo import fields, models, api, _

class HudsonAttendanceSyncJob(models.Model):
    _name = 'hudson.attendance.sync.job'
    _description = 'Biometric Sync Job'
    _order = 'start_time desc, id desc'

    device_id = fields.Many2one(
        'hudson.attendance.device',
        string='Device',
        required=True,
        ondelete='cascade',
    )
    start_time = fields.Datetime(
        string='Start Time',
        default=fields.Datetime.now,
        required=True,
    )
    end_time = fields.Datetime(
        string='End Time',
    )
    records_received = fields.Integer(
        string='Records Received',
        default=0,
    )
    records_processed = fields.Integer(
        string='Records Processed',
        default=0,
    )
    records_failed = fields.Integer(
        string='Records Failed',
        default=0,
    )
    records_duplicate = fields.Integer(
        string='Records Duplicate',
        default=0,
    )
    records_unmapped = fields.Integer(
        string='Records Unmapped',
        default=0,
    )
    state = fields.Selection([
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed')
    ], string='State', default='running', required=True)

    def action_retry_failed(self):
        self.ensure_one()
        domain = [('device_id', '=', self.device_id.id), ('state', '=', 'failed')]
        if self.start_time and self.end_time:
            domain += [('create_date', '>=', self.start_time), ('create_date', '<=', self.end_time)]
        failed_punches = self.env['hudson.attendance.raw.punch'].search(domain)
        if failed_punches:
            failed_punches.write({'state': 'new', 'error_message': False})
            failed_punches._process_punch()
        return True

    def action_reprocess_all(self):
        self.ensure_one()
        domain = [('device_id', '=', self.device_id.id)]
        if self.start_time and self.end_time:
            domain += [('create_date', '>=', self.start_time), ('create_date', '<=', self.end_time)]
        punches = self.env['hudson.attendance.raw.punch'].search(domain)
        if punches:
            punches.write({'state': 'new', 'error_message': False})
            punches._process_punch()
        return True
