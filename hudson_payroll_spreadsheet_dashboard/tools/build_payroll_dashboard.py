"""Build data/files/payroll_dashboard.json (Odoo Dashboards spreadsheet for payroll).

Odoo Community cannot edit spreadsheet dashboards in the UI, so the dashboard is generated
from this script. Run it after changing the layout:

    python tools/build_payroll_dashboard.py

Every figure reads the Payroll Analysis report (hds.payroll.analysis): no value is typed in.
The structure follows the Odoo 20 dashboards shipped with Odoo (spreadsheet data version 19.3.10).
"""
import ast
import json
import os

MODEL = 'hds.payroll.analysis'
ACTION = 'hudson_payroll_spreadsheet_dashboard.action_hds_payroll_analysis'
TITLE_COLOR = '#01666B'
MODULE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def model_constant(name):
    """Salary rule code tuples are read from the analysis model, so the dashboard and the view use the same codes."""
    with open(os.path.join(MODULE_DIR, 'models', 'hds_payroll_analysis.py'), encoding='utf-8') as handle:
        tree = ast.parse(handle.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == name for t in node.targets):
            return list(ast.literal_eval(node.value))
    raise KeyError(name)

# Global filters (stable ids)
F_PERIOD = '6f3c1a52-0d4e-4b7a-9a61-2b5e8f1c0a01'
F_COMPANY = '6f3c1a52-0d4e-4b7a-9a61-2b5e8f1c0a02'
F_DEPARTMENT = '6f3c1a52-0d4e-4b7a-9a61-2b5e8f1c0a03'
F_EMPLOYEE = '6f3c1a52-0d4e-4b7a-9a61-2b5e8f1c0a04'
F_PAYRUN = '6f3c1a52-0d4e-4b7a-9a61-2b5e8f1c0a05'

GLOBAL_FILTERS = [
    {'id': F_PERIOD, 'type': 'date', 'label': 'Period', 'defaultValue': 'this_month'},
    {'id': F_COMPANY, 'type': 'relation', 'label': 'Company', 'modelName': 'res.company', 'defaultValueDisplayNames': []},
    {'id': F_DEPARTMENT, 'type': 'relation', 'label': 'Department', 'modelName': 'hr.department', 'defaultValueDisplayNames': []},
    {'id': F_EMPLOYEE, 'type': 'relation', 'label': 'Employee', 'modelName': 'hr.employee', 'defaultValueDisplayNames': []},
    {'id': F_PAYRUN, 'type': 'relation', 'label': 'Pay Run', 'modelName': 'hr.payslip.run', 'defaultValueDisplayNames': []},
]


def field_matching(period=True, offset=0, prefix='', date_field='date', department='department_id',
                   payrun='payslip_run_id'):
    """Link every global filter to the analysis fields. Trend charts ignore the period so they show history.

    prefix / date_field / department: paths of the same fields on the models the KPI cards open
    (payslips, payslip lines), so a click shows the records of the figure with the same filters.
    """
    matching = {
        F_COMPANY: {'chain': f'{prefix}company_id', 'type': 'many2one'},
        F_DEPARTMENT: {'chain': f'{prefix}{department}', 'type': 'many2one'},
        F_EMPLOYEE: {'chain': f'{prefix}employee_id', 'type': 'many2one'},
        F_PAYRUN: {'chain': f'{prefix}{payrun}', 'type': 'many2one'},
    }
    if period:
        matching[F_PERIOD] = {'chain': f'{prefix}{date_field}', 'type': 'date', 'offset': offset}
    return matching


def measure(field, label):
    return {'id': field, 'fieldName': field, 'userDefinedName': label}


def pivot(pid, name, measures, rows=(), sorted_by=None, offset=0, domain=None, model=MODEL, matching=None):
    data = {
        'type': 'ODOO',
        'fieldMatching': (matching or field_matching)(offset=offset),
        'context': {},
        'domain': domain or [],
        'id': pid,
        'measures': measures,
        'model': model,
        'name': name,
        'formulaId': pid,
        'columns': [],
        'rows': [{'fieldName': row} for row in rows],
    }
    if sorted_by:
        data['sortedColumn'] = {'measure': sorted_by, 'order': 'desc', 'domain': []}
    return data


