from markupsafe import Markup

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    hudson_sign_terms = fields.Html(
        string="Sign Terms & Conditions", translate=True,
        default=lambda self: Markup("<h1>Terms &amp; Conditions</h1><p>Your conditions...</p>"))
    hudson_sign_certificate_id = fields.Many2one(
        'certificate.certificate', string="Signing certificate",
        domain="[('company_id', '=', id)]",
        help="Certificate (.pfx / .p12) used to sign the documents cryptographically once everyone has signed.")
