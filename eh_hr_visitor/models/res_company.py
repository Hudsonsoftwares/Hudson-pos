# -*- encoding: utf-8 -*-
from odoo import fields, models


DEFAULT_NDA_TEXT = (
    "While on site I agree to follow the instructions of my host and any "
    "site safety signage. I will not photograph confidential information, "
    "share access credentials, or copy proprietary documents. I acknowledge "
    "that some areas may be restricted to staff only. By signing in I "
    "confirm I have read and accept these terms."
)

DEFAULT_VISITOR_AGREEMENT_TEXT = (
    "I agree to comply with all company rules and regulations during my visit. "
    "I understand that my host is responsible for me while I am on the premises."
)

DEFAULT_SAFETY_DECLARATION_TEXT = (
    "I declare that I have not been exposed to any contagious diseases recently. "
    "I agree to follow all safety guidelines and evacuation procedures."
)

DEFAULT_PRIVACY_CONSENT_TEXT = (
    "I consent to the collection and processing of my personal data for the "
    "purpose of visitor management, in accordance with the company's privacy policy."
)


class ResCompany(models.Model):
    _inherit = 'res.company'

    eh_hr_visitor_nda_text = fields.Text(
        string='Visitor NDA text',
        default=DEFAULT_NDA_TEXT,
        help="Default NDA prose displayed at the visitor kiosk when the chosen purpose requires acceptance. Snapshotted onto each visitor record at sign-in time so the audit trail cannot drift.",
    )
    
    eh_hr_visitor_visitor_agreement_text = fields.Text(
        string='Visitor Agreement text',
        default=DEFAULT_VISITOR_AGREEMENT_TEXT,
        help="Default Visitor Agreement prose displayed when required.",
    )

    eh_hr_visitor_safety_declaration_text = fields.Text(
        string='Safety Declaration text',
        default=DEFAULT_SAFETY_DECLARATION_TEXT,
        help="Default Safety Declaration prose displayed when required.",
    )

    eh_hr_visitor_privacy_consent_text = fields.Text(
        string='Privacy Consent text',
        default=DEFAULT_PRIVACY_CONSENT_TEXT,
        help="Default Privacy Consent prose displayed when required.",
    )

    eh_hr_visitor_auto_checkout_enabled = fields.Boolean(
        string='Auto check-out at end of day',
        default=True,
    )
    eh_hr_visitor_auto_checkout_hour = fields.Integer(
        string='Auto check-out hour',
        default=18,
        help="Hour of day (24h) past which any visitor still signed in is automatically signed out by the daily cron.",
    )
    eh_hr_visitor_retention_days = fields.Integer(
        string='Visitor retention (days)',
        default=365,
        help="Signed-out visitor rows are deleted after this many days. NDA snapshot and photo go with the row.",
    )
    eh_hr_visitor_photo_consent_text = fields.Text(
        string='Photo consent text',
        default=(
            "I consent to my photo being captured and stored alongside my "
            "visitor record. The photo is deleted with my visitor record at "
            "the end of the retention period configured by my host. I "
            "understand the photo is used solely to assist site staff in "
            "verifying my presence on site."
        ),
        help="Shown above the camera button on the visitor kiosk when the chosen purpose requires a photo. Snapshotted with the visitor record.",
    )
