# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from . import models
from .models.demo_data_loader import load_pos_demo_data, clear_pos_demo_data
from .models.demo_autoloader import reset_state


def _post_init_hook(env):
    """Schedule the demo data load.

    The module depends only on ``base``, so when it is installed together with other modules
    (new database, or as an auto_install module) the registry is still partial at this point.
    Resetting the auto-load state makes ``hudson.pos.demo.autoloader._register_hook`` load the
    demo data of every installed app once all modules are loaded; apps installed later are
    picked up automatically by the same hook.
    """
    reset_state(env)


def _uninstall_hook(env):
    """Clean up demo data records when hudson_pos_demo_data is uninstalled."""
    clear_pos_demo_data(env)
    reset_state(env)
