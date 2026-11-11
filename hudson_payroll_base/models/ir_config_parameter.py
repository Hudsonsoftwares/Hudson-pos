# -*- coding: utf-8 -*-

# pyrefly: ignore [missing-import]
from odoo import api, models



class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    @api.model
    def get_param(self, key, default=False):
        """Odoo 20 compatibility: fallback for removed get_param method."""
        if hasattr(self, 'get_str'):
            val = self.get_str(key, default=None)
            return val if val is not None else default
        return default

    @api.model
    def set_param(self, key, value):
        """Odoo 20 compatibility: fallback for removed set_param method."""
        if hasattr(self, 'set_str'):
            return self.set_str(key, str(value) if value is not False else '')
        return False
