# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Sync product.group_product_pricelist when any POS config uses pricelists."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    pos_configs = env['pos.config'].sudo().search([('use_pricelist', '=', True)])
    if pos_configs:
        pos_configs._ensure_pricelist_group()
        _logger.info(
            "hudson_pos_booking: Synced pricelist group for %d POS config(s).",
            len(pos_configs),
        )

