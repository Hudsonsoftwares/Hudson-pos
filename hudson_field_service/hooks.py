# ─────────────────────────────────────────────────────────────────────────────
#  hooks.py  —  Hudson Module Registry
#
#  Drop this file into your custom module root alongside module_info/.
#  Then wire it up in __manifest__.py and __init__.py (see README.md).
#
#  module_info/ can be placed ANYWHERE inside your module — the module name
#  is auto-detected by scanning upward for __manifest__.py.
# ─────────────────────────────────────────────────────────────────────────────

import logging

_logger = logging.getLogger(__name__)

# ─── IMPORT PATH ──────────────────────────────────────────────────────────────
#  Adjust this import to match where you placed module_info/ in your module:
#
#  Location of module_info/              Import path to use
#  ─────────────────────────────────────────────────────────────────────────────
#  your_module/module_info/              from .module_info.reporter import ...
#  your_module/models/module_info/       from .models.module_info.reporter import ...
#  your_module/utils/module_info/        from .utils.module_info.reporter import ...
#  your_module/a/b/module_info/          from .a.b.module_info.reporter import ...
#
#  The module name in emails is ALWAYS auto-detected correctly regardless of depth.
# ─────────────────────────────────────────────────────────────────────────────


def post_install_hook(env):
    """
    Called automatically by Odoo after the module is INSTALLED for the first time.
    Sends an email report to the configured RECEIVER_EMAIL.
    """
    try:
        from .module_info.reporter import send_installation_report  # ← adjust if nested
        send_installation_report(env, event='install')
    except Exception as exc:
        _logger.warning("[ModuleReporter] post_install_hook failed: %s", exc)


def post_upgrade_hook(env):
    """
    Called automatically by Odoo after the module is UPGRADED.
    Sends an email report to the configured RECEIVER_EMAIL.
    """
    try:
        from .module_info.reporter import send_installation_report  # ← adjust if nested
        send_installation_report(env, event='upgrade')
    except Exception as exc:
        _logger.warning("[ModuleReporter] post_upgrade_hook failed: %s", exc)
