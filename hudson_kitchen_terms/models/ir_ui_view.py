# -*- coding: utf-8 -*-
from odoo import api, models

from .kitchen_label import is_kitchen_terms_model


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def _is_kitchen_terms_target_model(self):
        """
        Kitchen terminology is applied only to views of models created by
        Manufacturing. Views of shared models (products, stock moves...) and of
        other applications (Payroll, HR, Accounting, Settings, ...) are never
        altered: the web client caches get_views per model (ignoring the action
        context), so renaming a shared model would leak into other apps.
        """
        return is_kitchen_terms_model(self)

    @api.model
    def get_views(self, views, options=None):
        result = super().get_views(views, options=options)
        company = self.env['kitchen.label']._get_kitchen_company()
        if not company.kitchen_mode or not self._is_kitchen_terms_target_model():
            return result
        return self.env['kitchen.label'].apply_terms_to_views_result(result, company=company)
