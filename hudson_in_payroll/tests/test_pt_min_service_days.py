# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests.common import TransactionCase
from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_service import ProfessionalTaxService
from odoo.addons.hudson_in_payroll.services.professional_tax.pt_period_config_service import PTPeriodScheduleService
from odoo.addons.hudson_in_payroll.services.professional_tax.pt_periodicity_strategy import (
    PTPeriodicityStrategyRegistry, PT_COUNTED_PAYSLIP_STATES
)


class TestPTMinServiceDays(TransactionCase):
    # 18 statutory scenarios:
    # KL-01..KL-09 Kerala H1/H2 service day checks
    # TN-01..TN-06 Tamil Nadu H1 checks
    # GEN-01..GEN-03 engine guards

    def setUp(self):
        super().setUp()
        self.pt_service = ProfessionalTaxService(self.env)
        self.sched_service = PTPeriodScheduleService(self.env)
        self.company = self.env.company
        self.state_kl = (
            self.env.ref('base.state_in_kl', raise_if_not_found=False)
            or self.env['res.country.state'].search([('code', '=', 'KL')], limit=1)
        )
        self.state_tn = (
            self.env.ref('base.state_in_tn', raise_if_not_found=False)
            or self.env['res.country.state'].search([('code', '=', 'TN')], limit=1)
        )
        self.state_mh = (
            self.env.ref('base.state_in_mh', raise_if_not_found=False)
            or self.env['res.country.state'].search([('code', '=', 'MH')], limit=1)
        )
        self.emp = self.env['hr.employee'].create({
            'name': 'PT Min Service Days Test Employee',
            'company_id': self.company.id,
            'hds_in_pt_applicable': True,
        })
        self.emp.write({'contract_date_start': '2026-04-01', 'date_start': '2026-04-01'})
        if self.emp.version_id:
            self.emp.version_id.write({'contract_date_start': '2026-04-01', 'date_start': '2026-04-01'})

    # ---- helpers ----

    def _kl_h1(self, min_sd=60):
        s = self.env['pt.period.schedule'].search([
            ('state_id', '=', self.state_kl.id), ('periodicity', '=', 'half_yearly'),
            ('window_start_month', '=', '4'), ('window_end_month', '=', '9'),
        ], limit=1)
        if not s:
            s = self.env['pt.period.schedule'].create({
                'state_id': self.state_kl.id, 'periodicity': 'half_yearly',
                'window_start_month': '4', 'window_end_month': '9',
                'deduction_strategy': 'end_of_period', 'deduction_month': '9',
                'min_service_days': min_sd, 'active': True,
            })
        else:
            s.write({'min_service_days': min_sd})
        return s

    def _kl_h2(self, min_sd=60):
        s = self.env['pt.period.schedule'].search([
            ('state_id', '=', self.state_kl.id), ('periodicity', '=', 'half_yearly'),
            ('window_start_month', '=', '10'), ('window_end_month', '=', '3'),
        ], limit=1)
        if not s:
            s = self.env['pt.period.schedule'].create({
                'state_id': self.state_kl.id, 'periodicity': 'half_yearly',
                'window_start_month': '10', 'window_end_month': '3',
                'deduction_strategy': 'end_of_period', 'deduction_month': '3',
                'min_service_days': min_sd, 'active': True,
            })
        else:
            s.write({'min_service_days': min_sd})
        return s

    def _tn_h1(self, min_sd=60):
        s = self.env['pt.period.schedule'].search([
            ('state_id', '=', self.state_tn.id), ('periodicity', '=', 'half_yearly'),
            ('window_start_month', '=', '4'), ('window_end_month', '=', '9'),
        ], limit=1)
        if not s:
            s = self.env['pt.period.schedule'].create({
                'state_id': self.state_tn.id, 'periodicity': 'half_yearly',
                'window_start_month': '4', 'window_end_month': '9',
                'deduction_strategy': 'end_of_period', 'deduction_month': '9',
                'min_service_days': min_sd, 'active': True,
            })
        else:
            s.write({'min_service_days': min_sd})
        return s

    def _dates(self, join=None, exit=None):
        vals = {}
        if join:
            vals['contract_date_start'] = str(join)
            vals['date_start'] = str(join)
        if exit is not None:
            if exit is False:
                vals['departure_date'] = False
                vals['contract_date_end'] = False
            else:
                vals['departure_date'] = str(exit)
                vals['contract_date_end'] = str(exit)
        self.emp.write(vals)
        if self.emp.version_id:
            self.emp.version_id.write(vals)

    # KL-01
    def test_kl_01_service_days_calculation(self):
        w_start, w_end = date(2026, 4, 1), date(2026, 9, 30)
        self._dates(join=date(2026, 8, 2), exit=False)
        self.assertEqual(self.sched_service.compute_service_days(self.emp, w_start, w_end), 60)
        self.assertEqual(self.sched_service.calculate_service_days(self.emp, w_start, w_end), 60)
        self._dates(join=date(2026, 8, 3))
        self.assertEqual(self.sched_service.compute_service_days(self.emp, w_start, w_end), 59)
        self._dates(join=date(2026, 4, 1), exit=False)
        self.assertEqual(self.sched_service.compute_service_days(self.emp, w_start, w_end), 183)
        self._dates(join=date(2026, 4, 1), exit=date(2026, 5, 15))
        self.assertEqual(self.sched_service.compute_service_days(self.emp, w_start, w_end), 45)

    # KL-02
    def test_kl_02_kerala_below_min_service_days(self):
        self._kl_h1(60)
        self._dates(join=date(2026, 8, 3), exit=False)
        res = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2026, 9, 30), state=self.state_kl)
        self.assertEqual(res.amount, 0.0)
        self.assertEqual(res.validation_status, 'BELOW_MIN_SERVICE_DAYS')
        self.assertFalse(res.is_valid)

    # KL-03
    def test_kl_03_kerala_exactly_60_days_eligible(self):
        self._kl_h1(60)
        self._dates(join=date(2026, 8, 2), exit=False)
        res = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2026, 9, 30), state=self.state_kl)
        self.assertNotEqual(res.validation_status, 'BELOW_MIN_SERVICE_DAYS')
        self.assertGreater(res.amount, 0.0)

    # KL-04
    def test_kl_04_kerala_joined_before_h1_start(self):
        self._kl_h1(60)
        self._dates(join=date(2026, 1, 1), exit=False)
        res = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2026, 9, 30), state=self.state_kl)
        self.assertNotEqual(res.validation_status, 'BELOW_MIN_SERVICE_DAYS')

    # KL-05
    def test_kl_05_kerala_early_exit_below_60_days(self):
        self._kl_h1(60)
        self._dates(join=date(2026, 4, 1), exit=date(2026, 5, 29))
        res = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2026, 9, 30), state=self.state_kl)
        self.assertEqual(res.amount, 0.0)
        self.assertEqual(res.validation_status, 'BELOW_MIN_SERVICE_DAYS')

    # KL-06
    def test_kl_06_kerala_h2_below_60_days(self):
        self._kl_h2(60)
        self._dates(join=date(2027, 2, 1), exit=False)
        w_s, w_e = date(2026, 10, 1), date(2027, 3, 31)
        self.assertEqual(self.sched_service.compute_service_days(self.emp, w_s, w_e), 59)
        res = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2027, 3, 31), state=self.state_kl)
        self.assertEqual(res.amount, 0.0)
        self.assertEqual(res.validation_status, 'BELOW_MIN_SERVICE_DAYS')

    # KL-07
    def test_kl_07_kerala_h2_exactly_60_days_eligible(self):
        self._kl_h2(60)
        self._dates(join=date(2027, 1, 31), exit=False)
        w_s, w_e = date(2026, 10, 1), date(2027, 3, 31)
        self.assertEqual(self.sched_service.compute_service_days(self.emp, w_s, w_e), 60)
        res = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2027, 3, 31), state=self.state_kl)
        self.assertNotEqual(res.validation_status, 'BELOW_MIN_SERVICE_DAYS')

    # KL-08
    def test_kl_08_kerala_halfyear_boundary_reset(self):
        self._kl_h2(60)
        self._dates(join=date(2026, 8, 2), exit=date(2026, 9, 30))
        w_h2 = (date(2026, 10, 1), date(2027, 3, 31))
        self.assertEqual(self.sched_service.compute_service_days(self.emp, *w_h2), 0)
        res = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2027, 3, 31), state=self.state_kl)
        self.assertEqual(res.amount, 0.0)
        self.assertEqual(res.validation_status, 'BELOW_MIN_SERVICE_DAYS')

    # KL-09
    def test_kl_09_salary_revision_does_not_affect_service_days(self):
        self._kl_h1(60)
        self._dates(join=date(2026, 8, 2), exit=False)
        w_s, w_e = date(2026, 4, 1), date(2026, 9, 30)
        days_before = self.sched_service.compute_service_days(self.emp, w_s, w_e)
        contract = getattr(self.emp, 'contract_id', False) or getattr(self.emp, 'version_id', False)
        if contract:
            contract.write({'wage': 80000.0})
        self.assertEqual(self.sched_service.compute_service_days(self.emp, w_s, w_e), days_before)

    # TN-01
    def test_tn_01_tamilnadu_below_60_days_h1(self):
        self._tn_h1(60)
        self._dates(join=date(2026, 8, 3), exit=False)
        res = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2026, 9, 30), state=self.state_tn)
        self.assertEqual(res.amount, 0.0)
        self.assertEqual(res.validation_status, 'BELOW_MIN_SERVICE_DAYS')

    # TN-02
    def test_tn_02_tamilnadu_exactly_60_days_eligible(self):
        self._tn_h1(60)
        self._dates(join=date(2026, 8, 2), exit=False)
        res = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2026, 9, 30), state=self.state_tn)
        self.assertNotEqual(res.validation_status, 'BELOW_MIN_SERVICE_DAYS')

    # TN-03
    def test_tn_03_tamilnadu_full_period_employee(self):
        self._tn_h1(60)
        self._dates(join=date(2025, 1, 1), exit=False)
        res = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2026, 9, 30), state=self.state_tn)
        self.assertNotEqual(res.validation_status, 'BELOW_MIN_SERVICE_DAYS')

    # TN-04
    def test_tn_04_tamilnadu_early_exit_below_60_days(self):
        self._tn_h1(60)
        self._dates(join=date(2026, 4, 1), exit=date(2026, 5, 29))
        res = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2026, 9, 30), state=self.state_tn)
        self.assertEqual(res.amount, 0.0)
        self.assertEqual(res.validation_status, 'BELOW_MIN_SERVICE_DAYS')

    # TN-05
    def test_tn_05_tamilnadu_no_min_service_days_always_eligible(self):
        self._tn_h1(0)
        self._dates(join=date(2026, 8, 3), exit=False)
        res = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2026, 9, 30), state=self.state_tn)
        self.assertNotEqual(res.validation_status, 'BELOW_MIN_SERVICE_DAYS')

    # TN-06
    def test_tn_06_tamilnadu_check_min_service_days_return_tuple(self):
        sched = self._tn_h1(60)
        self._dates(join=date(2026, 8, 3), exit=False)
        meets, s_days, min_days = self.sched_service.check_min_service_days(sched, self.emp, eval_date=date(2026, 9, 30))
        self.assertFalse(meets)
        self.assertEqual(s_days, 59)
        self.assertEqual(min_days, 60)
        self._dates(join=date(2026, 8, 2), exit=False)
        meets60, s60, m60 = self.sched_service.check_min_service_days(sched, self.emp, eval_date=date(2026, 9, 30))
        self.assertTrue(meets60)
        self.assertEqual(s60, 60)
        self.assertEqual(m60, 60)

    # GEN-01
    def test_gen_01_zero_earned_wage_guard(self):
        res_zero = self.pt_service.compute_pt(employee=self.emp, salary=0.0, eval_date=date(2026, 9, 30), state=self.state_kl, is_simulation=False)
        self.assertEqual(res_zero.amount, 0.0)
        self.assertEqual(res_zero.validation_status, 'ZERO_WAGE')
        self.assertFalse(res_zero.is_valid)
        res_sim = self.pt_service.compute_pt(employee=self.emp, salary=0.0, eval_date=date(2026, 9, 30), state=self.state_kl, is_simulation=True)
        self.assertNotEqual(res_sim.validation_status, 'ZERO_WAGE')

    # GEN-02
    def test_gen_02_net_pay_guard(self):
        class MockCats:
            def __init__(self, g, d):
                self.GROSS = g
                self.DED = d
        self._dates(join=date(2026, 4, 1), exit=False)
        self._kl_h1(60)
        cats = MockCats(5000.0, -4900.0)
        res_c = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2026, 9, 30), state=self.state_kl, localdict={'categories': cats}, is_simulation=False)
        self.assertEqual(res_c.amount, 100.0)
        cats0 = MockCats(5000.0, -5000.0)
        res_0 = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2026, 9, 30), state=self.state_kl, localdict={'categories': cats0}, is_simulation=False)
        self.assertEqual(res_0.amount, 0.0)
        res_s = self.pt_service.compute_pt(employee=self.emp, salary=50000.0, eval_date=date(2026, 9, 30), state=self.state_kl, localdict={'categories': cats}, is_simulation=True)
        self.assertGreater(res_s.amount, 100.0)

    # GEN-03
    def test_gen_03_counted_payslip_states(self):
        strategy = PTPeriodicityStrategyRegistry.get_strategy('half_yearly')
        self.assertEqual(PT_COUNTED_PAYSLIP_STATES, ('verify', 'done', 'paid'))
        struct = self.env.ref('hudson_payroll_base.structure_base', raise_if_not_found=False) or self.env['hr.payroll.structure'].search([], limit=1)
        pt_rule = self.env.ref('hudson_in_payroll.hds_in_rule_pt', raise_if_not_found=False) or self.env['hr.salary.rule'].search([('code', '=', 'PT')], limit=1)
        contract = getattr(self.emp, 'contract_id', False) or getattr(self.emp, 'version_id', False)
        slip_draft = self.env['hr.payslip'].create({
            'name': 'Draft Slip Apr', 'employee_id': self.emp.id,
            'contract_id': contract.id if contract else False,
            'date_from': '2026-04-01', 'date_to': '2026-04-30',
            'struct_id': struct.id if struct else False, 'state': 'draft',
        })
        self.env['hr.payslip.line'].create({
            'slip_id': slip_draft.id, 'employee_id': self.emp.id,
            'contract_id': contract.id if contract else False,
            'salary_rule_id': pt_rule.id if pt_rule else False,
            'name': 'Professional Tax', 'code': 'PT',
            'amount': -500.0, 'quantity': 1.0, 'total': -500.0,
        })
        self.env.invalidate_all()
        deducted = strategy.get_period_already_deducted(self.env, employee=self.emp, start_date=date(2026, 4, 1), eval_date=date(2026, 9, 30))
        self.assertEqual(deducted, 0.0)
        slip_draft.write({'state': 'paid'})
        self.env.invalidate_all()
        deducted_paid = strategy.get_period_already_deducted(self.env, employee=self.emp, start_date=date(2026, 4, 1), eval_date=date(2026, 9, 30))
        self.assertEqual(deducted_paid, 500.0)
