# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class DMSFile(models.Model):
    _inherit = "dms.file"

    @api.onchange("tag_ids")
    def _onchange_tag_ids(self):
        # Auto-assign the category of the last added tag, if the document has no category
        # or if they want it to update to the latest tag's category.
        if self.tag_ids:
            tags_with_category = self.tag_ids.filtered(lambda t: t.category_id)
            if tags_with_category and self.category_id not in tags_with_category.mapped('category_id'):
                # Set it to the category of the last tag in the list
                self.category_id = tags_with_category[-1].category_id

    # We also want to ensure this happens during create/write, not just in UI onchange
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.tag_ids and not record.category_id:
                tags_with_category = record.tag_ids.filtered(lambda t: t.category_id)
                if tags_with_category:
                    record.category_id = tags_with_category[-1].category_id
        return records

    def write(self, vals):
        res = super().write(vals)
        if "tag_ids" in vals:
            for record in self:
                # If tags were updated and no category explicitly set in this write, update category
                if not "category_id" in vals and record.tag_ids:
                    tags_with_category = record.tag_ids.filtered(lambda t: t.category_id)
                    if tags_with_category and record.category_id not in tags_with_category.mapped('category_id'):
                        record.category_id = tags_with_category[-1].category_id
        return res


class DMSTag(models.Model):
    _inherit = "dms.tag"

    category_id = fields.Many2one(
        comodel_name="dms.category",
        context={"dms_category_show_path": True},
        string="Category",
        required=False,
        ondelete="set null",
    )

    def init(self):
        super().init()
        # Drop NOT NULL constraint on category_id in dms_tag if present
        self.env.cr.execute("""
            DO $$
            BEGIN
                ALTER TABLE dms_tag ALTER COLUMN category_id DROP NOT NULL;
            EXCEPTION
                WHEN undefined_column THEN NULL;
            END $$;
        """)
