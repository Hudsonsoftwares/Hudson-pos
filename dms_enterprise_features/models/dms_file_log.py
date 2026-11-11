# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import ast
import datetime
from odoo import api, fields, models, _

class DMSFileLog(models.Model):
    _name = 'dms.file.log'
    _description = 'Document Logs'
    _order = 'date desc'

    name = fields.Char(string='Document Name', required=True)
    file_id = fields.Many2one('dms.file', string='Document', ondelete='set null')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
    )
    action = fields.Selection([
        ('create', 'Created'),
        ('edit', 'Edited'),
        ('delete', 'Deleted')
    ], string='Action', required=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)
    date = fields.Datetime(string='Date', default=fields.Datetime.now)
    details = fields.Text(string='Details')

    @api.model
    def _format_details_string(self, details_val):
        if not details_val or not isinstance(details_val, str):
            return details_val
        text = details_val.strip()
        if not (text.startswith('{') and text.endswith('}')):
            return text

        try:
            data = ast.literal_eval(text)
            if not isinstance(data, dict):
                return text
        except Exception:
            return text

        technical_keys = {
            'checksum', 'size', 'attachment_id', 'current_revision_id',
            'image_1920', 'starred', 'color', 'write_date', 'write_uid',
            'create_date', 'create_uid', '__last_update', 'access_token',
        }
        changes = []
        for key, val in data.items():
            if key in technical_keys:
                continue
            if key == 'department_id':
                dept = self.env['hr.department'].sudo().browse(val) if val else False
                dept_name = dept.name if dept and dept.exists() else (val or _("None"))
                changes.append(_("Department set to '%s'") % dept_name)
            elif key == 'category_id':
                cat = self.env['dms.category'].sudo().browse(val) if val else False
                cat_name = cat.name if cat and cat.exists() else (val or _("None"))
                changes.append(_("Category set to '%s'") % cat_name)
            elif key == 'directory_id':
                folder = self.env['dms.directory'].sudo().browse(val) if val else False
                folder_name = folder.name if folder and folder.exists() else (val or _("Root"))
                changes.append(_("Moved to folder '%s'") % folder_name)
            elif key == 'document_owner_id':
                owner = self.env['res.users'].sudo().browse(val) if val else False
                owner_name = owner.name if owner and owner.exists() else (val or _("None"))
                changes.append(_("Owner set to '%s'") % owner_name)
            elif key == 'name':
                changes.append(_("Renamed to '%s'") % val)
            elif key in ('content', 'content_binary', 'file'):
                changes.append(_("File content updated"))
            elif key == 'document_number':
                changes.append(_("Document number set to '%s'") % val)
            elif key == 'expiration_date':
                changes.append(_("Expiration date set to %s") % val)
            elif key == 'is_trashed':
                changes.append(_("Moved to Trash") if val else _("Restored from Trash"))
            elif key == 'approval_state':
                changes.append(_("Approval status: %s") % str(val).replace('_', ' ').title())
            elif key == 'tag_ids':
                changes.append(_("Tags modified"))
            elif key == 'active':
                changes.append(_("Unarchived") if val else _("Archived"))
            else:
                formatted_key = key.replace('_id', '').replace('_', ' ').title()
                changes.append(f"{formatted_key} set to '{val}'")

        if not changes:
            return False
        return "; ".join(changes)

    @api.model_create_multi
    def create(self, vals_list):
        cleaned_vals = []
        for vals in vals_list:
            if not vals.get('company_id'):
                file_rec = self.env['dms.file'].browse(vals['file_id']) if vals.get('file_id') else None
                vals['company_id'] = file_rec.company_id.id if (file_rec and file_rec.exists() and file_rec.company_id) else self.env.company.id
            if vals.get('details'):
                formatted = self._format_details_string(vals['details'])
                # If only technical keys were passed (e.g. {'image_1920': False}), skip this log completely
                if formatted is False and vals.get('action') == 'edit':
                    continue
                vals['details'] = formatted or vals['details']

            # Debounce / Coalesce: find recent log by same user for this file within last 60s
            file_id = vals.get('file_id')
            user_id = vals.get('user_id') or self.env.user.id
            action = vals.get('action')
            details = vals.get('details')

            if file_id and action == 'edit' and details:
                recent_cutoff = fields.Datetime.now() - datetime.timedelta(seconds=60)
                recent_log = self.sudo().search([
                    ('file_id', '=', file_id),
                    ('user_id', '=', user_id),
                    ('action', '=', 'edit'),
                    ('date', '>=', recent_cutoff),
                ], order='date desc', limit=1)

                if recent_log:
                    existing_parts = [p.strip() for p in (recent_log.details or '').split('; ') if p.strip()]
                    new_parts = [p.strip() for p in details.split('; ') if p.strip()]
                    for part in new_parts:
                        if part not in existing_parts:
                            existing_parts.append(part)
                    recent_log.sudo().write({
                        'name': vals.get('name') or recent_log.name,
                        'details': "; ".join(existing_parts),
                        'date': fields.Datetime.now(),
                    })
                    continue  # Coalesced into existing log!

            cleaned_vals.append(vals)

        if not cleaned_vals:
            return self.browse()
        return super().create(cleaned_vals)