KPI_MEASURES = [
    measure('ctc', 'CTC'),
    measure('gross_wage', 'Gross'),
    measure('net_wage', 'Net Pay'),
    measure('employer_statutory', 'Employer Statutory'),
    measure('tds', 'TDS'),
    measure('__count', 'Payslips'),
]

# Final settlements and leave encashment of the period, with the payroll dashboard's rules:
# - final settlements not cancelled, by last working day (Final Settlement Planner)
# - leave encashment requests raised in the period, not rejected / cancelled (Leave Encashment section)
FS_MODEL = 'final.settlement'
FS_ACTION = 'hudson_in_final_settlement.action_final_settlement'
FS_SCOPE = [['state', '!=', 'cancel']]
LE_MODEL = 'hds.leave.encashment.request'
LE_ACTION = 'hudson_in_payroll.action_hds_leave_encashment_request'
LE_SCOPE = [['state', 'in', ['draft', 'submitted', 'approved', 'paid']]]


def fs_matching(period=True, offset=0):
    return field_matching(period=period, offset=offset, date_field='last_working_day', payrun='payslip_id.payslip_run_id')


def le_matching(period=True, offset=0):
    return field_matching(period=period, offset=offset, date_field='request_date',
                          department='employee_id.department_id', payrun='payslip_id.payslip_run_id')


FS_MEASURES = [measure('__count', 'Settlements'), measure('net_settlement_amount', 'Net Settlement')]
LE_MEASURES = [measure('__count', 'Requests'), measure('requested_days', 'Days'), measure('projected_amount', 'Amount')]

PIVOTS = {
    '1': pivot('1', 'Key figures (period)', KPI_MEASURES),
    '2': pivot('2', 'Key figures (previous period)', KPI_MEASURES, offset=-1),
    '3': pivot('3', 'Top wage earners', [measure('gross_wage', 'Gross'), measure('net_wage', 'Net Pay')],
               rows=('employee_id',), sorted_by='gross_wage'),
    '4': pivot('4', 'Departments', [measure('ctc', 'CTC'), measure('__count', 'Payslips')],
               rows=('department_id',), sorted_by='ctc'),
    '5': pivot('5', 'Top TDS', [measure('tds', 'TDS')], rows=('employee_id',), sorted_by='tds',
               domain=[['tds', '>', 0]]),
    '6': pivot('6', 'Final settlements (period)', FS_MEASURES, domain=FS_SCOPE, model=FS_MODEL, matching=fs_matching),
    '7': pivot('7', 'Final settlements (previous period)', FS_MEASURES, offset=-1, domain=FS_SCOPE, model=FS_MODEL,
               matching=fs_matching),
    '8': pivot('8', 'Leave encashment (period)', LE_MEASURES, domain=LE_SCOPE, model=LE_MODEL, matching=le_matching),
    '9': pivot('9', 'Leave encashment (previous period)', LE_MEASURES, offset=-1, domain=LE_SCOPE, model=LE_MODEL,
               matching=le_matching),
    '10': pivot('10', 'Final settlements by employee',
                [measure('net_settlement_amount', 'Net Settlement'), measure('gratuity_gross_amount', 'Gratuity'),
                 measure('leave_encash_gross_amount', 'Leave Encashment')],
                rows=('employee_id',), sorted_by='net_settlement_amount', domain=FS_SCOPE, model=FS_MODEL,
                matching=fs_matching),
    '11': pivot('11', 'Leave encashment by employee',
                [measure('requested_days', 'Days'), measure('projected_amount', 'Amount')],
                rows=('employee_id',), sorted_by='projected_amount', domain=LE_SCOPE, model=LE_MODEL,
                matching=le_matching),
}

# Records opened by the KPI cards (Odoo list data sources: not displayed, only used as card links).
# Same scope as the analysis: validated / paid payslips that are not flagged as duplicates.
PAYSLIP_SCOPE = [['state', 'in', ['done', 'paid']], ['has_duplicate_payslip', '!=', True]]


def odoo_list(name, model, action, domain, columns, matching):
    return {
        'model': model, 'domain': domain, 'context': {}, 'orderBy': [], 'name': name,
        'actionXmlId': action,
        'columns': [{'name': field, 'string': label} for field, label in columns],
        'fieldMatching': matching,
    }


