# -*- encoding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


CONSENT_TYPES = [
    ('face', 'Face recognition'),
    ('fingerprint', 'Fingerprint'),
    ('iris', 'Iris'),
    ('voice', 'Voice'),
    ('photo', 'Photo capture'),
    ('geolocation', 'Geolocation'),
]

CONSENT_STATES = [
    ('pending', 'Pending'),
    ('granted', 'Granted'),
    ('withdrawn', 'Withdrawn'),
    ('expired', 'Expired'),
]

GRANTED_VIA = [
    ('kiosk_screen', 'Kiosk screen capture'),
    ('hr_admin', 'HR administrator entry'),
    ('paper', 'Paper signature, scanned'),
    ('portal', 'Self-service portal'),
]


class EhHrConsent(models.Model):
    _name = 'eh.hr.consent'
    _description = 'Biometric and Location Consent Record'
    _inherit = ['mail.thread']
    _order = 'granted_on desc, id desc'

    name = fields.Char(
        string='Reference',
        compute='_compute_name',
        store=True,
        readonly=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        ondelete='cascade',
        index=True,
        tracking=True,
    )
    consent_type = fields.Selection(
        CONSENT_TYPES,
        string='Type',
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        CONSENT_STATES,
        string='Status',
        required=True,
        default='pending',
        tracking=True,
        index=True,
    )
    granted_on = fields.Datetime(string='Granted on', tracking=True)
    withdrawn_on = fields.Datetime(string='Withdrawn on', tracking=True)
    expires_on = fields.Datetime(
        string='Expires on',
        tracking=True,
        help="Computed from the company validity setting at grant time. The daily retention cron moves the row to expired after this date.",
    )
    granted_via = fields.Selection(GRANTED_VIA, string='Captured via', tracking=True)
    consent_text = fields.Text(
        string='Consent text shown',
        help="Snapshot of the exact consent prose displayed when the employee granted consent. Frozen at grant time so the audit record cannot drift if the company default text is later changed.",
    )
    evidence = fields.Binary(
        string='Evidence',
        attachment=True,
        help="Optional. Photo of the kiosk consent screen, scanned signed form, or other supporting artefact.",
    )
    evidence_filename = fields.Char(string='Evidence filename')
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )

    @api.depends('employee_id', 'consent_type', 'granted_on')
    def _compute_name(self):
        for record in self:
            employee = record.employee_id.name or _('No employee')
            ctype = dict(record._fields['consent_type'].selection).get(record.consent_type, '')
            stamp = fields.Datetime.to_string(record.granted_on) if record.granted_on else ''
            record.name = ' / '.join(part for part in (employee, ctype, stamp) if part) or _('New consent')

    @api.constrains('state', 'granted_on', 'withdrawn_on')
    def _check_state_dates(self):
        for record in self:
            if record.state == 'granted' and not record.granted_on:
                raise ValidationError(_("A granted consent must have a granted-on date."))
            if record.state == 'withdrawn' and not record.withdrawn_on:
                raise ValidationError(_("A withdrawn consent must have a withdrawn-on date."))
            if record.granted_on and record.withdrawn_on and record.withdrawn_on < record.granted_on:
                raise ValidationError(_("Withdrawal date cannot be before grant date."))

    def action_grant(self):
        for record in self:
            if record.state == 'granted':
                continue
            company = record.company_id or self.env.company
            now = fields.Datetime.now()
            validity_months = company.eh_hr_consent_validity_months or 12
            record.write({
                'state': 'granted',
                'granted_on': now,
                'expires_on': fields.Datetime.add(now, months=validity_months),
            })

    def action_withdraw(self):
        for record in self:
            if record.state == 'withdrawn':
                continue
            record.write({
                'state': 'withdrawn',
                'withdrawn_on': fields.Datetime.now(),
            })

    @api.model
    def _cron_retention_sweep(self, *, batch_limit=500):
        """Daily retention sweep, batched.

        Two passes:
        1. Move active grants past expires_on into expired state.
        2. Delete withdrawn or expired rows past the retention window per
           company. Deletion is intentional: once consent is withdrawn or
           expired the record's purpose is the audit window only.

        Both passes are bounded by batch_limit so a database with years
        of stale rows does not freeze a worker. The remaining count is
        reported via ir.cron._commit_progress so the cron framework can
        re-trigger if more work is pending.
        """
        now = fields.Datetime.now()

        to_expire = self.search([
            ('state', '=', 'granted'),
            ('expires_on', '!=', False),
            ('expires_on', '<=', now),
        ], limit=batch_limit)
        if to_expire:
            to_expire.write({'state': 'expired'})

        deleted = 0
        for company in self.env['res.company'].search([]):
            retention_months = company.eh_hr_consent_retention_months or 24
            cutoff = fields.Datetime.subtract(now, months=retention_months)
            remaining_quota = batch_limit - deleted
            if remaining_quota <= 0:
                break
            stale = self.search([
                ('company_id', '=', company.id),
                ('state', 'in', ('withdrawn', 'expired')),
                ('write_date', '<=', cutoff),
            ], limit=remaining_quota)
            if stale:
                deleted += len(stale)
                stale.unlink()

        cron_id = self.env.context.get('cron_id')
        if cron_id:
            still_pending = self.search_count([
                '|',
                '&', ('state', '=', 'granted'), ('expires_on', '!=', False), ('expires_on', '<=', now),
                '&', ('state', 'in', ('withdrawn', 'expired')), ('write_date', '<=', fields.Datetime.subtract(now, months=24)),
            ])
            self.env['ir.cron']._commit_progress(len(to_expire) + deleted, remaining=still_pending)
