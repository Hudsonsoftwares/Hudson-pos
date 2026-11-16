# -*- encoding: utf-8 -*-
from odoo import fields, models


DEFAULT_FACE_CONSENT_TEXT = (
    "I consent to my facial template being captured and stored by my employer "
    "for the purpose of verifying my identity at workplace clock-in and "
    "clock-out. I understand my facial template is stored only as a numeric "
    "embedding (not as a photograph), is used solely to confirm my attendance, "
    "and is deleted when I leave the organisation or withdraw this consent. "
    "I may withdraw consent at any time by notifying my manager or HR; "
    "withdrawal will not affect my employment, and an alternative clock-in "
    "method (PIN or manual sign-in) will be provided."
)


class ResCompany(models.Model):
    _inherit = 'res.company'

    eh_hr_consent_validity_months = fields.Integer(
        string='Consent validity (months)',
        default=12,
        help="Period for which a granted consent remains valid. After this the daily retention cron moves the consent to expired and the employee is asked to re-consent.",
    )
    eh_hr_consent_retention_months = fields.Integer(
        string='Withdrawn or expired consent retention (months)',
        default=24,
        help="Period for which withdrawn or expired consent records are kept for audit before deletion. Match this to your local privacy law's documentation requirement.",
    )
    eh_hr_audit_retention_months = fields.Integer(
        string='Kiosk audit log retention (months)',
        default=60,
        help="Period for which kiosk audit events (match attempts, attendance posts, exceptions) are retained. Used by fair-work or labour-dispute defence; longer is generally safer.",
    )
    eh_hr_consent_text_face = fields.Text(
        string='Face consent text (default)',
        default=DEFAULT_FACE_CONSENT_TEXT,
        help="Default consent prose displayed at the kiosk when an employee enrols. Snapshotted onto each consent record at grant time so audit trail is immutable. Customise to match your jurisdiction.",
    )
    eh_hr_match_threshold = fields.Float(
        string='Face match threshold',
        default=0.55,
        digits=(4, 4),
        help="Cosine distance threshold below which a face is considered a match. Lower values are stricter. Typical range 0.45 (very strict) to 0.65 (lenient).",
    )
    eh_hr_kiosk_idle_seconds = fields.Integer(
        string='Kiosk idle reset (seconds)',
        default=30,
        help="The kiosk shell resets to the welcome screen after this many seconds of inactivity.",
    )
