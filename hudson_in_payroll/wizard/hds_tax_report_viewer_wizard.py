# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class HdsTaxReportViewerWizard(models.TransientModel):
    """
    Interactive Online Viewer Modal for Statutory Tax Calculation Report.
    Allows HR and employees to preview the complete formatted tax computation
    directly inside the payslip UI before optionally downloading or printing.
    """
    _name = 'hds.tax.report.viewer.wizard'
    _description = 'Tax Calculation Report Online Viewer'

    payslip_id = fields.Many2one(
        'hr.payslip',
        string="Payslip",
        readonly=True
    )
    declaration_id = fields.Many2one(
        'tds.employee.declaration',
        string="Tax Declaration",
        readonly=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        readonly=True
    )
    pdf_file = fields.Binary(
        string="Report Document",
        readonly=True
    )
    pdf_filename = fields.Char(
        string="File Name",
        readonly=True
    )

    def action_download_pdf(self):
        """Triggers direct PDF download for the current report."""
        self.ensure_one()
        if self.payslip_id:
            return self.env.ref('hudson_in_payroll.action_report_statutory_tax_payslip').report_action(self.payslip_id)
        if self.declaration_id:
            return self.env.ref('hudson_in_payroll.action_report_statutory_tax_declaration').report_action(self.declaration_id)
        raise UserError(_("No source record found for downloading the report."))

    def action_print_report(self):
        """Triggers browser print preview / report download."""
        return self.action_download_pdf()
