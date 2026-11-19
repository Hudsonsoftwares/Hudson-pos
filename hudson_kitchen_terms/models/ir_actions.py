# -*- coding: utf-8 -*-
from odoo import models


class IrActionsActions(models.Model):
    _inherit = 'ir.actions.actions'

    def _get_action_dict(self):
        result = super()._get_action_dict()
        if not self.env.company.kitchen_mode:
            return result
        return self.env['kitchen.label'].apply_terms_to_action_dict(result)
