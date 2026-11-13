# -*- coding: utf-8 -*-
import base64
import io
import logging
import qrcode
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    booking_id = fields.Many2one(
        'appointment.booking',
        string="Linked Table Booking",
        compute='_compute_booking_id',
        store=True,
        check_company=True,
    )

    @api.depends('invoice_line_ids.sale_line_ids.order_id', 'pos_order_ids.booking_id', 'company_id')
    def _compute_booking_id(self):
        for move in self:
            booking = False
            so_ids = move.invoice_line_ids.sale_line_ids.order_id.ids
            if so_ids:
                booking = self.env['appointment.booking'].search([
                    ('sale_order_id', 'in', so_ids),
                    ('company_id', 'in', [move.company_id.id, False]),
                ], limit=1)
            if not booking and hasattr(move, 'pos_order_ids') and move.pos_order_ids:
                pos_booking = move.pos_order_ids.filtered('booking_id').mapped('booking_id')
                if pos_booking:
                    booking = pos_booking[0]
            move.booking_id = booking

    def _get_survey_qr_code(self):
        """Generate base64 data URI PNG QR code for the company's configured survey URL."""
        self.ensure_one()
        company = self.company_id or self.env.company
        if not getattr(company, 'show_survey_qr', False) or not getattr(company, 'survey_url', False):
            return False
        url = (company.survey_url or '').strip()
        if not url:
            return False
        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=1,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            qr_b64 = base64.b64encode(buffer.getvalue()).decode()
            return f"data:image/png;base64,{qr_b64}"
        except Exception as e:
            _logger.warning("Failed to generate survey QR code for invoice %s: %s", self.name or self.id, e)
            return False

