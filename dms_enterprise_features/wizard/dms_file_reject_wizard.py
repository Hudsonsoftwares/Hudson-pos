# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class DmsFileRejectWizard(models.TransientModel):
    _name = "dms.file.reject.wizard"
    _description = "Reject Document Approval Wizard"

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
    reason = fields.Text(
        string="Rejection Reason",
        required=True,
        placeholder="Please state the specific reason for rejecting this document...",
    )

    def action_confirm_reject(self):
        self.ensure_one()
        if not self.reason or not self.reason.strip():
            raise UserError(_("Please provide a rejection reason."))
        return self.file_id.action_process_rejection(self.reason.strip())
