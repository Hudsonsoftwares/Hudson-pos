from odoo import models, fields


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    type = fields.Selection(selection_add=[('grid', 'Grid')], ondelete={'grid': 'cascade'})

    def _get_view_info(self):
        res = super()._get_view_info()
        res['grid'] = {'icon': 'grid_view', 'multi_record': True}
        return res

    def _validate_tag_grid(self, node, name_manager, node_info):
        pass


class IrActionsActWindowView(models.Model):
    _inherit = 'ir.actions.act_window.view'

    view_mode = fields.Selection(selection_add=[('grid', 'Grid')], ondelete={'grid': 'cascade'})
