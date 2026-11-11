import json
from datetime import date, timedelta

from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open


def _collect_fields(data):
    """(model, field) used by pivots and carousel charts (grouped / summed: must be stored), and
    (model, path) of the global filter matchings (filtered only: must be searchable)."""
    used, filtered = set(), set()

    def add_domain(model, domain):
        for leaf in domain or []:
            if isinstance(leaf, (list, tuple)) and len(leaf) == 3:
                used.add((model, leaf[0]))

    def add_matching(model, matching):
        for link in (matching or {}).values():
            filtered.add((model, link['chain']))

    for pivot in data.get('pivots', {}).values():
        model = pivot['model']
        used.update((model, row['fieldName']) for row in pivot.get('rows', []))
        used.update((model, measure['fieldName']) for measure in pivot.get('measures', []) if measure['fieldName'] != '__count')
        add_domain(model, pivot.get('domain'))
        add_matching(model, pivot.get('fieldMatching'))
    for sheet in data['sheets']:
        for figure in sheet.get('figures', []):
            if figure.get('tag') != 'carousel':
                continue
            for chart_id, chart in figure['data'].get('chartDefinitions', {}).items():
                meta = chart['dataSource']['metaData']
                model = meta['resModel']
                if meta['measure'] != '__count':
                    used.add((model, meta['measure']))
                used.update((model, group.split(':')[0]) for group in meta['groupBy'])
                add_matching(model, figure['data'].get('fieldMatching', {}).get(chart_id))
    return used, filtered


