# -*- coding: utf-8 -*-
import logging

# pyrefly: ignore [missing-import]
from odoo import api, models
# pyrefly: ignore [missing-import]
from odoo.modules.module import Manifest

_logger = logging.getLogger(__name__)

BRIDGE_PREFIX = 'helpdesk_management_pro_'
INSTALL_STATES = frozenset(('installed', 'to install', 'to upgrade'))


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    @api.model
    def _helpdesk_register_bridges(self):
        """ Make sure every Helpdesk Pro bridge module found in the addons path is known by the
        database, so its auto-install can trigger without a manual "Update Apps List". """
        on_disk = {m.name for m in Manifest.all_addon_manifests() if m.name.startswith(BRIDGE_PREFIX)}
        if not on_disk:
            return
        known = set(self.search([('name', 'in', list(on_disk))]).mapped('name'))
        if on_disk - known:
            _logger.info("Registering Helpdesk Pro bridge modules: %s", sorted(on_disk - known))
            self.update_list()

    @api.model
    def _helpdesk_pending_bridges(self):
        """ Uninstalled auto-install Helpdesk Pro bridges whose dependencies are all installed
        (or about to be). Odoo only auto-installs a module when one of its dependencies is being
        installed at that very moment: this catches up the bridges whose dependencies were
        installed earlier (e.g. Live Chat installed before Helpdesk Pro, or before the bridge
        module was added to the addons path). """
        bridges = self.search([
            ('name', '=like', BRIDGE_PREFIX.replace('_', r'\_') + '%'),
            ('state', '=', 'uninstalled'),
            ('auto_install', '=', True),
        ])
        return bridges.filtered(
            lambda m: m.dependencies_id and all(dep.state in INSTALL_STATES for dep in m.dependencies_id)
        )

    @api.model
    def _helpdesk_install_pending_bridges(self):
        """ Mark the pending bridges 'to install'; the module loader installs them in the same run. """
        pending = self._helpdesk_pending_bridges()
        if pending:
            _logger.info("Auto-installing Helpdesk Pro bridge modules: %s", pending.mapped('name'))
            pending.button_install()
        return pending

    def button_install(self):
        self._helpdesk_register_bridges()
        res = super().button_install()
        # dependencies of a bridge may have been installed before: install the bridge now too
        if self._helpdesk_pending_bridges():
            self._helpdesk_install_pending_bridges()
        return res
