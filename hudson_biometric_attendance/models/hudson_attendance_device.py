# -*- coding: utf-8 -*-
import uuid
import logging
from datetime import timedelta
from odoo import fields, models, api
from odoo.exceptions import UserError, ValidationError
from werkzeug.security import generate_password_hash, check_password_hash

_logger = logging.getLogger(__name__)

class HudsonAttendanceDevice(models.Model):
    _name = 'hudson.attendance.device'
    _description = 'Biometric/Attendance Device Connection'
    _order = 'name'

    name = fields.Char(
        string='Device Name',
        required=True,
        help='A descriptive name for the biometric device or source.'
    )
    connection_type = fields.Selection([
        ('zk_direct', 'ZK Direct Connection'),
        ('rest_api', 'REST API Poll'),
        ('webhook', 'Webhook Push')
    ], string='Connection Type', required=True, default='zk_direct')
    
    address = fields.Char(
        string='Device Address/IP/URL',
        help='The IP address, URL, or API endpoint identifier for this device.'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        help='Company associated with this attendance device.'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, it will allow you to hide the device without removing it.'
    )
    
    uuid = fields.Char(
        string='Device UUID',
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: str(uuid.uuid4())
    )
    webhook_token = fields.Char(
        string='Webhook Token (Hashed)',
        copy=False,
        readonly=True,
        help='Hashed API token for webhook authentication.'
    )
    webhook_token_plain = fields.Char(
        string='New Webhook Token',
        store=False,
        help='Set this field to update the webhook token. It will be stored securely hashed.'
    )

    last_sync_time = fields.Datetime(
        string='Last Successful Sync',
        readonly=True,
    )
    failure_count = fields.Integer(
        string='Failure Count',
        default=0,
        readonly=True,
    )
    next_retry_time = fields.Datetime(
        string='Next Retry Time',
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'webhook_token_plain' in vals:
                plain = vals.pop('webhook_token_plain')
                if plain:
                    vals['webhook_token'] = generate_password_hash(plain)
        return super().create(vals_list)

    def write(self, vals):
        if 'webhook_token_plain' in vals:
            plain = vals.pop('webhook_token_plain')
            if plain:
                vals['webhook_token'] = generate_password_hash(plain)
        return super().write(vals)

    def verify_webhook_token(self, token):
        self.ensure_one()
        if not self.webhook_token or not token:
            return False
        return check_password_hash(self.webhook_token, token)

    def cron_sync_devices(self):
        """Cron job to sync punches from all active ZK and REST API devices."""
        now = fields.Datetime.now()
        devices = self.search([
            ('active', '=', True),
            ('connection_type', 'in', ('zk_direct', 'rest_api')),
            '|',
            ('next_retry_time', '=', False),
            ('next_retry_time', '<=', now)
        ])
        for device in devices:
            device.sync_punches()
        return True

    def sync_punches(self):
        self.ensure_one()
        job = self.env['hudson.attendance.sync.job'].create({
            'device_id': self.id,
            'state': 'running'
        })
        try:
            if self.connection_type == 'zk_direct':
                self._pull_zk_punches(job)
            elif self.connection_type == 'rest_api':
                self._poll_rest_punches(job)
            
            self.write({
                'last_sync_time': fields.Datetime.now(),
                'failure_count': 0,
                'next_retry_time': False
            })
            raw_punches = self.env['hudson.attendance.raw.punch'].search([
                ('device_id', '=', self.id),
                ('create_date', '>=', job.start_time)
            ])
            job.write({
                'end_time': fields.Datetime.now(),
                'records_received': len(raw_punches),
                'records_processed': len(raw_punches.filtered(lambda p: p.state == 'processed')),
                'records_failed': len(raw_punches.filtered(lambda p: p.state == 'failed')),
                'records_duplicate': len(raw_punches.filtered(lambda p: p.state == 'duplicate')),
                'records_unmapped': len(raw_punches.filtered(lambda p: p.state == 'unmapped')),
                'state': 'completed'
            })
        except Exception as e:
            _logger.exception("Failed executing punch polling job for device %s (ID: %s): %s", self.name, self.id, e)
            fail_count = self.failure_count + 1
            delay_minutes = min(2 ** fail_count, 1440)
            next_retry = fields.Datetime.now() + timedelta(minutes=delay_minutes)
            self.write({
                'failure_count': fail_count,
                'next_retry_time': next_retry
            })
            job.write({
                'end_time': fields.Datetime.now(),
                'state': 'failed',
                'records_failed': job.records_failed + 1
            })

    def _pull_zk_punches(self, job):
        pass

    def _poll_rest_punches(self, job):
        if not self.address:
            raise UserError(_("No address configured for REST API device"))
        
        mappings = self.env['hudson.attendance.field.mapping'].search([('device_id', '=', self.id)])
        if not mappings:
            raise UserError(_("No field mappings configured for this device"))
        
        import requests
        response = requests.get(self.address, timeout=10)
        if response.status_code != 200:
            raise UserError(_("REST API device HTTP Error: %s") % response.status_code)
        
        payload = response.json()
        
        records = []
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            found_list = False
            for val in payload.values():
                if isinstance(val, list) and all(isinstance(x, dict) for x in val):
                    records = val
                    found_list = True
                    break
            if not found_list:
                records = [payload]
        else:
            records = [payload]

        mapping_dict = {m.target_field: m for m in mappings}

        def get_by_path(data, path):
            if not path:
                return None
            parts = path.split('.')
            val = data
            for part in parts:
                if isinstance(val, dict):
                    val = val.get(part)
                elif isinstance(val, list):
                    try:
                        val = val[int(part)]
                    except (ValueError, IndexError):
                        return None
                else:
                    return None
            return val

        for rec in records:
            extracted = {}
            for target_field, m in mapping_dict.items():
                val = get_by_path(rec, m.src_path)
                if target_field == 'punch_type' and val is not None:
                    str_val = str(val).strip()
                    val_map = m.value_mapping_ids.filtered(lambda vm: vm.src_value == str_val)
                    if val_map:
                        val = val_map[0].target_value
                    else:
                        val = str_val.lower()
                extracted[target_field] = val

            if not extracted.get('employee_code') or not extracted.get('punch_time') or not extracted.get('punch_type'):
                continue

            raw_punch = self.env['hudson.attendance.raw.punch'].create({
                'device_id': self.id,
                'employee_code': str(extracted['employee_code']),
                'punch_time': extracted['punch_time'],
                'punch_type': extracted['punch_type'],
                'external_uid': str(extracted['external_uid']) if extracted.get('external_uid') else False,
            })
            raw_punch._process_punch()

    total_punches_7_days = fields.Integer(compute='_compute_punch_stats')
    total_punches_30_days = fields.Integer(compute='_compute_punch_stats')
    success_count = fields.Integer(compute='_compute_punch_stats')
    failed_count = fields.Integer(compute='_compute_punch_stats')
    duplicate_count = fields.Integer(compute='_compute_punch_stats')
    unmapped_count = fields.Integer(compute='_compute_punch_stats')
    connection_status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline')
    ], compute='_compute_connection_status', string='Status')

    def _compute_punch_stats(self):
        now = fields.Datetime.now()
        date_7d = now - timedelta(days=7)
        date_30d = now - timedelta(days=30)
        
        for device in self:
            punches = self.env['hudson.attendance.raw.punch'].search([('device_id', '=', device.id)])
            device.total_punches_7_days = len(punches.filtered(lambda p: p.create_date >= date_7d))
            device.total_punches_30_days = len(punches.filtered(lambda p: p.create_date >= date_30d))
            device.success_count = len(punches.filtered(lambda p: p.state == 'processed'))
            device.failed_count = len(punches.filtered(lambda p: p.state == 'failed'))
            device.duplicate_count = len(punches.filtered(lambda p: p.state == 'duplicate'))
            device.unmapped_count = len(punches.filtered(lambda p: p.state == 'unmapped'))

    def _compute_connection_status(self):
        for device in self:
            if device.connection_type == 'webhook':
                device.connection_status = 'online'
            else:
                if device.failure_count > 0:
                    device.connection_status = 'offline'
                else:
                    device.connection_status = 'online'

    def action_view_processed_punches(self):
        self.ensure_one()
        return {
            'name': _('Processed Punches - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'hudson.attendance.raw.punch',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', self.id), ('state', '=', 'processed')],
            'target': 'current',
        }

    def action_view_failed_punches(self):
        self.ensure_one()
        return {
            'name': _('Failed Punches - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'hudson.attendance.raw.punch',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', self.id), ('state', '=', 'failed')],
            'target': 'current',
        }

    def action_view_duplicate_punches(self):
        self.ensure_one()
        return {
            'name': _('Duplicate Punches - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'hudson.attendance.raw.punch',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', self.id), ('state', '=', 'duplicate')],
            'target': 'current',
        }

    def action_view_unmapped_punches(self):
        self.ensure_one()
        return {
            'name': _('Unmapped Punches - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'hudson.attendance.raw.punch',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', self.id), ('state', '=', 'unmapped')],
            'target': 'current',
        }

    def action_view_all_punches(self):
        self.ensure_one()
        return {
            'name': _('All Punches - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'hudson.attendance.raw.punch',
            'view_mode': 'list,form',
            'domain': [('device_id', '=', self.id)],
            'target': 'current',
        }
