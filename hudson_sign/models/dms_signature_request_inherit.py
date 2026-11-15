import base64
import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import is_html_empty, str2bool

from ..tools.pdf_certify import certify_pdf

_logger = logging.getLogger(__name__)


def _binary_bytes(value):
    """Raw bytes of a binary field value (BinaryBytes or base64)."""
    if not value:
        return b''
    if hasattr(value, 'content'):
        return value.content
    if isinstance(value, str):
        value = value.encode()
    return base64.b64decode(value)


class DMSFileSignatureItem(models.Model):
    _inherit = "dms.file.signature.item"

    type_id = fields.Many2one("hudson.sign.item.type", string="Field Type", ondelete="set null")


class DMSFileSignatureRequest(models.Model):
    _inherit = "dms.file.signature.request"

    template_id = fields.Many2one("hudson.sign.template", string="Template")
    hudson_request_id = fields.Many2one("hudson.sign.request", string="Group Request", ondelete="cascade")
    color = fields.Integer(compute="_compute_color", string="Color")
    hudson_auth_method = fields.Selection(
        [('none', 'None'), ('email', 'By Email')], string="Extra Authentication",
        default='none', copy=False)
    hudson_email_otp = fields.Boolean(
        compute='_compute_hudson_email_otp',
        help="A one-time code sent by email is asked before signing (Sign settings: Email verification).")

    @api.depends_context('uid')
    def _compute_hudson_email_otp(self):
        # Sign settings "Email verification": every signer, no per-signer setup
        self.hudson_email_otp = self.env['hudson.sign.template']._email_otp_enabled()

    @api.depends('state')
    def _compute_color(self):
        for req in self:
            # Green tag once signed, grey while waiting
            req.color = 10 if req.state == 'signed' else 0

    # ------------------------------------------------------------------
    # Hooks of the document signature editor (dms_enterprise_features)
    # ------------------------------------------------------------------

    def _prepare_signature_item_vals(self, item):
        vals = super()._prepare_signature_item_vals(item)
        item_type = self.env['hudson.sign.item.type'].browse(int(item.get('type_id') or 0)).exists()
        if item_type:
            vals['type_id'] = item_type.id
            # The signer fills the field: show what is expected ("Name", "Email"...),
            # never the data saved on the contact
            if not vals.get('placeholder'):
                vals['placeholder'] = item_type.name
        return vals

    def _get_blocking_requests(self):
        """Requests of earlier signers that must be signed before this one."""
        self.ensure_one()
        if self.state not in ('draft', 'sent') or not self.revision_id:
            return self.browse()
        earlier = self.sudo().search([
            ('revision_id', '=', self.revision_id.id),
            ('id', '!=', self.id),
            ('state', 'in', ('draft', 'sent')),
            ('sequence', '<', self.sequence),
        ], order='sequence, id')
        if self.state == 'draft':
            # Signing order: not this signer's turn yet
            return earlier
        if self.is_sign_now:
            # "Sign Now" with several signers: one after the other
            return earlier.filtered('is_sign_now')
        return self.browse()

    @api.model
    def _on_requests_created_from_ui(self, revision, requests, payload):
        res = super()._on_requests_created_from_ui(revision, requests, payload)
        # Pending requests replaced by the editor leave their Sign document empty
        self.env['hudson.sign.request'].search([
            ('revision_id', '=', revision.id), ('request_ids', '=', False),
        ]).unlink()
        if requests:
            template_id = payload.get('template_id') or False
            sign_request = self.env['hudson.sign.request'].create({
                'revision_id': revision.id,
                'template_id': template_id,
                'subject': payload.get('subject') or False,
                'message': payload.get('message') or False,
                'valid_until': payload.get('validUntil') or False,
                'tag_ids': [(6, 0, self.env['hudson.sign.template'].browse(template_id).tag_ids.ids)] if template_id else False,
            })
            requests.write({'hudson_request_id': sign_request.id, 'template_id': template_id})
        return res

    # ------------------------------------------------------------------
    # Signing
    # ------------------------------------------------------------------

    def action_apply_signature(self):
        self.ensure_one()
        sign_request = self.hudson_request_id
        if sign_request.state == 'canceled':
            raise UserError(_("This signature request has been canceled."))
        if self.valid_until and self.valid_until < fields.Date.context_today(self):
            raise UserError(_("This signature request has expired."))
        res = super().action_apply_signature()
        for item in self.item_ids.filtered(lambda i: i.type_id.update_field and i.value_text):
            item.type_id._write_back_value(self.recipient_id, item.value_text)
        if sign_request:
            sign_request.message_post(body=_("Signed by %s", self.recipient_id.name))
        return res

    def _get_signature_email_extra_html(self):
        """Sign settings: default Terms & Conditions in the request email."""
        html = super()._get_signature_email_extra_html()
        params = self.env['ir.config_parameter'].sudo()
        if not str2bool(params.get_param('hudson_sign.use_terms') or 'False'):
            return html
        company = self._hudson_sign_company()
        if is_html_empty(company.hudson_sign_terms):
            return html
        if params.get_param('hudson_sign.terms_type') == 'web':
            block = Markup(
                '<p style="color: #444; font-size: 13px; margin-top: 20px;">'
                'By signing this document, you accept the '
                '<a href="%s" style="color: #0066cc;">Terms &amp; Conditions</a>.</p>'
            ) % f"{self.get_base_url()}/hudson_sign/terms/{company.id}"
        else:
            block = Markup(
                '<div style="border-top: 1px solid #ddd; margin-top: 20px; padding-top: 10px; '
                'font-size: 13px; color: #444;">%s</div>'
            ) % company.hudson_sign_terms
        return Markup(html) + block

    def _hudson_send_otp_email(self, email, code, minutes):
        """Extra authentication "By Email": send the one-time code to the signer."""
        self.ensure_one()
        company = self._hudson_sign_company()
        doc_name = self.revision_id.file_id.name or _("Document")
        body = Markup(
            '<div style="font-family: \'Segoe UI\', Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #444;">'
            '<h2 style="font-size: 20px; font-weight: 500; border-bottom: 1px solid #ddd; padding-bottom: 10px;">%(title)s</h2>'
            '<p>%(intro)s</p>'
            '<p style="font-size: 30px; letter-spacing: 8px; font-weight: 600; color: #222; margin: 24px 0;">%(code)s</p>'
            '<p style="color: #666; font-size: 13px;">%(validity)s</p>'
            '<p style="color: #666; font-size: 13px;">%(warning)s</p>'
            '<p style="text-align: center; font-size: 12px; color: #888; border-top: 1px solid #ddd; padding-top: 10px;">%(company)s</p>'
            '</div>'
        ) % {
            'title': _("Verify your identity"),
            'intro': _("Use this code to sign the document %s:", doc_name),
            'code': code,
            'validity': _("The code is valid for %s minutes.", minutes),
            'warning': _("If you did not try to sign this document, you can ignore this email. Never share this code."),
            'company': company.name,
        }
        mail_server = self.env['ir.mail_server'].sudo().search([], limit=1, order='sequence asc')
        mail = self.env['mail.mail'].sudo().create({
            'subject': _("%(code)s is your code to sign %(doc)s", code=code, doc=doc_name),
            'email_from': company.email or self.create_uid.email or self.env.user.email,
            'email_to': email,
            'body_html': body,
            'auto_delete': True,
            'mail_server_id': mail_server.id,
        })
        mail.send(raise_exception=False)

    def _hudson_sign_company(self):
        self.ensure_one()
        file = self.revision_id.file_id
        return (file.company_id if 'company_id' in file._fields else False) or self.env.company

    # ------------------------------------------------------------------
    # Cryptographic signature (Sign settings)
    # ------------------------------------------------------------------

    def _stamp_pdf(self):
        res = super()._stamp_pdf()
        self._hudson_certify_completed_document()
        return res

    def _hudson_certify_completed_document(self):
        """Once everyone signed, sign the document with the company certificate (.pfx / .p12)."""
        self.ensure_one()
        revision = self.revision_id.sudo()
        if not revision or revision.file_id.mimetype != 'application/pdf':
            return
        if self.sudo().search_count([('revision_id', '=', revision.id), ('state', '!=', 'signed')]):
            return
        company = self._hudson_sign_company().sudo()
        certificate = company.hudson_sign_certificate_id
        if not certificate:
            return
        if not certificate.is_valid or not certificate.private_key_id:
            _logger.warning("Sign: certificate %s is not valid, document %s not certified.",
                            certificate.display_name, revision.file_id.display_name)
            return
        try:
            chain, issuer = [], certificate.issuer_cert_id
            while issuer and issuer != certificate and len(chain) < 5:
                chain.append(_binary_bytes(issuer.pem_certificate))
                issuer = issuer.issuer_cert_id
            signers = self.sudo().search([('revision_id', '=', revision.id)]).recipient_id
            signed = certify_pdf(
                _binary_bytes(revision.content),
                _binary_bytes(certificate.private_key_id.pem_key),
                _binary_bytes(certificate.pem_certificate),
                extra_pem_certificates=chain,
                name=company.name,
                reason=_("Signed by %s", ", ".join(signers.mapped('name'))),
            )
        except Exception:
            _logger.exception("Sign: could not certify document %s.", revision.file_id.display_name)
            return
        revision.write({'content': base64.b64encode(signed).decode()})
        revision._sync_to_file()

    def send_signature_email(self):
        active = self.filtered(lambda r: r.hudson_request_id.state != 'canceled')
        return super(DMSFileSignatureRequest, active).send_signature_email()

    def action_download(self):
        self.ensure_one()
        if not self.revision_id or not self.revision_id.content:
            return
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/dms.file.revision/{self.revision_id.id}/content?download=true',
            'target': 'self',
        }

    def action_resend(self):
        self.filtered(lambda r: r.state != 'signed').send_signature_email()
