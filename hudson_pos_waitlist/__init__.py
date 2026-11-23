# -*- coding: utf-8 -*-
import importlib
from . import models
from . import controllers

importlib.reload(models)
importlib.reload(controllers)


def _post_init_hook(env):
    """Ensure existing POS configs receive waitlist tokens and URLs."""
    configs = env['pos.config'].search([('waitlist_token', '=', False)])
    for config in configs:
        config._ensure_waitlist_token()
