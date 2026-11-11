# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class DMSFileApproval(models.Model):
    _name = "dms.file.approval"
    _description = "Document Approval Step"
    _order = "sequence asc, id asc"
    
    file_id = fields.Many2one(
        comodel_name="dms.file",
        string="Document",
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        related="file_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )

    revision_id = fields.Many2one(
        comodel_name="dms.file.revision",
        string="Revision",
        ondelete="set null",
    )
    sequence = fields.Integer(
        string="Order",
        default=10,
    )
    approver_id = fields.Many2one(
        comodel_name="res.users",
        string="Approver",
        required=True,
        domain="[('share', '=', False)]",
    )
    status = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('waiting', 'Waiting'),
            ('pending', 'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string="Status",
        default="draft",
        required=True,
    )
    comments = fields.Text(string="Comments / Rejection Reason")
    date = fields.Datetime(string="Action Date")

    is_current_approver = fields.Boolean(
        string="Is Current Approver",
        compute="_compute_is_current_approver",
    )

    def _compute_is_current_approver(self):
        current_uid = self.env.uid
        for record in self:
            record.is_current_approver = (
                record.status == 'pending'
                and record.approver_id.id == current_uid
            )

    def action_approve_step(self):
        current_uid = self.env.uid
        for record in self:
            if record.approver_id.id != current_uid:
                raise UserError(_("Only the assigned approver (%s) can approve this step.") % record.approver_id.name)
            record.file_id.action_approve_step(approver_user=record.approver_id)
        return True

    def action_open_reject_wizard(self):
        self.ensure_one()
        if self.approver_id.id != self.env.uid:
            raise UserError(_("Only the assigned approver (%s) can reject this step.") % self.approver_id.name)
        return {
            'name': _('Reject Approval: %s') % (self.file_id.name or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'dms.file.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_file_id': self.file_id.id,
            }
        }


class DMSUserDefaultApproval(models.Model):
    _name = "dms.user.default.approval"
    _description = "User Default Document Approver"
    _order = "sequence asc, id asc"

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="User",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(
        string="Order",
        default=10,
    )
    approver_id = fields.Many2one(
        comodel_name="res.users",
        string="Default Approver",
        required=True,
        domain="[('share', '=', False)]",
    )


class ResUsers(models.Model):
    _inherit = "res.users"

    default_approval_ids = fields.One2many(
        comodel_name="dms.user.default.approval",
        inverse_name="user_id",
        string="Default Document Approvers",
    )
    default_is_sequential_approval = fields.Boolean(
        string="Sequential Approval by Default",
        default=True,
        help="If checked, document approval requests will be sent sequentially in order. If unchecked, all approvers receive requests at the same time.",
    )
