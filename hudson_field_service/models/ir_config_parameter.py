# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, models


class IrConfigParameter(models.Model):
    _inherit = 'ir.config_parameter'

    @api.model
    def get_param(self, key, default=False):
        """Backward compatibility for Odoo 20: fallback to get_str."""
        val = self.get_str(key, default=None)
        return default if val is None else val

    @api.model
    def set_param(self, key, value):
        """Backward compatibility for Odoo 20: fallback to set_str."""
        return self.set_str(key, str(value) if value not in (False, None) else '')
