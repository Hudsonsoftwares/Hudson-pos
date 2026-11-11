from odoo import models, api, fields
from odoo.tools import SQL


class DmsSecurityMixin(models.AbstractModel):
    _inherit = "dms.security.mixin"

    @api.model
    def _get_access_groups_query(self, operation):
        """Return the query to select accessible directories based on custom folder permissions."""
        operation_check = {
            "create": "AND dp.perm_upload = TRUE",
            "read": "AND (dp.perm_view = TRUE OR dp.perm_download = TRUE)",
            "unlink": "AND dp.perm_delete = TRUE",
            "write": "AND (dp.perm_edit = TRUE OR dp.perm_move = TRUE OR dp.perm_rename = TRUE)",
        }[operation]

        uid = self.env.uid
        partner_id = self.env.user.partner_id.id if self.env.user.partner_id else 0

        select = (
            "("
            " SELECT dir_perm_rel.dir_id as aid"
            " FROM dms_dir_complete_perm_rel AS dir_perm_rel"
            " INNER JOIN dms_directory_permission AS dp ON dir_perm_rel.perm_id = dp.id"
            " LEFT JOIN dms_access_group AS dag ON dp.group_id = dag.id"
            " LEFT JOIN dms_access_group_users_rel AS users ON users.gid = dag.id"
            " WHERE (users.uid = %s OR dp.user_id = %s OR dp.partner_id = %s)"
            f" {operation_check}"
            ")"
        )
        return SQL(select, uid, uid, partner_id)

    permission_view = fields.Boolean(compute="_compute_granular_permissions", search="_search_permission_view")
    permission_download = fields.Boolean(compute="_compute_granular_permissions", search="_search_permission_download")
    permission_upload = fields.Boolean(compute="_compute_granular_permissions", search="_search_permission_upload")
    permission_edit = fields.Boolean(compute="_compute_granular_permissions", search="_search_permission_edit")
    permission_move = fields.Boolean(compute="_compute_granular_permissions", search="_search_permission_move")
    permission_rename = fields.Boolean(compute="_compute_granular_permissions", search="_search_permission_rename")
    permission_delete = fields.Boolean(compute="_compute_granular_permissions", search="_search_permission_delete")
    permission_share = fields.Boolean(compute="_compute_granular_permissions", search="_search_permission_share")

    @api.model
    def _search_permission_upload(self, operator, value):
        return self._get_permission_domain(operator, value, "create")

    @api.model
    def _search_permission_view(self, operator, value):
        return self._get_permission_domain(operator, value, "read")

    @api.model
    def _search_permission_download(self, operator, value):
        return self._get_permission_domain(operator, value, "read")

    @api.model
    def _search_permission_edit(self, operator, value):
        return self._get_permission_domain(operator, value, "write")

    @api.model
    def _search_permission_move(self, operator, value):
        return self._get_permission_domain(operator, value, "write")

    @api.model
    def _search_permission_rename(self, operator, value):
        return self._get_permission_domain(operator, value, "write")

    @api.model
    def _search_permission_delete(self, operator, value):
        return self._get_permission_domain(operator, value, "unlink")

    @api.model
    def _search_permission_share(self, operator, value):
        return self._get_permission_domain(operator, value, "read")

    @api.model
    def _get_domain_by_inheritance(self, operation):
        """Get domain for inherited accessible records (attachment-storage)."""
        from odoo.fields import Domain
        OR = Domain.OR
        FALSE_DOMAIN = [(0, '=', 1)]
        from odoo.exceptions import AccessError

        inherited_access_field = "storage_id_inherit_access_from_parent_record"
        if self._name != "dms.directory":
            inherited_access_field = f"{self._directory_field}.{inherited_access_field}"
        inherited_access_domain = [
            ("storage_id_save_type", "=", "attachment"),
            (inherited_access_field, "=", True),
        ]
        domains = []
        related_groups = self.sudo().read_group(
            domain=inherited_access_domain + [("res_model", "!=", False)],
            fields=["res_id:array_agg"],
            groupby=["res_model"],
        )
        for group in related_groups:
            try:
                model = self.env[group["res_model"]]
            except KeyError:
                continue
            try:
                model.check_access(operation)
            except AccessError:
                continue
            domains.append([("res_model", "=", model._name), ("res_id", "=", False)])
            res_ids = [i for i in group["res_id"] if i]
            model_records = model.browse(res_ids).exists()
            related_ok = model_records._filtered_access(operation)
            if not related_ok:
                continue
            domains.append(
                [("res_model", "=", model._name), ("res_id", "in", related_ok.ids)]
            )
        if not domains:
            return FALSE_DOMAIN
        return inherited_access_domain + OR(domains)

    @api.model
    def _is_dms_privileged_user(self):
        """Return True if the current user should have unrestricted DMS access."""
        return (
            self.env.is_superuser()
            or self.env.user.has_group('dms.group_dms_manager')
            or self.env.user.has_group('base.group_system')
            or self.env.user.has_group('dms_enterprise_features.group_dms_administrator')
        )

    @api.model
    def _get_permission_domain(self, operator, value, operation):
        """
        Central security domain used by the ir.access domain_force expressions.

        Security model:
          - DMS Managers / Administrators / Superuser -> unrestricted access.
          - All other users -> only records explicitly assigned or owned by them.
        """
        from odoo.fields import Domain
        OR = Domain.OR
        AND = Domain.AND
        TRUE_DOMAIN = [(1, '=', 1)]
        FALSE_DOMAIN = [(0, '=', 1)]
        NEGATIVE_TERM_OPERATORS = ('!=', 'not like', 'not ilike', 'not in', 'not any', 'not any!')

        positive = (operator not in NEGATIVE_TERM_OPERATORS) == bool(value)

        if self._is_dms_privileged_user():
            return TRUE_DOMAIN if positive else FALSE_DOMAIN

        uid = self.env.uid
        partner_id = self.env.user.partner_id.id if self.env.user.partner_id else 0

        # Collect user's group IDs and department IDs for file-level access checks
        user_group_ids = self.env['res.groups'].sudo().search([('user_ids', '=', uid)]).ids
        user_groups = tuple(user_group_ids) if user_group_ids else (0,)
        dept_ids = []
        if hasattr(self.env.user, 'employee_ids'):
            dept_ids = self.env.user.sudo().employee_ids.mapped('department_id').ids
        user_depts = tuple(dept_ids) if dept_ids else (0,)

        if self._name == 'dms.directory':
            result = self._build_directory_domain(
                operation, uid, partner_id, user_groups, user_depts, OR, AND
            )
        elif self._name == 'dms.file':
            result = self._build_file_domain(
                operation, uid, partner_id, user_groups, user_depts, OR, AND,
                FALSE_DOMAIN
            )
        else:
            # Fallback for any other DMS model
            result = OR([
                self._get_domain_by_access_groups(operation),
                self._get_domain_by_inheritance(operation),
            ])

        if not positive:
            result.insert(0, "!")
        return result

    @api.model
    def _build_directory_domain(
        self, operation, uid, partner_id, user_groups, user_depts, OR, AND
    ):
        """
        Security domain for dms.directory.

        Read access:
          (1) User has an explicit directory permission line granting view/download.
          (2) Directory is an ancestor of a dir/file the user can reach (navigation).
        Write/Create/Unlink:
          Only explicit directory permission lines grant those rights.
        """
        # Rule 1: directories with matching permission entry for this user
        dir_perm_domain = [
            ('storage_id_inherit_access_from_parent_record', '=', False),
            ('id', 'in', self._get_access_groups_query(operation)),
        ]

        if operation != 'read':
            return dir_perm_domain

        allowed_companies = tuple(self.env.companies.ids) if self.env.companies else ((self.env.user.company_id.id,) if self.env.user.company_id else (0,))

        # Rule 2 (read only): ancestor directories for tree navigation
        # Walk up the tree from directories/files the user can directly access
        ancestor_sql = SQL(
            """
            WITH RECURSIVE accessible AS (

                -- Directories with explicit view/download permission for this user
                SELECT rel.dir_id AS id
                FROM dms_dir_complete_perm_rel rel
                INNER JOIN dms_directory_permission dp ON rel.perm_id = dp.id
                LEFT JOIN dms_access_group dag ON dp.group_id = dag.id
                LEFT JOIN dms_access_group_users_rel gu ON gu.gid = dag.id
                WHERE (gu.uid = %s OR dp.user_id = %s OR dp.partner_id = %s)
                  AND (dp.perm_view = TRUE OR dp.perm_download = TRUE)

                UNION

                -- Directories containing files this user can access
                SELECT DISTINCT f.directory_id AS id
                FROM dms_file f
                LEFT JOIN dms_file_access fa ON fa.file_id = f.id
                WHERE f.directory_id IS NOT NULL
                  AND f.active = TRUE
                  AND (f.is_trashed = FALSE OR f.is_trashed IS NULL)
                  AND (f.company_id IS NULL OR f.company_id IN %s)
                  AND (
                      f.document_owner_id = %s
                      OR f.create_uid = %s
                      OR (
                          (fa.user_id = %s OR fa.partner_id = %s
                           OR fa.group_id IN %s OR fa.department_id IN %s
                           OR fa.access_group_id IN (
                               SELECT gid FROM dms_access_group_users_rel WHERE uid = %s))
                          AND (fa.perm_view = TRUE OR fa.perm_download = TRUE
                               OR fa.perm_share = TRUE)
                      )
                      OR EXISTS (
                          SELECT 1 FROM dms_file_revision rev
                          JOIN dms_file_signature_request sr ON sr.revision_id = rev.id
                          WHERE rev.file_id = f.id
                            AND (sr.recipient_id = %s OR EXISTS (
                                SELECT 1 FROM res_users ru WHERE ru.id = sr.recipient_id AND ru.partner_id = %s
                            ))
                      )
                  )
            ),
            ancestors AS (
                SELECT id FROM accessible
                UNION
                SELECT d.parent_id
                FROM dms_directory d
                INNER JOIN ancestors a ON d.id = a.id
                WHERE d.parent_id IS NOT NULL
                  AND (d.company_id IS NULL OR d.company_id IN %s)
            )
            SELECT id FROM ancestors WHERE id IS NOT NULL
            """,
            uid, uid, partner_id,          # permission line match
            allowed_companies,             # company isolation
            uid, uid,                      # owner / creator of file
            uid, partner_id, user_groups, user_depts, uid,  # file access entry
            uid, partner_id,               # signature request recipient
            allowed_companies              # ancestor company isolation
        )

        return OR([dir_perm_domain, [('id', 'in', ancestor_sql)]])

    @api.model
    def _build_file_domain(
        self, operation, uid, partner_id, user_groups, user_depts, OR, AND,
        FALSE_DOMAIN
    ):
        """
        Security domain for dms.file (SharePoint-style inheritance).

        A file is accessible when ANY of:
          (1) An explicit dms_file_access line grants the operation. File lines
              are additive: they add rights, they never remove folder rights.
          (2) User is the document owner or uploader (full control).
          (3) [Read only] User is an approver or signature recipient.
          (4) The file inherits folder permissions (inherit_permissions) AND
              the folder grants the user the operation. Files with inheritance
              stopped ("unique permissions") skip this rule.
        """
        op_file_sql = {
            'read':   '(fa.perm_view = TRUE OR fa.perm_download = TRUE OR fa.perm_share = TRUE)',
            'write':  '(fa.perm_edit = TRUE OR fa.perm_move = TRUE OR fa.perm_rename = TRUE)',
            'unlink': 'fa.perm_delete = TRUE',
            'create': 'FALSE',
        }.get(operation, 'FALSE')

        op_dir_sql = {
            'read':   '(dp.perm_view = TRUE OR dp.perm_download = TRUE)',
            'write':  '(dp.perm_edit = TRUE OR dp.perm_move = TRUE OR dp.perm_rename = TRUE)',
            'unlink': 'dp.perm_delete = TRUE',
            'create': 'dp.perm_upload = TRUE',
        }.get(operation, 'FALSE')

        domains = []

        # Rule 1: explicit file-level access entry
        if operation != 'create':
            domains.append([('id', 'in', SQL(
                "SELECT fa.file_id FROM dms_file_access fa"
                " WHERE (fa.user_id = %s OR fa.partner_id = %s"
                "        OR fa.group_id IN %s OR fa.department_id IN %s"
                "        OR fa.access_group_id IN ("
                "            SELECT gid FROM dms_access_group_users_rel WHERE uid = %s))"
                " AND " + op_file_sql,
                uid, partner_id, user_groups, user_depts, uid
            ))])

        # Rule 2: owner / uploader has full control of their own document
        if operation in ('read', 'write', 'unlink'):
            domains.append([('document_owner_id', '=', uid)])
            domains.append([('create_uid', '=', uid)])

        # Rule 3: approver (read only)
        if operation == 'read':
            domains.append([('id', 'in', SQL(
                "SELECT DISTINCT ap.file_id FROM dms_file_approval ap"
                " WHERE ap.approver_id = %s",
                uid
            ))])

            # Rule 3b: signature request recipient (read only)
            domains.append([('id', 'in', SQL(
                """
                SELECT DISTINCT rev.file_id
                FROM dms_file_signature_request sr
                JOIN dms_file_revision rev ON sr.revision_id = rev.id
                WHERE (sr.recipient_id = %s OR EXISTS (
                    SELECT 1 FROM res_users ru WHERE ru.id = sr.recipient_id AND ru.partner_id = %s
                ))
                """,
                uid, partner_id
            ))])

        # Rule 5 (create): uploading is a folder right, independent of the
        # new file's inheritance flag
        if operation == 'create':
            domains.append([('id', 'in', SQL(
                "SELECT f.id FROM dms_file f"
                " WHERE EXISTS ("
                "     SELECT 1 FROM dms_dir_complete_perm_rel rel"
                "     INNER JOIN dms_directory_permission dp ON rel.perm_id = dp.id"
                "     LEFT JOIN dms_access_group dag ON dp.group_id = dag.id"
                "     LEFT JOIN dms_access_group_users_rel gu ON gu.gid = dag.id"
                "     WHERE rel.dir_id = f.directory_id"
                "       AND (gu.uid = %s OR dp.user_id = %s OR dp.partner_id = %s)"
                "       AND dp.perm_upload = TRUE"
                " )",
                uid, uid, partner_id
            ))])

        # Rule 4: file inherits folder permissions + folder grants this operation
        if operation in ('read', 'write', 'unlink'):
            domains.append([('id', 'in', SQL(
                "SELECT f.id FROM dms_file f"
                " WHERE f.inherit_permissions = TRUE"
                " AND EXISTS ("
                "     SELECT 1 FROM dms_dir_complete_perm_rel rel"
                "     INNER JOIN dms_directory_permission dp ON rel.perm_id = dp.id"
                "     LEFT JOIN dms_access_group dag ON dp.group_id = dag.id"
                "     LEFT JOIN dms_access_group_users_rel gu ON gu.gid = dag.id"
                "     WHERE rel.dir_id = f.directory_id"
                "       AND (gu.uid = %s OR dp.user_id = %s OR dp.partner_id = %s)"
                "       AND " + op_dir_sql +
                " )",
                uid, uid, partner_id
            ))])

        return OR(domains) if domains else FALSE_DOMAIN

    def _compute_permissions(self):
        for record in self:
            if (self.env.su
                    or self.env.user.has_group('dms.group_dms_manager')
                    or self.env.user.has_group('base.group_system')
                    or self.env.user.has_group('dms_enterprise_features.group_dms_administrator')):
                record.permission_read = True
                record.permission_create = True
                record.permission_write = True
                record.permission_unlink = True
            else:
                record.permission_read = record.permission_view or record.permission_download
                record.permission_create = record.permission_upload
                record.permission_write = record.permission_edit or record.permission_move or record.permission_rename
                record.permission_unlink = record.permission_delete

    _DMS_PERM_KEYS = ("view", "download", "upload", "edit", "move", "rename", "delete", "share")

    @api.model
    def _dms_directory_perms_for_user(self, directory, user):
        """Union of the folder permission lines (incl. inherited parents) that
        target ``user``."""
        perms = dict.fromkeys(self._DMS_PERM_KEYS, False)
        if not directory:
            return perms
        partner = user.partner_id
        for perm in directory.sudo().complete_permission_line_ids:
            if (
                (perm.group_id and user in perm.group_id.users)
                or (perm.user_id and perm.user_id == user)
                or (perm.partner_id and perm.partner_id == partner)
            ):
                for key in self._DMS_PERM_KEYS:
                    if perm[f"perm_{key}"]:
                        perms[key] = True
        return perms

    def _compute_granular_permissions(self):
        user = self.env.user
        privileged = self.env.su or self._is_dms_privileged_user()
        for record in self:
            if privileged:
                perms = dict.fromkeys(self._DMS_PERM_KEYS, True)
            elif record._name == "dms.file":
                perms = record._dms_effective_permissions(user)
            else:
                perms = self._dms_directory_perms_for_user(record, user)
            for key in self._DMS_PERM_KEYS:
                record[f"permission_{key}"] = perms[key]
