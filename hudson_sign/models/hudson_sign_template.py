from datetime import datetime
import base64

from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError
from odoo.tools import SQL, html2plaintext, is_html_empty, str2bool
from odoo.addons.dms_enterprise_features.models.dms_signature import _extract_pdf_bytes

from .hudson_sign_item_type import split_options

SIGN_REQUESTS_URL = '/odoo/action-hudson_sign.action_hudson_sign_request'

# Role colour themes, shared with the editor's signer settings dialog
ROLE_PALETTE = [
    ('#e2dcf3', '#a495d6', '#2e2252'),
    ('#d1fae5', '#10b981', '#065f46'),
    ('#fef3c7', '#f59e0b', '#92400e'),
    ('#e0e7ff', '#6366f1', '#3730a3'),
    ('#fce7f3', '#ec4899', '#9d174d'),
    ('#e0f2fe', '#0ea5e9', '#075985'),
    ('#ffedd5', '#f97316', '#9a3412'),
    ('#f3e8ff', '#a855f7', '#6b21a8'),
    ('#ccfbf1', '#14b8a6', '#115e59'),
]


class HudsonSignTemplate(models.Model):
    _name = "hudson.sign.template"
    _description = "Signature Template"

    name = fields.Char(string="Template Name", required=True)
    attachment_id = fields.Many2one("ir.attachment", string="PDF Document", required=True)
    active = fields.Boolean(default=True)
    author_id = fields.Many2one("res.users", string="Owner", default=lambda self: self.env.user)

    # Properties (Configuration)
    authorized_ids = fields.Many2many(
        'res.users', 'hudson_sign_template_authorized_rel', 'template_id', 'user_id',
        string="Authorized Users", default=lambda self: self.env.user,
        help="Users who can see and use this template. Leave empty to share it with everyone.")
    cc_partner_ids = fields.Many2many(
        'res.partner', 'hudson_sign_template_cc_rel', 'template_id', 'partner_id', string="CC",
        help="Contacts in copy of every signature request sent with this template.")
    signature_request_validity = fields.Integer(
        string="Valid for", default=60,
        help="Number of days the signers have to sign. Leave 0 for no expiration.")
    directory_id = fields.Many2one(
        'dms.directory', string="Documents folder",
        default=lambda self: self.env['dms.directory'].search([('name', '=', 'Sign')], limit=1),
        help="Folder of the Documents app where the documents to sign are stored.")
    dms_tag_ids = fields.Many2many(
        'dms.tag', 'hudson_sign_template_dms_tag_rel', 'template_id', 'tag_id', string="Documents tags",
        help="Tags set on the documents created to be signed.")
    redirect_url = fields.Char(
        string="Redirect Link", help="Page the signers are sent to after signing.")
    message = fields.Html(string="Message", help="Default message sent to the signers.")
    signed_request_count = fields.Integer(compute="_compute_signed_request_count", string="Signed Document")

    tag_ids = fields.Many2many('hudson.sign.template.tag', string="Tags")
    favorited_ids = fields.Many2many(
        'res.users', 'hudson_sign_template_favorite_rel', 'template_id', 'user_id',
        string="Favorited by", default=lambda self: self.env.user)
    is_favorite = fields.Boolean(
        string="Favorite", compute='_compute_is_favorite', inverse='_inverse_is_favorite',
        compute_sql='_compute_sql_is_favorite', compute_sudo=True)

    role_ids = fields.One2many("hudson.sign.template.role", "template_id", string="Roles")
    sign_item_ids = fields.One2many("hudson.sign.template.item", "template_id", string="Signature Fields")

    # Set when the template was started from a document of the Documents app:
    # requests are then signed on that document instead of a copy.
    dms_file_id = fields.Many2one("dms.file", string="Document", ondelete="set null", index=True)
    dms_revision_id = fields.Many2one("dms.file.revision", string="Document Revision", ondelete="set null")

    # Statistics
    request_ids = fields.One2many("dms.file.signature.request", "template_id", string="Requests")
    count_in_progress = fields.Integer(compute="_compute_counts", string="In Progress")
    count_signed = fields.Integer(compute="_compute_counts", string="Signed")

    @api.model
    def _create_pdf_attachment(self, file_name, raw):
        return self.env['ir.attachment'].create({
            'name': file_name,
            'type': 'binary',
            'mimetype': 'application/pdf',
            'raw': raw,
        })

    @api.model
    def create_template_from_file(self, file_name, file_content, from_templates=False):
        if not file_name.lower().endswith('.pdf'):
            raise UserError(_("Only PDF files are supported."))
        raw = _extract_pdf_bytes(file_content)
        vals = {
            'name': file_name.rsplit('.', 1)[0],
            'attachment_id': self._create_pdf_attachment(file_name, raw).id,
        }
        if from_templates:
            # Uploaded in Sign > Templates: a template right away, listed under "My Favorites"
            vals.update(active=True, favorited_ids=[Command.link(self.env.user.id)])
        else:
            # Uploaded in the Documents dashboard: a draft, kept as a template only
            # with "Save as Template" (or "Save & close" when leaving the editor)
            vals['active'] = False
        template = self.create(vals)
        if from_templates:
            template = template.with_context(hudson_sign_from_templates=True)
        return template.action_open_builder()

    @api.model
    def _get_or_create_for_dms_file(self, dms_file):
        """Template used to request signatures on a document of the Documents app.
        The same template is reopened as long as the document revision is unchanged."""
        revision = dms_file.current_revision_id
        template = self.with_context(active_test=False).search([
            ('dms_file_id', '=', dms_file.id), ('dms_revision_id', '=', revision.id),
        ], limit=1)
        if template:
            return template
        raw = _extract_pdf_bytes(revision.content)
        if not raw:
            raise UserError(_("Please upload a PDF document before setting up signatures."))
        file_name = dms_file.name if dms_file.name.lower().endswith('.pdf') else f"{dms_file.name}.pdf"
        return self.create({
            'name': file_name.rsplit('.', 1)[0],
            'attachment_id': self._create_pdf_attachment(file_name, raw).id,
            'dms_file_id': dms_file.id,
            'dms_revision_id': revision.id,
            'active': False,
        })

    @api.depends_context('uid')
    @api.depends('favorited_ids')
    def _compute_is_favorite(self):
        for template in self:
            template.is_favorite = self.env.user in template.favorited_ids

    def _inverse_is_favorite(self):
        for template in self:
            command = Command.link if template.is_favorite else Command.unlink
            template.favorited_ids = [command(self.env.user.id)]

    def _compute_sql_is_favorite(self, table):
        return SQL(
            "%s IN (SELECT template_id FROM hudson_sign_template_favorite_rel WHERE user_id = %s)",
            table.id, self.env.user.id,
        )

    @api.depends('request_ids.state')
    def _compute_counts(self):
        for template in self:
            # The request behind a share link is never signed itself: not "in progress"
            template.count_in_progress = len(template.request_ids.filtered(
                lambda r: r.state in ['draft', 'sent'] and not r.hudson_request_id.is_shared))
            template.count_signed = len(template.request_ids.filtered(lambda r: r.state == 'signed'))

    def _compute_signed_request_count(self):
        groups = self.env['hudson.sign.request']._read_group(
            [('template_id', 'in', self.ids), ('state', '=', 'signed')], ['template_id'], ['__count'])
        counts = {template.id: count for template, count in groups}
        for template in self:
            template.signed_request_count = counts.get(template.id, 0)

    def action_view_signed_documents(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('hudson_sign.action_hudson_sign_request')
        action.update({
            'name': _("Signed Documents"),
            'domain': [('template_id', '=', self.id), ('state', '=', 'signed')],
            'context': {'create': False},
        })
        return action

    def _get_default_valid_until(self):
        self.ensure_one()
        if self.signature_request_validity > 0:
            return fields.Date.add(fields.Date.context_today(self), days=self.signature_request_validity)
        return False

    # ------------------------------------------------------------------
    # Editor
    # ------------------------------------------------------------------

    def action_open_builder(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'hudson_sign.template_builder',
            'name': self.name,
            'context': {
                'active_id': self.id,
                'active_model': 'hudson.sign.template',
                # Opened from Sign > Templates: the editor shows a "Save" button
                'hudson_sign_from_templates': bool(self.env.context.get('hudson_sign_from_templates')),
            },
        }

    def action_save_as_template(self):
        """Make the document a reusable template, listed in Sign > Templates.

        A document of the Documents app stays bound to its file: it is copied
        into an independent template instead."""
        self.ensure_one()
        if not self.dms_file_id:
            self.write({'active': True, 'favorited_ids': [Command.link(self.env.user.id)]})
            return {'id': self.id, 'name': self.name, 'copied': False}
        template = self.copy({
            'name': self.name,
            'attachment_id': self.attachment_id.copy().id,
            'dms_file_id': False,
            'dms_revision_id': False,
            'active': True,
            'author_id': self.env.user.id,
            'favorited_ids': [Command.set(self.env.user.ids)],
        })
        role_map = {role: role.copy({'template_id': template.id}) for role in self.role_ids}
        for item in self.sign_item_ids:
            item.copy({
                'template_id': template.id,
                'role_id': role_map[item.role_id].id if item.role_id in role_map else False,
            })
        return {'id': template.id, 'name': template.name, 'copied': True, 'action': template.action_open_builder()}

    def get_editor_data(self):
        self.ensure_one()
        if not self.role_ids:
            self.env['hudson.sign.template.role'].create({'name': _("Signer 1"), 'template_id': self.id})
        return {
            'template': {
                'id': self.id,
                'name': self.name,
                'attachment_id': self.attachment_id.id,
                'tag_ids': self.tag_ids.ids,
                'dms_file_id': self.dms_file_id.id,
                'active': self.active,
                'document_name': self.attachment_id.name or self.name,
            },
            'roles': [role._get_editor_values() for role in self.role_ids],
            'items': [item._get_editor_values() for item in self.sign_item_ids],
            'tools': self.env['hudson.sign.item.type'].get_editor_tools(),
            'tags': self.env['hudson.sign.template.tag'].search_read([], ['name', 'color']),
            'views': {
                'template_form': self.env.ref('hudson_sign.hudson_sign_template_view_form_properties').id,
                'item_type_form': self.env.ref('hudson_sign.hudson_sign_item_type_view_form_quick').id,
            },
        }

    def rename_document(self, name):
        self.ensure_one()
        name = (name or '').strip()
        if not name:
            raise UserError(_("The document name cannot be empty."))
        if not name.lower().endswith('.pdf'):
            name += '.pdf'
        self.attachment_id.name = name
        return name

    def save_from_editor(self, roles, items):
        """Persist the editor state. ``roles`` carry either a database id or a
        temporary string id; returns the mapping of temporary ids to database ids."""
        self.ensure_one()
        Role = self.env['hudson.sign.template.role']
        role_map = {}
        for sequence, role in enumerate(roles):
            vals = {
                'name': role.get('name') or _("Signer"),
                'sequence': sequence,
                'color': role.get('color'),
                'border_color': role.get('borderColor'),
                'text_color': role.get('textColor'),
                'auth_method': role.get('authMethod') or 'none',
                'can_delegate': bool(role.get('canDelegate')),
            }
            record = Role.browse(role['id']).exists() if isinstance(role['id'], int) else Role
            if record and record.template_id == self:
                record.write(vals)
            else:
                record = Role.create(dict(vals, template_id=self.id))
            role_map[str(role['id'])] = record.id
        (self.role_ids - Role.browse(list(role_map.values()))).unlink()

        self.sign_item_ids.unlink()
        self.env['hudson.sign.template.item'].create([{
            'template_id': self.id,
            'type_id': item['typeId'],
            'role_id': role_map.get(str(item.get('roleId'))),
            'page_number': item['page'],
            'pos_x': item['x'],
            'pos_y': item['y'],
            'width': item['width'],
            'height': item['height'],
            'placeholder': item.get('placeholder') or False,
            'alignment': item.get('alignment') or 'left',
            'mandatory': bool(item.get('mandatory')),
            'readonly': bool(item.get('readonly')),
            'options': item.get('options') or False,
            'radio_group_name': item.get('radioGroupName') or False,
            'radio_option_value': item.get('radioOptionValue') or False,
        } for item in items if item.get('typeId')])
        return role_map

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def _check_has_fields(self):
        self.ensure_one()
        if not self.sign_item_ids:
            raise UserError(_("Please add at least one field to the template before sending it."))

    def _get_sign_directory(self):
        if len(self) == 1 and self.directory_id:
            return self.directory_id
        sign_dir =self.env['dms.directory'].search([('name', '=', 'Sign')], limit=1)
        if not sign_dir:
            storage = self.env['dms.storage'].search([], limit=1)
            if not storage:
                raise UserError(_("No DMS Storage found. Please configure Document Management System."))
            sign_dir = self.env['dms.directory'].create({
                'name': 'Sign',
                'is_root_directory': True,
                'storage_id': storage.id,
            })
        return sign_dir

    def _get_signing_revision(self):
        """Document revision the signers will sign."""
        self.ensure_one()
        if self.dms_revision_id:
            return self.dms_revision_id
        # Template from the Sign app: every request signs its own copy
        return self._create_signing_copy()

    def _create_signing_copy(self):
        """New document of the Sign folder holding a copy of the template PDF."""
        self.ensure_one()
        file_name = f"{self.name} - {datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        new_file = self.env['dms.file'].sudo().create({
            'name': file_name,
            'directory_id': self._get_sign_directory().id,
            'content': base64.b64encode(self.attachment_id.raw).decode(),
            'mimetype': 'application/pdf',
            'extension': 'pdf',
            'tag_ids': [Command.set(self.dms_tag_ids.ids)],
        })
        revision = new_file.current_revision_id
        if not revision:
            revision = self.env['dms.file.revision'].sudo().create({
                'file_id': new_file.id,
                'version': '1.0',
                'content': new_file.content,
                'file_name': new_file.name,
                'comments': 'Initial revision for signature request.',
            })
            new_file.sudo().write({'current_revision_id': revision.id})
        return revision

    def _send_signature_request(self, signers, options):
        """Create the signature requests.

        :param signers: ordered list of (role, partner) tuples; the order is the signing order
        :param options: dict with subject, message, cc, is_sign_now, signing_order,
            reminders, reminder_days, valid_until, hide_certificate_key
        """
        self.ensure_one()
        self._check_has_fields()
        revision = self._get_signing_revision()
        items = []
        for role, partner in signers:
            for item in self.sign_item_ids.filtered(lambda i: i.role_id == role):
                items.append(item._get_request_payload(str(partner.id)))
        payload = {
            'template_id': self.id,
            'documents': [{'revision_id': revision.id, 'items': items}],
            'subject': options.get('subject') or '',
            'message': options.get('message') or '',
            'cc': options.get('cc') or '',
            'is_sign_now': bool(options.get('is_sign_now')),
            'signingOrder': bool(options.get('signing_order')),
            'reminders': bool(options.get('reminders')),
            'reminderDays': options.get('reminder_days') or 7,
            'validUntil': options.get('valid_until') or False,
            'hideCertificateKey': bool(options.get('hide_certificate_key')),
        }
        if not self.dms_file_id:
            payload['return_url'] = SIGN_REQUESTS_URL
        result = self.env['dms.file.signature.request'].create_from_ui(payload)
        self._apply_role_authentication(revision, signers)
        return result

    @api.model
    def _email_otp_enabled(self):
        """Sign settings: "Email verification" (one-time code before signing)."""
        return str2bool(self.env['ir.config_parameter'].sudo().get_param('hudson_sign.email_otp') or 'False')

    def _apply_role_authentication(self, revision, signers):
        """Extra authentication of the roles ("By Email": one-time code before signing)."""
        requests = self.env['dms.file.signature.request'].sudo().search([
            ('revision_id', '=', revision.id), ('state', 'in', ('draft', 'sent')),
        ])
        for role, partner in signers:
            if role.auth_method != 'email':
                continue
            email = (partner.email or '').strip().lower()
            requests.filtered(
                lambda r: r.recipient_id.partner_id == partner
                or (email and (r.recipient_id.email or '').strip().lower() == email)
            ).write({'hudson_auth_method': 'email'})

    def _open_send_wizard(self, is_sign_now=False):
        self.ensure_one()
        self._check_has_fields()
        roles = self.sign_item_ids.role_id.sorted('sequence')
        return {
            'name': _("Sign Now") if is_sign_now else _("Send Signature Request"),
            'type': 'ir.actions.act_window',
            'res_model': 'hudson.sign.send.wizard',
            'views': [[False, 'form']],
            'target': 'new',
            'context': {
                'default_template_id': self.id,
                'default_is_sign_now': is_sign_now,
                'default_subject': _("Signature Request - %s", self.name),
                'default_message': html2plaintext(self.message) if not is_html_empty(self.message) else False,
                'default_cc': ", ".join(self.cc_partner_ids.filtered('email').mapped('email')) or False,
                'default_valid_until': self._get_default_valid_until(),
                'default_role_ids': [(0, 0, {'role_id': role.id, 'sequence': seq})
                                     for seq, role in enumerate(roles, 1)],
            },
        }

    def action_send(self):
        return self._open_send_wizard()

    def action_sign_now(self):
        return self._open_send_wizard(is_sign_now=True)

    def action_share(self):
        """Share the template by a public link: anyone with it can sign their own copy."""
        self.ensure_one()
        self._check_has_fields()
        if len(self.sign_item_ids.role_id) > 1:
            raise UserError(_(
                "You cannot share this document by link, because it has fields to be filled "
                "by different roles. Use the Send button instead."))
        shared = self.env['hudson.sign.request'].search([
            ('template_id', '=', self.id), ('is_shared', '=', True), ('canceled', '=', False),
        ], order='id desc', limit=1)
        if not shared:
            shared = self._create_shared_request()
        return {
            'name': _("Share Document"),
            'type': 'ir.actions.act_window',
            'res_model': 'hudson.sign.request',
            'res_id': shared.id,
            'views': [[self.env.ref('hudson_sign.hudson_sign_request_view_form_share').id, 'form']],
            'target': 'new',
        }

    def _create_shared_request(self):
        self.ensure_one()
        DmsRequest = self.env['dms.file.signature.request'].sudo()
        revision = self._create_signing_copy()
        # Anonymous until someone signs: the visitor gives their name and email then
        shared_request = DmsRequest.create({
            'revision_id': revision.id,
            'recipient_id': self.env.ref('base.public_user').id,
            'template_id': self.id,
            'state': 'sent',
            'sequence': 1,
            'hudson_auth_method': 'email' if self.sign_item_ids.role_id[:1].auth_method == 'email' else 'none',
        })
        self.env['dms.file.signature.item'].sudo().create([
            shared_request._prepare_signature_item_vals(item._get_request_payload(False))
            for item in self.sign_item_ids
        ])
        return self.env['hudson.sign.request'].create({
            'revision_id': revision.id,
            'template_id': self.id,
            'subject': _("Signature Request - %s", self.name),
            'is_shared': True,
            'tag_ids': [(6, 0, self.tag_ids.ids)],
        })._link_requests(shared_request)


