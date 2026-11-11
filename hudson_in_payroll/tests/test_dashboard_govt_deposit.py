# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestDashboardGovtDeposit(TransactionCase):
    """The Govt Deposit card opens the payslips of its amount; their deposits add up to it."""

    def test_govt_deposit_list_matches_the_card(self):
        Dashboard = self.env['hds.payroll.dashboard']
        Slip = self.env['hr.payslip']
        months = Slip.search([('state', 'in', ('done', 'paid'))]).mapped(lambda s: (s.date_from.month, s.date_from.year))
        if not months:
            self.skipTest("No validated payslips to compare")
        financial_years = self.env['tds.financial.year']
        for month, year in sorted(set(months)):
            fy_start = year if month >= 4 else year - 1
            fy = financial_years.search([('start_date', '=', f'{fy_start}-04-01')], limit=1)
            if not fy:
                continue
            month_key = next(key for key, _label in Dashboard._fields['payroll_month_num'].selection if int(key) == month)
            dashboard = Dashboard.new({'payroll_month_num': month_key, 'financial_year_id': fy.id})
            action = Dashboard.get_card_action(card_type='govt_deposit', month_num=month, fy_id=fy.id)
            self.assertEqual(action['views'][0][0], self.env.ref('hudson_in_payroll.view_hr_payslip_list_govt_deposit').id)
            slips = Slip.search(action['domain'])
            self.assertAlmostEqual(sum(slips.mapped('hds_in_govt_deposit_total')), dashboard.total_statutory_liability,
                                   places=2, msg=f"{month}/{year}")
            self.assertAlmostEqual(sum(slips.mapped('hds_in_govt_tds')), dashboard.tds_this_month, places=2)
            self.assertAlmostEqual(sum(slips.mapped('hds_in_govt_pt')), dashboard.pt_total_liability, places=2)
            # TDS This Month card: same payslips, their TDS adds up to the card
            action = Dashboard.get_card_action(card_type='tds_breakdown', month_num=month, fy_id=fy.id)
            self.assertEqual(action['views'][0][0], self.env.ref('hudson_in_payroll.view_hr_payslip_list_tds').id)
            self.assertAlmostEqual(sum(Slip.search(action['domain']).mapped('hds_in_govt_tds')), dashboard.tds_this_month,
                                   places=2, msg=f"TDS {month}/{year}")
            # Net Salary card: same payslips, their net (paid and due) adds up to the card
            action = Dashboard.get_card_action(card_type='net_breakdown', month_num=month, fy_id=fy.id)
            self.assertEqual(action['views'][0][0], self.env.ref('hudson_in_payroll.view_hr_payslip_list_net').id)
            net_slips = Slip.search(action['domain'])
            self.assertAlmostEqual(sum(net_slips.mapped('hds_in_net_salary')), dashboard.total_net_pay,
                                   places=2, msg=f"Net {month}/{year}")
            self.assertAlmostEqual(sum(net_slips.filtered(lambda s: s.state == 'paid').mapped('hds_in_net_salary')),
                                   dashboard.total_net_paid, places=2)
            # CTC card: same payslips, gross + employer cost add up to the card
            action = Dashboard.get_card_action(card_type='ctc_breakdown', month_num=month, fy_id=fy.id)
            self.assertEqual(action['views'][0][0], self.env.ref('hudson_in_payroll.view_hr_payslip_list_ctc').id)
            slips = Slip.search(action['domain'])
            self.assertAlmostEqual(sum(slips.mapped('hds_in_ctc_total')), dashboard.total_payroll_cost,
                                   places=2, msg=f"CTC {month}/{year}")
            self.assertAlmostEqual(sum(slips.mapped('hds_in_ctc_gross')), dashboard.total_gross_pay, places=2)

    def test_payslip_parts_add_up(self):
        for slip in self.env['hr.payslip'].search([('state', 'in', ('done', 'paid'))], limit=50):
            parts = sum(slip[f'hds_in_govt_{key}'] for key in (
                'ee_epf', 'er_epf', 'edli_admin', 'ee_esic', 'er_esic', 'pt', 'ee_lwf', 'er_lwf', 'tds'))
            self.assertAlmostEqual(parts, slip.hds_in_govt_deposit_total, places=2)
            employer = sum(slip[f'hds_in_ctc_{key}'] for key in ('er_epf', 'er_edli', 'er_admin', 'er_esic', 'er_lwf', 'er_other'))
            self.assertAlmostEqual(employer, slip.hds_in_ctc_employer_cost, places=2)
            self.assertAlmostEqual(slip.hds_in_ctc_gross + employer, slip.hds_in_ctc_total, places=2)
            deductions = sum(slip[name] for name in ('hds_in_govt_ee_epf', 'hds_in_govt_ee_esic', 'hds_in_govt_pt',
                                                     'hds_in_govt_ee_lwf', 'hds_in_govt_tds', 'hds_in_net_other_deductions'))
            if slip.gross_wage:
                self.assertAlmostEqual(slip.gross_wage - deductions, slip.hds_in_net_salary, places=2)

    def test_joiners_and_exits_cards(self):
        """Joiners This Month / Exits This Month open the employees of their count (exits include archived)."""
        from datetime import date
        Dashboard = self.env['hds.payroll.dashboard']
        Employee = self.env['hr.employee']
        fy = self.env['tds.financial.year'].create({
            'name': 'Tax Year 2099-2100 (dashboard test)', 'code': '2099-2100-dash',
            'start_date': date(2099, 4, 1), 'end_date': date(2100, 3, 31)})
        reason = self.env['hr.departure.reason'].search([], limit=1) if 'hr.departure.reason' in self.env else False
        if 'departure_date' not in Employee._fields or 'departure_id' not in self.env['hr.version']._fields or not reason:
            self.skipTest("No employee departure records")
        leaver = Employee.create({'name': 'Dashboard Leaver'})
        departure = self.env['hr.employee.departure'].create({
            'employee_id': leaver.id, 'departure_reason_id': reason.id,
            'dismissal_date': date(2099, 5, 20), 'departure_date': date(2099, 5, 20)})
        leaver.version_id.write({'departure_id': departure.id})
        leaver.action_archive() if hasattr(leaver, 'action_archive') else leaver.write({'active': False})
        # Month of the departure date as Odoo stores it (it may follow the dismissal date by a notice period)
        month = leaver.with_context(active_test=False).departure_date.month
        month_key = next(key for key, _label in Dashboard._fields['payroll_month_num'].selection if int(key) == month)
        dashboard = Dashboard.create({'payroll_month_num': month_key, 'financial_year_id': fy.id})
        for card_type, count in (('exits', dashboard.exits_count), ('new_joiners', dashboard.new_joiners_count)):
            action = Dashboard.get_card_action(dashboard_id=dashboard.id, card_type=card_type, month_num=month)
            self.assertEqual(action['res_model'], 'hr.employee')
            self.assertEqual(Employee.search_count(action['domain']), count, card_type)
        self.assertEqual(dashboard.exits_count, 1)
        self.assertIn(leaver, Employee.search(Dashboard.get_card_action(dashboard_id=dashboard.id, card_type='exits', month_num=month)['domain']))
        html = str(dashboard.dashboard_html)
        self.assertIn('Joiners This Month', html)
        self.assertIn('Exits This Month', html)

    def test_tax_declarations_card(self):
        """Tax Declarations card: counts of the selected month by stage, each opening its declarations;
        reaching Proof Submitted records the proof submission date."""
        import calendar
        from datetime import date
        Dashboard = self.env['hds.payroll.dashboard']
        Declaration = self.env['tds.employee.declaration']
        dashboard = Dashboard.search([], limit=1) or Dashboard.create({})
        fy = dashboard.financial_year_id
        today = date.today()
        if not fy or not (fy.start_date <= today <= fy.end_date):
            self.skipTest("The dashboard tax year does not cover today")
        month_key = next(key for key, _label in Dashboard._fields['payroll_month_num'].selection if int(key) == today.month)
        dashboard.write({'payroll_month_num': month_key})
        month_start = today.replace(day=1)
        month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])

        def declarations(kind):
            return Declaration.search(dashboard._month_declaration_domain(kind, fy, month_start, month_end))

        before = {kind: len(declarations(kind)) for kind in ('pending', 'declared', 'draft')}
        employee = self.env['hr.employee'].create({'name': 'Declaration Card Employee'})
        declaration = Declaration.create({'employee_id': employee.id, 'financial_year_id': fy.id})
        self.assertIn(declaration, declarations('draft'))
        declaration.write({'state': 'declared', 'submission_date': today})
        self.assertIn(declaration, declarations('declared'))
        self.assertEqual(len(declarations('draft')), before['draft'])
        declaration.write({'state': 'proof_submitted'})
        self.assertEqual(declaration.proof_submission_date, today)
        self.assertIn(declaration, declarations('pending'))
        # Each count opens its own declarations
        for card_type, kind in (('decl_pending', 'pending'), ('decl_declared', 'declared'), ('decl_draft', 'draft')):
            action = Dashboard.get_card_action(dashboard_id=dashboard.id, card_type=card_type, month_num=today.month)
            self.assertEqual(action['res_model'], 'tds.employee.declaration')
            self.assertEqual(Declaration.search(action['domain']), declarations(kind), card_type)
        html = str(dashboard.dashboard_html)
        self.assertIn('Awaiting proofs', html)
        self.assertIn('Not submitted', html)
