# -*- coding: utf-8 -*-
import json

from odoo import http
from odoo.http import request
from odoo.http.stream import content_disposition


class DynamicReportController(http.Controller):

    @http.route(['/hudson_dynamic_reports/export_xlsx', '/hudson_accounting_enhancements/export_xlsx'], type='http', auth='user', methods=['POST'], csrf=False)
    def export_xlsx(self, **post):
        try:
            report_data = json.loads(post.get('data') or '{}')
        except ValueError:
            report_data = {}
        if not isinstance(report_data, dict):
            report_data = {}

        snapshot = request.env['hudson.report.snapshot']
        title = report_data.get('title') or 'Report'
        content = snapshot.render_xlsx(report_data)
        return request.make_response(
            content,
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', content_disposition(snapshot._get_filename(title, 'xlsx'))),
            ]
        )

    @http.route('/hudson_accounting_enhancements/export_pdf', type='http', auth='user', methods=['POST'], csrf=False)
    def export_pdf(self, **post):
        """ PDF of the whole report shown in the dynamic report screen (every
        line, folded or not), for reports without a wizard PDF (Aged
        Receivable / Payable...). Same layout as "Copy to Documents". """
        try:
            report_data = json.loads(post.get('data') or '{}')
        except ValueError:
            report_data = {}
        if not isinstance(report_data, dict):
            report_data = {}

        snapshot = request.env['hudson.report.snapshot']
        title = report_data.get('title') or 'Report'
        content = snapshot.render_pdf(report_data)
        return request.make_response(
            content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Length', str(len(content))),
                ('Content-Disposition', content_disposition(snapshot._get_filename(title, 'pdf'))),
            ]
        )
