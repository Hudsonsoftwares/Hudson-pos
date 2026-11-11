# -*- coding: utf-8 -*-
import logging

from lxml import etree

# pyrefly: ignore [missing-import]
from odoo.modules.module import Manifest
# pyrefly: ignore [missing-import]
from odoo.tools.misc import file_open

_logger = logging.getLogger(__name__)

BRIDGE_PREFIX = 'helpdesk_management_pro_'
XMLID_TAGS = ('record', 'template', 'menuitem')


def _bridge_xmlids(manifest):
    """ Local XML IDs (without module prefix) defined by the data files of a bridge module. """
    names = set()
    for path in manifest.get('data', []):
        if not path.endswith('.xml'):
            continue
        try:
            with file_open(f'{manifest.name}/{path}', 'rb') as fp:
                tree = etree.parse(fp)
        except Exception:  # noqa: BLE001
            _logger.warning("Could not parse %s/%s", manifest.name, path, exc_info=True)
            continue
        for node in tree.iter(*XMLID_TAGS):
            xmlid = node.get('id')
            if xmlid and '.' not in xmlid:
                names.add(xmlid)
    return names


def migrate(cr, version):
    """ The integrations with Live Chat, CRM, Project, Forum, eLearning, Sales and Knowledge moved
    from Helpdesk Pro to separate bridge modules.

    Records they define (views, chatbot data, menus, ...) still belong to Helpdesk Pro in the
    database. Hand them over to the bridge now defining them, before Helpdesk Pro is updated:
    - Helpdesk Pro's views are validated without them (e.g. the Live Chat view using
      `origin_channel_id`, a field now added by the Live Chat bridge),
    - they are not deleted as obsolete at the end of the update, so existing data is kept and
      updated in place when the bridge gets installed (see the post-migration). """
    for manifest in Manifest.all_addon_manifests():
        if not manifest.name.startswith(BRIDGE_PREFIX):
            continue
        names = _bridge_xmlids(manifest)
        if not names:
            continue
        cr.execute("""
            UPDATE ir_model_data
               SET module = %s
             WHERE module = 'helpdesk_management_pro'
               AND name IN %s
               AND NOT EXISTS (SELECT 1 FROM ir_model_data d2 WHERE d2.module = %s AND d2.name = ir_model_data.name)
         RETURNING model, name
        """, [manifest.name, tuple(names), manifest.name])
        moved = cr.fetchall()
        if moved:
            _logger.info("Moved %d records from helpdesk_management_pro to %s: %s",
                         len(moved), manifest.name, sorted(name for _model, name in moved))
