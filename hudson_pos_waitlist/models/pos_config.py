# -*- coding: utf-8 -*-
import re
import secrets
from io import BytesIO

import qrcode

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.binary import BinaryBytes

# Waitlist configuration never needs to reach the POS cashier UI.
_WAITLIST_POS_FIELDS = {
    'enable_qr_self_join', 'waitlist_token', 'qr_join_url',
    'qr_code_image', 'qr_code_url', 'qr_code_outdated', 'waitlist_minutes_per_party',
}


class PosConfig(models.Model):
    _inherit = 'pos.config'

    enable_qr_self_join = fields.Boolean(
        string="Enable QR Self Join",
        default=False,
        help="Let guests scan a QR code at the entrance to open this restaurant's waitlist page.",
    )
    waitlist_token = fields.Char(
        string="Waitlist Token",
        copy=False,
        index=True,
        readonly=True,
        help="Permanent random token identifying this POS in the public join URL. "
             "It never exposes the database name or internal IDs.",
    )
    qr_join_url = fields.Char(
        string="QR Join URL",
        compute='_compute_qr_join_url',
        help="Public join URL, built from the Odoo base URL (web.base.url) and this POS token.",
    )
    qr_code_image = fields.Binary(
        string="QR Code",
        readonly=True,
        copy=False,
        attachment=False,
        help="Generated QR image (PNG). Stays the same until 'Generate QR Code' is clicked again.",
    )
    qr_code_url = fields.Char(
        string="URL Encoded in QR",
        readonly=True,
        copy=False,
        help="The exact URL that was encoded into the stored QR image.",
    )
    qr_code_outdated = fields.Boolean(
        compute='_compute_qr_join_url',
        help="True when the Odoo base URL changed after the QR image was generated.",
    )
    # Technical name kept from earlier versions (no data migration); the meaning is now a flat
    # average, never multiplied by the guest's place in the queue.
    waitlist_minutes_per_party = fields.Integer(
        string="Average Waiting Time",
        default=10,
        help="Estimated average wait, in minutes, shown to every waiting guest on their "
             "Track My Waitlist page. The same value for everyone: it is never multiplied by "
             "the guest's place in the queue, and the queue position is never shown. Minimum 1.",
    )

    @api.constrains('waitlist_minutes_per_party')
    def _check_waitlist_minutes_per_party(self):
        for config in self:
            if config.waitlist_minutes_per_party < 1:
                raise ValidationError(_("Average Waiting Time must be at least 1 minute."))

    # ------------------------------------------------------------------
    # Token / URL
    # ------------------------------------------------------------------
    @api.model
    def _generate_waitlist_token(self):
        """Cryptographically secure, URL-safe random token (22 chars)."""
        return secrets.token_urlsafe(16)

    def _ensure_waitlist_token(self):
        for config in self:
            if not config.waitlist_token:
                config.waitlist_token = self._generate_waitlist_token()

    @api.depends('waitlist_token', 'qr_code_url')
    def _compute_qr_join_url(self):
        for config in self:
            if config.waitlist_token:
                base_url = (config.get_base_url() or '').rstrip('/')
                config.qr_join_url = f"{base_url}/waitlist/join/{config.waitlist_token}"
            else:
                config.qr_join_url = False
            config.qr_code_outdated = bool(
                config.qr_code_url and config.qr_code_url != config.qr_join_url
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('waitlist_token'):
                vals['waitlist_token'] = self._generate_waitlist_token()
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # POS frontend: keep waitlist data out of the cashier session payload
    # ------------------------------------------------------------------
    @api.model
    def _load_pos_data_fields(self, config):
        result = super()._load_pos_data_fields(config)
        if result:
            result = [f for f in result if f not in _WAITLIST_POS_FIELDS]
        return result

    @api.model
    def _load_pos_data_read(self, records, config):
        read_records = super()._load_pos_data_read(records, config)
        for rec in read_records or []:
            for key in _WAITLIST_POS_FIELDS:
                rec.pop(key, None)
        return read_records

    # ------------------------------------------------------------------
    # QR image
    # ------------------------------------------------------------------
    @api.model
    def _make_qr_png(self, data):
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=12,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#18120e", back_color="#ffffff")
        buf = BytesIO()
        img.save(buf)  # PNG for both PIL and pure-python qrcode factories
        return buf.getvalue()

    def _check_qr_self_join_enabled(self):
        for config in self:
            if not config.enable_qr_self_join:
                raise UserError(_("Enable QR Self Join on %s first.", config.name))

    def _generate_qr_code(self):
        """(Re)build the QR image from the current join URL. Never changes the token."""
        for config in self:
            config._ensure_waitlist_token()
            url = config.qr_join_url
            config.write({
                'qr_code_image': BinaryBytes(config._make_qr_png(url)),
                'qr_code_url': url,
            })

    def action_generate_qr_code(self):
        self.ensure_one()
        self._check_qr_self_join_enabled()
        self._generate_qr_code()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("QR Code Generated"),
                'message': _("QR Self Join code for %(pos)s now points to %(url)s",
                             pos=self.name, url=self.qr_code_url),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_download_qr_code(self):
        self.ensure_one()
        self._check_qr_self_join_enabled()
        if not self.qr_code_image:
            self._generate_qr_code()
        safe_name = re.sub(r'[^A-Za-z0-9_-]', '_', self.name or 'POS')
        return {
            'type': 'ir.actions.act_url',
            'url': (f"/web/content/pos.config/{self.id}/qr_code_image"
                    f"?download=true&filename=QR_Self_Join_{safe_name}.png"),
            'target': 'download',
        }

    def action_print_qr_code(self):
        self.ensure_one()
        self._check_qr_self_join_enabled()
        if not self.qr_code_image:
            self._generate_qr_code()
        return self.env.ref('hudson_pos_waitlist.action_report_waitlist_qr').report_action(self)
