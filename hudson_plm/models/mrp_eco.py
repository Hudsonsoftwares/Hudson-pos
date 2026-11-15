# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import UserError

APPROVAL_ACTIVITY = 'hudson_plm.mail_activity_eco_approval'


class MrpEco(models.Model):
    _name = 'mrp.eco'
    _description = 'Engineering Change Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, id desc'

    name = fields.Char('Reference', required=True, copy=False)
    active = fields.Boolean('Active', default=True)
    priority = fields.Selection([('0', 'Normal'), ('1', 'Urgent')], string='Priority', default='0')
    type_id = fields.Many2one('mrp.eco.type', string='Type', required=True)
    type = fields.Selection([
        ('bom', 'Bill of Materials'),
        ('routing', 'Routing'),
        ('product', 'Product Only')
    ], string='Apply on', default='bom', required=True)

    stage_id = fields.Many2one(
        'mrp.eco.stage', string='Stage', copy=False, group_expand='_read_group_stage_ids', tracking=True,
        domain="[('type_ids', 'in', type_id)]")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    # Not required at database level so that ECOs can be created from incoming emails;
    # the form view still asks for it.
    product_tmpl_id = fields.Many2one('product.template', string='Product', tracking=True)
    bom_id = fields.Many2one('mrp.bom', string='Bill of Materials', domain="[('product_tmpl_id', '=', product_tmpl_id)]")
    new_bom_id = fields.Many2one('mrp.bom', string='New Bill of Materials', copy=False)

    # Master data fetched from the product, its current BoM and the work centers used by its operations
    product_default_code = fields.Char(related='product_tmpl_id.default_code', string='Internal Reference')
    product_categ_id = fields.Many2one(related='product_tmpl_id.categ_id', string='Product Category')
    product_uom_id = fields.Many2one(related='product_tmpl_id.uom_id', string='Unit')
    product_standard_price = fields.Float(related='product_tmpl_id.standard_price', string='Product Cost')
    product_bom_count = fields.Integer(related='product_tmpl_id.bom_count', string='# BoMs')
    bom_line_ids = fields.One2many(related='bom_id.bom_line_ids', string='Current Components')
    operation_ids = fields.One2many(related='bom_id.operation_ids', string='Current Operations')
    workcenter_ids = fields.Many2many('mrp.workcenter', string='Work Centers', compute='_compute_workcenter_ids')

    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user, tracking=True)
    effectivity = fields.Selection([
        ('asap', 'As soon as possible'),
        ('date', 'At Date')
    ], string='Effective Date', default='asap', required=True)
    effectivity_date = fields.Datetime('Effective Date (Custom)', tracking=True)

    tag_ids = fields.Many2many('mrp.eco.tag', string='Tags')
    note = fields.Html('Note')

    update_version = fields.Boolean('Update Version', default=True)
    new_bom_version = fields.Integer('New BoM Version', related='new_bom_id.version')
    document_count = fields.Integer('Document Count', compute='_compute_document_count')

    # Track if changes have been applied so Apply Changes button disappears after use
    is_applied = fields.Boolean('Changes Applied', default=False, copy=False, tracking=True)
    date_done = fields.Datetime('Completion Date', copy=False, readonly=True)
    lead_time = fields.Float('Lead Time (Days)', compute='_compute_lead_time', store=True, aggregator='avg')

    approval_ids = fields.One2many('mrp.eco.approval', 'eco_id', string='Approvals')
    current_approval_ids = fields.Many2many(
        'mrp.eco.approval', string='Current Stage Approvals', compute='_compute_current_approval_ids')
    bom_change_ids = fields.One2many('mrp.eco.bom.change', 'eco_id', string='BoM Changes')
    routing_change_ids = fields.One2many('mrp.eco.routing.change', 'eco_id', string='Operation Changes')
    color = fields.Integer('Color')

    user_can_approve = fields.Boolean(
        'Can Approve', compute='_compute_user_can_approve', search='_search_user_can_approve')
    user_can_reject = fields.Boolean(
        'Can Reject', compute='_compute_user_can_approve')
    can_revert_stage = fields.Boolean('Can Revert Stage', compute='_compute_can_revert_stage')

    state = fields.Selection([
        ('progress', 'In Progress'),
        ('done', 'Done'),
        ('conflict', 'Rejected')
    ], string='Status', compute='_compute_state', store=True)

    def _compute_document_count(self):
        for eco in self:
            eco.document_count = self.env['ir.attachment'].search_count([
                ('res_model', '=', 'mrp.eco'),
                ('res_id', '=', eco.id)
            ])

    @api.depends('bom_id.operation_ids.workcenter_id', 'new_bom_id.operation_ids.workcenter_id')
    def _compute_workcenter_ids(self):
        for eco in self:
            boms = (eco.bom_id | eco.new_bom_id).with_context(active_test=False)
            eco.workcenter_ids = boms.operation_ids.workcenter_id

    @api.depends('create_date', 'date_done')
    def _compute_lead_time(self):
        for eco in self:
            if eco.create_date and eco.date_done:
                eco.lead_time = (eco.date_done - eco.create_date).total_seconds() / 86400.0
            else:
                eco.lead_time = 0.0

    @api.depends('stage_id', 'stage_id.final_stage', 'approval_ids.status', 'approval_ids.stage_id')
    def _compute_state(self):
        for eco in self:
            if eco.stage_id.final_stage:
                eco.state = 'done'
            elif any(a.status == 'rejected' and a.stage_id == eco.stage_id for a in eco.approval_ids):
                eco.state = 'conflict'
            else:
                eco.state = 'progress'

    @api.depends('approval_ids.stage_id', 'stage_id')
    def _compute_current_approval_ids(self):
        for eco in self:
            eco.current_approval_ids = eco.approval_ids.filtered(lambda a: a.stage_id == eco.stage_id)

    @api.depends_context('uid')
    @api.depends('approval_ids.status', 'approval_ids.stage_id', 'stage_id')
    def _compute_user_can_approve(self):
        for eco in self:
            mine = eco._get_user_current_approvals()
            eco.user_can_approve = eco.state != 'done' and any(a.status != 'approved' for a in mine)
            eco.user_can_reject = eco.state != 'done' and any(a.status != 'rejected' for a in mine)

    def _search_user_can_approve(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        approvals = self.env['mrp.eco.approval'].search([
            ('status', '!=', 'approved'),
            ('approval_template_id.user_ids', 'in', self.env.uid),
            ('eco_id.state', '!=', 'done'),
        ])
        eco_ids = approvals.filtered(lambda a: a.stage_id == a.eco_id.stage_id).eco_id.ids
        positive = (operator == '=') == value
        return [('id', 'in' if positive else 'not in', eco_ids)]

    @api.depends('stage_id', 'type_id', 'is_applied')
    def _compute_can_revert_stage(self):
        for eco in self:
            eco.can_revert_stage = bool(eco._get_previous_stage()) and not eco.is_applied

    def _get_user_current_approvals(self):
        self.ensure_one()
        return self.approval_ids.filtered(
            lambda a: a.stage_id == self.stage_id and self.env.user in a.approval_template_id.user_ids)

    # ------------------------------------------------------------------
    # Stages
    # ------------------------------------------------------------------

    def _get_type_stages(self):
        self.ensure_one()
        return self.env['mrp.eco.stage'].search([('type_ids', 'in', self.type_id.id)], order='sequence, id')

    def _get_previous_stage(self):
        self.ensure_one()
        if not self.stage_id or not self.type_id:
            return self.env['mrp.eco.stage']
        stages = self._get_type_stages()
        previous = stages.filtered(lambda s: s._stage_key() < self.stage_id._stage_key())
        return previous[-1:] if previous else self.env['mrp.eco.stage']

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        type_id = self.env.context.get('default_type_id')
        stage_domain = [('type_ids', 'in', type_id)] if type_id else []
        return stages.search(stage_domain, order='sequence, id')

    def _check_stage_can_advance(self):
        """ Leaving the current stage forward requires every mandatory approval
        to be granted and no approval to be rejected. """
        for eco in self:
            approvals = eco.approval_ids.filtered(lambda a: a.stage_id == eco.stage_id)
            rejected = approvals.filtered(lambda a: a.status == 'rejected')
            if rejected:
                raise UserError(_(
                    'Cannot move ECO %(eco)s forward: the stage "%(stage)s" was rejected by %(roles)s.\n'
                    'Ask the approvers to reconsider ("Request Re-approval") or send the ECO back '
                    'with "Revert to Previous Stage".',
                    eco=eco.name, stage=eco.stage_id.name, roles=', '.join(rejected.mapped('name'))))
            pending = approvals.filtered(lambda a: a.approval_type == 'mandatory' and a.status != 'approved')
            if pending:
                raise UserError(_(
                    'Cannot move to the next stage. Mandatory approvals for stage '
                    '"%(stage)s" are still pending: %(roles)s',
                    stage=eco.stage_id.name, roles=', '.join(pending.mapped('name'))))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('mrp.eco') or _('New')
            if not vals.get('stage_id'):
                type_id = vals.get('type_id')
                if type_id:
                    stage = self.env['mrp.eco.stage'].search([('type_ids', 'in', type_id)], order='sequence', limit=1)
                    if stage:
                        vals['stage_id'] = stage.id
        ecos = super(MrpEco, self).create(vals_list)
        ecos._create_approvals()
        ecos._sync_approval_activities()
        return ecos

    def write(self, vals):
        backward_ecos = self.env['mrp.eco']
        if vals.get('stage_id'):
            new_stage = self.env['mrp.eco.stage'].browse(vals['stage_id'])
            for eco in self:
                if not eco.stage_id or eco.stage_id == new_stage:
                    continue
                if new_stage._stage_key() < eco.stage_id._stage_key():
                    if eco.is_applied:
                        raise UserError(_(
                            'The changes of ECO %s have already been applied; it cannot be moved back.', eco.name))
                    backward_ecos |= eco
                else:
                    eco._check_stage_can_advance()

        res = super(MrpEco, self).write(vals)

        if 'stage_id' in vals:
            # Going back re-opens the decisions of the target stage and every later stage
            for eco in backward_ecos:
                to_reset = eco.approval_ids.filtered(
                    lambda a: a.stage_id._stage_key() >= eco.stage_id._stage_key() and a.status != 'none')
                to_reset.write({'status': 'none', 'user_id': False, 'approval_date': False})
            # Create approval records for the newly entered stage
            self._create_approvals()
            self._sync_approval_activities()
            for eco in self:
                if eco.stage_id.final_stage and not eco.date_done:
                    eco.date_done = fields.Datetime.now()
                # If the new stage has allow_apply_change, auto-apply
                if eco.stage_id.allow_apply_change and not eco.is_applied and eco.new_bom_id:
                    eco.action_apply_changes()

        return res

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """ ECO created from the email alias of an ECO type. """
        defaults = {
            'name': msg_dict.get('subject') or _('No Subject'),
            'note': msg_dict.get('body'),
            'user_id': False,
        }
        defaults.update(custom_values or {})
        return super().message_new(msg_dict, custom_values=defaults)

    def _create_approvals(self):
        for eco in self:
            if eco.stage_id and eco.stage_id.approval_template_ids:
                existing_templates = eco.approval_ids.mapped('approval_template_id')
                new_templates = eco.stage_id.approval_template_ids - existing_templates
                for template in new_templates:
                    self.env['mrp.eco.approval'].create({
                        'eco_id': eco.id,
                        'approval_template_id': template.id,
                    })

    def _sync_approval_activities(self):
        """ Keep one 'ECO Approval' to-do per approver who still has a pending
        decision on the current stage, and close the others. """
        for eco in self:
            pending_users = self.env['res.users']
            if eco.state != 'done':
                for approval in eco.approval_ids.filtered(lambda a: a.stage_id == eco.stage_id and a.status == 'none'):
                    pending_users |= approval.approval_template_id.user_ids
            activities = eco.activity_search([APPROVAL_ACTIVITY])
            for activity in activities.filtered(lambda act: act.user_id not in pending_users):
                if activity.user_id == self.env.user:
                    activity.action_feedback(feedback=_('Decision recorded'))
                else:
                    activity.unlink()
            for user in pending_users - activities.exists().user_id:
                eco.activity_schedule(
                    APPROVAL_ACTIVITY, user_id=user.id,
                    summary=_('Approve %(eco)s (%(stage)s)', eco=eco.name, stage=eco.stage_id.name))

    # ------------------------------------------------------------------
    # Revision
    # ------------------------------------------------------------------

    def action_start_revision(self):
        for eco in self:
            if not eco.bom_id:
                raise UserError(_('Please select a Bill of Materials before starting a revision.'))
            if eco.new_bom_id:
                raise UserError(_('A revision has already been started for this ECO.'))
            if eco.type in ('bom', 'routing'):
                new_version = eco.bom_id.version + 1 if eco.update_version else eco.bom_id.version
                eco.new_bom_id = eco.bom_id.copy({
                    'version': new_version,
                    'active': False,
                })
                eco.message_post(body=_(
                    'Revision started. A new draft BoM (V%s) has been created and is ready for editing.'
                ) % new_version)

    def action_apply_changes(self):
        for eco in self:
            if not eco.new_bom_id:
                raise UserError(_('Please click "Start Revision" first to create a draft BoM before applying changes.'))
            if eco.is_applied:
                raise UserError(_('Changes have already been applied to this ECO.'))
            if eco.type in ('bom', 'routing'):
                eco._compute_eco_changes()
                # Archive old BoM, activate the new revised BoM. PLM users may only edit
                # draft (archived) BoMs, so the switch of the live BoM is done as superuser.
                if eco.bom_id:
                    eco.bom_id.sudo().with_context(active_test=False).write({'active': False})
                eco.new_bom_id.sudo().with_context(active_test=False).write({'active': True})
                eco.write({'is_applied': True})
                eco.message_post(body=_(
                    'Changes applied successfully. The BoM has been updated to version V%s. '
                    'The previous version has been archived.'
                ) % eco.new_bom_id.version)

    def _compute_eco_changes(self):
        """ (Re)build the component and operation differences between the
        current BoM and its revision. """
        BomChange = self.env['mrp.eco.bom.change']
        RoutingChange = self.env['mrp.eco.routing.change']
        for eco in self:
            if eco.is_applied:
                continue
            eco.bom_change_ids.unlink()
            eco.routing_change_ids.unlink()
            if not eco.bom_id or not eco.new_bom_id:
                continue
            old_bom = eco.bom_id.with_context(active_test=False)
            new_bom = eco.new_bom_id.with_context(active_test=False)

            old_lines, new_lines = defaultdict(float), defaultdict(float)
            for line in old_bom.bom_line_ids:
                old_lines[line.product_id.id] += line.product_qty
            for line in new_bom.bom_line_ids:
                new_lines[line.product_id.id] += line.product_qty
            BomChange.create([
                dict(change, eco_id=eco.id, product_id=key, old_qty=old_qty, new_qty=new_qty)
                for key, old_qty, new_qty, change in self._diff_values(old_lines, new_lines)
            ])

            old_ops, new_ops = defaultdict(float), defaultdict(float)
            for operation in old_bom.operation_ids:
                old_ops[(operation.name, operation.workcenter_id.id)] += operation.time_cycle_manual
            for operation in new_bom.operation_ids:
                new_ops[(operation.name, operation.workcenter_id.id)] += operation.time_cycle_manual
            RoutingChange.create([
                dict(change, eco_id=eco.id, operation_name=key[0], workcenter_id=key[1],
                     old_duration=old_qty, new_duration=new_qty)
                for key, old_qty, new_qty, change in self._diff_values(old_ops, new_ops, presence=True)
            ])

    @api.model
    def _diff_values(self, old, new, presence=False):
        """ Yield (key, old, new, {'change_type'}) for each key whose value differs.
        With presence=True a key existing on one side only is an add/remove even if
        its value is 0 (an operation without duration still exists). """
        for key in set(old) | set(new):
            old_val, new_val = old.get(key, 0.0), new.get(key, 0.0)
            in_old = key in old if presence else old_val != 0
            in_new = key in new if presence else new_val != 0
            if in_new and not in_old:
                change_type = 'add'
            elif in_old and not in_new:
                change_type = 'remove'
            elif old_val != new_val:
                change_type = 'update'
            else:
                continue
            yield key, old_val, new_val, {'change_type': change_type}

    def action_review_changes(self):
        self.ensure_one()
        if not self.new_bom_id:
            raise UserError(_('Please start a revision first before reviewing changes.'))
        if not self.bom_id:
            raise UserError(_('No original Bill of Materials to compare against.'))
        self._compute_eco_changes()
        return {
            'name': _('ECO Changes Summary'),
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.eco.bom.change',
            'view_mode': 'list',
            'domain': [('eco_id', '=', self.id)],
            'target': 'current',
        }

    def action_refresh_changes(self):
        self._compute_eco_changes()

    def action_open_documents(self):
        self.ensure_one()
        return {
            'name': _('Documents'),
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'kanban,list,form',
            'domain': [('res_model', '=', 'mrp.eco'), ('res_id', '=', self.id)],
            'context': {'default_res_model': 'mrp.eco', 'default_res_id': self.id},
        }

    def action_open_new_bom(self):
        self.ensure_one()
        if self.new_bom_id:
            # Use active_test=False since draft revision BoM is archived
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'mrp.bom',
                'res_id': self.new_bom_id.id,
                'view_mode': 'form',
                'context': {'active_test': False},
            }

    def action_open_product(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'res_id': self.product_tmpl_id.id,
            'view_mode': 'form',
        }

    # ------------------------------------------------------------------
    # Approval workflow
    # ------------------------------------------------------------------

    def action_approve(self):
        for eco in self:
            eco._get_user_current_approvals().filtered(lambda a: a.status != 'approved').action_approve()

    def action_reject(self):
        for eco in self:
            eco._get_user_current_approvals().filtered(lambda a: a.status != 'rejected').action_reject()

    def _check_can_manage_workflow(self):
        is_manager = self.env.user.has_group('hudson_plm.group_plm_manager')
        for eco in self:
            if not is_manager and self.env.user != eco.user_id:
                raise UserError(_('Only the responsible of ECO %s or a PLM Administrator can do this.', eco.name))

    def action_request_reapproval(self):
        """ Reopen the rejected decisions of the current stage so the approvers
        can review the ECO again (e.g. after the revision was corrected). """
        self._check_can_manage_workflow()
        for eco in self:
            rejected = eco.approval_ids.filtered(lambda a: a.stage_id == eco.stage_id and a.status == 'rejected')
            if not rejected:
                raise UserError(_('There is no rejected approval on the current stage of %s.', eco.name))
            rejected.write({'status': 'none', 'user_id': False, 'approval_date': False})
            eco.message_post(body=_(
                'Re-approval requested by %(user)s for: %(roles)s',
                user=self.env.user.name, roles=', '.join(rejected.mapped('name'))))
        self._sync_approval_activities()

    def action_revert_stage(self):
        """ Send the ECO back to the previous stage of its type. """
        self._check_can_manage_workflow()
        for eco in self:
            previous = eco._get_previous_stage()
            if not previous:
                raise UserError(_('ECO %s is already in the first stage.', eco.name))
            current = eco.stage_id
            eco.stage_id = previous
            eco.message_post(body=_(
                'Reverted from "%(from)s" to "%(to)s" by %(user)s.',
                **{'from': current.name, 'to': previous.name, 'user': self.env.user.name}))
