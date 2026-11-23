# -*- coding: utf-8 -*-
from odoo import models

from .kitchen_label import is_kitchen_terms_model, is_kitchen_terms_xmlid


class IrActionsActions(models.Model):
    _inherit = 'ir.actions.actions'

    def _is_kitchen_terms_target_action(self, result):
        """
        True only for actions that belong to Manufacturing.
        Actions of every other application (Payroll, HR, Accounting, ...)
        are never altered.
        """
        result = result if isinstance(result, dict) else {}
        xml_id = result.get('xml_id') or self.get_external_id().get(self.id) or ''
        res_model = result.get('res_model') or getattr(self, 'res_model', False) or ''

        # The Kitchen Labels configuration screen itself must show the real
        # standard terms, otherwise users cannot see what they are mapping.
        if res_model == 'kitchen.label' or xml_id.startswith('hudson_kitchen_terms.'):
            return False
        if is_kitchen_terms_xmlid(xml_id):
            return True
        if res_model and res_model in self.env:
            return is_kitchen_terms_model(self.env[res_model])
        return False

    def _get_action_dict(self):
        result = super()._get_action_dict()
        company = self.env['kitchen.label']._get_kitchen_company()
        if not company.kitchen_mode or not self._is_kitchen_terms_target_action(result):
            return result
        return self.env['kitchen.label'].apply_terms_to_action_dict(result, company=company)
