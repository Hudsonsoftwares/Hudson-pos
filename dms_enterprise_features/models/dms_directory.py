from odoo import models, api, fields, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.tools.misc import file_path

from odoo.addons.dms.tools.file import check_name, unique_name


def _dms_unlimited_panel(kwargs):
    """The dms search views declare ``limit="0"`` on their search-panel
    sections, meaning "no limit". Since Odoo 20 the ORM reads ``limit=0`` as
    "zero rows", which left those sidebars empty (Configuration > Directories
    showed no folders at all). Map it back to "unlimited"."""
    if kwargs.get("limit") == 0:
        kwargs["limit"] = None

class DmsDirectory(models.Model):
    _inherit = 'dms.directory'

    @api.constrains("is_root_directory", "parent_id")
    def _check_directory_parent(self):
        """Override: if no parent and not flagged as root, we auto-promote to root
        in create(), so we skip the error here — it has already been handled."""
        for record in self:
            if record.is_root_directory and record.parent_id:
                raise ValidationError(
                    _("A directory can't be a root and have a parent directory.")
                )
            # The original raises an error when is_root_directory=False AND no parent.
            # We intentionally skip that case because create() pre-fills is_root_directory.

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        compute="_compute_company_id",
        store=True,
        readonly=False,
        index="btree",
        related=False,
        recursive=True,
    )

    @api.depends("parent_id.company_id", "storage_id.company_id")
    def _compute_company_id(self):
        for rec in self:
            if rec.parent_id and rec.parent_id.company_id:
                rec.company_id = rec.parent_id.company_id
            elif rec.storage_id and rec.storage_id.company_id:
                rec.company_id = rec.storage_id.company_id
            elif not rec.company_id:
                rec.company_id = self.env.company

    @api.depends_context("directory_short_name", "allowed_company_ids")
    def _compute_display_name(self):
        super()._compute_display_name()
        allowed_companies = self.env.context.get("allowed_company_ids") or self.env.companies.ids
        if len(allowed_companies) > 1:
            for record in self:
                if record.company_id:
                    base_name = record.name if self.env.context.get("directory_short_name") else (record.complete_name or record.name)
                    record.display_name = f"{base_name} ({record.company_id.name})"

    @api.model
    def _get_or_create_company_storage(self, company):
        if not company:
            company = self.env.company
        storage = self.env['dms.storage'].sudo().search([
            ('company_id', '=', company.id)
        ], limit=1)
        if not storage:
            # Check default enterprise storage if company matches or has no company
            default_storage = self.env.ref('dms_enterprise_features.dms_storage_enterprise', raise_if_not_found=False)
            if default_storage and (not default_storage.company_id or default_storage.company_id.id == company.id):
                if not default_storage.company_id:
                    default_storage.sudo().write({'company_id': company.id})
                return default_storage
            # Otherwise create a dedicated storage for this company
            storage = self.env['dms.storage'].sudo().create({
                'name': f"Enterprise Documents - {company.name}",
                'save_type': 'file',
                'company_id': company.id,
                'is_hidden': False,
            })
        return storage

    @api.model
    def _ensure_company_default_directories(self, company):
        """Ensure standard enterprise root directories exist for the specified company."""
        if not company:
            company = self.env.company
        storage = self._get_or_create_company_storage(company)
        enterprise_group = self.env.ref("dms_enterprise_features.dms_access_group_enterprise", raise_if_not_found=False)
        group_cmd = [(4, enterprise_group.id)] if enterprise_group else []

        from .res_company import DEFAULT_ROOT_DIRECTORIES
        created_dirs = self.env['dms.directory']
        for name, _icon in DEFAULT_ROOT_DIRECTORIES:
            existing = self.sudo().search([
                ('name', '=', name),
                ('is_root_directory', '=', True),
                ('company_id', '=', company.id),
            ], limit=1)
            if not existing:
                new_dir = self.sudo().create({
                    'name': name,
                    'is_root_directory': True,
                    'storage_id': storage.id,
                    'company_id': company.id,
                    'group_ids': group_cmd,
                })
                created_dirs |= new_dir
        return created_dirs

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self._is_dms_privileged_user():
            raise AccessError(_("Only Documents Managers and Administrators are allowed to create folders."))
        for vals in vals_list:
            # Determine target company
            company_id = vals.get('company_id')
            if not company_id and vals.get('parent_id'):
                parent = self.browse(vals['parent_id'])
                company_id = parent.company_id.id if parent.company_id else False
            if not company_id:
                company_id = self.env.company.id
            vals['company_id'] = company_id
            company = self.env['res.company'].browse(company_id)

            # Auto-promote to root directory when no parent is given
            if not vals.get('parent_id') and not vals.get('is_root_directory'):
                vals['is_root_directory'] = True
                if not vals.get('storage_id'):
                    storage = self._get_or_create_company_storage(company)
                    vals['storage_id'] = storage.id
            elif vals.get('parent_id') and not vals.get('storage_id'):
                parent = self.browse(vals['parent_id'])
                if parent.storage_id:
                    vals['storage_id'] = parent.storage_id.id
                else:
                    storage = self._get_or_create_company_storage(company)
                    vals['storage_id'] = storage.id
        return super().create(vals_list)

    def write(self, vals):
        if 'company_id' in vals and vals['company_id']:
            new_cid = vals['company_id']
            for record in self:
                if record.child_directory_ids:
                    record.child_directory_ids.sudo().write({'company_id': new_cid})
                if record.file_ids:
                    record.file_ids.sudo().write({'company_id': new_cid})
        return super().write(vals)



    @api.depends("file_ids.is_trashed", "file_ids.active")
    def _compute_count_files(self):
        file_data = self.env['dms.file']._read_group(
            [('directory_id', 'in', self.ids), ('is_trashed', '=', False)],
            groupby=['directory_id'],
            aggregates=['__count']
        )
        counts = {dir_rec.id: count for dir_rec, count in file_data}
        for record in self:
            count = counts.get(record.id, 0)
            record.count_files = count
            record.count_files_title = _("%s Files") % count

    @api.depends("child_directory_ids.is_trashed")
    def _compute_count_directories(self):
        """Subfolders in the Trash are not part of the folder any more."""
        for record in self:
            count = len(record.child_directory_ids.filtered(lambda d: not d.is_trashed))
            record.count_directories = count
            record.count_directories_title = _("%s Subdirectories") % count

    @api.depends("count_files", "count_directories", "file_ids", "child_directory_ids")
    def _compute_count_elements(self):
        for record in self:
            record.count_elements = (record.count_files or len(record.file_ids)) + (record.count_directories or len(record.child_directory_ids))

    @api.depends("child_directory_ids", "file_ids")
    def _compute_size(self):
        """Override to neutralize size computation for performance."""
        for record in self:
            record.size = 0
            record.human_size = ""

    # Icon
    def _get_icon_placeholder_name(self):
        return "open-folder.png"

    def _get_icon_disk_path(self):
        try:
            return file_path("dms/static/description/open-folder.png")
        except FileNotFoundError:
            try:
                return file_path("dms/static/icons/open-folder.png")
            except FileNotFoundError:
                return super()._get_icon_disk_path()

    def _get_icon_url(self):
        return "/dms/static/description/open-folder.png"

    @api.depends("image_128")
    def _compute_icon_url(self):
        for one in self:
            one.icon_url = (
                f"/web/image/{one._name}/{one.id}/image_128/128x128?crop=1"
                if one.image_128
                else "/dms/static/description/open-folder.png"
            )

    @api.model
    def _dms_strip_trashed_panel_values(self, values):
        """Drop trashed directories from a search-panel folder tree.

        Trashed folders live only in the Trash; the sidebar tree must never
        list them. Children of a trashed folder are trashed with it, but any
        survivor whose parent was dropped is re-attached to the root so the
        tree stays consistent.
        """
        ids = [v["id"] for v in values if isinstance(v, dict) and v.get("id")]
        if not ids:
            return values
        trashed = set(
            self.sudo().search([("id", "in", ids), ("is_trashed", "=", True)]).ids
        )
        if not trashed:
            return values
        kept = [v for v in values if not (isinstance(v, dict) and v.get("id") in trashed)]
        for v in kept:
            if isinstance(v, dict):
                parent = v.get("parent_id")
                parent_id = parent[0] if isinstance(parent, (list, tuple)) else parent
                if parent_id in trashed:
                    v["parent_id"] = False
        return kept

    @api.model
    def name_search(self, name="", domain=None, operator="ilike", limit=100):
        # Folder pickers (move wizard, upload target, parent folder...) must
        # not offer folders that are in the Trash.
        if not self._dms_domain_mentions_trash(domain):
            domain = Domain.AND([domain or [], [("is_trashed", "=", False)]])
        return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

    @api.model
    def _dms_domain_mentions_trash(self, domain):
        for leaf in domain or []:
            if isinstance(leaf, (list, tuple)) and leaf and isinstance(leaf[0], str) \
                    and leaf[0].split(".")[0] in ("is_trashed", "parent_is_trashed"):
                return True
        return False

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        _dms_unlimited_panel(kwargs)
        res = super().search_panel_select_range(field_name, **kwargs)
        if isinstance(res, list):
            res = {"values": res}
        elif not isinstance(res, dict):
            res = {"values": []}
        elif "values" not in res:
            res["values"] = []

        if field_name == "parent_id":
            # Same folder tree as the documents sidebar (dms.file directory_id)
            res["values"] = self._dms_folder_tree_values(res["values"])
        return res

    @api.model
    def _dms_folder_tree_values(self, values):
        """Shared builder for the Documents sidebar folder tree.

        Used by both the documents browser (dms.file / directory_id) and
        Configuration > Directories (dms.directory / parent_id) so the two
        sidebars list the same folders, with the same counters (files directly
        in the folder) and the same per-folder action permissions.
        """
        values = self._dms_strip_trashed_panel_values(values)
        dir_ids = [v["id"] for v in values if isinstance(v, dict) and v.get("id")]
        if not dir_ids:
            return values
        directories = self.browse(dir_ids)
        file_counts = {
            d.id: count for d, count in self.env["dms.file"]._read_group(
                [("directory_id", "in", dir_ids), ("is_trashed", "=", False)],
                groupby=["directory_id"],
                aggregates=["__count"],
            )
        }
        info = {
            d.id: {
                "permission_download": d.permission_download,
                "permission_write": d.permission_write,
                "permission_unlink": d.permission_unlink,
                "permission_move": d.permission_move,
                "count_files": file_counts.get(d.id, 0),
                "company_id": d.company_id.id if d.company_id else False,
                "company_name": d.company_id.name if d.company_id else "",
            }
            for d in directories
        }
        allowed_companies = self.env.context.get("allowed_company_ids") or self.env.companies.ids
        multi_company = len(allowed_companies) > 1
        for v in values:
            if not (isinstance(v, dict) and v.get("id") in info):
                continue
            data = info[v["id"]]
            v.update(data)
            v["__count"] = data["count_files"]
            cname = data["company_name"]
            if multi_company and cname:
                disp = v.get("display_name") or v.get("name") or ""
                if f"({cname})" not in disp:
                    v["display_name"] = f"{disp} ({cname})"
        return values


    @api.model
    def search_panel_select_multi_range(self, field_name, **kwargs):
        _dms_unlimited_panel(kwargs)
        res = super().search_panel_select_multi_range(field_name, **kwargs)
        if isinstance(res, list):
            res = {"values": res}
        elif not isinstance(res, dict):
            res = {"values": []}
        elif "values" not in res:
            res["values"] = []
        return res

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        """Override to neutralize recursive full path computation."""
        for record in self:
            record.complete_name = record.name

    @api.onchange("tag_ids")
    def _onchange_tag_ids_autofill_category(self):
        for record in self:
            if not record.category_id and record.tag_ids:
                for tag in record.tag_ids:
                    if tag.category_id:
                        record.category_id = tag.category_id
                        break

    permission_line_ids = fields.One2many(
        "dms.directory.permission",
        "directory_id",
        string="Permission Lines",
    )
    group_permission_ids = fields.One2many(
        "dms.directory.permission",
        "directory_id",
        domain=[("group_id", "!=", False)],
        string="Access Group Permissions",
    )
    user_permission_ids = fields.One2many(
        "dms.directory.permission",
        "directory_id",
        domain=[("group_id", "=", False)],
        string="User Permissions",
    )

    # Users/contacts already covered by an access group on this folder: they
    # cannot be added again in the Users tab.
    group_member_user_ids = fields.Many2many(
        "res.users",
        string="Members via Access Groups",
        compute="_compute_group_member_ids",
    )
    group_member_partner_ids = fields.Many2many(
        "res.partner",
        compute="_compute_group_member_ids",
    )

    def _dms_dedupe_permission_lines(self):
        """Remove individual user/contact lines for people already covered by
        an access group line on the same folder, and log what was removed."""
        keys = ("perm_view", "perm_download", "perm_upload", "perm_edit",
                "perm_rename", "perm_move", "perm_delete", "perm_share")
        for directory in self.sudo().exists():
            group_lines = directory.permission_line_ids.filtered("group_id")
            if not group_lines:
                continue
            members = group_lines.group_id.users
            dupes = directory.permission_line_ids.filtered(
                lambda l: not l.group_id and (l.user_id | l.partner_id.user_ids) & members
            )
            if not dupes:
                continue
            notes = []
            for line in dupes:
                people = line.user_id | line.partner_id.user_ids
                covering = group_lines.filtered(lambda g: people & g.group_id.users)
                lost = [line._fields[k].string for k in keys
                        if line[k] and not any(g[k] for g in covering)]
                note = _("%s (via %s)") % ((line.user_id or line.partner_id).display_name,
                                    ", ".join(covering.group_id.mapped("name")))
                if lost:
                    note += _(" (individual rights no longer granted: %s)") % ", ".join(lost)
                notes.append(note)
            dupes.unlink()
            directory.message_post(
                body=_("Individual access removed because these people are now covered by an access group: %s")
                % "; ".join(notes),
                subtype_xmlid="mail.mt_note",
            )

    @api.depends("group_permission_ids.group_id")
    def _compute_group_member_ids(self):
        for record in self:
            users = record.group_permission_ids.group_id.sudo().users
            record.group_member_user_ids = users
            record.group_member_partner_ids = users.partner_id

    complete_permission_line_ids = fields.Many2many(
        "dms.directory.permission",
        relation="dms_dir_complete_perm_rel",
        column1="dir_id",
        column2="perm_id",
        compute="_compute_complete_permission_line_ids",
        store=True,
        recursive=True,
    )

    @api.depends(
        "permission_line_ids",
        "parent_id.complete_permission_line_ids",
        "inherit_group_ids",
    )
    def _compute_complete_permission_line_ids(self):
        for one in self:
            perms = one.permission_line_ids
            if one.inherit_group_ids and one.parent_id:
                perms |= one.parent_id.complete_permission_line_ids
            one.complete_permission_line_ids = perms

    def write(self, vals):
        if not self.env.su and not self.env.user.has_group('dms.group_dms_manager'):
            for record in self:
                if 'name' in vals and not record.permission_rename:
                    raise AccessError(_("You do not have permission to rename this directory."))
                if 'parent_id' in vals and not record.permission_move:
                    raise AccessError(_("You do not have permission to move this directory."))
                trash_fields = {'is_trashed', 'trash_date'}
                if trash_fields & set(vals) and not record.permission_delete:
                    raise AccessError(_("You do not have permission to delete this directory."))
                # Edits to other fields might be considered "edit"
                edit_fields = set(vals.keys()) - {'name', 'parent_id'} - trash_fields
                if edit_fields and not record.permission_edit:
                    raise AccessError(_("You do not have permission to edit this directory."))
        return super().write(vals)

    # Trash Management
    is_trashed = fields.Boolean(
        string="In Trash",
        default=False,
    )
    trash_date = fields.Datetime(
        string="Trash Date"
    )
    parent_is_trashed = fields.Boolean(
        related='parent_id.is_trashed',
        string="Parent is Trashed"
    )

    def action_dms_open_in_documents(self):
        """Open this folder in the documents browser (My Documents)."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "dms_enterprise_features.action_dms_my_documents"
        )
        action["context"] = {"searchpanel_default_directory_id": self.id}
        return action

    def action_open_move_wizard(self):
        return {
            'name': _('Move Folder(s)'),
            'type': 'ir.actions.act_window',
            'res_model': 'dms.move.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'dms.directory',
                'active_ids': self.ids,
            },
        }

    def action_send_to_trash(self):
        for record in self:
            record.write({
                'is_trashed': True,
                'trash_date': fields.Datetime.now()
            })
            # Permission to delete a folder covers its contents (OneDrive /
            # SharePoint behaviour), so cascade without per-item checks.
            # Locked files still block the operation.
            record.sudo().file_ids.action_send_to_trash()
            record.sudo().child_directory_ids.action_send_to_trash()
        return {
            'type': 'ir.actions.client',
            'tag': 'soft_reload',
        }

    def _dms_live_sibling_names(self):
        """Names of the non-trashed folders sharing this folder's parent."""
        self.ensure_one()
        if self.is_root_directory or not self.parent_id:
            siblings = self.sudo().storage_id.root_directory_ids
        else:
            siblings = self.sudo().parent_id.child_directory_ids
        return (siblings - self).filtered(lambda d: not d.is_trashed).mapped('name')

    @api.constrains("name")
    def _check_name(self):
        """Same-name check as dms, but folders in the Trash don't count:
        a user may recreate "Invoices" after trashing it. Restoring the old
        one then gets a unique name (see action_restore)."""
        for record in self:
            if self.env.context.get("check_name", True) and not check_name(record.name):
                raise ValidationError(_("The directory name is invalid."))
            if record.is_trashed:
                continue
            if record.name in record._dms_live_sibling_names():
                raise ValidationError(_("A directory with the same name already exists."))

    def action_restore(self):
        for record in self:
            # A live folder with the same name may have been created (or moved
            # in) while this one was in the Trash: restore as "Name (1)"
            # instead of producing two identical folders side by side. The
            # rename is part of the restore, so it doesn't need the separate
            # rename permission (sudo); the restore itself is still checked.
            live_names = record._dms_live_sibling_names()
            if record.name in live_names:
                record.sudo().write({'name': unique_name(record.name, live_names)})
            record.write({
                'is_trashed': False,
                'trash_date': False
            })
            # Restore files within
            record.sudo().with_context(active_test=False).file_ids.filtered('is_trashed').action_restore()
            # Restore child directories
            record.sudo().with_context(active_test=False).child_directory_ids.filtered('is_trashed').action_restore()
        return {
            'type': 'ir.actions.client',
            'tag': 'soft_reload',
        }

    def unlink(self):
        # Soft delete logic: if not in trash, send to trash instead.
        to_trash = self.filtered(lambda r: not r.is_trashed)
        if to_trash:
            to_trash.action_send_to_trash()
            
        to_delete = self - to_trash
        if to_delete:
            return super(DmsDirectory, to_delete).unlink()
        return True

    def action_open_form_view(self):
        self.ensure_one()
        if not self.permission_write and not self.env.user.has_group('dms.group_dms_manager') and not self.env.user.has_group('base.group_system'):
            raise UserError(_("You do not have permission to edit this directory."))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dms.directory',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_download_directory_zip(self):
        self.ensure_one()
        if not self.permission_download and not self.env.user.has_group('dms.group_dms_manager') and not self.env.user.has_group('base.group_system') and not self.env.user.has_group('dms_enterprise_features.group_dms_document_controller'):
            raise UserError(_("You do not have permission to download files from this directory."))
        try:
            import importlib
            import odoo.addons.dms_enterprise_features.controllers.directory_download as dd
            importlib.reload(dd)
        except Exception:
            pass
        return {
            'type': 'ir.actions.act_url',
            'url': f'/dms/directory/{self.id}/download_zip',
            'target': 'self',
        }

    @api.model
    def _search_starred(self, operator, operand):
        import collections.abc
        if isinstance(operand, (list, tuple, set, collections.abc.Set)):
            has_true = True in operand
            has_false = False in operand
        else:
            has_true = bool(operand)
            has_false = not bool(operand)
        if operator in ("!=", "not in"):
            has_true, has_false = not has_true, not has_false
        if has_true and not has_false:
            return [("user_star_ids", "in", [self.env.uid])]
        elif has_false and not has_true:
            return [("user_star_ids", "not in", [self.env.uid])]
        elif has_true and has_false:
            return []
        else:
            return [("id", "=", False)]

