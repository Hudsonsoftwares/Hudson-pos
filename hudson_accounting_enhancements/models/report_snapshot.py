import io
import re

from markupsafe import Markup

from odoo import api, models, _
from odoo.exceptions import UserError
from odoo.tools.misc import formatLang


class HudsonReportSnapshot(models.AbstractModel):
    """ Renders the report currently displayed in the dynamic report screen
    (title, columns and visible lines sent by the client) as PDF, XLSX or HTML.

    Used by the XLSX download and by the Documents / Knowledge bridge modules,
    so every export of a report looks the same and shows the same figures. """
    _name = 'hudson.report.snapshot'
    _description = 'Dynamic Report Snapshot'

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    @api.model
    def _get_rows(self, report_data):
        """ Return (columns, rows) where every row carries its kind and
        already formatted cell texts. Nothing here trusts the client data:
        values are only read and converted to text. """
        columns = [c for c in (report_data.get('columns') or []) if isinstance(c, dict)]
        rows = []
        for line in report_data.get('lines') or []:
            if not isinstance(line, dict):
                continue
            try:
                level = max(int(line.get('level') or 1), 1)
            except (TypeError, ValueError):
                level = 1
            if line.get('is_summary_banner') or line.get('is_summary_total'):
                kind = 'total'
            elif level == 1:
                kind = 'section'
            elif level == 2:
                kind = 'group'
            else:
                kind = 'line'
            cells = []
            for col in columns:
                value = line.get(col.get('field') or '')
                cells.append({
                    'text': self._format_value(value, col.get('type')),
                    'raw': value,
                    'numeric': col.get('type') in ('monetary', 'number', 'percent', 'integer'),
                    'negative': isinstance(value, (int, float)) and value < 0,
                })
            rows.append({'level': level, 'kind': kind, 'cells': cells})
        return columns, rows

    @api.model
    def _format_value(self, value, col_type):
        if value is None or value is False:
            return ''
        if col_type in ('monetary', 'number') and isinstance(value, (int, float)):
            return formatLang(self.env, value, digits=2)
        if col_type == 'percent' and isinstance(value, (int, float)):
            return '%s %%' % formatLang(self.env, value, digits=1)
        if col_type == 'integer' and isinstance(value, (int, float)):
            return formatLang(self.env, value, digits=0)
        return str(value)

    @api.model
    def _get_filename(self, name, extension):
        """ File-system safe name (DMS validates file names). """
        clean = re.sub(r'[\\/:*?"<>|\r\n\t]+', '-', (name or '').strip()).strip(' .-') or _('Report')
        return '%s.%s' % (clean[:120], extension)

    # ------------------------------------------------------------------
    # Renderers
    # ------------------------------------------------------------------

    @api.model
    def render_pdf(self, report_data, name=None):
        columns, rows = self._get_rows(report_data)
        if not columns:
            raise UserError(_("There is nothing to export: the report has no columns."))
        data = {
            'title': name or report_data.get('title') or _('Report'),
            'subtitle': report_data.get('date_str') or '',
            'filters': report_data.get('filters') or [],
            'columns': [{'label': c.get('label') or '',
                         'numeric': c.get('type') in ('monetary', 'number', 'percent', 'integer')}
                        for c in columns],
            'rows': rows,
        }
        company = self.env.company
        pdf, _type = self.env['ir.actions.report']._render_qweb_pdf(
            'hudson_accounting_enhancements.action_report_dynamic_snapshot', [company.id], data=data)
        return pdf

    @api.model
    def render_xlsx(self, report_data, name=None):
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(_("The Python library xlsxwriter is not installed."))
        title = name or report_data.get('title') or _('Report')
        columns, rows = self._get_rows(report_data)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        # Excel sheet names: max 31 chars, none of []:*?/\
        sheet_name = re.sub(r'[\[\]:*?/\\]', '-', str(title))[:31].strip() or 'Report'
        sheet = workbook.add_worksheet(sheet_name)

        fmt_title = workbook.add_format({'bold': True, 'font_size': 14})
        fmt_subtitle = workbook.add_format({'font_color': '#64748b'})
        fmt_head = workbook.add_format({'bold': True, 'bottom': 2, 'bg_color': '#f8fafc'})
        fmt_head_num = workbook.add_format({'bold': True, 'bottom': 2, 'bg_color': '#f8fafc', 'align': 'right'})
        styles = {
            'section': {'bold': True, 'bg_color': '#f8fafc', 'top': 1, 'top_color': '#e2e8f0'},
            'group': {'bold': True},
            'line': {'font_color': '#334155'},
            'total': {'bold': True, 'bg_color': '#f8fafc', 'top': 1, 'top_color': '#94a3b8'},
        }
        cache = {}

        def cell_format(kind, numeric, level, first):
            key = (kind, numeric, level if first else 0)
            if key not in cache:
                props = dict(styles[kind])
                if numeric:
                    props['num_format'] = '#,##0.00;[Red]-#,##0.00'
                if first and level > 1 and kind != 'total':
                    props['indent'] = level - 1
                cache[key] = workbook.add_format(props)
            return cache[key]

        sheet.write_string(0, 0, str(title), fmt_title)
        if report_data.get('date_str'):
            sheet.write_string(1, 0, str(report_data['date_str']), fmt_subtitle)
        sheet.set_column(0, 0, 48)
        if len(columns) > 1:
            sheet.set_column(1, len(columns) - 1, 18)

        row_idx = 3
        for i, col in enumerate(columns):
            numeric = col.get('type') in ('monetary', 'number', 'percent', 'integer')
            sheet.write_string(row_idx, i, str(col.get('label') or ''), fmt_head_num if numeric else fmt_head)
        sheet.freeze_panes(row_idx + 1, 1)

        for row in rows:
            row_idx += 1
            for i, cell in enumerate(row['cells']):
                fmt = cell_format(row['kind'], cell['numeric'], row['level'], i == 0)
                raw = cell['raw']
                if cell['numeric'] and isinstance(raw, (int, float)) and not isinstance(raw, bool):
                    sheet.write_number(row_idx, i, raw, fmt)
                elif cell['text']:
                    sheet.write_string(row_idx, i, cell['text'], fmt)
                else:
                    sheet.write_blank(row_idx, i, None, fmt)

        workbook.close()
        return output.getvalue()

    @api.model
    def render_html(self, report_data, name=None):
        """ Self-contained HTML table (inline styles) to embed in a Knowledge
        article. Every value is escaped: report lines contain partner, account
        and label texts entered by users. """
        title = name or report_data.get('title') or _('Report')
        columns, rows = self._get_rows(report_data)
        border = '#e2e8f0'
        parts = [
            Markup('<div class="o_hudson_report_snapshot" style="margin:16px 0;border:1px solid %s;'
                   'border-radius:8px;overflow:hidden;font-size:13px;">') % border,
            Markup('<div style="padding:12px 16px;background-color:#f8fafc;border-bottom:1px solid %s;">'
                   '<div style="font-size:16px;font-weight:700;color:#0f172a;">%s</div>') % (border, title),
        ]
        if report_data.get('date_str'):
            parts.append(Markup('<div style="margin-top:2px;font-size:12px;color:#64748b;">%s</div>')
                         % report_data['date_str'])
        parts.append(Markup('</div><div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;">'
                            '<thead><tr>'))
        for col in columns:
            numeric = col.get('type') in ('monetary', 'number', 'percent', 'integer')
            parts.append(Markup('<th style="padding:7px 12px;text-align:%s;font-size:11px;font-weight:600;'
                                'text-transform:uppercase;letter-spacing:.04em;color:#475569;'
                                'background-color:#f8fafc;border-bottom:2px solid #cbd5e1;white-space:nowrap;">%s</th>')
                         % ('right' if numeric else 'left', col.get('label') or ''))
        parts.append(Markup('</tr></thead><tbody>'))
        row_styles = {
            'section': 'font-weight:700;color:#0f172a;background-color:#f8fafc;',
            'group': 'font-weight:600;color:#1e293b;',
            'line': 'color:#334155;',
            'total': 'font-weight:700;color:#0f172a;background-color:#f8fafc;border-top:1px solid #94a3b8;',
        }
        for row in rows:
            parts.append(Markup('<tr style="%s">') % row_styles[row['kind']])
            for i, cell in enumerate(row['cells']):
                style = 'padding:5px 12px;border-bottom:1px solid #f1f5f9;'
                if cell['numeric']:
                    style += 'text-align:right;white-space:nowrap;'
                if cell['negative']:
                    style += 'color:#dc2626;'
                if i == 0 and row['level'] > 1 and row['kind'] != 'total':
                    style += 'padding-left:%dpx;' % (12 + (row['level'] - 1) * 16)
                parts.append(Markup('<td style="%s">%s</td>') % (style, cell['text']))
            parts.append(Markup('</tr>'))
        parts.append(Markup('</tbody></table></div></div>'))
        return Markup('').join(parts)


class ReportDynamicSnapshot(models.AbstractModel):
    _name = 'report.hudson_accounting_enhancements.report_dynamic_snapshot'
    _description = 'Dynamic Report Snapshot PDF'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data or 'rows' not in data:
            raise UserError(_("Report data is missing. Please export the report again from the report screen."))
        return {
            'doc_ids': docids,
            'doc_model': 'res.company',
            'docs': self.env['res.company'].browse(docids),
            'report': data,
        }
