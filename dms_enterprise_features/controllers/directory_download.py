import io
import os
import zipfile
import base64
import datetime
from odoo import http, _
from odoo.http import request
from odoo.http.stream import content_disposition
from odoo.exceptions import AccessError

def sanitize_segment(name):
    """Sanitize path segments for cross-platform zip compatibility (especially Windows)."""
    invalid_chars = '<>:"/\\|?*'
    clean = "".join(c if c not in invalid_chars else "_" for c in (name or ""))
    return clean.strip(" .") or "unnamed"

def extract_file_raw_bytes(record):
    """
    Extracts the exact, uncorrupted raw bytes of a dms.file.
    Supports revisions, Odoo 20 BinaryValue / BinaryValueAttachment,
    attachments, byte streams, and base64 payloads without corrupting raw binary.
    """
    if not record:
        return b""

    val = False
    # 1. Prefer current revision if present and populated
    if hasattr(record, 'current_revision_id') and record.current_revision_id and record.current_revision_id.content:
        val = record.current_revision_id.content
    elif hasattr(record, 'content') and record.content:
        val = record.content

    # 2. Fallbacks to direct storage fields if content is not yet in cache
    if not val:
        if hasattr(record, 'content_file') and record.content_file:
            val = record.content_file
        elif hasattr(record, 'content_binary') and record.content_binary:
            val = record.content_binary
        elif hasattr(record, 'attachment_id') and record.attachment_id:
            val = record.attachment_id.raw

    if not val:
        return b""

    # 3. Handle Odoo 20 BinaryValue / BinaryValueAttachment / BinaryBytes
    if hasattr(val, 'content'):
        c = val.content
        if isinstance(c, (bytes, bytearray)):
            return bytes(c)
        val = c
    if hasattr(val, 'open'):
        try:
            return bytes(val)
        except Exception:
            pass

    # 4. Handle bytes / bytearray
    if isinstance(val, (bytes, bytearray)):
        raw = bytes(val)
        # Check known binary magic signatures
        magic_signatures = (
            b'%PDF',         # PDF
            b'\x89PNG',      # PNG
            b'\xff\xd8\xff', # JPEG
            b'GIF8',         # GIF
            b'PK\x03\x04',   # ZIP, DOCX, XLSX, PPTX, ODT, ODS
            b'\x1f\x8b',     # GZIP
            b'RIFF',         # WebP / WAV / AVI
            b'BM',           # BMP
            b'7z\xbc\xaf',   # 7-Zip
            b'Rar!\x1a\x07', # RAR
            b'\x00\x00\x01\x00', # ICO
            b'<!DOCTYPE',    # HTML/XML
            b'<html',
            b'<?xml',
            b'{\\rtf',        # RTF
        )
        if raw.startswith(magic_signatures):
            return raw

        # Known base64 prefixes for common formats
        known_b64_prefixes = (
            b'JVBERi', # %PDF
            b'iVBORw', # \x89PNG
            b'/9j/',   # \xff\xd8\xff
            b'UEsDB',  # PK\x03\x04
            b'R0lGOD', # GIF8
            b'H4sI',   # \x1f\x8b
        )
        if raw.startswith(known_b64_prefixes):
            try:
                decoded = base64.b64decode(raw)
                if decoded and len(decoded) > 0:
                    return decoded
            except Exception:
                pass

        # Strict base64 check for other file types stored as base64 ASCII bytes
        if len(raw) % 4 == 0 and all(c in b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\r\n ' for c in raw[:min(512, len(raw))]):
            try:
                decoded = base64.b64decode(raw, validate=True)
                if decoded and decoded.startswith(magic_signatures):
                    return decoded
            except Exception:
                pass

        return raw

    # 5. Handle base64 string
    if isinstance(val, str):
        try:
            return base64.b64decode(val.encode('ascii'))
        except Exception:
            return val.encode('utf-8')

    try:
        return bytes(val)
    except Exception:
        return b""

def get_clean_filename(file_record):
    """Ensure file name inside zip has the proper extension and no invalid filesystem chars."""
    fname = (
        (file_record.current_revision_id.file_name if hasattr(file_record, 'current_revision_id') and file_record.current_revision_id and file_record.current_revision_id.file_name else False)
        or file_record.name
        or "document"
    )
    ext = file_record.extension
    if ext and ext.strip():
        ext_clean = ext.strip().lstrip('.').lower()
        if not fname.lower().endswith(f".{ext_clean}"):
            fname = f"{fname}.{ext_clean}"
    return sanitize_segment(fname)


class DmsDirectoryDownloadController(http.Controller):

    @http.route('/dms/directory/<int:directory_id>/download_zip', type='http', auth='user')
    def download_directory_zip(self, directory_id, **kw):
        directory = request.env['dms.directory'].browse(directory_id)
        if not directory.exists():
            return request.not_found()

        is_admin = (
            request.env.user.has_group('dms.group_dms_manager')
            or request.env.user.has_group('base.group_system')
            or request.env.user.has_group('dms_enterprise_features.group_dms_document_controller')
        )

        # Check download permission on root directory
        if not directory.permission_download and not is_admin:
            raise AccessError(_("You do not have permission to download files from this directory."))

        # Find all permitted subdirectories (exclude trashed)
        subdirs = request.env['dms.directory'].search([
            ('id', 'child_of', directory.id),
            ('is_trashed', '=', False),
        ])
        if not is_admin:
            subdirs = subdirs.filtered(lambda d: d.permission_read or d.permission_download)

        # Find all non-trashed files in these directories
        files = request.env['dms.file'].search([
            ('directory_id', 'in', subdirs.ids),
            ('is_trashed', '=', False),
        ])
        if not is_admin:
            files = files.filtered(lambda f: f.permission_read or f.permission_download)

        # Build in-memory zip
        zip_buffer = io.BytesIO()
        used_names = set()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Add directory entries for empty subdirectories to preserve folder structure
            for d in subdirs:
                if d.id == directory.id:
                    continue
                rel_parts = []
                curr = d
                while curr and curr.id != directory.id:
                    rel_parts.insert(0, sanitize_segment(curr.name))
                    curr = curr.parent_id
                if rel_parts:
                    dir_entry = "/".join(rel_parts) + "/"
                    if dir_entry not in used_names:
                        zip_file.writestr(dir_entry, b"")
                        used_names.add(dir_entry)

            # 2. Add files with exact raw uncorrupted bytes
            for f in files:
                rel_path_parts = []
                curr_dir = f.directory_id
                while curr_dir and curr_dir.id != directory.id:
                    rel_path_parts.insert(0, sanitize_segment(curr_dir.name))
                    curr_dir = curr_dir.parent_id

                clean_fname = get_clean_filename(f)
                rel_path_parts.append(clean_fname)
                archive_name = "/".join(rel_path_parts)

                # Ensure unique archive name in zip
                if archive_name in used_names:
                    base_name, ext = os.path.splitext(archive_name)
                    counter = 1
                    while f"{base_name}_{counter}{ext}" in used_names:
                        counter += 1
                    archive_name = f"{base_name}_{counter}{ext}"
                used_names.add(archive_name)

                file_data = extract_file_raw_bytes(f)

                # Set accurate ZipInfo with file modification time
                zip_info = zipfile.ZipInfo(archive_name)
                dt = f.write_date or f.create_date
                if dt:
                    zip_info.date_time = (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
                else:
                    now = datetime.datetime.now()
                    zip_info.date_time = (now.year, now.month, now.day, now.hour, now.minute, now.second)
                zip_info.compress_type = zipfile.ZIP_DEFLATED
                zip_info.external_attr = 0o644 << 16

                zip_file.writestr(zip_info, file_data)

        zip_buffer.seek(0)
        zip_data = zip_buffer.read()
        clean_zip_name = f"{sanitize_segment(directory.name)}.zip"

        return request.make_response(
            zip_data,
            headers=[
                ('Content-Type', 'application/zip'),
                ('Content-Disposition', content_disposition(clean_zip_name)),
                ('Cache-Control', 'no-cache, no-store, must-revalidate, max-age=0'),
                ('Pragma', 'no-cache'),
                ('Expires', '0'),
            ]
        )
