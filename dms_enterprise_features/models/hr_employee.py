# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

class HrEmployee(models.Model):
    _inherit = "hr.employee"

    dms_directory_id = fields.Many2one(
        "dms.directory",
        string="DMS Folder",
        readonly=True,
        ondelete="set null",
        copy=False,
    )
    dms_access_group_id = fields.Many2one(
        "dms.access.group",
        string="DMS Access Group",
        readonly=True,
        ondelete="set null",
        copy=False,
    )

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        for employee in employees:
            employee._setup_dms_folder_and_permissions()
        return employees

    def write(self, vals):
        res = super().write(vals)
        for employee in self:
            if "name" in vals:
                # Rename directory and access group
                if employee.dms_directory_id:
                    directory = employee.dms_directory_id.sudo()
                    directory.name = employee._get_unique_dms_folder_name(
                        directory.parent_id, exclude=directory
                    )
                if employee.dms_access_group_id:
                    employee.dms_access_group_id.sudo().name = f"Access Group - {employee.name}"
            
            if "user_id" in vals:
                # Sync user_id to the access group
                if employee.dms_access_group_id:
                    if employee.user_id:
                        employee.dms_access_group_id.sudo().write({
                            "explicit_user_ids": [(6, 0, [employee.user_id.id])]
                        })
                    else:
                        employee.dms_access_group_id.sudo().write({
                            "explicit_user_ids": [(6, 0, [])]
                        })
                else:
                    employee._setup_dms_folder_and_permissions()
        return res

    def _get_company_root_directory(self, company):
        """Find or create the 'Employee - {Company}' (or 'Employees') root directory for this company."""
        if not company:
            company = self.company_id or self.env.company
        dir_name = f"Employee - {company.name}"
        root_dir = self.env["dms.directory"].sudo().search([
            ("name", "in", [dir_name, "Employees"]),
            ("is_root_directory", "=", True),
            ("company_id", "=", company.id),
        ], limit=1)

        if not root_dir:
            storage = self.env["dms.directory"]._get_or_create_company_storage(company)
            enterprise_group = self.env.ref("dms_enterprise_features.dms_access_group_enterprise", raise_if_not_found=False)
            group_cmd = [(4, enterprise_group.id)] if enterprise_group else []
            root_dir = self.env["dms.directory"].sudo().create({
                "name": dir_name,
                "is_root_directory": True,
                "storage_id": storage.id,
                "company_id": company.id,
                "group_ids": group_cmd,
            })
                
        return root_dir

    def _get_unique_dms_folder_name(self, parent, exclude=None):
        """Return the employee name, suffixed with " (2)", " (3)"... if a
        sibling folder under `parent` already uses it (dms.directory forbids
        duplicate names among siblings)."""
        self.ensure_one()
        base = (self.name or str(self.id)).replace("/", "-").strip()
        taken = set(
            (parent.sudo().child_directory_ids - (exclude or parent.browse())).mapped("name")
        )
        name, n = base, 1
        while name in taken:
            n += 1
            name = f"{base} ({n})"
        return name

    def _setup_dms_folder_and_permissions(self):
        """Creates the DMS folder and assigns View & Download permissions."""
        self.ensure_one()
        if self.dms_directory_id:
            return  # Already set up

        # 1. Get Root Directory
        root_dir = self._get_company_root_directory(self.company_id or self.env.company)

        # 2. Create Employee Subfolder. A folder with this name may already
        # exist under the root, e.g. one left by an earlier setup or an
        # unlinked folder created manually. Reuse it if no other employee
        # owns it; otherwise pick a unique name so homonyms don't collide.
        Directory = self.env["dms.directory"].sudo()
        employee_dir = Directory.search([
            ("parent_id", "=", root_dir.id),
            ("name", "=", self.name),
        ], limit=1)
        if employee_dir and self.sudo().search_count([
            ("dms_directory_id", "=", employee_dir.id),
            ("id", "!=", self.id),
        ], limit=1):
            employee_dir = Directory
        if not employee_dir:
            employee_dir = Directory.create({
                "name": self._get_unique_dms_folder_name(root_dir),
                "parent_id": root_dir.id,
                "storage_id": root_dir.storage_id.id,
            })
        # Link the folder to the employee: dms.file.res_model/res_id are
        # related to the directory, so this is what ties routed files back
        # to the employee (rule "Routed Files" counts, smart buttons).
        if (employee_dir.res_model, employee_dir.res_id) != ("hr.employee", self.id):
            employee_dir.write({"res_model": "hr.employee", "res_id": self.id})

        # 3. Create Access Group
        users = [(4, self.user_id.id)] if self.user_id else []
        access_group = self.env["dms.access.group"].sudo().create({
            "name": f"Access Group - {self.name}",
            "explicit_user_ids": users,
        })

        # 4. Link Access Group to Directory with View/Download permissions
        self.env["dms.directory.permission"].sudo().create({
            "directory_id": employee_dir.id,
            "group_id": access_group.id,
            "perm_view": True,
            "perm_download": True,
            "perm_upload": False,
            "perm_edit": False,
            "perm_rename": False,
            "perm_move": False,
            "perm_delete": False,
            "perm_share": False,
        })

        # 5. Link to Employee
        self.sudo().write({
            "dms_directory_id": employee_dir.id,
            "dms_access_group_id": access_group.id,
        })

    @api.model
    def _dms_backfill_folders(self):
        """Give every employee created before DMS was enabled their folder,
        and file their already-existing documents into it.

        Idempotent: employees that already have a folder are skipped, so it
        is safe to run on every install/upgrade, rule activation and when
        the HR documents setting is switched on.
        """
        employees = self.sudo().with_context(active_test=False).search([
            ("dms_directory_id", "=", False),
        ])
        done = self.browse()
        for employee in employees:
            try:
                with self.env.cr.savepoint():
                    employee._setup_dms_folder_and_permissions()
                done |= employee
            except Exception as e:
                _logger.warning(
                    "DMS: could not create folder for employee %s (%s): %s",
                    employee.id, employee.name, e,
                )
        # Link folders created before folders were tied to their employee
        for employee in self.sudo().with_context(active_test=False).search([
            ("dms_directory_id", "!=", False),
            ("dms_directory_id.res_id", "=", 0),
        ]):
            employee.dms_directory_id.write({"res_model": "hr.employee", "res_id": employee.id})
        if done:
            _logger.info("DMS: created folders for %d existing employee(s)", len(done))
            done._dms_route_existing_attachments()
        return done

    def _dms_route_existing_attachments(self):
        """Route the employees' existing documents (chatter files etc.)
        through the active employee folder rule, if there is one."""
        FolderRule = self.env["dms.folder.rule"].sudo()
        Attachment = self.env["ir.attachment"].sudo()
        # search() already hides binary-field storage (avatars): res_field=False
        attachments = Attachment.search([
            ("res_model", "=", "hr.employee"),
            ("res_id", "in", self.ids),
        ])
        for employee in self:
            rule = FolderRule.find_matching_rule("hr.employee", record=employee)
            if not rule:
                continue
            for attachment in attachments.filtered(lambda a, e=employee: a.res_id == e.id):
                rule.route_attachment(attachment)

    def action_setup_dms_folders(self):
        """Server action for existing employees."""
        for employee in self:
            employee._setup_dms_folder_and_permissions()