PAYSLIP_MATCHING = field_matching(date_field='date_from', department='contract_id.department_id')
LIST_PAYSLIPS, LIST_STATUTORY, LIST_TDS, LIST_ANALYSIS = '1', '2', '3', '4'
LIST_SETTLEMENTS, LIST_ENCASHMENT = '5', '6'
LISTS = {
    LIST_PAYSLIPS: odoo_list(
        'Payslips', 'hr.payslip', 'hudson_payroll_base.action_hr_payslip', PAYSLIP_SCOPE,
        [('employee_id', 'Employee'), ('gross_wage', 'Gross'), ('net_wage', 'Net')], PAYSLIP_MATCHING),
    LIST_STATUTORY: odoo_list(
        'Employer Statutory', 'hr.payslip', 'hudson_payroll_spreadsheet_dashboard.action_hds_payroll_employer_statutory',
        PAYSLIP_SCOPE, [('employee_id', 'Employee'), ('hds_in_total_employer_statutory', 'Total Statutory')],
        PAYSLIP_MATCHING),
    LIST_TDS: odoo_list(
        'TDS Deducted', 'hr.payslip.line', 'hudson_payroll_base.action_hr_payslip_line_report',
        [['slip_id.' + leaf[0]] + leaf[1:] for leaf in PAYSLIP_SCOPE]
        + [['code', 'in', model_constant('TDS_CODES')], ['total', '!=', 0]],
        [('employee_id', 'Employee'), ('total', 'TDS')],
        field_matching(prefix='slip_id.', date_field='date_from', department='contract_id.department_id')),
    LIST_ANALYSIS: odoo_list(
        'Payroll Analysis', MODEL, ACTION, [],
        [('employee_id', 'Employee'), ('gross_wage', 'Gross'), ('ctc', 'CTC')], field_matching()),
    LIST_SETTLEMENTS: odoo_list(
        'Final Settlements', FS_MODEL, FS_ACTION, FS_SCOPE,
        [('employee_id', 'Employee'), ('last_working_day', 'Last Working Day'), ('net_settlement_amount', 'Net Settlement')],
        fs_matching()),
    LIST_ENCASHMENT: odoo_list(
        'Leave Encashment Requests', LE_MODEL, LE_ACTION, LE_SCOPE,
        [('employee_id', 'Employee'), ('request_date', 'Request Date'), ('projected_amount', 'Amount')],
        le_matching()),
}

# Key figures: Data sheet row -> (label, current formula, previous formula)
KPI_ROWS = [
    ('Total CTC', '=PIVOT.VALUE(1,"ctc")', '=PIVOT.VALUE(2,"ctc")'),
    ('Gross Pay', '=PIVOT.VALUE(1,"gross_wage")', '=PIVOT.VALUE(2,"gross_wage")'),
    ('Net Pay', '=PIVOT.VALUE(1,"net_wage")', '=PIVOT.VALUE(2,"net_wage")'),
    ('Employer Statutory', '=PIVOT.VALUE(1,"employer_statutory")', '=PIVOT.VALUE(2,"employer_statutory")'),
    ('TDS Deducted', '=PIVOT.VALUE(1,"tds")', '=PIVOT.VALUE(2,"tds")'),
    ('Payslips', '=PIVOT.VALUE(1,"__count")', '=PIVOT.VALUE(2,"__count")'),
    ('Average Net Pay', '=IFERROR(B4/B7,0)', '=IFERROR(C4/C7,0)'),
    ('Average CTC', '=IFERROR(B2/B7,0)', '=IFERROR(C2/C7,0)'),
    ('Final Settlements', '=PIVOT.VALUE(6,"__count")', '=PIVOT.VALUE(7,"__count")'),
    ('Settlement Amount', '=PIVOT.VALUE(6,"net_settlement_amount")', '=PIVOT.VALUE(7,"net_settlement_amount")'),
    ('Leave Encashment Requests', '=PIVOT.VALUE(8,"__count")', '=PIVOT.VALUE(9,"__count")'),
    ('Leave Encashment Amount', '=PIVOT.VALUE(8,"projected_amount")', '=PIVOT.VALUE(9,"projected_amount")'),
]


