# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import html_escape

class DmsFileShareWizard(models.TransientModel):
    _name = "dms.file.share.wizard"
    _description = "Share Document Wizard"

    file_id = fields.Many2one(
        comodel_name="dms.file",
        string="Document",
        required=True,
    )
    file_name = fields.Char(
        string="Document Name",
        related="file_id.name",
        readonly=True,
    )
    share_mode = fields.Selection(
        selection=[
            ("people", "Add People"),
            ("groups", "Add Groups"),
        ],
        string="Share Mode",
        default="people",
        required=True,
    )
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Add people, contacts, or email addresses",
    )
    group_ids = fields.Many2many(
        comodel_name="res.groups",
        string="Add groups",
    )
    new_access_role = fields.Selection(
        selection=[
            ("viewer", "Viewer"),
            ("editor", "Editor"),
        ],
        string="Role",
        default="viewer",
        required=True,
    )
    share_internal_access = fields.Selection(
        selection=[
            ("editor", "Editor"),
            ("viewer", "Viewer"),
            ("none", "None"),
        ],
        string="Internal Users",
        default="editor",
        required=True,
    )
    share_link_access = fields.Selection(
        selection=[
            ("none", "None"),
            ("viewer", "Viewer"),
            ("editor", "Editor"),
        ],
        string="Access Through Link",
        default="none",
        required=True,
    )
    share_is_discoverable = fields.Selection(
        selection=[
            ("no", "No"),
            ("yes", "Yes"),
        ],
        string="Discoverable",
        default="no",
        required=True,
    )
    share_link_url = fields.Char(
        string="Share Link",
        compute="_compute_share_link_url",
    )
    people_with_access_html = fields.Html(
        string="People with Access",
        compute="_compute_people_with_access_html",
        sanitize=False,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get("active_id") or self.env.context.get("default_file_id")
        if active_id:
            file_rec = self.env["dms.file"].browse(active_id)
            if file_rec.exists():
                if file_rec.is_locked and not file_rec.is_lock_editor and not self.env.user.has_group('dms.group_dms_manager') and not self.env.su:
                    raise UserError(_("Cannot share '%s' because it is locked by %s.") % (file_rec.name, file_rec.locked_by.name or 'another user'))
                if not file_rec.permission_share and not self.env.user.has_group('dms.group_dms_manager') and not self.env.su:
                    raise UserError(_("You do not have permission to share '%s'.") % file_rec.name)
                res["file_id"] = file_rec.id
                res["share_internal_access"] = file_rec.share_internal_access or "editor"
                res["share_link_access"] = file_rec.share_link_access or "none"
                res["share_is_discoverable"] = file_rec.share_is_discoverable or "no"
        return res

    @api.depends("file_id")
    def _compute_share_link_url(self):
        for wizard in self:
            if wizard.file_id:
                wizard.share_link_url = wizard.file_id.share_link_url
            else:
                wizard.share_link_url = False

    @api.depends("file_id", "file_id.access_ids", "file_id.document_owner_id")
    def _compute_people_with_access_html(self):
        for wizard in self:
            if not wizard.file_id:
                wizard.people_with_access_html = ""
                continue

            file_rec = wizard.file_id
            rows_html = []

            # 1. Document Owner
            owner = file_rec.document_owner_id or file_rec.create_uid
            if owner:
                owner_avatar = f"/web/image/res.users/{owner.id}/avatar_128"
                rows_html.append(f"""
                <div class="d-flex align-items-center justify-content-between py-2 border-bottom">
                    <div class="d-flex align-items-center">
                        <img src="{owner_avatar}" class="rounded-circle me-3" style="width: 38px; height: 38px; object-fit: cover; border: 1px solid #dee2e6;"/>
                        <div>
                            <div class="fw-bold text-dark">{html_escape(owner.name or '')} <span class="badge bg-secondary ms-1 small">Owner</span></div>
                            <div class="text-muted small">{html_escape(owner.email or '')}</div>
                        </div>
                    </div>
                    <span class="badge rounded-pill bg-light text-dark border px-3 py-2">Editor</span>
                </div>
                """)

            # 2. Explicit User & Group Access Rules
            for access in file_rec.access_ids:
                is_editor = access.perm_edit or access.perm_rename or access.perm_move
                role_label = _("Editor") if is_editor else _("Viewer")
                role_color = "primary" if is_editor else "info"

                if access.partner_id:
                    avatar = f"/web/image/res.partner/{access.partner_id.id}/avatar_128"
                    name = access.partner_id.name or ''
                    subtext = access.partner_id.email or ''
                    icon = ""
                elif access.user_id:
                    avatar = f"/web/image/res.users/{access.user_id.id}/avatar_128"
                    name = access.user_id.name or ''
                    subtext = access.user_id.email or ''
                    icon = ""
                elif access.group_id:
                    avatar = ""
                    name = access.group_id.name or ''
                    subtext = _("User Group")
                    icon = '<div class="rounded-circle bg-light border d-flex align-items-center justify-content-center me-3" style="width: 38px; height: 38px;"><i class="fa fa-users text-secondary"></i></div>'
                elif access.access_group_id:
                    avatar = ""
                    name = access.access_group_id.name or ''
                    subtext = _("Access Group")
                    icon = '<div class="rounded-circle bg-light border d-flex align-items-center justify-content-center me-3" style="width: 38px; height: 38px;"><i class="fa fa-users text-secondary"></i></div>'
                elif access.department_id:
                    avatar = ""
                    name = access.department_id.name or ''
                    subtext = _("Department")
                    icon = '<div class="rounded-circle bg-light border d-flex align-items-center justify-content-center me-3" style="width: 38px; height: 38px;"><i class="fa fa-building text-secondary"></i></div>'
                else:
                    continue

                img_or_icon = f'<img src="{avatar}" class="rounded-circle me-3" style="width: 38px; height: 38px; object-fit: cover; border: 1px solid #dee2e6;"/>' if avatar else icon

                rows_html.append(f"""
                <div class="d-flex align-items-center justify-content-between py-2 border-bottom">
                    <div class="d-flex align-items-center">
                        {img_or_icon}
                        <div>
                            <div class="fw-bold text-dark">{html_escape(name)}</div>
                            <div class="text-muted small">{html_escape(subtext)}</div>
                        </div>
                    </div>
                    <div class="d-flex align-items-center">
                        <span class="badge rounded-pill bg-light text-{role_color} border px-3 py-2 me-2">{role_label}</span>
                    </div>
                </div>
                """)

            wizard.people_with_access_html = "".join(rows_html)

    @api.onchange("share_link_access", "share_internal_access", "share_is_discoverable")
    def _onchange_share_settings(self):
        for wizard in self:
            if wizard.file_id:
                wizard.file_id.sudo().write({
                    "share_internal_access": wizard.share_internal_access,
                    "share_link_access": wizard.share_link_access,
                    "share_is_discoverable": wizard.share_is_discoverable,
                })
                wizard.share_link_url = wizard.file_id.share_link_url

    def action_add_access(self):
        """Add selected contacts or groups to file access rules."""
        self.ensure_one()
        file_rec = self.file_id
        if not file_rec:
            return

        if file_rec.is_locked and not file_rec.is_lock_editor and not self.env.user.has_group('dms.group_dms_manager') and not self.env.su:
            raise UserError(_("Cannot modify access because '%s' is locked by %s.") % (file_rec.name, file_rec.locked_by.name or 'another user'))
        if not file_rec.permission_share and not self.env.user.has_group('dms.group_dms_manager') and not self.env.su:
            raise UserError(_("You do not have permission to share '%s'.") % file_rec.name)

        is_editor = (self.new_access_role == "editor")
        perm_vals = {
            "perm_view": True,
            "perm_download": True,
            "perm_edit": is_editor,
            "perm_rename": is_editor,
            "perm_move": is_editor,
            "perm_delete": is_editor,
            "perm_share": is_editor,
        }

        if self.share_mode == "people" and self.partner_ids:
            for partner in self.partner_ids:
                user = self.env['dms.file.access']._ensure_user_for_partner(partner)
                existing = file_rec.access_ids.filtered(lambda a: (a.partner_id.id == partner.id) or (user and a.user_id.id == user.id))
                if existing:
                    existing.write({
                        **perm_vals,
                        "partner_id": partner.id,
                        "user_id": user.id if user else False,
                    })
                else:
                    self.env["dms.file.access"].create({
                        "file_id": file_rec.id,
                        "partner_id": partner.id,
                        "user_id": user.id if user else False,
                        **perm_vals,
                    })
            self.partner_ids = [(5, 0, 0)]

        elif self.share_mode == "groups" and self.group_ids:
            for group in self.group_ids:
                existing = file_rec.access_ids.filtered(lambda a: a.group_id.id == group.id)
                if existing:
                    existing.write(perm_vals)
                else:
                    self.env["dms.file.access"].create({
                        "file_id": file_rec.id,
                        "group_id": group.id,
                        **perm_vals,
                    })
            self.group_ids = [(5, 0, 0)]

        # Also persist general access settings
        file_rec.write({
            "share_internal_access": self.share_internal_access,
            "share_link_access": self.share_link_access,
            "share_is_discoverable": self.share_is_discoverable,
        })
        self.share_link_url = file_rec.share_link_url

        # Re-open wizard to show updated list
        return {
            "type": "ir.actions.act_window",
            "res_model": "dms.file.share.wizard",
            "res_id": self.id,
            "views": [[False, "form"]],
            "view_mode": "form",
            "target": "new",
            "context": {"dialog_size": "md"},
        }

    def action_save(self):
        """Save General Access and any pending contacts/groups immediately to the document."""
        self.ensure_one()
        file_rec = self.file_id
        if not file_rec:
            return {"type": "ir.actions.act_window_close"}

        if file_rec.is_locked and not file_rec.is_lock_editor and not self.env.user.has_group('dms.group_dms_manager') and not self.env.su:
            raise UserError(_("Cannot modify access settings because '%s' is locked by %s.") % (file_rec.name, file_rec.locked_by.name or 'another user'))
        if not file_rec.permission_share and not self.env.user.has_group('dms.group_dms_manager') and not self.env.su:
            raise UserError(_("You do not have permission to share '%s'.") % file_rec.name)

        # 1. Process any pending contacts or groups if selected
        if self.partner_ids or self.group_ids:
            self.action_add_access()

        # 2. Write general access settings to document
        file_rec.write({
            "share_internal_access": self.share_internal_access,
            "share_link_access": self.share_link_access,
            "share_is_discoverable": self.share_is_discoverable,
        })
        self.share_link_url = file_rec.share_link_url

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Saved"),
                "message": _("Access settings saved successfully."),
                "type": "success",
                "sticky": False,
                "next": {
                    "type": "ir.actions.act_window",
                    "res_model": "dms.file.share.wizard",
                    "res_id": self.id,
                    "views": [[False, "form"]],
                    "view_mode": "form",
                    "target": "new",
                    "context": {"dialog_size": "md"},
                }
            }
        }

    def action_save_and_close(self):
        """Save General Access settings to document and close."""
        self.action_save()
        return {"type": "ir.actions.act_window_close"}