class HudsonSignTemplateRole(models.Model):
    _name = "hudson.sign.template.role"
    _description = "Template Role"
    _order = "sequence, id"

    name = fields.Char(string="Role Name", required=True)
    sequence = fields.Integer(default=10)
    template_id = fields.Many2one("hudson.sign.template", required=True, ondelete="cascade")
    color = fields.Char(string="Color", default=ROLE_PALETTE[0][0])
    border_color = fields.Char(string="Border Color", default=ROLE_PALETTE[0][1])
    text_color = fields.Char(string="Text Color", default=ROLE_PALETTE[0][2])
    auth_method = fields.Selection([
        ('none', 'None'), ('email', 'By Email'),
    ], string="Extra Authentication Step", default='none',
        help="By Email: the signer enters a one-time code sent to their email address before signing.")
    can_delegate = fields.Boolean(string="Can delegate")

    def _get_editor_values(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color or ROLE_PALETTE[0][0],
            'borderColor': self.border_color or ROLE_PALETTE[0][1],
            'textColor': self.text_color or ROLE_PALETTE[0][2],
            'authMethod': self.auth_method or 'none',
            'canDelegate': self.can_delegate,
        }


class HudsonSignTemplateItem(models.Model):
    _name = "hudson.sign.template.item"
    _description = "Signature Template Item"

    template_id = fields.Many2one("hudson.sign.template", required=True, ondelete="cascade")
    type_id = fields.Many2one("hudson.sign.item.type", string="Field Type", required=True)
    role_id = fields.Many2one("hudson.sign.template.role", string="Role")

    # Position and size are ratios (0.0-1.0) of the page dimensions
    page_number = fields.Integer(string="Page Number", required=True, default=1)
    pos_x = fields.Float(string="X Position", required=True, default=0.1)
    pos_y = fields.Float(string="Y Position", required=True, default=0.1)
    width = fields.Float(string="Width", default=0.2)
    height = fields.Float(string="Height", default=0.05)

    placeholder = fields.Char(string="Placeholder")
    alignment = fields.Selection([('left', 'Left'), ('center', 'Center'), ('right', 'Right')], default='left')
    mandatory = fields.Boolean(string="Mandatory", default=True)
    readonly = fields.Boolean(string="Read-only")
    options = fields.Text(string="Options", help="Choices of a selection field, one per line.")
    radio_group_name = fields.Char(string="Radio Group")
    radio_option_value = fields.Char(string="Radio Option")

    def _get_editor_values(self):
        self.ensure_one()
        return {
            'id': self.id,
            'typeId': self.type_id.id,
            'type': self.type_id.item_type,
            'label': self.type_id.name,
            'roleId': self.role_id.id or self.template_id.role_ids[:1].id,
            'page': self.page_number,
            'x': self.pos_x,
            'y': self.pos_y,
            'width': self.width,
            'height': self.height,
            'placeholder': self.placeholder if self.placeholder is not False else (self.type_id.placeholder or self.type_id.name),
            'alignment': self.alignment or 'left',
            'mandatory': self.mandatory,
            'readonly': self.readonly,
            'options': '\n'.join(split_options(self.options or self.type_id.options)),
            'radioGroupName': self.radio_group_name or '',
            'radioOptionValue': self.radio_option_value or '',
        }

    def _get_request_payload(self, assigned_user):
        """Item in the format of ``dms.file.signature.request.create_from_ui``."""
        self.ensure_one()
        return {
            'item_type': self.type_id.item_type,
            'type_id': self.type_id.id,
            'page_number': self.page_number,
            'pos_x': self.pos_x,
            'pos_y': self.pos_y,
            'width': self.width,
            'height': self.height,
            'placeholder': self.placeholder or '',
            'alignment': self.alignment or 'left',
            'mandatory': self.mandatory,
            'readonly': self.readonly,
            'options': '\n'.join(split_options(self.options or self.type_id.options)),
            'radioGroupName': self.radio_group_name or '',
            'radioOptionValue': self.radio_option_value or '',
            'assigned_user_id': assigned_user,
        }


class HudsonSignTemplateUploadWizard(models.TransientModel):
    _name = "hudson.sign.template.upload.wizard"
    _description = "Upload Template Wizard"

    file_content = fields.Binary(string="PDF Document", required=True)
    file_name = fields.Char(string="File Name", required=True)

    def action_upload(self):
        return self.env['hudson.sign.template'].create_template_from_file(self.file_name, self.file_content)