def sheet(sheet_id, name, cells=None, col_sizes=None, row_count=100, col_count=26, styles=None, formats=None,
          figures=None, background=None, conditional_formats=None):
    data = {
        'id': sheet_id,
        'name': name,
        'colNumber': col_count,
        'rowNumber': row_count,
        'rows': {},
        'cols': {str(i): {'size': size} for i, size in enumerate(col_sizes or [])},
        'merges': [],
        'cells': cells or {},
        'styles': styles or {},
        'formats': formats or {},
        'borders': {},
        'conditionalFormats': conditional_formats or [],
        'dataValidationRules': [],
        'figures': figures or [],
        'tables': [],
        'areGridLinesVisible': True,
        'isVisible': True,
        'headerGroups': {'ROW': [], 'COL': []},
        'comments': {},
    }
    if background:
        data['backgroundColor'] = background
    return data


def data_sheet():
    cells = {'A1': '=_t("KPI")', 'B1': '=_t("Current")', 'C1': '=_t("Previous")',
             'D1': '=_t("Current")', 'E1': '=_t("Previous")'}
    for i, (label, current, previous) in enumerate(KPI_ROWS, start=2):
        cells[f'A{i}'] = f'=_t("{label}")'
        cells[f'B{i}'] = current
        cells[f'C{i}'] = previous
        cells[f'D{i}'] = f'=FORMAT.LARGE.NUMBER(B{i})'
        cells[f'E{i}'] = f'=FORMAT.LARGE.NUMBER(C{i})'
    return sheet('7a1d2c3e-0001-4c5d-8e9f-payrolldata01', 'Data', cells=cells,
                 col_sizes=[160, 110, 110, 90, 90], styles={'A1:E1': 1})


def top_sheet(sheet_id, name, pivot_id, width):
    """A 'Top' list: PIVOT() spills the sorted rows (header + 10 rows)."""
    last_col = 'ABCD'[width - 1]
    return sheet(sheet_id, name, cells={'A1': f'=PIVOT({pivot_id},10,false,false)'},
                 col_sizes=[260] + [110] * (width - 1),
                 styles={f'A1:{last_col}1': 2, f'A2:{last_col}11': 3},
                 formats={f'B2:{last_col}11': 1})


SHEET_TOP_EARNERS = '7a1d2c3e-0002-4c5d-8e9f-payrolltop001'
SHEET_DEPARTMENTS = '7a1d2c3e-0003-4c5d-8e9f-payrolldept01'
SHEET_TOP_TDS = '7a1d2c3e-0004-4c5d-8e9f-payrolltds001'
SHEET_SETTLEMENTS = '7a1d2c3e-0005-4c5d-8e9f-payrollfset01'
SHEET_ENCASHMENT = '7a1d2c3e-0006-4c5d-8e9f-payrollencsh1'


def scorecard(fig_id, title, row, x, y):
    return {
        'id': fig_id, 'width': 238, 'height': 101, 'tag': 'chart',
        'data': {
            'baselineColorDown': '#DC6965', 'baselineColorUp': '#00A04A', 'baselineMode': 'percentage',
            'title': {'text': title, 'bold': True, 'color': TITLE_COLOR},
            'type': 'scorecard', 'background': '',
            'baseline': f'Data!E{row}', 'baselineDescr': {'text': 'since last period'},
            'keyValue': f'Data!D{row}', 'humanize': False, 'chartId': fig_id,
        },
        'offset': {'x': x, 'y': y}, 'col': 0, 'row': 0,
    }


def odoo_chart(chart_type, field, group_by, model=MODEL, action=ACTION):
    chart = {
        'title': {'text': ''},
        'legendPosition': 'top' if chart_type == 'pie' else 'none',
        'type': chart_type,
        'humanize': True,
        'dataSource': {
            'type': 'odoo',
            'metaData': {'groupBy': [group_by], 'measure': field, 'order': None, 'resModel': model,
                         'mode': chart_type, 'cumulatedStart': False},
            'searchParams': {'comparison': None, 'context': {}, 'domain': [], 'groupBy': [group_by], 'orderBy': []},
            'actionXmlId': action,
        },
        'dataSetStyles': {},
    }
    if chart_type == 'bar':
        chart['stacked'] = False
    if chart_type == 'line':
        chart['stacked'] = False
        chart['fillArea'] = True
    return chart


