from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class DmsDirectoryPermission(models.Model):
    _name = "dms.directory.permission"
    _description = "Directory Permission"

    directory_id = fields.Many2one(
        "dms.directory",
        string="Directory",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="directory_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )

    group_id = fields.Many2one(
        "dms.access.group",
        string="Access Group",
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        ondelete="cascade",
    )
    user_id = fields.Many2one(
        "res.users",
        string="User",
        ondelete="cascade",
    )
    
    perm_view = fields.Boolean("View", default=False)
    perm_download = fields.Boolean("Download", default=False)
    perm_upload = fields.Boolean("Upload", default=False)
    perm_edit = fields.Boolean("Edit", default=False)
    perm_rename = fields.Boolean("Rename", default=False)
    perm_move = fields.Boolean("Move", default=False)
    perm_delete = fields.Boolean("Delete", default=False)
    perm_share = fields.Boolean("Share", default=False)

    @api.model
    def _ensure_user_for_partner(self, partner):
        """Find an existing active user for the partner or create a portal user."""
        if not partner:
            return False
        
        # 1. Existing user
        user = partner.user_ids.filtered(lambda u: u.active)[:1] or partner.user_ids[:1]
        if not user:
            user = self.env['res.users'].sudo().search([('partner_id', '=', partner.id)], limit=1)
            
        if user:
            if user.has_group('base.group_user'):
                dms_user_group = self.env.ref('dms.group_dms_user', raise_if_not_found=False)
                if dms_user_group and not user.has_group('dms.group_dms_user'):
                    dms_user_group.sudo().write({'user_ids': [(4, user.id)]})
            elif not user.has_group('base.group_portal'):
                portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
                if portal_group:
                    portal_group.sudo().write({'user_ids': [(4, user.id)]})
            return user

        # 2. No user exists for this contact -> create a portal user
        portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
        login = (partner.email or '').strip()
        if not login or self.env['res.users'].sudo().search_count([('login', '=', login)]):
            login = f"portal_user_{partner.id}"
            
        try:
            user_vals = {
                'name': partner.name,
                'login': login,
                'partner_id': partner.id,
                'email': partner.email or False,
                'active': True,
            }
            if portal_group:
                user_vals['group_ids'] = [(4, portal_group.id)]
                
            user = self.env['res.users'].sudo().with_context(no_reset_password=True).create(user_vals)
            return user
        except Exception:
            user = self.env['res.users'].sudo().search([('partner_id', '=', partner.id)], limit=1)
            return user or False

    @api.onchange('perm_download', 'perm_upload', 'perm_edit', 'perm_rename', 'perm_move', 'perm_delete', 'perm_share')
    def _onchange_sub_permissions(self):
        if any([self.perm_download, self.perm_upload, self.perm_edit, self.perm_rename, self.perm_move, self.perm_delete, self.perm_share]):
            self.perm_view = True
        if self.perm_edit:
            self.perm_download = True

    @api.onchange('perm_view')
    def _onchange_perm_view(self):
        if not self.perm_view:
            self.perm_download = False
            self.perm_upload = False
            self.perm_edit = False
            self.perm_rename = False
            self.perm_move = False
            self.perm_delete = False
            self.perm_share = False
        else:
            self.perm_download = True

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            user = self._ensure_user_for_partner(self.partner_id)
            if user:
                self.user_id = user.id

    @api.onchange('user_id')
    def _onchange_user_id(self):
        if self.user_id and not self.partner_id:
            self.partner_id = self.user_id.partner_id.id

    @api.constrains('group_id', 'partner_id', 'user_id')
    def _check_target(self):
        for record in self:
            if not record.group_id and not record.partner_id and not record.user_id:
                raise ValidationError(_("You must select either an Access Group or a Contact/User for this permission rule."))

    @api.constrains('group_id', 'partner_id', 'user_id', 'directory_id')
    def _check_user_not_in_folder_access_group(self):
        """A user who is already a member of an access group granted on this
        folder must not be added again as an individual user line."""
        for record in self.filtered(lambda r: not r.group_id and (r.user_id or r.partner_id)):
            users = (record.user_id | record.partner_id.user_ids).sudo()
            group_lines = record.directory_id.sudo().permission_line_ids.filtered('group_id')
            for line in group_lines:
                overlap = users & line.group_id.users
                if overlap:
                    raise ValidationError(_(
                        "%(user)s is already a member of the access group '%(group)s' on this folder. "
                        "Change that group's permissions, or remove the user from the group, "
                        "instead of adding them separately.",
                        user=overlap[0].name,
                        group=line.group_id.name,
                    ))

    def _normalize_permissions(self, vals):
        sub_perms = ['perm_download', 'perm_upload', 'perm_edit', 'perm_rename', 'perm_move', 'perm_delete', 'perm_share']
        if any(vals.get(p) for p in sub_perms):
            vals['perm_view'] = True
        if vals.get('perm_edit'):
            vals['perm_download'] = True
        if vals.get('perm_view') and 'perm_download' not in vals:
            vals['perm_download'] = True
        if 'perm_view' in vals and not vals['perm_view']:
            for p in sub_perms:
                vals[p] = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._normalize_permissions(vals)
            if vals.get('partner_id') and not vals.get('user_id'):
                partner = self.env['res.partner'].browse(vals['partner_id'])
                user = self._ensure_user_for_partner(partner)
                if user:
                    vals['user_id'] = user.id
            elif vals.get('user_id') and not vals.get('partner_id'):
                user = self.env['res.users'].browse(vals['user_id'])
                if user.partner_id:
                    vals['partner_id'] = user.partner_id.id

        records = super().create(vals_list)
        records.filtered('group_id').directory_id._dms_dedupe_permission_lines()
        dms_user_group = self.env.ref('dms.group_dms_user', raise_if_not_found=False)
        portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
        for record in records:
            if record.user_id:
                if record.user_id.has_group('base.group_user') and dms_user_group and not record.user_id.has_group('dms.group_dms_user'):
                    dms_user_group.sudo().write({'user_ids': [(4, record.user_id.id)]})
                elif not record.user_id.has_group('base.group_user') and portal_group and not record.user_id.has_group('base.group_portal'):
                    portal_group.sudo().write({'user_ids': [(4, record.user_id.id)]})
        return records

    def write(self, vals):
        self._normalize_permissions(vals)
        if vals.get('partner_id') and 'user_id' not in vals:
            partner = self.env['res.partner'].browse(vals['partner_id'])
            user = self._ensure_user_for_partner(partner)
            vals['user_id'] = user.id if user else False
        elif vals.get('user_id') and 'partner_id' not in vals:
            user = self.env['res.users'].browse(vals['user_id'])
            if user.partner_id:
                vals['partner_id'] = user.partner_id.id

        res = super().write(vals)
        if vals.get('group_id'):
            self.directory_id._dms_dedupe_permission_lines()
        if 'user_id' in vals or 'partner_id' in vals:
            dms_user_group = self.env.ref('dms.group_dms_user', raise_if_not_found=False)
            portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
            for record in self:
                if record.user_id:
                    if record.user_id.has_group('base.group_user') and dms_user_group and not record.user_id.has_group('dms.group_dms_user'):
                        dms_user_group.sudo().write({'user_ids': [(4, record.user_id.id)]})
                    elif not record.user_id.has_group('base.group_user') and portal_group and not record.user_id.has_group('base.group_portal'):
                        portal_group.sudo().write({'user_ids': [(4, record.user_id.id)]})
        return res
