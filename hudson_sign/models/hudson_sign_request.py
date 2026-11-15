import base64

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.addons.dms_enterprise_features.models.dms_signature import _extract_pdf_bytes

from .hudson_sign_template import ROLE_PALETTE


class HudsonSignRequest(models.Model):
    _name = "hudson.sign.request"
    _description = "Signature Request Group"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = "name"
    _order = "create_date desc, id desc"

    name = fields.Char(related="revision_id.file_name", string="Name", store=True)
    revision_id = fields.Many2one("dms.file.revision", string="Document", required=True, ondelete="cascade")
    file_id = fields.Many2one(related="revision_id.file_id", string="File", store=True)
    template_id = fields.Many2one("hudson.sign.template", string="Template")
    subject = fields.Char(string="Subject")
    message = fields.Text(string="Message")
    valid_until = fields.Date(string="Valid Until", tracking=True)
    canceled = fields.Boolean(string="Canceled", copy=False, tracking=True)
    # Shared by link from Sign > Templates: never signed itself, every visitor
    # who signs it gets a request of their own (see _create_from_share)
    is_shared = fields.Boolean(string="Shared by Link", copy=False, readonly=True)
    share_link = fields.Char(compute="_compute_share_link", string="Share Link")
    tag_ids = fields.Many2many('hudson.sign.template.tag', 'hudson_sign_request_tag_rel', 'request_id', 'tag_id', string="Tags")

    request_ids = fields.One2many("dms.file.signature.request", "hudson_request_id", string="Signers")
    signed_count = fields.Integer(compute="_compute_signer_counts", string="Signed")
    signer_count = fields.Integer(compute="_compute_signer_counts", string="Signers Count")

    state = fields.Selection([
        ('draft', 'Draft'),
        ('shared', 'Shared'),
        ('sent', 'To Sign'),
        ('signed', 'Signed'),
        ('canceled', 'Cancelled'),
        ('expired', 'Expired'),
    ], compute='_compute_state', string="Status", store=True, tracking=True)

    @api.depends('request_ids.state', 'canceled', 'valid_until', 'is_shared')
    def _compute_state(self):
        today = fields.Date.context_today(self)
        for req in self:
            if req.is_shared:
                req.state = 'canceled' if req.canceled else 'shared'
            elif req.request_ids and all(r.state == 'signed' for r in req.request_ids):
                req.state = 'signed'
            elif req.canceled:
                req.state = 'canceled'
            elif not req.request_ids:
                req.state = 'draft'
            elif req.valid_until and req.valid_until < today:
                req.state = 'expired'
            else:
                req.state = 'sent'

    @api.depends('is_shared', 'request_ids.access_token')
    def _compute_share_link(self):
        for req in self:
            shared_request = req.sudo().request_ids[:1] if req.is_shared else False
            req.share_link = shared_request.get_portal_url() if shared_request else False

    def write(self, vals):
        res = super().write(vals)
        if 'valid_until' in vals:
            # The signing page checks the expiry date of the signer requests
            self.sudo().request_ids.filtered(lambda r: r.state != 'signed').write({'valid_until': vals['valid_until']})
        return res

    # ------------------------------------------------------------------
    # Sharing by link
    # ------------------------------------------------------------------

    def action_stop_sharing(self):
        self.write({'canceled': True})
        return {'type': 'ir.actions.act_window_close'}

    def _link_requests(self, requests):
        requests.write({'hudson_request_id': self.id})
        return self

    def _create_from_share(self, partner):
        """Copy of a shared request for one visitor: their own document, request and fields.

        :return: the new ``dms.file.signature.request`` and the mapping of the
            shared field ids to the new ones
        """
        self.ensure_one()
        shared = self.sudo()
        if not shared.is_shared or shared.state != 'shared':
            raise UserError(_("This document is no longer shared."))
        if shared.valid_until and shared.valid_until < fields.Date.context_today(self):
            raise UserError(_("This signature request has expired."))
        shared_request = shared.request_ids[:1]
        DmsRequest = self.env['dms.file.signature.request'].sudo()
        user_id = DmsRequest._get_or_create_user(str(partner.id))
        if not user_id:
            raise UserError(_("Could not register the signer %s.", partner.display_name))
        revision = shared.template_id.sudo()._create_signing_copy()
        new_request = DmsRequest.create({
            'revision_id': revision.id,
            'recipient_id': user_id,
            'template_id': shared.template_id.id,
            'state': 'sent',
            'sequence': 1,
            'valid_until': shared.valid_until,
            'hide_certificate_key': shared_request.hide_certificate_key,
            'hudson_auth_method': shared_request.hudson_auth_method,
        })
        item_map = {}
        for item in shared_request.item_ids:
            item_map[item.id] = item.copy({'request_id': new_request.id}).id
        shared.create({
            'revision_id': revision.id,
            'template_id': shared.template_id.id,
            'subject': shared.subject,
            'tag_ids': [(6, 0, shared.tag_ids.ids)],
        })._link_requests(new_request)
        revision.file_id.status = 'in_approval'
        shared.message_post(body=_(
            "%(name)s (%(email)s) signed through the shared link.", name=partner.name, email=partner.email))
        return new_request, item_map

    def _notify_refusal(self, signer_name, signer_email, reason):
        """Log a refusal to sign and notify the sender and the other signers."""
        self.ensure_one()
        sign_request = self.sudo()
        partners = sign_request.create_uid.partner_id
        if not sign_request.is_shared:
            partners |= sign_request.request_ids.recipient_id.partner_id
            sign_request.canceled = True
        body = Markup("<p>%s</p><p>%s</p>") % (
            _("%(name)s (%(email)s) declined to sign the document.", name=signer_name, email=signer_email or "-"),
            _("Reason: %s", reason),
        )
        author = signer_email and self.env['res.partner'].sudo().search([('email', '=ilike', signer_email)], limit=1)
        sign_request.message_post(
            body=body,
            subject=_("Signature refused: %s", sign_request.name),
            author_id=author.id if author else False,
            partner_ids=partners.ids,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    @api.depends('request_ids.state')
    def _compute_signer_counts(self):
        for req in self:
            req.signer_count = len(req.request_ids)
            req.signed_count = len(req.request_ids.filtered(lambda r: r.state == 'signed'))

    def action_send_reminder(self):
        pending = self.filtered(lambda r: r.state == 'sent').request_ids.filtered(lambda r: r.state == 'sent')
        pending.send_signature_email()
        pending.write({'last_reminder_date': fields.Date.context_today(self)})
        for req in self:
            names = ", ".join(req.request_ids.filtered(lambda r: r.state == 'sent').mapped('recipient_id.name'))
            if names:
                req.message_post(body=_("Reminder sent to %s", names))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success' if pending else 'warning',
                'message': _("Reminder sent.") if pending else _("Nobody is waiting to sign this document."),
            },
        }

    # Kept for backward compatibility with older views/buttons
    def action_resend(self):
        return self.action_send_reminder()

    def action_cancel(self):
        self.filtered(lambda r: r.state in ('draft', 'sent', 'expired')).write({'canceled': True})

    def action_download(self):
        self.ensure_one()
        file = self.file_id
        if file and file.content:
            url = f'/web/content/dms.file/{file.id}/content?download=true'
        elif self.revision_id.content:
            url = f'/web/content/dms.file.revision/{self.revision_id.id}/content?download=true'
        else:
            return
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'self'}

    def action_open_file(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dms.file',
            'res_id': self.file_id.id,
            'views': [[False, 'form']],
        }

    # ------------------------------------------------------------------
    # Document viewer
    # ------------------------------------------------------------------

    def action_open_viewer(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'hudson_sign.document_viewer',
            'name': self.name,
            'context': {'active_id': self.id, 'active_model': self._name},
        }

    def action_open_details(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'views': [[self.env.ref('hudson_sign.hudson_sign_request_view_form').id, 'form']],
            'target': 'current',
        }

    def _get_current_revision(self):
        """Signing creates a new revision of the document: the requests follow the latest one."""
        self.ensure_one()
        revisions = self.sudo().request_ids.revision_id
        return revisions.sorted('id')[-1:] or self.sudo().revision_id

    def _get_current_pdf(self):
        return _extract_pdf_bytes(self._get_current_revision().content)

    def _get_sorted_signers(self):
        return self.sudo().request_ids.sorted(lambda r: (r.sequence, r.id))

    def get_viewer_data(self):
        self.ensure_one()
        self.check_access('read')
        signers = []
        items = []
        for index, request in enumerate(self._get_sorted_signers()):
            color, border_color, text_color = ROLE_PALETTE[index % len(ROLE_PALETTE)]
            signers.append({
                'id': request.id,
                'name': request.recipient_id.name,
                'state': request.state,
                'isMe': request.recipient_id == self.env.user,
                'color': color,
                'borderColor': border_color,
                'textColor': text_color,
            })
            if request.state == 'signed':
                # Already stamped on the document
                continue
            for item in request.item_ids:
                items.append({
                    'id': item.id,
                    'type': item.item_type,
                    'roleId': request.id,
                    'page': item.page_number,
                    'x': item.pos_x,
                    'y': item.pos_y,
                    'width': item.width,
                    'height': item.height,
                    'placeholder': item.value_text or item.placeholder or item.type_id.name or '',
                    'alignment': item.alignment or 'left',
                })
        return {
            'request': {
                'id': self.id,
                'name': self.name,
                'state': self.state,
                'tag_ids': self.tag_ids.ids,
                'canCancel': self.state in ('draft', 'sent', 'expired'),
            },
            'pdf': base64.b64encode(self._get_current_pdf()).decode(),
            'signers': signers,
            'items': items,
            'tags': self.env['hudson.sign.template.tag'].search_read([], ['name', 'color']),
        }

    def action_sign_now(self):
        self.ensure_one()
        request = self.sudo().request_ids.filtered(lambda r: r.recipient_id == self.env.user and r.state == 'sent')[:1]
        if not request:
            raise UserError(_("You have no signature pending on this document."))
        return {'type': 'ir.actions.act_url', 'url': request.get_portal_url(), 'target': 'self'}

    def _get_pdf_file_name(self):
        file_name = self.name or _("Document")
        return file_name if file_name.lower().endswith('.pdf') else f"{file_name}.pdf"

    def action_send_to(self):
        """Send a copy of the document, as it currently is, to anyone."""
        self.ensure_one()
        attachment = self.env['ir.attachment'].create({
            'name': self._get_pdf_file_name(),
            'raw': self._get_current_pdf(),
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _("Send to"),
            'res_model': 'mail.compose.message',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_model': self._name,
                'default_res_ids': self.ids,
                'default_composition_mode': 'comment',
                'default_subject': self.subject or self.name,
                'default_attachment_ids': [(6, 0, attachment.ids)],
            },
        }

    def action_save_as_template(self):
        """New template from the unsigned document, with one signer role per signer."""
        self.ensure_one()
        raw = _extract_pdf_bytes(self.sudo().revision_id.content)
        if not raw:
            raise UserError(_("The document has no PDF content."))
        Template = self.env['hudson.sign.template']
        file_name = self._get_pdf_file_name()
        template = Template.create({
            'name': self.template_id.name or file_name.rsplit('.', 1)[0],
            'attachment_id': Template._create_pdf_attachment(file_name, raw).id,
            'tag_ids': [(6, 0, self.tag_ids.ids)],
        })
        ItemType = self.env['hudson.sign.item.type']
        item_vals = []
        for index, request in enumerate(self._get_sorted_signers()):
            color, border_color, text_color = ROLE_PALETTE[index % len(ROLE_PALETTE)]
            role = self.env['hudson.sign.template.role'].create({
                'template_id': template.id,
                'name': request.recipient_id.name or _("Signer %s", index + 1),
                'sequence': index,
                'color': color,
                'border_color': border_color,
                'text_color': text_color,
            })
            for item in request.item_ids:
                item_type = item.type_id or ItemType.search([('item_type', '=', item.item_type)], limit=1)
                if not item_type:
                    continue
                item_vals.append({
                    'template_id': template.id,
                    'role_id': role.id,
                    'type_id': item_type.id,
                    'page_number': item.page_number,
                    'pos_x': item.pos_x,
                    'pos_y': item.pos_y,
                    'width': item.width,
                    'height': item.height,
                    'placeholder': item.placeholder,
                    'alignment': item.alignment or 'left',
                    'mandatory': item.mandatory,
                    'readonly': item.readonly,
                    'options': item.options,
                    'radio_group_name': item.radio_group_name,
                    'radio_option_value': item.radio_option_value,
                })
        self.env['hudson.sign.template.item'].create(item_vals)
        return template.action_open_builder()

    @api.model
    def _cron_update_expired(self):
        overdue = self.search([
            ('state', '=', 'sent'),
            ('valid_until', '<', fields.Date.context_today(self)),
        ])
        self.env.add_to_compute(self._fields['state'], overdue)
        overdue.flush_recordset(['state'])
