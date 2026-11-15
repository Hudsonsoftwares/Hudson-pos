# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, _

FS_SCHEDULE_VALID_ATTRIBUTES = {
    '__validate__',     # ir.ui.view implementation detail
    'class',
    'js_class',
    'string',
    'create',
    'edit',
    'delete',
    'date_start',
    'date_stop',
    'default_group_by',
    'default_scale',
}

FS_MAP_VALID_ATTRIBUTES = {
    '__validate__',
    'class',
    'js_class',
    'string',
    'create',
    'default_group_by',
    'limit',
}


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    type = fields.Selection(selection_add=[('fs_schedule', "Schedule"), ('fs_map', "Map")])

    def _validate_tag_fs_schedule(self, node, name_manager, node_info):
        if not node_info['validate']:
            return
        remaining = set(node.attrib) - FS_SCHEDULE_VALID_ATTRIBUTES
        if remaining:
            self._raise_view_error(_(
                "Invalid attributes (%(invalid)s) in schedule view. Attributes must be in (%(valid)s)",
                invalid=remaining, valid=FS_SCHEDULE_VALID_ATTRIBUTES,
            ), node)

    def _validate_tag_fs_map(self, node, name_manager, node_info):
        if not node_info['validate']:
            return
        remaining = set(node.attrib) - FS_MAP_VALID_ATTRIBUTES
        if remaining:
            self._raise_view_error(_(
                "Invalid attributes (%(invalid)s) in map view. Attributes must be in (%(valid)s)",
                invalid=remaining, valid=FS_MAP_VALID_ATTRIBUTES,
            ), node)

    def _get_view_info(self):
        return {
            'fs_schedule': {'icon': 'view_timeline'},
            'fs_map': {'icon': 'location_on'},
        } | super()._get_view_info()


class IrActionsActWindowView(models.Model):
    _inherit = 'ir.actions.act_window.view'

    view_mode = fields.Selection(
        selection_add=[('fs_schedule', "Schedule"), ('fs_map', "Map")],
        ondelete={'fs_schedule': 'cascade', 'fs_map': 'cascade'},
    )
