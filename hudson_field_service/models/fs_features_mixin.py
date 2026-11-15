# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

# Feature flag -> default, as stored in ir.config_parameter by the settings
# (Planning > Configuration > Settings).
FS_FEATURES = {
    'fs_worksheets': True,
    'fs_customer_signature': True,
    'fs_billing': True,
    'fs_products': True,
    'fs_hide_prices': False,
    'fs_geolocation': True,
    'fs_equipment': True,
    'fs_maintenance_contracts': False,
    'fs_travel_fees': False,
}


class FsFeaturesMixin(models.AbstractModel):
    """Expose the field service settings to views and code of jobs and shifts."""
    _name = 'fs.features.mixin'
    _description = 'Field Service Features'

    fs_worksheets_enabled = fields.Boolean(compute='_compute_fs_features')
    fs_customer_report_enabled = fields.Boolean(compute='_compute_fs_features')
    fs_billing_enabled = fields.Boolean(compute='_compute_fs_features')
    fs_products_enabled = fields.Boolean(compute='_compute_fs_features')
    fs_hide_prices_enabled = fields.Boolean(compute='_compute_fs_features')
    fs_geolocation_enabled = fields.Boolean(compute='_compute_fs_features')
    fs_equipment_enabled = fields.Boolean(compute='_compute_fs_features')
    fs_maintenance_enabled = fields.Boolean(compute='_compute_fs_features')
    fs_travel_fees_enabled = fields.Boolean(compute='_compute_fs_features')

    @api.model
    def _fs_feature(self, name):
        return self.env['ir.config_parameter'].sudo().get_bool(f'hudson_field_service.{name}', FS_FEATURES[name])

    def _compute_fs_features(self):
        values = {
            'fs_worksheets_enabled': self._fs_feature('fs_worksheets'),
            'fs_customer_report_enabled': self._fs_feature('fs_customer_signature'),
            'fs_billing_enabled': self._fs_feature('fs_billing'),
            'fs_products_enabled': self._fs_feature('fs_products'),
            'fs_hide_prices_enabled': self._fs_feature('fs_hide_prices'),
            'fs_geolocation_enabled': self._fs_feature('fs_geolocation'),
            'fs_equipment_enabled': self._fs_feature('fs_equipment'),
            'fs_maintenance_enabled': self._fs_feature('fs_equipment') and self._fs_feature('fs_maintenance_contracts'),
            'fs_travel_fees_enabled': self._fs_feature('fs_billing') and self._fs_feature('fs_travel_fees'),
        }
        for record in self:
            record.update(values)
