from odoo import models, fields, api

class DmsAccessGroup(models.Model):
    _inherit = 'dms.access.group'

    company_id = fields.Many2one(
        'res.company',
        string="Company",
        default=lambda self: self.env.company,
        index=True,
    )

    dms_manager_user_ids = fields.Many2many(
        'res.users', 
        compute='_compute_dms_manager_user_ids',
        string="DMS Manager Users"
    )

    def _compute_dms_manager_user_ids(self):
        manager_group = self.env.ref('dms.group_dms_manager', raise_if_not_found=False)
        manager_users = manager_group.all_user_ids if manager_group else self.env['res.users']
        for record in self:
            record.dms_manager_user_ids = manager_users

    @api.depends("group_ids", "explicit_user_ids")
    def _compute_users(self):
        for record in self:
            users = record.explicit_user_ids
            if record.group_ids:
                users |= self.env["res.users"].search(
                    [("group_ids", "in", record.group_ids.ids)]
                )
            record.users = users

    def _dms_ensure_members_are_dms_users(self):
        """Internal members of an access group need the DMS User group to work
        with the folders/files the group is granted (e.g. upload), exactly like
        users granted individually on a permission line."""
        dms_user_group = self.env.ref("dms.group_dms_user", raise_if_not_found=False)
        if not dms_user_group:
            return
        members = self.sudo().users.filtered(
            lambda u: u.active and not u.share and dms_user_group not in u.all_group_ids
        )
        if members:
            dms_user_group.sudo().write({"user_ids": [(4, uid) for uid in members.ids]})

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._dms_ensure_members_are_dms_users()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"explicit_user_ids", "group_ids", "parent_group_id"} & set(vals):
            self._dms_ensure_members_are_dms_users()
            # New members may already have their own line on folders/documents
            # this group is granted on: the group now covers them.
            self.env["dms.directory.permission"].sudo().search(
                [("group_id", "in", self.ids)]).directory_id._dms_dedupe_permission_lines()
            self.env["dms.file.access"].sudo().search(
                [("access_group_id", "in", self.ids)]).file_id._dms_dedupe_access_lines()
        return res

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # Remove the current user from being added automatically to explicit_user_ids
        if 'explicit_user_ids' in res:
            if isinstance(res['explicit_user_ids'], list) and res['explicit_user_ids'] and isinstance(res['explicit_user_ids'][0], tuple):
                # Format is [(6, 0, [ids])]
                for cmd in res['explicit_user_ids']:
                    if cmd[0] == 6 and self.env.uid in cmd[2]:
                        cmd[2].remove(self.env.uid)
            elif isinstance(res['explicit_user_ids'], list) and self.env.uid in res['explicit_user_ids']:
                res['explicit_user_ids'].remove(self.env.uid)
        return res
