# -*- encoding: utf-8 -*-
import re

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


def _tz_get(self):
    return [(tz, tz) for tz in pytz.all_timezones]


class EhHrKioskSite(models.Model):
    _name = 'eh.hr.kiosk.site'
    _description = 'Kiosk Site'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(string='Site name', required=True, tracking=True)
    code = fields.Char(
        string='Code',
        required=True,
        tracking=True,
        help="Short URL-safe identifier, used in the kiosk shell URL. Letters, digits, dash, underscore only.",
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    address = fields.Text(string='Address')
    timezone = fields.Selection(
        _tz_get,
        string='Timezone',
        default=lambda self: self.env.user.tz or 'UTC',
        help="Used to interpret kiosk timestamps for late and no-show evaluation.",
    )
    geofence_enabled = fields.Boolean(string='Enforce geofence', tracking=True)
    geofence_lat = fields.Float(string='Latitude', digits=(10, 6))
    geofence_lng = fields.Float(string='Longitude', digits=(10, 6))
    geofence_radius_m = fields.Integer(string='Radius (m)', default=50)
    device_ids = fields.One2many('eh.hr.kiosk.terminal', 'site_id', string='Devices')
    device_count = fields.Integer(string='Device count', compute='_compute_device_count')
    notes = fields.Text(string='Notes')

    @api.depends('device_ids')
    def _compute_device_count(self):
        for site in self:
            site.device_count = len(site.device_ids)

    if hasattr(models, 'Constraint'):
        _unique_code_per_company = models.Constraint('UNIQUE(code, company_id)', 'Site code must be unique per company.')
    else:
        _sql_constraints = [('unique_code_per_company', 'UNIQUE(code, company_id)', 'Site code must be unique per company.')]

    @api.constrains('code')
    def _check_code_format(self):
        for site in self:
            if not site.code:
                raise ValidationError(_("Site code is required."))
            if not re.match(r'^[A-Za-z0-9_-]+$', site.code):
                raise ValidationError(_("Site code may contain letters, digits, dashes and underscores only."))

    @api.constrains('geofence_enabled', 'geofence_lat', 'geofence_lng', 'geofence_radius_m')
    def _check_geofence(self):
        for site in self:
            if not site.geofence_enabled:
                continue
            if not (-90.0 <= site.geofence_lat <= 90.0):
                raise ValidationError(_("Latitude must be between -90 and 90."))
            if not (-180.0 <= site.geofence_lng <= 180.0):
                raise ValidationError(_("Longitude must be between -180 and 180."))
            if site.geofence_radius_m <= 0:
                raise ValidationError(_("Geofence radius must be positive."))

    def action_view_devices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Devices for %s') % self.name,
            'res_model': 'eh.hr.kiosk.terminal',
            'view_mode': 'list,form',
            'domain': [('site_id', '=', self.id)],
            'context': {'default_site_id': self.id},
        }

    def action_issue_pairing_pin(self):
        """Generate a one-time pairing PIN and display it to the admin.

        The PIN is short-lived (5 minutes) and one-shot. The admin reads
        it (or scans the QR rendered next to it) on the kiosk during
        first-time setup; the kiosk POSTs site_code + pin to
        /eh_hr/kiosk/pair to receive its long-lived device token.
        """
        self.ensure_one()
        from odoo.addons.eh_hr_attendance_base.controllers.kiosk import issue_pairing_pin
        pin = issue_pairing_pin(self.code)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Kiosk pairing PIN'),
                'message': _("Pairing PIN for site %(site)s: %(pin)s. Valid for 5 minutes, one-shot.") % {
                    'site': self.name,
                    'pin': pin,
                },
                'type': 'success',
                'sticky': True,
            },
        }
