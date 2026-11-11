# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import base64
import io
import logging
import uuid
from datetime import datetime, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from PyPDF2 import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    from reportlab.lib.colors import black
except ImportError:
    _logger.debug("PyPDF2 or reportlab not installed.")

def _extract_pdf_bytes(raw_field):
    """Safely extracts raw binary bytes from a PDF binary/base64 field."""
    if not raw_field:
        return b''
    raw_bytes = None
    if hasattr(raw_field, '__bytes__') or isinstance(raw_field, (bytes, bytearray)):
        raw_bytes = bytes(raw_field)
    elif isinstance(raw_field, str):
        if raw_field.startswith('%PDF'):
            return raw_field.encode('latin1')
        try:
            raw_bytes = base64.b64decode(raw_field.encode('ascii'))
        except Exception:
            raw_bytes = raw_field.encode('utf-8')

    if raw_bytes is not None:
        idx = raw_bytes.find(b'%PDF')
        if idx != -1:
            return raw_bytes[idx:]
        try:
            decoded = base64.b64decode(raw_bytes)
            idx_dec = decoded.find(b'%PDF')
            if idx_dec != -1:
                return decoded[idx_dec:]
        except Exception:
            pass
        return raw_bytes
    return b''

class DMSFileSignatureItem(models.Model):
    _name = "dms.file.signature.item"
    _description = "Signature Request Item"

    request_id = fields.Many2one("dms.file.signature.request", string="Request", required=True, ondelete="cascade")
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="request_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    item_type = fields.Selection([
        ('signature', 'Signature'),
        ('initial', 'Initials'),
        ('initials', 'Initials'),
        ('name', 'Name'),
        ('email', 'Email'),
        ('phone', 'Phone'),
        ('company', 'Company'),
        ('text', 'Text'),
        ('multiline', 'Multiline'),
        ('checkbox', 'Checkbox'),
        ('radio', 'Radio'),
        ('selection', 'Selection'),
        ('date', 'Date'),
        ('strikethrough', 'Strikethrough'),
        ('stamp', 'Stamp'),
    ], string="Type", required=True)
    page_number = fields.Integer(string="Page Number", required=True, default=1)
    pos_x = fields.Float(string="X Position", required=True, default=100.0)
    pos_y = fields.Float(string="Y Position", required=True, default=100.0)
    width = fields.Float(string="Width", default=150.0)
    height = fields.Float(string="Height", default=50.0)
    
    value_text = fields.Text(string="Text Value")
    value_image = fields.Binary(string="Image Value", attachment=True)
    value_bool = fields.Boolean(string="Boolean Value")
    options = fields.Char(string="Options (comma separated)")
    
    placeholder = fields.Char(string="Placeholder")
    alignment = fields.Selection([('left', 'Left'), ('center', 'Center'), ('right', 'Right')], default='left')
    mandatory = fields.Boolean(string="Mandatory", default=True)
    readonly = fields.Boolean(string="Read-only", default=False)
    radio_group_name = fields.Char(string="Radio Group Name")
    radio_option_value = fields.Char(string="Radio Option Value")
    
    state = fields.Selection([('draft', 'Draft'), ('completed', 'Completed')], string="Status", default="draft")

