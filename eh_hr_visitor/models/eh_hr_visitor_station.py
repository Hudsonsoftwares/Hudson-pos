# -*- encoding: utf-8 -*-
import secrets
import base64
# pyrefly: ignore [missing-import]
from odoo import api, fields, models


class EhHrVisitorStation(models.Model):
    _name = 'eh.hr.visitor.station'
    _description = 'Frontdesk Station'

    name = fields.Char(string='Frontdesk Name', required=True)
    responsible_employee_ids = fields.Many2many(
        'hr.employee',
        'eh_hr_visitor_station_responsible_rel',
        'station_id',
        'employee_id',
        string='Responsible Employee(s)'
    )
    allowed_host_employee_ids = fields.Many2many(
        'hr.employee',
        'eh_hr_visitor_station_host_rel',
        'station_id',
        'employee_id',
        string='Allowed Host Employees',
        help='If empty, all employees are allowed.'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True
    )
    station_image = fields.Binary(string='Station Image', attachment=True)
    kiosk_token = fields.Char(
        string='Kiosk Token',
        default=lambda s: secrets.token_urlsafe(32),
        copy=False,
        readonly=True,
        index=True
    )
    kiosk_url = fields.Char(string='Kiosk URL', compute='_compute_kiosk_url')
    active = fields.Boolean(default=True)

    # Options Tab
    host_selection = fields.Boolean(string='Host Selection', default=True, help="Allows visitors to choose the employee they are visiting.")
    default_host_employee_id = fields.Many2one(
        'hr.employee',
        string='Default Host',
        help="Automatically assign this host if host selection is disabled."
    )
    authenticate_guest = fields.Boolean(string='Authenticate Guest', default=True)
    field_email = fields.Selection([
        ('required', 'Required'),
        ('optional', 'Optional'),
        ('hidden', 'Hidden'),
    ], string='Email', default='optional')
    field_phone = fields.Selection([
        ('required', 'Required'),
        ('optional', 'Optional'),
        ('hidden', 'Hidden'),
    ], string='Phone', default='optional')
    field_organization = fields.Selection([
        ('required', 'Required'),
        ('optional', 'Optional'),
        ('hidden', 'Hidden'),
    ], string='Organization', default='optional')
    self_checkin = fields.Boolean(string='Self Check-In', default=False)
    qr_code = fields.Binary(string='QR Code', compute='_compute_qr_code')
    offer_drinks = fields.Boolean(string='Offer Drinks', default=False)
    drink_ids = fields.Many2many(
        'eh.hr.visitor.drink',
        string='Available Drinks'
    )
    notify_email = fields.Boolean(string='Notify by Email', default=True)
    notify_discuss = fields.Boolean(string='Notify by Discuss', default=True)
    notify_sms = fields.Boolean(string='Notify by SMS', default=False)
    theme = fields.Selection([
        ('light', 'Light'),
        ('dark', 'Dark'),
    ], string='Theme', default='dark')

    # Side Message Tab
    side_message = fields.Html(string='Side Message', sanitize=True)

    @api.depends('kiosk_token')
    def _compute_kiosk_url(self):
        # pyrefly: ignore [missing-import]
        from werkzeug.urls import url_join
        for station in self:
            if station.kiosk_token:
                base_kiosk_url = url_join(station.get_base_url(), f'/fd/kiosk/{station.kiosk_token}')
                station.kiosk_url = f"{base_kiosk_url}?db={station.env.cr.dbname}"
            else:
                station.kiosk_url = False

    @api.depends('kiosk_url')
    def _compute_qr_code(self):
        for station in self:
            if station.kiosk_url:
                try:
                    barcode_bytes = self.env['ir.actions.report'].barcode('QR', station.kiosk_url, width=300, height=300)
                    station.qr_code = base64.b64encode(barcode_bytes).decode('utf-8') if barcode_bytes else False
                except Exception:
                    station.qr_code = False
            else:
                station.qr_code = False

    def action_open_kiosk(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.kiosk_url,
            'target': 'new',
        }

    def action_regenerate_token(self):
        for station in self:
            station.kiosk_token = secrets.token_urlsafe(32)
