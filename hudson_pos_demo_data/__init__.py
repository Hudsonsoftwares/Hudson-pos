# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from . import models
from .models.demo_data_loader import load_pos_demo_data, clear_pos_demo_data


def _post_init_hook(env):
    """Load Restaurant & Cafe demo data when hudson_pos_demo_data is manually activated."""
    load_pos_demo_data(env)


def _uninstall_hook(env):
    """Clean up demo data records when hudson_pos_demo_data is uninstalled."""
    clear_pos_demo_data(env)