class DMSFileSignatureRequest(models.Model):
    _name = "dms.file.signature.request"
    _description = "Document Signature Request"
    _rec_name = "recipient_id"
    _inherit = ['portal.mixin', 'mail.thread']

    revision_id = fields.Many2one(
        comodel_name="dms.file.revision",
        string="Document Revision",
        required=True,
        ondelete="cascade"
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="revision_id.file_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    is_sign_now = fields.Boolean("Is Sign Now", default=False)
    pdf_content = fields.Binary(
        compute="_compute_pdf_content",
        string="Document Preview",
    )
    recipient_id = fields.Many2one(
        comodel_name="res.users",
        string="Recipient",
        required=True
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('sent', 'Sent'),
            ('signed', 'Signed')
        ],
        string="Status",
        default="draft",
        tracking=True
    )
    item_ids = fields.One2many('dms.file.signature.item', 'request_id', string="Items")
    signed_date = fields.Datetime(string="Signed On")
    sequence = fields.Integer(string="Sequence", default=10)
    access_token = fields.Char(string="Access Token", copy=False)
    
    # New fields for Reminders and Expiration
    reminders_enabled = fields.Boolean(string="Reminders Enabled", default=False)
    reminder_days = fields.Integer(string="Reminder Days", default=7)
    last_reminder_date = fields.Date(string="Last Reminder Sent Date")
    valid_until = fields.Date(string="Valid Until")
    hide_certificate_key = fields.Boolean(string="Hide Certificate Key", default=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('access_token'):
                vals['access_token'] = str(uuid.uuid4())
        records = super().create(vals_list)
        dms_user_group = self.env.ref('dms.group_dms_user', raise_if_not_found=False)
        if dms_user_group:
            for record in records:
                if record.recipient_id and not record.recipient_id.share:
                    dms_user_group.sudo().write({'user_ids': [(4, record.recipient_id.id)]})
        return records

    def get_portal_url(self):
        """Return a secure URL for the signer to access the document."""
        self.ensure_one()
        base_url = self.get_base_url()
        return f"{base_url}/dms/signature/{self.id}/{self.access_token}"

    @api.model
    def _get_or_create_user(self, user_string):
        """Get or create a portal user from a partner ID, email address, or name string."""
        if not user_string:
            return False

        partner = False

        # Case 1: user_string is a partner ID (numeric string or int)
        user_str = str(user_string).strip()
        if user_str.isdigit():
            partner = self.env['res.partner'].sudo().browse(int(user_str))
            if not partner.exists():
                partner = False

        # Case 2: user_string is an email address
        if not partner:
            if '@' in user_str:
                email = user_str
                user = self.env['res.users'].sudo().search(['|', ('login', '=', email), ('email', '=', email)], limit=1)
                if user:
                    return user.id
                partner = self.env['res.partner'].sudo().search([('email', '=', email)], limit=1)
                if not partner:
                    name = email.split('@')[0].replace('.', ' ').title()
                    partner = self.env['res.partner'].sudo().create({
                        'name': name,
                        'email': email,
                    })
            else:
                # Case 3: name string
                name = user_str
                user = self.env['res.users'].sudo().search([('name', '=', name)], limit=1)
                if user:
                    return user.id
                partner = self.env['res.partner'].sudo().search([('name', '=', name)], limit=1)
                if not partner:
                    partner = self.env['res.partner'].sudo().create({
                        'name': name,
                        'email': False,
                    })

        if not partner:
            return False

        # If partner already has a linked active user, return it
        user = partner.user_ids.filtered(lambda u: u.active)[:1] or partner.user_ids[:1]
        if user:
            return user.id

        # A user may already own this email under another contact (e.g. the admin's
        # personal contact): reuse it, a second user with the same login cannot be created.
        email = (partner.email or '').strip()
        if email:
            user = self.env['res.users'].sudo().search(
                ['|', ('login', '=ilike', email), ('email', '=ilike', email)], limit=1)
            if user:
                return user.id

        # Otherwise create a portal user for this partner
        portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
        public_group = self.env.ref('base.group_public', raise_if_not_found=False)
        login = email or f'portal_user_{partner.id}'
        try:
            # Savepoint: a failed insert must not abort the whole transaction
            with self.env.cr.savepoint():
                user = self.env['res.users'].sudo().with_context(no_reset_password=True)._create_user_from_template({
                    'name': partner.name,
                    'login': login,
                    'partner_id': partner.id,
                    'email': partner.email or False,
                })
            group_commands = []
            if portal_group:
                group_commands.append((4, portal_group.id))
            if public_group:
                group_commands.append((3, public_group.id))
            if group_commands:
                user.sudo().write({
                    'active': True,
                    'group_ids': group_commands,
                })
            return user.id
        except Exception as e:
            _logger.warning("Could not create portal user for partner %s (%s): %s", partner.name, user_string, e)
            user = self.env['res.users'].sudo().search([('partner_id', '=', partner.id)], limit=1)
            return user.id if user else False


    def _get_signature_email_extra_html(self):
        """Extension hook: HTML added to the signature request email, under the sign button."""
        return ''

    def _send_mails_batch(self, mails):
        """Send ``mails`` together (one connection to the mail server instead of one per
        email); the ones that fail are put back in the queue and retried a minute later."""
        mails = mails.sudo().exists()
        if not mails:
            return
        try:
            mails.send(raise_exception=False)
        except Exception as e:
            _logger.warning("Sending emails %s failed: %s", mails.ids, e)
        failed = mails.filtered(lambda m: m.state in ('exception', 'outgoing'))
        if failed:
            _logger.warning("Emails %s could not be sent now, retried by the email queue.", failed.ids)
            failed.write({'state': 'outgoing'})
            self.env.ref('mail.ir_cron_mail_scheduler_action').sudo()._trigger(
                fields.Datetime.now() + timedelta(minutes=1))

    def send_signature_email(self):
        """Queue signature request emails via mail.mail (non-blocking)."""
        mails = self.env['mail.mail']
        for req in self:
            recipient = req.recipient_id
            recipient_email = (recipient.email or (recipient.partner_id and recipient.partner_id.email) or '').strip()
            if not recipient or not recipient_email:
                _logger.warning(
                    "Skipping signature email for request %s: recipient has no email.", req.id
                )
                continue

            base_url = self.env['ir.config_parameter'].sudo().get_param(
                'web.base.url', 'http://localhost:8069'
            )
            sign_url = f"{base_url}/dms/signature/{req.id}/{req.access_token}"
            doc_name = (
                req.revision_id.file_id.name
                if req.revision_id and req.revision_id.file_id
                else 'Document'
            )
            sender_name = self.env.user.name or self.env.company.name
            sender_email = self.env.user.email or self.env.company.email
            company_name = self.env.company.name
            recipient_name = recipient.name or (recipient.partner_id and recipient.partner_id.name) or recipient_email
            
            message_html = ""
            
            valid_until_text = ""
            if req.valid_until:
                valid_until_text = f"<p style='color: #444; margin-top: 20px;'>You have until <strong>{req.valid_until.strftime('%Y-%m-%d')}</strong> to sign the document.</p>"

            body_html = f"""
<div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 650px; margin: 0 auto; color: #444;">
    <div style="padding: 10px 0;">
        <div style="font-size: 11px; color: #666; margin-bottom: 5px;">Signature Request</div>
        <h2 style="margin: 0; color: #444; font-size: 22px; padding-bottom: 10px; border-bottom: 1px solid #ddd;">{doc_name}</h2>
    </div>
    
    <div style="padding: 20px 0;">
        <p style="margin-top: 0;">Hello <strong>{recipient_name}</strong> (<a href="mailto:{recipient_email}" style="color: #0066cc; text-decoration: none;">{recipient_email}</a>),</p>
        
        <p style="margin-bottom: 25px;">
            {sender_name} (<a href="mailto:{sender_email}" style="color: #0066cc; text-decoration: none;">{sender_email}</a>) has requested your signature on the document {doc_name}.
        </p>

        <div style="text-align: center; margin: 40px 0;">
            <a href="{sign_url}"
               style="background-color: #875A7B; color: #ffffff; padding: 12px 25px;
                      text-decoration: none; border-radius: 4px; font-size: 15px;">
                Sign document
            </a>
        </div>

        {valid_until_text}

        {req._get_signature_email_extra_html()}

        <p style="color: #666; font-size: 13px; line-height: 1.5; margin-top: 20px;">
            <strong style="color: #444;">Warning</strong> do not forward this email to other people!<br/>
            They will be able to access this document and sign it as yourself.<br/>
            Your IP address and localization are associated to your signature to ensure traceability.
        </p>
        
        <p style="color: #666; font-size: 13px; margin-top: 20px;">
            If you do not wish to receive future reminders about this document, <a href="#" style="color: #666;">click here</a> to cancel it.
        </p>
        
        <p style="margin-top: 30px;">{sender_name}</p>
    </div>
    
    <div style="text-align: center; font-size: 12px; color: #888; border-top: 1px solid #ddd; padding-top: 10px; margin-top: 20px;">
        <strong>{company_name}</strong><br/>
        {sender_email}
    </div>
</div>
"""
            # Pick the first outgoing mail server
            mail_server = self.env['ir.mail_server'].sudo().search(
                [], limit=1, order='sequence asc'
            )

            # Create mail.mail with state='outgoing' so the scheduler picks it up,
            # but also force-send immediately (non-blocking via a new cursor)
            mail = self.env['mail.mail'].sudo().create({
                'subject': f'{doc_name} - Signature Request',
                'email_from': sender_email,
                'email_to': recipient_email,
                'body_html': body_html,
                'auto_delete': False,           # visible in Technical > Emails
                'state': 'outgoing',
                'mail_server_id': mail_server.id if mail_server else False,
            })
            mails |= mail
            _logger.info(
                "Queued signature email to %s (mail.mail id=%s, request id=%s)",
                recipient_email, mail.id, req.id
            )
        self._send_mails_batch(mails)


    @api.model
    def create_from_ui(self, payload):
        is_sign_now = payload.get('is_sign_now', False)
        signing_order = payload.get('signingOrder', False)
        reminders_enabled = payload.get('reminders', False)
        reminder_days = payload.get('reminderDays', 7)
        valid_until = payload.get('validUntil') or False
        hide_certificate_key = payload.get('hideCertificateKey', False)

        for doc in payload.get('documents', []):
            revision_id = doc.get('revision_id')
            revision = self.env['dms.file.revision'].browse(revision_id)
            if not revision.exists():
                continue
                
            # Remove any existing pending requests for this revision to prevent duplicates
            existing_requests = self.search([('revision_id', '=', revision.id), ('state', 'in', ['draft', 'sent'])])
            existing_requests.unlink()
            
            # Group items by assigned_user_id (which is a string like email)
            # Also keep track of the order of roles based on when they appear in items
            recipients = {}
            ordered_users = []
            
            for item in doc.get('items', []):
                user_string = item.get('assigned_user_id')
                if not user_string:
                    continue
                    
                user_id = self._get_or_create_user(user_string)
                if not user_id:
                    # Never drop a signer silently: the request would look sent but no email goes out
                    partner = str(user_string).isdigit() and self.env['res.partner'].sudo().browse(int(user_string)).exists()
                    raise UserError(self.env._(
                        "Could not find or create a user for the signer \"%s\". "
                        "Check that the contact has a unique email address.",
                        partner.display_name if partner else user_string,
                    ))
                    
                if user_id not in recipients:
                    recipients[user_id] = []
                    ordered_users.append(user_id)
                recipients[user_id].append(item)
                
            seq = 1
            requests_created = []
            for user_id in ordered_users:
                items = recipients[user_id]
                
                # Determine state and sequence
                # For is_sign_now, all requests are immediately active (sent)
                state = 'sent' if not signing_order or seq == 1 or is_sign_now else 'draft'
                
                req = self.create({
                    'revision_id': revision.id,
                    'recipient_id': user_id,
                    'state': state,
                    'sequence': seq,
                    'is_sign_now': is_sign_now,
                    'reminders_enabled': reminders_enabled,
                    'reminder_days': reminder_days,
                    'valid_until': valid_until,
                    'hide_certificate_key': hide_certificate_key,
                })
                requests_created.append(req)
                seq += 1
                

                self.env['dms.file.signature.item'].create([
                    req._prepare_signature_item_vals(item) for item in items
                ])

            self._on_requests_created_from_ui(
                revision, self.browse([r.id for r in requests_created]), payload
            )
            revision.file_id.status = 'in_approval'
            # Every signer whose turn it is, notified together (one connection to the mail server)
            if not is_sign_now:
                self.browse([r.id for r in requests_created]).filtered(
                    lambda r: r.state == 'sent').send_signature_email()
            
        if is_sign_now and payload.get('documents'):
            # Find the very first request created for the first document
            first_req = self.search([
                ('revision_id', '=', payload['documents'][0]['revision_id']),
                ('state', '=', 'sent'),
                ('is_sign_now', '=', True)
            ], order='id asc', limit=1)
            
            if first_req:
                url = first_req.get_portal_url()
                # Redirect back to backend document if it's a backend user doing "Sign Now"
                if payload.get('return_url'):
                    url += f"?return_url={payload['return_url']}"
                elif first_req.revision_id and first_req.revision_id.file_id:
                    file_id = first_req.revision_id.file_id.id
                    url += f"?return_url=/web#id={file_id}&model=dms.file&view_type=form"
                return {
                    'type': 'ir.actions.act_url',
                    'url': url,
                    'target': 'self',
                }

        # If not sign_now (or if it didn't return act_url), go back to the document
        if payload.get('documents'):
            rev_id = payload['documents'][0]['revision_id']
            revision = self.env['dms.file.revision'].browse(rev_id)
            if revision.exists() and revision.file_id:
                return {
                    'type': 'ir.actions.act_window',
                    'name': revision.file_id.name,
                    'res_model': 'dms.file',
                    'res_id': revision.file_id.id,
                    'view_mode': 'form',
                    'views': [[False, 'form']],
                    'target': 'main',
                }
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _prepare_signature_item_vals(self, item):
        """Map one editor payload item to ``dms.file.signature.item`` values.
        Extension hook: other modules can add values (e.g. field type links)."""
        self.ensure_one()
        return {
            'request_id': self.id,
            'item_type': item.get('item_type', 'signature'),
            'page_number': int(item.get('page_number', 1)),
            # Store coordinates as pure ratios (0.0–1.0) relative to page dimensions
            'pos_x': float(item.get('pos_x', 0.0)),
            'pos_y': float(item.get('pos_y', 0.0)),
            'width': float(item.get('width', 0.2)),
            'height': float(item.get('height', 0.05)),
            'placeholder': item.get('placeholder', ''),
            'options': item.get('options', ''),
            'alignment': item.get('alignment', 'left'),
            'mandatory': item.get('mandatory', True),
            'readonly': item.get('readonly', False),
            'radio_group_name': item.get('radioGroupName', ''),
            'radio_option_value': item.get('radioOptionValue', ''),
        }

    @api.model
    def _on_requests_created_from_ui(self, revision, requests, payload):
        """Extension hook called once per document after its signer requests
        and items have been created from the signature editor."""
        return True

    def write(self, vals):
        res = super().write(vals)
        if 'recipient_id' in vals:
            dms_user_group = self.env.ref('dms.group_dms_user', raise_if_not_found=False)
            if dms_user_group:
                for record in self:
                    if record.recipient_id and not record.recipient_id.share:
                        dms_user_group.sudo().write({'user_ids': [(4, record.recipient_id.id)]})
        return res
        
    @api.depends('revision_id.content', 'item_ids.pos_x', 'item_ids.pos_y', 'item_ids.page_number', 'state')
    def _compute_pdf_content(self):
        for req in self:
            if req.state == 'signed' or not req.revision_id.content:
                req.pdf_content = req.revision_id.content
            else:
                try:
                    req.pdf_content = req._generate_preview_pdf()
                except Exception as e:
                    _logger.error(f"Failed to generate preview PDF: {e}")
                    req.pdf_content = req.revision_id.content

    def _generate_preview_pdf(self):
        self.ensure_one()
        if self.revision_id.file_id.mimetype != 'application/pdf':
            return self.revision_id.content

        original_pdf = _extract_pdf_bytes(self.revision_id.content)
        if not original_pdf:
            return self.revision_id.content
        
        pdf_reader = PdfReader(io.BytesIO(original_pdf))
        pdf_writer = PdfWriter()
        
        # Watermark page for each page that has items
        page_watermarks = {}
        
        for item in self.item_ids:
            page_idx = item.page_number - 1
            target_page = pdf_reader.pages[page_idx]
            
            # Frontend uses PDF.js viewport which is based on CropBox
            cb = target_page.cropbox
            cb_width = float(cb.width)
            cb_height = float(cb.height)
            cb_ll_x = float(cb.lower_left[0])
            cb_ll_y = float(cb.lower_left[1])
            
            # Coordinates are pure ratios (0.0-1.0) of the cropbox
            rx = cb_ll_x + (item.pos_x * cb_width)
            rw = item.width * cb_width
            rh = item.height * cb_height
            
            # Frontend Y=0 is top of cropbox
            ry_from_top_of_cb = item.pos_y * cb_height
            
            # Invert Y for ReportLab (Y=0 at bottom of mediabox)
            # The top of the cropbox is cb_ll_y + cb_height
            ry = (cb_ll_y + cb_height) - ry_from_top_of_cb - rh
            
            if page_idx not in page_watermarks:
                # Watermark must be full mediabox size to merge correctly
                mb_width = float(target_page.mediabox.width)
                mb_height = float(target_page.mediabox.height)
                io_buf = io.BytesIO()
                c = canvas.Canvas(io_buf, pagesize=(mb_width, mb_height))
                page_watermarks[page_idx] = {'io': io_buf, 'canvas': c}
            
            c = page_watermarks[page_idx]['canvas']
            # Transparent blue box
            c.setFillColorRGB(0, 0.48, 1, 0.15)
            c.rect(rx, ry, rw, rh, fill=1, stroke=0)
            c.setFillColorRGB(0, 0.48, 1, 1)
            c.setLineWidth(0.8)
            c.rect(rx, ry, rw, rh, fill=0, stroke=1)
            c.setFont("Helvetica-Bold", 8)
            label = item.item_type.upper()
            c.drawString(rx + 3, ry + (rh / 2) - 3, label)

        # Finalize canvases
        watermark_pages = {}
        for p_idx, data in page_watermarks.items():
            data['canvas'].save()
            data['io'].seek(0)
            wp = PdfReader(data['io']).pages[0]
            watermark_pages[p_idx] = wp
            
        for i, page in enumerate(pdf_reader.pages):
            if i in watermark_pages:
                page.merge_page(watermark_pages[i])
            pdf_writer.add_page(page)

        output_io = io.BytesIO()
        pdf_writer.write(output_io)
        return base64.b64encode(output_io.getvalue()).decode()
    
    def _compute_access_url(self):
        super()._compute_access_url()
        for request in self:
            request.access_url = f'/my/dms/signature/{request.id}'

    def action_send(self):
        self.write({'state': 'sent'})
        return True

    def _get_missing_mandatory_items(self):
        """Mandatory items the signer left empty. A radio group is answered once
        one of its options is chosen; checkboxes and strikethroughs must be ticked."""
        self.ensure_one()
        missing = self.env['dms.file.signature.item']
        radio_groups = {}
        for item in self.item_ids.filtered(lambda i: i.mandatory and not i.readonly):
            if item.item_type == 'radio':
                group = item.radio_group_name or f'radio_{item.id}'
                radio_groups[group] = radio_groups.get(group, missing) | item
            elif item.item_type in ('checkbox', 'strikethrough'):
                if not item.value_bool:
                    missing |= item
            elif item.item_type in ('signature', 'initial', 'initials', 'stamp'):
                if not item.value_image:
                    missing |= item
            elif not (item.value_text or '').strip():
                missing |= item
        for options in radio_groups.values():
            if not any(options.mapped('value_bool')):
                missing |= options
        return missing

    def action_apply_signature(self):
        self.ensure_one()
        # Pre-filled values (e.g. auto-completed fields the signer did not touch) count as answered
        self.item_ids.filtered(
            lambda i: i.state == 'draft' and (i.value_text or i.value_bool or i.value_image)
        ).write({'state': 'completed'})
        if self._get_missing_mandatory_items():
            raise UserError("Please fill all required fields before applying.")
        
        self.process_signature()
        
        # Sequential signing logic
        next_req = self.env['dms.file.signature.request'].search([
            ('revision_id', '=', self.revision_id.id),
            ('state', '=', 'draft'),
            ('sequence', '=', self.sequence + 1)
        ], limit=1)
        
        if next_req:
            next_req.write({'state': 'sent'})
            next_req.send_signature_email()
            
        pending_sigs = self.env['dms.file.signature.request'].search([
            ('revision_id', '=', self.revision_id.id),
            ('state', '!=', 'signed')
        ])
        if not pending_sigs:
            self.revision_id.file_id.status = 'approved'
            self._send_completed_document_email()
        return True

    def _send_completed_document_email(self):
        """Send the final signed document to all participants."""
        all_requests = self.env['dms.file.signature.request'].search([
            ('revision_id', '=', self.revision_id.id)
        ])
        
        completed_mails = self.env['mail.mail']
        doc_name = self.revision_id.file_id.name or 'Document'
        attachment_name = doc_name if doc_name.startswith('signed_') else f"signed_{doc_name}"
        if not attachment_name.lower().endswith('.pdf'):
            attachment_name += '.pdf'

        attachment = self.env['ir.attachment'].sudo().create({
            'name': attachment_name,
            'type': 'binary',
            # Odoo 20 reads binaries as BinaryValue objects: 'datas' would store them empty
            'raw': _extract_pdf_bytes(self.revision_id.content),
            'res_model': 'dms.file',
            'res_id': self.revision_id.file_id.id,
            'mimetype': 'application/pdf'
        })
        
        sender_name = self.env.user.name or self.env.company.name
        sender_email = self.env.user.email or self.env.company.email
        company_name = self.env.company.name
        
        for req in all_requests:
            recipient = req.recipient_id
            recipient_email = (recipient.email or (recipient.partner_id and recipient.partner_id.email) or '').strip()
            if not recipient or not recipient_email:
                continue
            recipient_name = recipient.name or (recipient.partner_id and recipient.partner_id.name) or recipient_email
                
            body_html = f"""
<div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 650px; margin: 0 auto; color: #444;">
    <div style="padding: 10px 0;">
        <div style="font-size: 11px; color: #666; margin-bottom: 5px;">Signature Completed</div>
        <h2 style="margin: 0; color: #444; font-size: 22px; padding-bottom: 10px; border-bottom: 1px solid #ddd;">{doc_name}</h2>
    </div>
    
    <div style="padding: 20px 0;">
        <p style="margin-top: 0;">Hello <strong>{recipient_name}</strong> (<a href="mailto:{recipient_email}" style="color: #0066cc; text-decoration: none;">{recipient_email}</a>),</p>
        
        <p style="margin-bottom: 25px;">
            All parties have finished signing the document {doc_name}. Please find the final signed copy attached to this email.
        </p>

        <p style="margin-top: 30px;">{sender_name}</p>
    </div>
    
    <div style="text-align: center; font-size: 12px; color: #888; border-top: 1px solid #ddd; padding-top: 10px; margin-top: 20px;">
        <strong>{company_name}</strong><br/>
        {sender_email}
    </div>
</div>
"""
            mail_server = self.env['ir.mail_server'].sudo().search([], limit=1, order='sequence asc')
            mail = self.env['mail.mail'].sudo().create({
                'subject': f'{doc_name} - Signature Completed',
                'email_from': sender_email,
                'email_to': req.recipient_id.email,
                'body_html': body_html,
                'auto_delete': False,
                'state': 'outgoing',
                'mail_server_id': mail_server.id if mail_server else False,
                'attachment_ids': [(4, attachment.id)]
            })
            
            completed_mails |= mail
        self._send_mails_batch(completed_mails)

    def process_signature(self):
        self.ensure_one()
        self.write({
            'signed_date': fields.Datetime.now(),
            'state': 'signed'
        })
        self._stamp_pdf()

    def _stamp_pdf(self):
        """Stamps the items onto the PDF and creates a new revision."""
        if not self.revision_id.content or not self.item_ids:
            return
        
        if self.revision_id.file_id.mimetype != 'application/pdf':
            raise UserError("Only PDF documents can be stamped with signatures.")

        try:
            original_pdf = _extract_pdf_bytes(self.revision_id.content)
            if not original_pdf:
                raise UserError("The document has no PDF content to sign.")
            
            pdf_reader = PdfReader(io.BytesIO(original_pdf))
            pdf_writer = PdfWriter()
            
            import hashlib
            cert_key = ""
            if not self.hide_certificate_key:
                cert_key = hashlib.sha256(self.access_token.encode('utf-8')).hexdigest()

            # Initialize a canvas for EVERY page if we need to print the cert key
            page_watermarks = {}
            for page_idx in range(len(pdf_reader.pages)):
                if not self.hide_certificate_key or any(item.page_number - 1 == page_idx for item in self.item_ids if item.state == 'completed'):
                    target_page = pdf_reader.pages[page_idx]
                    
                    # Watermark must span the full mediabox to merge securely
                    mb_width = float(target_page.mediabox.width)
                    mb_height = float(target_page.mediabox.height)
                    
                    io_buf = io.BytesIO()
                    c = canvas.Canvas(io_buf, pagesize=(mb_width, mb_height))
                    
                    # But we map coordinates relative to the cropbox
                    cb = target_page.cropbox
                    page_watermarks[page_idx] = {
                        'io': io_buf, 
                        'canvas': c, 
                        'cb_width': float(cb.width), 
                        'cb_height': float(cb.height),
                        'cb_ll_x': float(cb.lower_left[0]),
                        'cb_ll_y': float(cb.lower_left[1])
                    }
                    
                    if not self.hide_certificate_key:
                        # Clear any existing certificate header from previous signing passes with an opaque white strip
                        # Placed at the top of the cropbox for visibility
                        cb_top = float(cb.lower_left[1]) + float(cb.height)
                        c.setFillColorRGB(1, 1, 1)
                        c.rect(float(cb.lower_left[0]), cb_top - 24, float(cb.width), 24, fill=1, stroke=0)
                        
                        c.setFillColorRGB(0.45, 0.45, 0.45)
                        c.setFont("Helvetica", 8)
                        # Print cleanly at the top left corner of the cropbox
                        c.drawString(float(cb.lower_left[0]) + 10, cb_top - 15, f"Signature Certificate: {cert_key}")

            for item in self.item_ids:
                if item.state != 'completed':
                    continue
                
                page_idx = item.page_number - 1
                c = page_watermarks[page_idx]['canvas']
                cb_width = page_watermarks[page_idx]['cb_width']
                cb_height = page_watermarks[page_idx]['cb_height']
                cb_ll_x = page_watermarks[page_idx]['cb_ll_x']
                cb_ll_y = page_watermarks[page_idx]['cb_ll_y']
                
                # Coordinates are stored as pure ratios (0.0-1.0) relative to cropbox dimensions
                ratio_x = item.pos_x
                ratio_y = item.pos_y
                ratio_w = item.width
                ratio_h = item.height

                real_x = cb_ll_x + (ratio_x * cb_width)
                real_w = ratio_w * cb_width
                real_h = ratio_h * cb_height

                # Frontend Y=0 is at top of cropbox. ReportLab Y=0 is at bottom of mediabox.
                ry_from_top_of_cb = ratio_y * cb_height
                real_y_reportlab = (cb_ll_y + cb_height) - ry_from_top_of_cb - real_h
                
                if item.item_type in ['signature', 'initial', 'initials', 'stamp']:
                    if item.value_image:
                        img_raw = item.value_image
                        if isinstance(img_raw, str) and ',' in img_raw:
                            img_raw = img_raw.split(',', 1)[1]
                        if isinstance(img_raw, str):
                            img_data = base64.b64decode(img_raw)
                        elif hasattr(img_raw, '__bytes__') or isinstance(img_raw, (bytes, bytearray)):
                            # Odoo 20 reads binary fields as raw bytes; older values may be base64.
                            # b64decode never fails on raw image bytes (it drops invalid characters),
                            # so recognise the image signature first.
                            raw_b = bytes(img_raw)
                            if raw_b.startswith((b'\x89PNG', b'\xff\xd8', b'GIF8', b'RIFF', b'BM')):
                                img_data = raw_b
                            else:
                                try:
                                    img_data = base64.b64decode(raw_b, validate=True)
                                except Exception:
                                    img_data = raw_b
                        else:
                            img_data = img_raw
                        img = ImageReader(io.BytesIO(img_data))
                        
                        # Reportlab drawImage x,y are ALWAYS the bottom-left of the bounding box.
                        # The anchor parameter only controls how the image is aligned WITHIN that bounding box when preserveAspectRatio=True.
                        c.drawImage(img, real_x, real_y_reportlab, width=real_w, height=real_h, mask='auto', preserveAspectRatio=True, anchor='c')
                elif item.item_type in ['text', 'name', 'email', 'phone', 'company', 'date', 'selection']:
                    if item.value_text:
                        c.setFillColor(black)
                        font_size = 14
                        c.setFont("Helvetica", font_size)
                        # Vertical center for a 14pt font (cap height ~10pt, half cap height is 5pt)
                        text_y = real_y_reportlab + (real_h / 2.0) - 5.0
                        text_x = real_x + 4.0
                        if item.alignment == 'center':
                            text_x = real_x + (real_w / 2.0) - (c.stringWidth(str(item.value_text), "Helvetica", font_size) / 2.0)
                        elif item.alignment == 'right':
                            text_x = real_x + real_w - c.stringWidth(str(item.value_text), "Helvetica", font_size) - 4.0
                        c.drawString(text_x, text_y, str(item.value_text))
                elif item.item_type == 'multiline':
                    if item.value_text:
                        c.setFillColor(black)
                        font_size = 11
                        leading = 14
                        c.setFont("Helvetica", font_size)
                        # One line at a time, aligned like the field (left / center / right)
                        line_y = real_y_reportlab + real_h - 13.0
                        for line in str(item.value_text).split('\n'):
                            line_width = c.stringWidth(line, "Helvetica", font_size)
                            if item.alignment == 'center':
                                line_x = real_x + (real_w - line_width) / 2.0
                            elif item.alignment == 'right':
                                line_x = real_x + real_w - line_width - 4.0
                            else:
                                line_x = real_x + 4.0
                            c.drawString(line_x, line_y, line)
                            line_y -= leading
                elif item.item_type == 'radio':
                    cx = real_x + (real_w / 2.0)
                    cy = real_y_reportlab + (real_h / 2.0)
                    r_outer = 5.0
                    c.setStrokeColor(black)
                    c.setFillColor(black)
                    c.setLineWidth(1.0)
                    c.circle(cx, cy, r_outer, stroke=1, fill=0)
                    if item.value_bool or item.value_text in ['1', 'true', 'True']:
                        c.circle(cx, cy, 3.0, stroke=0, fill=1)
                elif item.item_type == 'checkbox':
                    box_size = 11.0
                    bx = real_x + (real_w - box_size) / 2.0
                    by = real_y_reportlab + (real_h - box_size) / 2.0
                    c.setStrokeColor(black)
                    c.setFillColor(black)
                    c.setLineWidth(1.0)
                    c.rect(bx, by, box_size, box_size, stroke=1, fill=0)
                    if item.value_bool or item.value_text in ['1', 'true', 'True']:
                        c.setLineWidth(1.5)
                        p = c.beginPath()
                        p.moveTo(bx + 2.0, by + 5.5)
                        p.lineTo(bx + 4.5, by + 2.5)
                        p.lineTo(bx + 9.0, by + 9.0)
                        c.drawPath(p, stroke=1, fill=0)
                elif item.item_type == 'strikethrough' and item.value_bool:
                    c.setStrokeColor(black)
                    c.setLineWidth(2)
                    c.line(real_x, real_y_reportlab + (real_h / 2.0), real_x + real_w, real_y_reportlab + (real_h / 2.0))

            watermark_pages = {}
            for p_idx, data in page_watermarks.items():
                data['canvas'].save()
                data['io'].seek(0)
                wp = PdfReader(data['io']).pages[0]
                watermark_pages[p_idx] = wp
                
            for i, page in enumerate(pdf_reader.pages):
                if i in watermark_pages:
                    page.merge_page(watermark_pages[i])
                pdf_writer.add_page(page)

            output_io = io.BytesIO()
            pdf_writer.write(output_io)
            signed_pdf_base64 = base64.b64encode(output_io.getvalue()).decode()
            
            new_version_num = str(int(self.revision_id.version) + 1) if self.revision_id.version.isdigit() else self.revision_id.version + "_signed"
            new_revision = self.env['dms.file.revision'].create({
                'file_id': self.revision_id.file_id.id,
                'version': new_version_num,
                'content': signed_pdf_base64,
                'file_name': f"signed_{self.revision_id.file_name or self.revision_id.file_id.name}",
                'comments': f"Signed by {self.recipient_id.name}"
            })
            
            new_revision.action_make_current()
            
            pending_requests = self.env['dms.file.signature.request'].search([
                ('revision_id', '=', self.revision_id.id),
                ('id', '!=', self.id)
            ])
            pending_requests.write({'revision_id': new_revision.id})
            
            self.revision_id = new_revision.id

        except Exception as e:
            _logger.error(f"Failed to stamp PDF: {str(e)}")
            raise UserError(f"Failed to apply signature to PDF. Error: {str(e)}")

    @api.model
    def _cron_send_signature_reminders(self):
        """Send reminders for pending signature requests."""
        # Find requests that are sent, reminders enabled, and not signed
        requests = self.search([
            ('state', '=', 'sent'),
            ('reminders_enabled', '=', True)
        ])
        
        today = fields.Date.today()
        due = self.browse()
        for req in requests:
            # Determine the baseline date to compare against
            base_date = req.last_reminder_date or req.create_date.date()
            if not req.reminder_days or req.reminder_days <= 0:
                continue

            delta = today - base_date
            if delta.days >= req.reminder_days:
                due |= req
        if due:
            # All reminders together (one connection to the mail server)
            due.send_signature_email()
            due.write({'last_reminder_date': today})
