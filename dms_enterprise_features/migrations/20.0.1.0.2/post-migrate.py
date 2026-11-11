import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _remove_binary_field_dms_files(cr)
    # Access-group members get the DMS User group (needed to upload into
    # folders their group may upload to), like individually granted users.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["dms.access.group"].search([])._dms_ensure_members_are_dms_users()


def _remove_binary_field_dms_files(cr):
    """Folder rules used to route binary-field storage attachments (e.g. the
    hr.employee avatar fields image_1920/1024/512/256/128) into DMS as files.

    Remove those DMS files but keep the underlying ir.attachment: it is the
    actual field value (deleting it would wipe the employee's photo).
    """
    cr.execute(
        """
        SELECT f.id
          FROM dms_file f
          JOIN ir_attachment a ON a.id = f.attachment_id
         WHERE a.res_field IS NOT NULL
        """
    )
    file_ids = [row[0] for row in cr.fetchall()]
    if not file_ids:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    files = env["dms.file"].with_context(active_test=False).browse(file_ids)
    # Bypass the soft-delete (trash) step and the lock check, and detach the
    # attachment so dms.file.unlink() does not delete it.
    files.write({"locked_by": False, "is_trashed": True, "active": False})
    cr.execute(
        "UPDATE dms_file SET attachment_id = NULL WHERE id = ANY(%s)", (file_ids,)
    )
    files.invalidate_recordset()
    files.with_context(dms_file=True).unlink()
    _logger.info(
        "Removed %s DMS files that were copies of binary-field attachments (avatars)",
        len(file_ids),
    )
