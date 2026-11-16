# -*- encoding: utf-8 -*-
import secrets

# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError


class EhHrKioskDevice(models.Model):
    _name = 'eh.hr.kiosk.terminal'
    _description = 'Registered Kiosk Terminal'
    _inherit = ['mail.thread']
    _order = 'last_seen desc, id desc'

    name = fields.Char(string='Device name', required=True, tracking=True)
    site_id = fields.Many2one(
        'eh.hr.kiosk.site',
        string='Site',
        required=True,
        ondelete='restrict',
        tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='site_id.company_id',
        store=True,
        index=True,
    )
    device_token = fields.Char(
        string='Device token',
        required=True,
        index=True,
        copy=False,
        readonly=True,
        default=lambda self: secrets.token_urlsafe(32),
        help="Server-issued opaque token. The kiosk includes this in every request to authenticate itself.",
    )
    registered_on = fields.Datetime(
        string='Registered on',
        default=fields.Datetime.now,
        readonly=True,
    )
    last_seen = fields.Datetime(string='Last seen', readonly=True)
    last_ip = fields.Char(string='Last IP', readonly=True)
    user_agent = fields.Char(string='User agent', readonly=True)
    active = fields.Boolean(default=True, tracking=True)
    notes = fields.Text(string='Notes')

    if hasattr(models, 'Constraint'):
        _unique_device_token = models.Constraint('UNIQUE(device_token)', 'Device token collision detected.')
    else:
        _sql_constraints = [('unique_device_token', 'UNIQUE(device_token)', 'Device token collision detected.')]

    @api.constrains('device_token')
    def _check_token_present(self):
        for record in self:
            if not record.device_token:
                raise ValidationError(_("Device token is required."))

    def action_rotate_token(self):
        for record in self:
            record.device_token = secrets.token_urlsafe(32)

    def action_revoke(self):
        self.write({'active': False})

    def _touch(self, ip_address=None, user_agent=None):
        """Record a heartbeat. Called from the kiosk controller."""
        vals = {'last_seen': fields.Datetime.now()}
        if ip_address:
            vals['last_ip'] = ip_address
        if user_agent:
            vals['user_agent'] = user_agent[:255]
        self.sudo().write(vals)