def carousel(fig_id, title, x, y, width, items):
    """items: ('chart', chart_id, tab_title, chart_definition, follows_period[, matching function]) or
              ('table', sheet_id, tab_title, last_column_index)"""
    definitions, matching, entries = {}, {}, []
    for item in items:
        if item[0] == 'chart':
            _kind, chart_id, tab, definition, follows_period = item[:5]
            matching_of = item[5] if len(item) > 5 else field_matching
            definitions[chart_id] = definition
            matching[chart_id] = matching_of(period=follows_period)
            entries.append({'type': 'chart', 'chartId': chart_id, 'title': tab})
        else:
            _kind, sheet_id, tab, right = item
            entries.append({'type': 'carouselDataView', 'title': tab,
                            'rangeData': {'_sheetId': sheet_id, '_zone': {'top': 0, 'left': 0, 'bottom': 10, 'right': right}}})
    return {
        'id': fig_id, 'col': 0, 'row': 0, 'offset': {'x': x, 'y': y}, 'width': width, 'height': 417,
        'tag': 'carousel',
        'data': {'chartDefinitions': definitions,
                 'title': {'text': title, 'fontSize': 21, 'bold': True, 'color': TITLE_COLOR},
                 'items': entries, 'fieldMatching': matching},
    }


# KPI cards: (title, Data sheet row, list opened on click)
KPI_CARDS = [
    ('Total CTC', 2, LIST_ANALYSIS), ('Gross Pay', 3, LIST_ANALYSIS), ('Net Pay', 4, LIST_PAYSLIPS),
    ('Employer Statutory', 5, LIST_STATUTORY), ('TDS Deducted', 6, LIST_TDS), ('Payslips', 7, LIST_PAYSLIPS),
    ('Average Net Pay', 8, LIST_PAYSLIPS), ('Average CTC', 9, LIST_ANALYSIS),
    ('Final Settlements', 10, LIST_SETTLEMENTS), ('Settlement Amount', 11, LIST_SETTLEMENTS),
    ('Leave Encashment Requests', 12, LIST_ENCASHMENT), ('Leave Encashment Amount', 13, LIST_ENCASHMENT),
]
PAYROLL_CARDS = 8           # first two rows, at the top
EXIT_SECTION_Y = 1541       # final settlement / leave encashment section, below the statutory charts


