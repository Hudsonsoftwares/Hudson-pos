# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, SUPERUSER_ID
from odoo.addons.hudson_pos_demo_data.models.demo_data_loader import _load_product_images


def migrate(cr, version):
    """Replace placeholder outline icons and reused photos with dedicated product images."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    _load_product_images(env, replace_placeholders=True)

