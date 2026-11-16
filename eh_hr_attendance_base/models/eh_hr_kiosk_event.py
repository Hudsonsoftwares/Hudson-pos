# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _


EVENT_TYPES = [
    ('device_register', 'Device registered'),
    ('device_revoke', 'Device revoked'),
    ('device_heartbeat', 'Device heartbeat'),
    ('kiosk_open', 'Kiosk opened'),
    ('kiosk_close', 'Kiosk closed'),
    ('attempt_match', 'Match attempt'),
    ('match_success', 'Match success'),
    ('match_fail', 'Match failure'),
    ('attendance_in', 'Attendance check-in'),
    ('attendance_out', 'Attendance check-out'),
    ('consent_grant', 'Consent granted'),
    ('consent_withdraw', 'Consent withdrawn'),
    ('exception_raised', 'Exception raised'),
    ('geofence_pass', 'Geofence passed'),
    ('geofence_fail', 'Geofence failed'),
    ('liveness_pass', 'Liveness passed'),
    ('liveness_fail', 'Liveness failed'),
    ('error', 'Error'),
]


class EhHrKioskEvent(models.Model):
    _name = 'eh.hr.kiosk.event'
    _description = 'Kiosk Audit Event'
    _order = 'timestamp desc, id desc'
    _rec_name = 'display_name'

    display_name = fields.Char(string='Reference', compute='_compute_display_name', store=True)
    timestamp = fields.Datetime(
        string='Timestamp',
        required=True,
        default=fields.Datetime.now,
        index=True,
        readonly=True,
    )
    event_type = fields.Selection(
        EVENT_TYPES,
        string='Event',
        required=True,
        index=True,
        readonly=True,
    )
    device_id = fields.Many2one('eh.hr.kiosk.terminal', string='Device', ondelete='set null', readonly=True)
    site_id = fields.Many2one(
        'eh.hr.kiosk.site',
        string='Site',
        related='device_id.site_id',
        store=True,
        index=True,
        readonly=True,
    )
    employee_id = fields.Many2one('hr.employee', string='Employee', ondelete='set null', index=True, readonly=True)
    confidence = fields.Float(string='Match confidence', digits=(4, 4), readonly=True)
    ip_address = fields.Char(string='IP', readonly=True)
    user_agent = fields.Char(string='User agent', readonly=True)
    notes = fields.Text(string='Notes', readonly=True)
    ref_model = fields.Char(string='Linked model', readonly=True)
    ref_id = fields.Integer(string='Linked record', readonly=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        readonly=True,
    )

    @api.depends('timestamp', 'event_type', 'employee_id')
    def _compute_display_name(self):
        types = dict(self._fields['event_type'].selection)
        for record in self:
            stamp = fields.Datetime.to_string(record.timestamp) if record.timestamp else ''
            label = types.get(record.event_type, record.event_type or '')
            who = record.employee_id.name or ''
            record.display_name = ' / '.join(part for part in (stamp, label, who) if part) or _('Event')

    @api.model
    def log(self, event_type, **kwargs):
        """Single entry point for any module to write to the audit trail.

        Mandatory: event_type. All other fields optional.
        Caller's environment determines company_id by default.
        """
        vals = {'event_type': event_type}
        for key in ('device_id', 'employee_id', 'confidence', 'ip_address', 'user_agent', 'notes', 'ref_model', 'ref_id', 'company_id'):
            if key in kwargs and kwargs[key] is not None:
                vals[key] = kwargs[key]
        return self.sudo().create(vals)

    @api.model
    def _cron_retention_sweep(self, *, batch_limit=2000):
        """Daily. Trim the audit trail to each company's configured horizon.

        Audit events accumulate fast (every match attempt, every heartbeat,
        every match success / failure on every kiosk). The sweep is bounded
        by batch_limit so the cron worker is not held under a long delete
        on a busy installation. Remaining work is reported via
        ir.cron._commit_progress so the framework can schedule a re-run.
        """
        now = fields.Datetime.now()
        deleted = 0
        for company in self.env['res.company'].search([]):
            retention_months = company.eh_hr_audit_retention_months or 60
            cutoff = fields.Datetime.subtract(now, months=retention_months)
            remaining_quota = batch_limit - deleted
            if remaining_quota <= 0:
                break
            stale = self.search([
                ('company_id', '=', company.id),
                ('timestamp', '<=', cutoff),
            ], limit=remaining_quota)
            if stale:
                deleted += len(stale)
                stale.sudo().unlink()

        cron_id = self.env.context.get('cron_id')
        if cron_id:
            still_pending = self.search_count([
                ('timestamp', '<=', fields.Datetime.subtract(now, months=60)),
            ])
            self.env['ir.cron']._commit_progress(deleted, remaining=still_pending)
