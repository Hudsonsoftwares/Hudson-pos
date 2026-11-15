# -*- coding: utf-8 -*-
from odoo import models, fields

class MrpEcoStage(models.Model):
    _name = 'mrp.eco.stage'
    _description = 'ECO Stage'
    _order = 'sequence, id'

    name = fields.Char('Name', required=True, translate=True)
    sequence = fields.Integer('Sequence', default=10)
    folded = fields.Boolean('Folded in kanban view', default=False)
    allow_apply_change = fields.Boolean('Allow to apply changes', default=False, help="Allow to apply changes from this stage.")
    final_stage = fields.Boolean('Final Stage', default=False, help="Folded in kanban view and implies no more changes can be done.")
    type_ids = fields.Many2many('mrp.eco.type', string='Types', required=True)
    approval_template_ids = fields.One2many('mrp.eco.approval.template', 'stage_id', string='Approvals')

    def _stage_key(self):
        """ Position of the stage in the workflow, used to tell forward from backward moves. """
        self.ensure_one()
        return (self.sequence, self.id)


class MrpEcoApprovalTemplate(models.Model):
    _name = 'mrp.eco.approval.template'
    _description = 'ECO Approval Template'

    stage_id = fields.Many2one('mrp.eco.stage', string='Stage', required=True, ondelete='cascade')
    name = fields.Char('Role', required=True)
    user_ids = fields.Many2many('res.users', string='Users', required=True)
    approval_type = fields.Selection([
        ('optional', 'Optional'),
        ('mandatory', 'Mandatory')
    ], string='Approval Type', required=True, default='mandatory')
