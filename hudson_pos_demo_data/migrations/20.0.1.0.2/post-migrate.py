# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Remove legacy Kitchen Display demo records while preserving user-created displays."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    if 'pos.prep.display' not in env:
        return

    PrepDisplay = env['pos.prep.display'].sudo()
    KitchenOrder = env['pos.kitchen.order'].sudo().with_context(active_test=False)
    StageLog = env['pos.kitchen.order.stage.log'].sudo() if 'pos.kitchen.order.stage.log' in env else False
    IrModelData = env['ir.model.data'].sudo()

    demo_imds = IrModelData.search([
        ('module', '=', 'hudson_pos_demo_data'),
        ('model', '=', 'pos.prep.display'),
    ])
    if not demo_imds:
        return

    res_ids = [rid for rid in demo_imds.mapped('res_id') if rid]
    demo_displays = PrepDisplay.browse(res_ids).exists()

    if demo_displays:
        demo_stage_ids = demo_displays.mapped('stage_ids').ids
        order_domain = [('display_id', 'in', demo_displays.ids)]
        if demo_stage_ids:
            order_domain = ['|'] + order_domain + [('stage_id', 'in', demo_stage_ids)]
        demo_orders = KitchenOrder.search(order_domain)

        if StageLog:
            log_domain = [('prep_order_id', 'in', demo_orders.ids)] if demo_orders else []
            if demo_stage_ids:
                stage_log_leaf = ('stage_id', 'in', demo_stage_ids)
                log_domain = (['|'] + log_domain + [stage_log_leaf]) if log_domain else [stage_log_leaf]
            if log_domain:
                StageLog.search(log_domain).unlink()

        if demo_orders:
            demo_orders.unlink()
        demo_displays.unlink()
        _logger.info(
            "Hudson POS: Removed %d legacy Kitchen Display demo record(s).",
            len(demo_displays),
        )

    demo_imds.unlink()

    if not PrepDisplay.search([], limit=1):
        PrepDisplay.create({
            'name': 'Kitchen Display',
            'company_id': env.company.id,
        })



# Added in 20.0.1.0.23: never modify or delete records that existed before this upgrade
# (data the user may have changed); only new demo records and newly added fields are written.
_hudson_unguarded_migrate = migrate


def migrate(cr, version):
    from odoo import api as _api, SUPERUSER_ID as _SUPERUSER_ID
    from odoo.addons.hudson_pos_demo_data.models.demo_guard import protect_existing
    with protect_existing(_api.Environment(cr, _SUPERUSER_ID, {})):
        _hudson_unguarded_migrate(cr, version)
