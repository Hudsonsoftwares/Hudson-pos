# -*- coding: utf-8 -*-
from odoo import models
from odoo.http import request


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _build_wkhtmltopdf_args(self, paperformat_id, landscape, specific_paperformat_args=None,
                                set_viewport_size=False):
        """Payslip PDFs rendered by the background job have no browser session: wkhtmltopdf then
        cannot load the report stylesheets and company header from a server hosting several
        databases. Name the database in a header (supported by Odoo, stateless) so the stored PDF
        looks exactly like the printed one. Only for the payroll documents job; with a session
        (Print) Odoo passes its session cookie instead."""
        args = super()._build_wkhtmltopdf_args(paperformat_id, landscape, specific_paperformat_args,
                                               set_viewport_size)
        if self.env.context.get('hds_dms_render') and not (request and request.db):
            args += ['--custom-header', 'X-Odoo-Database', self.env.cr.dbname, '--custom-header-propagation']
        return args
