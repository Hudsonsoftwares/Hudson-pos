# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """ Install the Helpdesk Pro bridge modules whose connected app (Live Chat, CRM, Project,
    Forum, eLearning, Sales, Knowledge) is already installed. The module loader picks up the
    modules marked 'to install' here and installs them in the same upgrade. """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ir.module.module']._helpdesk_install_pending_bridges()
