# -*- coding: utf-8 -*-
from odoo import fields, models

class HudsonAttendanceWebhookLog(models.Model):
    _name = 'hudson.attendance.webhook.log'
    _description = 'Webhook Ingest Log'
    _order = 'timestamp desc, id desc'

    device_id = fields.Many2one(
        'hudson.attendance.device',
        string='Device',
        ondelete='set null',
    )
    timestamp = fields.Datetime(
        string='Log Time',
        required=True,
        default=fields.Datetime.now,
    )
    source_ip = fields.Char(
        string='Source IP',
    )
    payload_size = fields.Integer(
        string='Payload Size (Bytes)',
    )
    payload = fields.Text(
        string='Payload Content',
    )
    result = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed')
    ], string='Result', required=True)
    
    error_message = fields.Text(
        string='Error Details',
    )
