import json
import logging

from odoo.tools.misc import file_open

_logger = logging.getLogger(__name__)

TEMPLATE_FILE = 'Quality/data/files/quality_control_spreadsheet.json'


def _is_legacy_template_copy(content):
    """Unedited copy of the pre-20 default template.

    That template was stored as spreadsheet format "version": 1 while its gauge
    charts used a newer layout ("dataSets"); the Odoo 20 spreadsheet engine
    crashes when importing it. A copy still at version 1 was never saved by the
    spreadsheet editor (every save re-exports the current version), so it only
    holds the template's default values and can be replaced safely.
    """
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return False
    if not isinstance(data, dict) or data.get('version') != 1:
        return False
    return any(
        isinstance(figure.get('data'), dict)
        and figure['data'].get('type') == 'gauge'
        and 'dataSets' in figure['data']
        for sheet in data.get('sheets') or []
        for figure in sheet.get('figures') or []
    )


def migrate(cr, version):
    with file_open(TEMPLATE_FILE, 'rb') as f:
        new_template = f.read().decode('utf-8')
    cr.execute("""
        SELECT id, spreadsheet_content
          FROM quality_check
         WHERE spreadsheet_content LIKE '%%"gauge"%%'
    """)
    ids = [check_id for check_id, content in cr.fetchall() if _is_legacy_template_copy(content)]
    if ids:
        cr.execute(
            "UPDATE quality_check SET spreadsheet_content = %s WHERE id IN %s",
            (new_template, tuple(ids)),
        )
    _logger.info("Quality: refreshed %s unedited spreadsheet check(s) to the Odoo 20 template", len(ids))
