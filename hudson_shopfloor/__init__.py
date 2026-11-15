# -*- coding: utf-8 -*-
from . import models


def uninstall_hook(env):
    # Give the Manufacturing app back its default landing page
    menu = env.ref('mrp.menu_mrp_root', raise_if_not_found=False)
    if menu:
        menu.action = False
