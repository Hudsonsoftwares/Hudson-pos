# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MrpEcoApproval(models.Model):
    _name = 'mrp.eco.approval'
    _description = 'ECO Approval'
    _order = 'stage_sequence, id'

    eco_id = fields.Many2one('mrp.eco', string='ECO', required=True, ondelete='cascade', index=True)
    approval_template_id = fields.Many2one('mrp.eco.approval.template', string='Template', required=True)
    name = fields.Char(related='approval_template_id.name', string='Role', store=True)
    approval_type = fields.Selection(related='approval_template_id.approval_type', store=True)
    stage_id = fields.Many2one(related='approval_template_id.stage_id', string='Stage', store=True)
    stage_sequence = fields.Integer(related='approval_template_id.stage_id.sequence', store=True)
    approver_ids = fields.Many2many(related='approval_template_id.user_ids', string='Approvers')

    # Reporting helpers
    eco_type_id = fields.Many2one(related='eco_id.type_id', string='ECO Type', store=True)
    product_tmpl_id = fields.Many2one(related='eco_id.product_tmpl_id', string='Product', store=True)
    company_id = fields.Many2one(related='eco_id.company_id', store=True)

    user_id = fields.Many2one('res.users', string='Approved by')
    approval_date = fields.Datetime('Decision Date', readonly=True)
    status = fields.Selection([
        ('none', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], string='Status', default='none', required=True)
    is_approved = fields.Boolean('Is Approved', compute='_compute_is_approved', store=True)
    is_current_stage = fields.Boolean('Current Stage', compute='_compute_is_current_stage')
    user_is_approver = fields.Boolean('Current User Is Approver', compute='_compute_user_is_approver')

    @api.depends('status')
    def _compute_is_approved(self):
        for record in self:
            record.is_approved = record.status == 'approved'

    @api.depends('stage_id', 'eco_id.stage_id')
    def _compute_is_current_stage(self):
        for record in self:
            record.is_current_stage = record.stage_id == record.eco_id.stage_id

    @api.depends_context('uid')
    @api.depends('approver_ids')
    def _compute_user_is_approver(self):
        for record in self:
            record.user_is_approver = self.env.user in record.approver_ids

    def _check_can_decide(self):
        for approval in self:
            if self.env.user not in approval.approver_ids and not self.env.user.has_group('hudson_plm.group_plm_manager'):
                raise UserError(_('You are not an approver for the role "%s".', approval.name))
            if approval.eco_id.state == 'done':
                raise UserError(_('ECO %s is already done; approvals can no longer be changed.', approval.eco_id.name))
            if not approval.is_current_stage:
                raise UserError(_(
                    'The approval "%(role)s" belongs to stage "%(stage)s", which is not the current stage of the ECO.',
                    role=approval.name, stage=approval.stage_id.name))

    def _set_status(self, status):
        self._check_can_decide()
        self.write({
            'status': status,
            'user_id': self.env.user.id if status != 'none' else False,
            'approval_date': fields.Datetime.now() if status != 'none' else False,
        })
        labels = dict(self._fields['status'].selection)
        for approval in self:
            approval.eco_id.message_post(body=_(
                '%(role)s: %(status)s by %(user)s',
                role=approval.name, status=labels[status], user=self.env.user.name))
        self.eco_id._sync_approval_activities()

    def action_approve(self):
        self._set_status('approved')

    def action_reject(self):
        self._set_status('rejected')

    def action_reset(self):
        """ Put a decision back to pending so that it can be reconsidered. """
        self._set_status('none')