@tagged('post_install', '-at_install')
class TestPayrollSpreadsheetDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with file_open('hudson_payroll_spreadsheet_dashboard/data/files/payroll_dashboard.json') as handle:
            cls.data = json.load(handle)
        cls.dashboard = cls.env.ref('hudson_payroll_spreadsheet_dashboard.spreadsheet_dashboard_payroll')

    def test_dashboard_record(self):
        self.assertEqual(self.dashboard.dashboard_group_id, self.env.ref('spreadsheet_dashboard.spreadsheet_dashboard_group_hr'))
        self.assertTrue(self.dashboard.is_published)
        stored = json.loads(self.dashboard.spreadsheet_data)
        self.assertEqual(stored['version'], self.data['version'])

    def test_every_field_exists_and_is_stored(self):
        """A pivot / chart on a missing or non-stored field cannot be computed (the old dashboard's bug)."""
        used, filtered = _collect_fields(self.data)
        self.assertTrue(used)
        for model, field_name in sorted(used):
            self.assertIn(model, self.env, model)
            field = self._field_of_chain(model, field_name)
            self.assertTrue(field.store, f'{model}.{field_name} is not stored')
        for model, path in sorted(filtered):
            field = self._field_of_chain(model, path)
            self.assertTrue(field._description_searchable, f'{model}.{path} cannot be filtered')

    def test_pivots_and_charts_compute(self):
        """Every pivot and chart definition can be grouped and summed as the spreadsheet does."""
        for pivot in self.data['pivots'].values():
            measures = [m['fieldName'] + ':sum' for m in pivot['measures'] if m['fieldName'] != '__count'] + ['__count']
            groupby = [row['fieldName'] for row in pivot['rows']]
            self.env[pivot['model']].read_group(pivot['domain'], groupby, measures)
        for sheet in self.data['sheets']:
            for figure in sheet.get('figures', []):
                for chart in figure.get('data', {}).get('chartDefinitions', {}).values():
                    meta = chart['dataSource']['metaData']
                    measure = '__count' if meta['measure'] == '__count' else meta['measure'] + ':sum'
                    self.env[meta['resModel']].read_group([], meta['groupBy'], [measure])

    def test_totals_match_payroll_dashboard(self):
        """CTC / gross / net / employer statutory / TDS agree with the payroll dashboard for each month with payslips."""
        Analysis = self.env['hds.payroll.analysis']
        dashboard = self.env.ref('hudson_in_payroll.hds_payroll_dashboard_singleton')
        months = {(row.date.year, row.date.month) for row in Analysis.search([])}
        for year, month in sorted(months)[-6:]:
            fy = self.env['tds.financial.year'].search([('start_date', '<=', date(year, month, 1)),
                                                        ('end_date', '>=', date(year, month, 1))], limit=1)
            if not fy:
                continue
            dashboard.write({'payroll_month_num': str(month), 'financial_year_id': fy.id})
            dashboard._compute_dashboard_metrics()
            start, end = date(year, month, 1), date(year + (month == 12), month % 12 + 1, 1)
            rows = Analysis.search([('date', '>=', start), ('date', '<', end), ('company_id', 'in', self.env.companies.ids)])
            for field, expected in (
                ('ctc', dashboard.total_payroll_cost),
                ('gross_wage', dashboard.total_gross_pay),
                ('net_wage', dashboard.total_net_pay),
                ('employer_statutory', dashboard.total_employer_statutory_liability),
                ('tds', dashboard.tds_this_month),
            ):
                self.assertAlmostEqual(sum(rows.mapped(field)), expected, places=2, msg=f'{field} {year}-{month:02d}')

    def _field_of_chain(self, model, chain):
        Model = self.env[model]
        field = None
        for name in chain.split('.'):
            field = Model._fields.get(name)
            self.assertTrue(field, f'{model}: {chain} does not exist')
            if field.relational:
                Model = self.env[field.comodel_name]
        return field

    def test_kpi_cards_open_payroll_records(self):
        """Every KPI card links to a list data source whose model, fields and action exist."""
        cards = [figure['id'] for sheet in self.data['sheets'] for figure in sheet.get('figures', [])
                 if figure['data'].get('type') == 'scorecard']
        self.assertEqual(len(cards), 12)
        links = self.data['odooLinkReferences']
        for card in cards:
            link = links.get(card)
            self.assertTrue(link, f'card {card} has no link')
            self.assertEqual(link['type'], 'dataSource')
            self.assertEqual(link['dataSourceType'], 'list')
            self.assertIn(link['dataSourceCoreId'], self.data['lists'])
        for list_def in self.data['lists'].values():
            action = self.env.ref(list_def['actionXmlId'])
            self.assertEqual(action.res_model, list_def['model'])
            self.assertIn('list', action.view_mode)
            for column in list_def['columns']:
                self._field_of_chain(list_def['model'], column['name'])
            for link in list_def['fieldMatching'].values():
                self.assertTrue(self._field_of_chain(list_def['model'], link['chain'])._description_searchable, link['chain'])
            for leaf in list_def['domain']:
                self._field_of_chain(list_def['model'], leaf[0])
            self.assertEqual(set(list_def['fieldMatching']), {f['id'] for f in self.data['globalFilters']})

    def test_kpi_card_records_match_card_values(self):
        """The records a card opens add up to the card's value (same period and company)."""
        Analysis = self.env['hds.payroll.analysis']
        lists = self.data['lists']
        links = {figure['data']['title']['text']: lists[self.data['odooLinkReferences'][figure['id']]['dataSourceCoreId']]
                 for sheet in self.data['sheets'] for figure in sheet.get('figures', [])
                 if figure['data'].get('type') == 'scorecard'}
        period_filter = next(f['id'] for f in self.data['globalFilters'] if f['type'] == 'date')
        company_filter = next(f['id'] for f in self.data['globalFilters'] if f.get('modelName') == 'res.company')

        def records(list_def, start, end, company):
            matching = list_def['fieldMatching']
            domain = list_def['domain'] + [
                [matching[period_filter]['chain'], '>=', start],
                [matching[period_filter]['chain'], '<', end],
                [matching[company_filter]['chain'], '=', company.id],
            ]
            return self.env[list_def['model']].search(domain)

        checks = (
            ('Total CTC', 'ctc', lambda recs: sum(recs.mapped('ctc'))),
            ('Gross Pay', 'gross_wage', lambda recs: sum(recs.mapped('gross_wage'))),
            ('Net Pay', 'net_wage', lambda recs: sum(recs.mapped('net_wage'))),
            ('Employer Statutory', 'employer_statutory', lambda recs: sum(recs.mapped('hds_in_total_employer_statutory'))),
            ('TDS Deducted', 'tds', lambda recs: sum(abs(total) for total in recs.mapped('total'))),
            ('Payslips', None, len),
        )
        rows = Analysis.search([])
        self.assertTrue(rows)
        for year, month, company in {(row.date.year, row.date.month, row.company_id) for row in rows}:
            start, end = date(year, month, 1), date(year + (month == 12), month % 12 + 1, 1)
            expected_rows = Analysis.search([('date', '>=', start), ('date', '<', end), ('company_id', '=', company.id)])
            for title, field, total in checks:
                expected = len(expected_rows) if field is None else sum(expected_rows.mapped(field))
                self.assertAlmostEqual(total(records(links[title], start, end, company)), expected, places=2,
                                       msg=f'{title} {company.name} {year}-{month:02d}')

    def _pivot(self, name):
        return next(pivot for pivot in self.data['pivots'].values() if pivot['name'] == name)

    def _period_records(self, pivot, start, end):
        """Records of a pivot for a period, as the spreadsheet filters them (period + selected companies)."""
        period_filter = next(f['id'] for f in self.data['globalFilters'] if f['type'] == 'date')
        company_filter = next(f['id'] for f in self.data['globalFilters'] if f.get('modelName') == 'res.company')
        matching = pivot['fieldMatching']
        return self.env[pivot['model']].search(pivot['domain'] + [
            [matching[period_filter]['chain'], '>=', start],
            [matching[period_filter]['chain'], '<', end],
            [matching[company_filter]['chain'], 'in', self.env.companies.ids],
        ])

    def test_final_settlements_match_payroll_dashboard(self):
        """Final settlements of the period: same count and amount as the payroll dashboard's planner."""
        dashboard = self.env.ref('hudson_in_payroll.hds_payroll_dashboard_singleton')
        pivot = self._pivot('Final settlements (period)')
        settlements = self.env['final.settlement'].search([('state', '!=', 'cancel'), ('last_working_day', '!=', False)])
        months = {(s.last_working_day.year, s.last_working_day.month) for s in settlements}
        for year, month in sorted(months):
            start, end = date(year, month, 1), date(year + (month == 12), month % 12 + 1, 1)
            expected = self.env['final.settlement'].search(dashboard._final_settlement_domain(start, end - timedelta(days=1)))
            records = self._period_records(pivot, start, end)
            self.assertEqual(records, expected, f'{year}-{month:02d}')
            self.assertAlmostEqual(sum(records.mapped('net_settlement_amount')),
                                   sum(expected.mapped('net_settlement_amount')), places=2)

    def test_leave_encashment_matches_payroll_dashboard(self):
        """Leave encashment of the period: the requests shown in the payroll dashboard's section
        (draft, submitted, approved, paid) raised in the month."""
        dashboard = self.env.ref('hudson_in_payroll.hds_payroll_dashboard_singleton')
        pivot = self._pivot('Leave encashment (period)')
        states = ('draft', 'submitted', 'approved', 'paid')
        requests = self.env['hds.leave.encashment.request'].search([('request_date', '!=', False)])
        for year, month in sorted({(r.request_date.year, r.request_date.month) for r in requests}):
            start, end = date(year, month, 1), date(year + (month == 12), month % 12 + 1, 1)
            expected = self.env['hds.leave.encashment.request'].search(
                dashboard._leave_encashment_domain(states, start, end - timedelta(days=1)))
            records = self._period_records(pivot, start, end)
            self.assertEqual(records, expected, f'{year}-{month:02d}')
            self.assertAlmostEqual(sum(records.mapped('projected_amount')), sum(expected.mapped('projected_amount')), places=2)

    def test_exit_cards_open_the_same_records(self):
        """The final settlement / leave encashment cards open exactly the records they count."""
        links = self.data['odooLinkReferences']
        cards = {figure['data']['title']['text']: self.data['lists'][links[figure['id']]['dataSourceCoreId']]
                 for sheet in self.data['sheets'] for figure in sheet.get('figures', [])
                 if figure['data'].get('type') == 'scorecard'}
        for title, pivot_name in (('Final Settlements', 'Final settlements (period)'),
                                  ('Settlement Amount', 'Final settlements (period)'),
                                  ('Leave Encashment Requests', 'Leave encashment (period)'),
                                  ('Leave Encashment Amount', 'Leave encashment (period)')):
            pivot, list_def = self._pivot(pivot_name), cards[title]
            self.assertEqual(list_def['model'], pivot['model'], title)
            self.assertEqual(list_def['domain'], pivot['domain'], title)
            self.assertEqual(list_def['fieldMatching'], pivot['fieldMatching'], title)

    def test_old_dashboard_removed(self):
        """The old dashboard is gone; its group (cannot be deleted) is empty, so the Dashboards app hides it."""
        self.assertFalse(self.env.ref('hudson_in_payroll.spreadsheet_dashboard_payroll', raise_if_not_found=False))
        old_group = self.env.ref('hudson_in_payroll.spreadsheet_dashboard_group_hr_payroll', raise_if_not_found=False)
        if old_group:
            self.assertFalse(old_group.published_dashboard_ids)
