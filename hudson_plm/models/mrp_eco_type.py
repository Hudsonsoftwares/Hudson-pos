# -*- coding: utf-8 -*-
import ast

from odoo import models, fields


class MrpEcoType(models.Model):
    _name = 'mrp.eco.type'
    _description = 'ECO Type'
    _inherit = ['mail.alias.mixin', 'mail.thread']
    _order = 'sequence, id'

    name = fields.Char('Name', required=True, translate=True)
    sequence = fields.Integer('Sequence', default=1)
    active = fields.Boolean('Active', default=True)
    color = fields.Integer('Color', default=1)

    eco_ids = fields.One2many('mrp.eco', 'type_id', string='ECOs')
    eco_count = fields.Integer('ECO Count', compute='_compute_eco_counts')
    eco_progress_count = fields.Integer('ECOs In Progress', compute='_compute_eco_counts')
    eco_conflict_count = fields.Integer('ECOs Blocked', compute='_compute_eco_counts')
    eco_approval_count = fields.Integer('ECOs To Approve', compute='_compute_eco_counts')
    eco_my_count = fields.Integer('My ECOs', compute='_compute_eco_counts')
    alias_id = fields.Many2one(help="Email address on which incoming emails create a new Engineering Change Order of this type.")

    def _compute_eco_counts(self):
        Eco = self.env['mrp.eco']
        domain = [('type_id', 'in', self.ids)]

        def count_by_type(extra_domain):
            groups = Eco._read_group(domain + extra_domain, ['type_id'], ['__count'])
            return {eco_type.id: count for eco_type, count in groups}

        total = count_by_type([])
        progress = count_by_type([('state', '=', 'progress')])
        conflict = count_by_type([('state', '=', 'conflict')])
        approval = count_by_type([('user_can_approve', '=', True)])
        mine = count_by_type([('user_id', '=', self.env.uid), ('state', '!=', 'done')])
        for eco_type in self:
            eco_type.eco_count = total.get(eco_type.id, 0)
            eco_type.eco_progress_count = progress.get(eco_type.id, 0)
            eco_type.eco_conflict_count = conflict.get(eco_type.id, 0)
            eco_type.eco_approval_count = approval.get(eco_type.id, 0)
            eco_type.eco_my_count = mine.get(eco_type.id, 0)

    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get('mrp.eco').id
        if self.id:
            values['alias_defaults'] = defaults = ast.literal_eval(self.alias_defaults or "{}")
            defaults['type_id'] = self.id
        return values

    def _get_eco_action(self, extra_context=None):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('hudson_plm.mrp_eco_action_main')
        context = {'search_default_type_id': self.id, 'default_type_id': self.id}
        context.update(extra_context or {})
        action['context'] = context
        action['display_name'] = self.name
        return action

    def action_open_ecos(self):
        return self._get_eco_action()

    def action_open_ecos_progress(self):
        return self._get_eco_action({'search_default_filter_progress': 1})

    def action_open_ecos_conflict(self):
        return self._get_eco_action({'search_default_filter_conflict': 1})

    def action_open_ecos_to_approve(self):
        return self._get_eco_action({'search_default_filter_to_approve': 1})

    def action_open_my_ecos(self):
        return self._get_eco_action({'search_default_filter_my': 1})
