# -*- coding: utf-8 -*-
import logging
from datetime import date

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.tools import BinaryBytes

_logger = logging.getLogger(__name__)

PAYSLIP_REPORT = 'hudson_payroll_base.action_report_payslip'
PAYROLL_FOLDER = 'Payroll'
# A payslip that keeps failing is retried by the scheduled job a few times only
MAX_ATTEMPTS = 5
BATCH_SIZE = 50


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    hds_dms_state = fields.Selection([
        ('none', 'Not Stored'),
        ('pending', 'Pending'),
        ('stored', 'Stored'),
        ('failed', 'Failed'),
    ], string="Documents", default='none', copy=False, readonly=True, index=True,
        help="Whether the PDF of this validated payslip is stored in the employee's Documents folder.")
    hds_dms_file_id = fields.Many2one('dms.file', string="Document", copy=False, readonly=True,
                                      ondelete='set null')
    hds_dms_error = fields.Text(string="Documents Error", copy=False, readonly=True)
    hds_dms_attempts = fields.Integer(copy=False, readonly=True)

    # ------------------------------------------------------------------
    # Payslip lifecycle: validated -> store, back to draft / cancelled -> Trash
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        slips = super().create(vals_list)
        slips.filtered(lambda slip: slip.state in ('done', 'paid'))._hds_dms_queue()
        return slips

    def write(self, vals):
        if 'state' not in vals:
            return super().write(vals)
        issued = self.filtered(lambda slip: slip.state in ('done', 'paid'))
        res = super().write(vals)
        if vals['state'] in ('done', 'paid'):
            # Newly validated (a paid payslip keeps the PDF of its validation)
            (self - issued)._hds_dms_queue()
        else:
            # Reset to draft / to verify, or cancelled: the PDF is not issued any more
            issued._hds_dms_remove()
        return res

    def unlink(self):
        files = self.mapped('hds_dms_file_id')
        res = super().unlink()
        self.env['hr.payslip']._hds_dms_trash(files)
        return res

    def _hds_dms_queue(self):
        """Mark the payslips of companies storing payslips in Documents for the background job."""
        slips = self.filtered(lambda slip: slip.company_id.hds_dms_store_payslips)
        if not slips:
            return
        slips.sudo().with_context(tracking_disable=True).write({
            'hds_dms_state': 'pending', 'hds_dms_error': False, 'hds_dms_attempts': 0,
        })
        cron = self.env.ref('hudson_payroll_dms.ir_cron_hds_dms_store_payslips', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    def _hds_dms_remove(self):
        files = self.mapped('hds_dms_file_id')
        self.sudo().with_context(tracking_disable=True).write({
            'hds_dms_state': 'none', 'hds_dms_error': False, 'hds_dms_attempts': 0,
        })
        self._hds_dms_trash(files)

    @api.model
    def _hds_dms_trash(self, files):
        """Move the payslip PDFs to the Documents Trash (recoverable, then emptied automatically).
        Never blocks the payslip operation: a locked file is left as it is and logged."""
        for dms_file in files.sudo().exists():
            if dms_file.is_trashed:
                continue
            try:
                with self.env.cr.savepoint():
                    dms_file.action_send_to_trash()
            except Exception as error:  # e.g. the file is locked by a user
                _logger.warning("Payroll Documents: payslip file %s (%s) not moved to the Trash: %s",
                                dms_file.id, dms_file.name, error)

    # ------------------------------------------------------------------
    # Background job
    # ------------------------------------------------------------------
    @api.model
    def _cron_hds_dms_store_payslips(self):
        domain = ['|', ('hds_dms_state', '=', 'pending'),
                  '&', ('hds_dms_state', '=', 'failed'), ('hds_dms_attempts', '<', MAX_ATTEMPTS)]
        slips = self.sudo().search(domain, limit=BATCH_SIZE, order='id')
        for slip in slips:
            slip._hds_dms_store()
        if len(slips) == BATCH_SIZE:
            self.env.ref('hudson_payroll_dms.ir_cron_hds_dms_store_payslips')._trigger()

    def action_hds_dms_store(self):
        """Store now (payslip button): same as the background job, for these payslips."""
        for slip in self.filtered(lambda slip: slip.state in ('done', 'paid')):
            slip.sudo()._hds_dms_store()

    def _hds_dms_store(self):
        """Generate the payslip PDF and store it in the employee's Documents folder."""
        self.ensure_one()
        slip = self.sudo().with_company(self.company_id).with_context(tracking_disable=True)
        if slip.state not in ('done', 'paid') or not slip.company_id.hds_dms_store_payslips:
            slip.write({'hds_dms_state': 'none', 'hds_dms_error': False})
            return
        try:
            with self.env.cr.savepoint():
                dms_file = slip._hds_dms_write_file()
            slip.write({'hds_dms_state': 'stored', 'hds_dms_file_id': dms_file.id,
                        'hds_dms_error': False, 'hds_dms_attempts': 0})
        except Exception as error:
            _logger.warning("Payroll Documents: payslip %s not stored: %s", slip.display_name, error)
            slip.write({'hds_dms_state': 'failed', 'hds_dms_error': str(error),
                        'hds_dms_attempts': slip.hds_dms_attempts + 1})

    def _hds_dms_write_file(self):
        """Create the payslip's document, or update the one already linked to it (also when it is in
        the Trash after a cancellation or a reset to draft). Created by the system, not by the user
        who validated, so that nobody personally owns the payslips."""
        self.ensure_one()
        folder = self._hds_dms_payroll_folder()
        pdf, _report_type = self.env['ir.actions.report'].sudo().with_context(hds_dms_render=True)._render_qweb_pdf(
            PAYSLIP_REPORT, res_ids=self.ids)
        File = self.env['dms.file'].with_user(SUPERUSER_ID).sudo().with_context(no_document=True, active_test=False)
        dms_file = File.browse(self.hds_dms_file_id.id).exists()
        name = self._hds_dms_file_name(folder, dms_file)
        vals = {
            'name': name,
            'directory_id': folder.id,
            'content': BinaryBytes(pdf, name),
            'company_id': folder.company_id.id or self.company_id.id,
        }
        tags = self._hds_dms_payslip_tags()
        if tags:
            vals['tag_ids'] = [(6, 0, tags.ids)]
        if dms_file:
            if dms_file.is_trashed:
                dms_file.action_restore()
            dms_file.write(vals)
        else:
            dms_file = File.create(vals)
        return dms_file

    # ------------------------------------------------------------------
    # Folders and names
    # ------------------------------------------------------------------
    def _hds_dms_employee_folder(self):
        """The employee's own Documents folder, set up by the Documents module when missing.
        This is the only place that depends on how Documents manages employee folders."""
        self.ensure_one()
        employee = self.employee_id.sudo()
        if not employee.dms_directory_id:
            employee._setup_dms_folder_and_permissions()
        if not employee.dms_directory_id:
            raise ValueError(_("The employee %s has no Documents folder.", employee.name))
        return employee.dms_directory_id

    def _hds_dms_payroll_folder(self):
        """Employee folder / Payroll / <tax year> (created when missing; they inherit the employee
        folder's access, so the employee sees their own payslips)."""
        folder = self._hds_dms_employee_folder()
        for name in (PAYROLL_FOLDER, self._hds_dms_tax_year_label()):
            folder = self._hds_dms_subfolder(folder, name)
        return folder

    @api.model
    def _hds_dms_subfolder(self, parent, name):
        Directory = self.env['dms.directory'].sudo()
        folder = Directory.search([('parent_id', '=', parent.id), ('name', '=', name),
                                   ('is_trashed', '=', False)], limit=1)
        if not folder:
            folder = Directory.with_user(SUPERUSER_ID).sudo().create({
                'name': name, 'parent_id': parent.id, 'storage_id': parent.storage_id.id,
            })
        return folder

    def _hds_dms_tax_year_label(self):
        """Tax year of the payslip period, e.g. '2026-27' (or '2026' for a calendar fiscal year)."""
        self.ensure_one()
        day = self.date_to or self.date_from or fields.Date.context_today(self)
        start = end = None
        if 'tds.financial.year' in self.env:
            # Indian payroll: the Tax Year covering the period, else its April to March rule
            tax_year = self.env['tds.financial.year'].sudo().search(
                [('start_date', '<=', day), ('end_date', '>=', day)], limit=1)
            if tax_year:
                start, end = tax_year.start_date, tax_year.end_date
            else:
                start = date(day.year if day.month >= 4 else day.year - 1, 4, 1)
                end = date(start.year + 1, 3, 31)
        elif hasattr(self.company_id, 'compute_fiscalyear_dates'):
            dates = self.company_id.compute_fiscalyear_dates(day)
            start, end = dates['date_from'], dates['date_to']
        else:
            start, end = date(day.year, 1, 1), date(day.year, 12, 31)
        return str(start.year) if start.year == end.year else f"{start.year}-{str(end.year)[-2:]}"

    def _hds_dms_file_name(self, folder, dms_file):
        """'Arun Kumar - October 2026.pdf'; a second payslip of the same month (split period or
        off-cycle) gets its number added so the names stay unique in the folder."""
        self.ensure_one()
        day = self.date_to or self.date_from
        employee = (self.employee_id.name or '').replace('/', '-').strip()
        base = f"{employee} - {day.strftime('%B %Y')}" if day else employee
        taken = self.env['dms.file'].sudo().with_context(active_test=False).search([
            ('directory_id', '=', folder.id), ('id', '!=', dms_file.id),
        ]).mapped('name')
        name = f"{base}.pdf"
        if name in taken:
            name = f"{base} - {(self.number or str(self.id)).replace('/', '-')}.pdf"
        return name

    def _hds_dms_payslip_tags(self):
        """Tags of the Documents setting 'Default tags applied to payslip documents'."""
        param = self.env['ir.config_parameter'].sudo()
        key = 'dms_enterprise.hr_payslip_tag_ids'
        value = param.get_param(f"{key}_{self.company_id.id}") or param.get_param(key, '') or ''
        ids = [int(tag_id) for tag_id in value.split(',') if tag_id.strip().isdigit()]
        return self.env['dms.tag'].sudo().browse(ids).exists()

    # ------------------------------------------------------------------
    # Payslip button
    # ------------------------------------------------------------------
    def action_hds_dms_open_document(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Payslip Document"),
            'res_model': 'dms.file',
            'res_id': self.hds_dms_file_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }
