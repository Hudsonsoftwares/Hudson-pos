import logging

from odoo import api, SUPERUSER_ID

from odoo.addons.dms_enterprise_features.models.dms_signature import _extract_pdf_bytes

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """The signed copy attached to the "Signature Completed" email was stored empty:
    refill it from the signed document."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    attachments = env['ir.attachment'].search([
        ('res_model', '=', 'dms.file'),
        ('name', '=like', 'signed_%'),
        ('mimetype', '=', 'application/pdf'),
        ('file_size', '=', 0),
    ])
    repaired = 0
    for attachment in attachments:
        dms_file = env['dms.file'].browse(attachment.res_id).exists()
        raw = dms_file and _extract_pdf_bytes(dms_file.current_revision_id.content)
        if raw:
            attachment.raw = raw
            repaired += 1
    _logger.info("Refilled %s empty signed document attachments", repaired)
