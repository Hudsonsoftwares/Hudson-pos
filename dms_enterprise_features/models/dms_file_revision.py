# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import base64

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from PIL import Image

class DMSFileRevision(models.Model):
    _name = "dms.file.revision"
    _description = "Document Revision"
    _order = "create_date desc, version desc"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    file_id = fields.Many2one(
        comodel_name="dms.file",
        string="Document",
        required=True,
        ondelete="cascade",
        index=True
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        related="file_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    version = fields.Char(
        string="Version",
        required=True,
        tracking=True
    )
    content = fields.Binary(
        string="File Content",
        required=True,
        attachment=True
    )
    file_name = fields.Char(string="File Name")
    mimetype = fields.Char(
        related="file_id.mimetype",
        string="MIME Type",
        readonly=True,
        store=True,
    )
    uploader_id = fields.Many2one(
        comodel_name="res.users",
        string="Uploaded By",
        default=lambda self: self.env.user,
        readonly=True
    )
    upload_date = fields.Datetime(
        string="Upload Date",
        default=fields.Datetime.now,
        readonly=True
    )
    comments = fields.Text(string="Comments")
    approval_history_ids = fields.One2many(
        comodel_name="dms.file.approval",
        inverse_name="revision_id",
        string="Approval History"
    )
    signature_request_ids = fields.One2many(
        comodel_name="dms.file.signature.request",
        inverse_name="revision_id",
        string="Signature Requests"
    )
    is_current = fields.Boolean(
        string="Is Current",
        default=False,
    )
    active = fields.Boolean(default=True)
    
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.file_id.name or 'Document'} - v{record.version or '1.0'}"

    def name_get(self):
        result = []
        for record in self:
            result.append((record.id, f"{record.file_id.name or 'Document'} - v{record.version or '1.0'}"))
        return result

    def _sync_to_file(self):
        """Sync this active revision's content, name, and cover image to the parent dms.file."""
        for record in self:
            if not record.file_id or not record.content:
                continue
            file_rec = record.file_id
            
            # Sync attachment if attachment storage is used
            if file_rec.attachment_id:
                # Odoo 20 reads binaries as BinaryValue objects: 'datas' would store them empty
                content = record.content
                file_rec.attachment_id.sudo().write({
                    'raw': base64.b64decode(content) if isinstance(content, str) else bytes(content),
                    'name': record.file_name or file_rec.name,
                })

            file_vals = {
                'current_revision_id': record.id,
                'content': record.content,
                'name': record.file_name or file_rec.name,
            }
            file_rec.with_context(from_revert_revision=True, dms_skip_log=True).write(file_vals)
            
            # Update image_1920 directly for image file types
            if file_rec.mimetype != "application/pdf" and file_rec.mimetype in (*Image.MIME.values(), "image/svg+xml"):
                file_rec.sudo().with_context(dms_skip_log=True).write({'image_1920': record.content})
            else:
                file_rec.sudo().with_context(dms_skip_log=True).write({'image_1920': False})

    def action_make_current(self):
        self.ensure_one()
        if self.file_id.is_locked and not self.file_id.is_lock_editor and not self.env.user.has_group('dms.group_dms_manager') and not self.env.su:
            raise UserError(_("Cannot activate revision because '%s' is locked by %s.") % (self.file_id.name, self.file_id.locked_by.name or 'another user'))
        other_revs = self.file_id.revision_ids.filtered(lambda r: r.id != self.id)
        if other_revs:
            other_revs.sudo().write({'is_current': False})
        
        self.sudo().write({'is_current': True})
        self._sync_to_file()
        self.env['dms.file.log'].sudo().create({
            'name': self.file_id.name,
            'file_id': self.file_id.id,
            'action': 'edit',
            'details': f"Reverted to revision {self.version} ({self.file_name or self.file_id.name})"
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_view_online(self):
        self.ensure_one()
        filename = self.file_name or self.file_id.name or 'document'
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/dms.file.revision/{self.id}/content/{filename}?download=False',
            'target': 'new',
        }

    def action_download_online(self):
        self.ensure_one()
        filename = self.file_name or self.file_id.name or 'document'
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/dms.file.revision/{self.id}/content/{filename}?download=True',
            'target': 'new',
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('file_id'):
                f = self.env['dms.file'].browse(vals['file_id'])
                if f.is_locked and not f.is_lock_editor and not self.env.user.has_group('dms.group_dms_manager') and not self.env.su:
                    raise UserError(_("Cannot add new revisions because '%s' is locked by %s.") % (f.name, f.locked_by.name or 'another user'))
        records = super().create(vals_list)
        for record in records:
            if record.is_current:
                other_revs = record.file_id.revision_ids.filtered(lambda r: r.id != record.id)
                if other_revs:
                    other_revs.sudo().write({'is_current': False})
                record._sync_to_file()
            elif not record.file_id.current_revision_id:
                record.sudo().write({'is_current': True})
                record._sync_to_file()
        return records

    def write(self, vals):
        for rec in self:
            if rec.file_id.is_locked and not rec.file_id.is_lock_editor and not self.env.user.has_group('dms.group_dms_manager') and not self.env.su:
                raise UserError(_("Cannot modify revisions because '%s' is locked by %s.") % (rec.file_id.name, rec.file_id.locked_by.name or 'another user'))
        res = super().write(vals)
        if vals.get('is_current'):
            for record in self.filtered('is_current'):
                other_revs = record.file_id.revision_ids.filtered(lambda r: r.id != record.id)
                if other_revs:
                    other_revs.sudo().write({'is_current': False})
                record._sync_to_file()
        elif 'content' in vals:
            for record in self.filtered('is_current'):
                record._sync_to_file()
        return res

    def unlink(self):
        for record in self:
            if record.file_id.is_locked:
                raise UserError(_("Cannot delete revisions from '%s' because it is locked by %s. Please unlock it first.") % (record.file_id.name, record.file_id.locked_by.name or 'another user'))
            if record.is_current:
                raise UserError(_("You cannot delete the active version of a file. Please set another version as active before deleting this one."))
        return super().unlink()

    def action_delete_revision(self):
        self.ensure_one()
        self.unlink()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

