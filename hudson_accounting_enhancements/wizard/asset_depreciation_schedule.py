from odoo import api, fields, models, _


class AssetDepreciationSchedule(models.TransientModel):
    _inherit = 'asset.depreciation.schedule'

    def check_report(self):
        self.ensure_one()
        return self.action_print()
