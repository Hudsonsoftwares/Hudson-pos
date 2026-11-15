from odoo import _, models
from odoo.exceptions import UserError


class DmsFile(models.Model):
    _inherit = "dms.file"

    def action_setup_signatures(self):
        """Request a signature on a document: opens the Sign editor on a template
        made from this document. Signed versions are saved back to the document."""
        if len(self) != 1:
            raise UserError(_("Please select a single PDF document to request a signature."))
        record = self
        if record.is_locked and not record.is_lock_editor and not self.env.user.has_group('dms.group_dms_manager') and not self.env.su:
            raise UserError(_("Cannot setup signatures because '%s' is locked by %s.") % (record.name, record.locked_by.name or 'another user'))
        if record.mimetype and record.mimetype != 'application/pdf' and not record.name.lower().endswith('.pdf'):
            raise UserError(_("Electronic signature is only supported for PDF documents. '%s' is not a PDF.") % record.name)

        if not record.current_revision_id and record.content:
            record.current_revision_id = self.env['dms.file.revision'].create({
                'file_id': record.id,
                'version': '1.0',
                'content': record.content,
                'file_name': record.name,
                'comments': 'Initial revision auto-created for signature setup.',
            })
        if not record.current_revision_id.content:
            raise UserError(_("Please upload a PDF document before setting up signatures."))

        template = self.env['hudson.sign.template']._get_or_create_for_dms_file(record)
        return template.action_open_builder()