def kpi_card_y(index):
    if index < PAYROLL_CARDS:
        return 9 + (index // 4) * 112
    return EXIT_SECTION_Y + ((index - PAYROLL_CARDS) // 4) * 112


def kpi_card_id(index):
    return f'9b2e4f10-00{index + 1:02d}-4a1b-9c2d-payrollkpi0{index + 1}'


def odoo_links():
    """Clicking a KPI card opens its records in the payroll module, filtered like the dashboard."""
    return {kpi_card_id(i): {'type': 'dataSource', 'dataSourceType': 'list', 'dataSourceCoreId': list_id}
            for i, (_title, _row, list_id) in enumerate(KPI_CARDS)}


def dashboard_sheet():
    figures = []
    for i, (title, row, _list_id) in enumerate(KPI_CARDS):
        figures.append(scorecard(kpi_card_id(i), title, row, x=(i % 4) * 254, y=kpi_card_y(i)))
    figures += [
        carousel('9b2e4f10-0101-4a1b-9c2d-payrolltrend1', 'Payroll Cost Trend', 0, 245, 1000, [
            ('chart', 'c1a00001-trend-ctc', 'CTC', odoo_chart('line', 'ctc', 'date:month'), False),
            ('chart', 'c1a00002-trend-gross', 'Gross', odoo_chart('bar', 'gross_wage', 'date:month'), False),
            ('chart', 'c1a00003-trend-net', 'Net Pay', odoo_chart('bar', 'net_wage', 'date:month'), False),
            ('chart', 'c1a00004-trend-stat', 'Employer Statutory', odoo_chart('bar', 'employer_statutory', 'date:month'), False),
        ]),
        carousel('9b2e4f10-0102-4a1b-9c2d-payrolltop001', 'Top Wage Earners', 0, 677, 495, [
            ('table', SHEET_TOP_EARNERS, 'Top 10 (Gross)', 2),
            ('chart', 'c1a00005-top-gross', 'Chart', odoo_chart('bar', 'gross_wage', 'employee_id'), True),
        ]),
        carousel('9b2e4f10-0103-4a1b-9c2d-payrolldept01', 'Departments', 505, 677, 495, [
            ('chart', 'c1a00006-dept-ctc', 'CTC Share', odoo_chart('pie', 'ctc', 'department_id'), True),
            ('table', SHEET_DEPARTMENTS, 'Cost by Department', 2),
        ]),
        carousel('9b2e4f10-0104-4a1b-9c2d-payrollstat01', 'Statutory Deductions', 0, 1109, 495, [
            ('chart', 'c1a00007-stat-tds', 'TDS', odoo_chart('bar', 'tds', 'date:month'), False),
            ('chart', 'c1a00008-stat-epf', 'Employee EPF', odoo_chart('bar', 'employee_epf', 'date:month'), False),
            ('chart', 'c1a00009-stat-esic', 'Employee ESIC', odoo_chart('bar', 'employee_esic', 'date:month'), False),
            ('chart', 'c1a00010-stat-pt', 'Professional Tax', odoo_chart('bar', 'professional_tax', 'date:month'), False),
        ]),
        carousel('9b2e4f10-0105-4a1b-9c2d-payrolltds001', 'TDS by Tax Regime', 505, 1109, 495, [
            ('chart', 'c1a00011-tds-regime', 'By Regime', odoo_chart('pie', 'tds', 'tax_regime'), True),
            ('table', SHEET_TOP_TDS, 'Top 10 TDS', 1),
        ]),
        carousel('9b2e4f10-0106-4a1b-9c2d-payrollfset01', 'Final Settlements', 0, EXIT_SECTION_Y + 112, 495, [
            ('table', SHEET_SETTLEMENTS, 'Settlements', 3),
            ('chart', 'c1a00012-fset-status', 'By Status',
             odoo_chart('pie', '__count', 'state', FS_MODEL, FS_ACTION), True, fs_matching),
        ]),
        carousel('9b2e4f10-0107-4a1b-9c2d-payrollencsh1', 'Leave Encashment', 505, EXIT_SECTION_Y + 112, 495, [
            ('table', SHEET_ENCASHMENT, 'Requests', 2),
            ('chart', 'c1a00013-encash-status', 'By Status',
             odoo_chart('bar', 'projected_amount', 'state', LE_MODEL, LE_ACTION), True, le_matching),
        ]),
    ]
    return sheet('7a1d2c3e-0000-4c5d-8e9f-payrolldash01', 'Dashboard', col_sizes=[136], col_count=10,
                 row_count=100, figures=figures, background='#F9FAFB')


def build():
    return {
        'version': '19.3.10',
        'sheets': [
            dashboard_sheet(),
            data_sheet(),
            top_sheet(SHEET_TOP_EARNERS, 'Top Wage Earners', 3, 3),
            top_sheet(SHEET_DEPARTMENTS, 'Departments', 4, 3),
            top_sheet(SHEET_TOP_TDS, 'Top TDS', 5, 2),
            top_sheet(SHEET_SETTLEMENTS, 'Final Settlements', 10, 4),
            top_sheet(SHEET_ENCASHMENT, 'Leave Encashment', 11, 3),
        ],
        'styles': {
            '1': {'bold': True},
            '2': {'bold': True, 'textColor': '#434343', 'verticalAlign': 'middle'},
            '3': {'textColor': '#434343', 'verticalAlign': 'middle'},
        },
        'formats': {'1': '#,##0'},
        'borders': {},
        'revisionId': 'START_REVISION',
        'uniqueFigureIds': True,
        'settings': {'locale': {
            'name': 'English (US)', 'code': 'en_US', 'thousandsSeparator': ',', 'decimalSeparator': '.',
            'dateFormat': 'mm/dd/yyyy', 'timeFormat': 'hh:mm:ss', 'formulaArgSeparator': ',', 'weekStart': 7,
        }},
        'pivots': PIVOTS,
        'pivotNextId': len(PIVOTS) + 1,
        'customTableStyles': {},
        'namedRanges': {},
        'globalFilters': GLOBAL_FILTERS,
        'lists': LISTS,
        'listNextId': len(LISTS) + 1,
        'odooLinkReferences': odoo_links(),
    }


if __name__ == '__main__':
    target = os.path.join(MODULE_DIR, 'data', 'files', 'payroll_dashboard.json')
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'w', encoding='utf-8') as handle:
        json.dump(build(), handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    print(f'Wrote {target}')
