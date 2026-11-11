# Copyright 2024 Hudson Community
# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).

import io
import logging
import os
import shutil
import stat
import tempfile
import time
import uuid

from odoo import api, models
from odoo.addons.base.models.ir_attachment import DIRECTORY_MODE

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    """Extend ir.attachment to route new attachments to DMS via folder rules."""

    _inherit = "ir.attachment"

    @api.model
    def _file_write(self, fname: str, bin_value: io.IOBase) -> None:
        """Persist the data for the given fname with Windows permission & lock handling."""
        assert hasattr(bin_value, 'read') and hasattr(bin_value, 'seek'), f'expecting a seekable IO object, got {bin_value}'
        full_path = os.path.normpath(self._full_path(fname))
        try:
            # add fname to checklist, in case the transaction aborts
            self._mark_for_gc(fname)

            # check if file exists and prevent sha-1 collision
            try:
                with open(full_path, 'rb') as existing_file:
                    if self._same_content(bin_value, existing_file):
                        return
                    e = f"The attachment {fname} collides with an existing file."
                    raise RuntimeError(e)
            except (FileNotFoundError, PermissionError):
                pass

            upload_dir = self._full_path('upload')
            prefix = os.path.basename(fname) + '-'
            try:
                os.mkdir(upload_dir, DIRECTORY_MODE)
            except FileExistsError:
                pass
            tmp_path = os.path.join(upload_dir, prefix + uuid.uuid4().hex[:16])
            try:
                try:
                    # Fast hardlink, works for io.FileIO when it's on the same filesystem
                    if not (hasattr(bin_value, 'name') and isinstance(bin_value, (tempfile._TemporaryFileWrapper, io.IOBase))):
                        raise OSError("Cannot hardlink in _file_write")
                    os.link(bin_value.name, tmp_path)
                except OSError:
                    # Copy, works for all io.IOBase
                    with open(tmp_path, 'wb') as tmp_file:
                        shutil.copyfileobj(bin_value, tmp_file)
                        tmp_file.flush()

                # Ensure destination directory exists
                dest_dir = os.path.dirname(full_path)
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, DIRECTORY_MODE, exist_ok=True)

                # On Windows, if target exists, remove read-only attribute so replace can succeed
                if os.path.exists(full_path):
                    try:
                        os.chmod(full_path, stat.S_IWRITE | stat.S_IREAD)
                    except OSError:
                        pass

                # "commit" the file by moving it to its right place, with retry / copy fallback on Windows
                committed = False
                for attempt in range(5):
                    try:
                        os.replace(tmp_path, full_path)
                        tmp_path = None
                        committed = True
                        break
                    except (PermissionError, OSError):
                        if attempt == 4:
                            # Fallback: copyfile then remove tmp
                            try:
                                shutil.copyfile(tmp_path, full_path)
                                committed = True
                            finally:
                                try:
                                    if os.path.exists(tmp_path):
                                        os.chmod(tmp_path, stat.S_IWRITE)
                                        os.unlink(tmp_path)
                                except OSError:
                                    pass
                                tmp_path = None
                            break
                        time.sleep(0.05)

                if committed:
                    try:
                        if hasattr(os, 'fchmod'):
                            pass
                        else:
                            os.chmod(full_path, 0o444)
                    except OSError:
                        pass
            finally:
                # Clean-up the temporary file
                if tmp_path:
                    try:
                        if os.name == 'nt' and os.path.exists(tmp_path):
                            os.chmod(tmp_path, stat.S_IWRITE)
                        os.unlink(tmp_path)
                    except OSError:
                        _logger.debug("Failed to remove temporary file: %s", tmp_path, exc_info=True)

        except OSError as e:
            e.add_note(f"_file_write writing {full_path}")
            raise


    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Skip if we're already inside DMS file creation to avoid infinite loops
        if not self.env.context.get("dms_file") and not self.env.context.get(
            "dms_enterprise_routing"
        ):
            records.with_context(dms_enterprise_routing=True)._route_to_dms_folders()
        return records

    def write(self, vals):
        res = super().write(vals)
        # Re-route when attaching to a record (e.g., website forms, chatter)
        if (
            not self.env.context.get("dms_file")
            and not self.env.context.get("dms_enterprise_routing")
            and ("res_model" in vals or "res_id" in vals)
        ):
            self.with_context(dms_enterprise_routing=True)._route_to_dms_folders()
        return res

    @api.model
    def _dms_is_routable(self, attachment):
        """Same filter Odoo Documents applies before turning an attachment
        into a document: only real files attached to a business record.

        Excluded:
        * binary-field storage (``res_field`` set): avatars and their
          image_1920/1024/512/256/128 resizes, generated letter-avatar SVGs,
          signatures, report caches... These are field values, not documents.
        * unlinked or ``res_id = 0`` attachments (chatter uploads before the
          message is posted, wizard temp files).
        * DMS's own records, and anything created with ``no_document`` in
          context (Odoo's opt-out flag).
        """
        return bool(
            attachment.res_model
            and attachment.res_id
            and not attachment.res_field
            and attachment.res_model not in ("dms.file", "dms.directory")
            and not self.env.context.get("no_document")
        )

    def _route_to_dms_folders(self):
        """For each attachment, find a matching dms.folder.rule and route it."""
        FolderRule = self.env["dms.folder.rule"].sudo()
        for attachment in self:
            if not self._dms_is_routable(attachment):
                continue

            record = None
            if attachment.res_model in self.env:
                try:
                    record = self.env[attachment.res_model].sudo().browse(attachment.res_id)
                    if not record.exists():
                        record = None
                except Exception:
                    record = None

            rule = FolderRule.find_matching_rule(attachment.res_model, record=record)
            if rule:
                try:
                    rule.route_attachment(attachment)
                except Exception as e:
                    _logger.warning(
                        "DMS Enterprise: failed to route attachment %s (rule '%s'): %s",
                        attachment.id,
                        rule.name,
                        e,
                    )
