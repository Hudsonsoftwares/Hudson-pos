# -*- coding: utf-8 -*-
import logging

# pyrefly: ignore [missing-import]
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """ Remove the orphan copies of the ticket "Action" menu entries (Share Ticket, Preview, ...).

    Older databases kept action records whose XML ID was lost: every update then created a new
    record for the XML ID, and the ticket form showed each entry twice. An action bound to the ticket
    model, without XML ID and with the same type and name as an action of this module, is such a copy. """
    env = api.Environment(cr, SUPERUSER_ID, {})
    bound = env['ir.actions.actions'].search([('binding_model_id.model', '=', 'helpdesk.management.ticket')])
    # XML IDs are stored on the concrete action models (ir.actions.act_window, ir.actions.server, ...)
    xmlids = {}
    for action_type in set(bound.mapped('type')):
        xmlids.update(env[action_type].browse(bound.filtered(lambda a: a.type == action_type).ids)._get_external_ids())
    managed = {(a.type, a.name) for a in bound
               if any(x.startswith('helpdesk_management_pro.') for x in xmlids.get(a.id, []))}
    orphans = bound.filtered(lambda a: not xmlids.get(a.id) and (a.type, a.name) in managed)
    for action in orphans:
        _logger.info("Removing the duplicated ticket action %s (%s, id %s)", action.name, action.type, action.id)
        env[action.type].browse(action.id).unlink()
