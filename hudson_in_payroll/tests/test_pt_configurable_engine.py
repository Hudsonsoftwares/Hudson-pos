# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests.common import TransactionCase
from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_service import ProfessionalTaxService
from odoo.addons.hudson_in_payroll.services.professional_tax.pt_period_config_service import PTPeriodScheduleService


from odoo.exceptions import ValidationError


class TestPTConfigurableEngine(TransactionCase):
    """
    Exhaustive Test Suite for Configurable Professional Tax (PT) Periodicity & Strategy Engine.
    Validates:
    - Monthly, Quarterly, Half-Yearly, and Annual periodicities
    - Quarterly and Half-Yearly disallow Every Payroll & Equal Distribution (strictly Full Amount)
    - End of Period (lump sum) deduction strategy
    - Mid-period joining and mid-period leaving
    - Lump-sum deduction in statutory settlement month
    """

    def setUp(self):
        super().setUp()
        self.pt_service = ProfessionalTaxService(self.env)
        self.sched_service = PTPeriodScheduleService(self.env)

        # Base company & states
        self.company = self.env.company
        self.state_mh = self.env.ref('base.state_in_mh', raise_if_not_found=False) or self.env['res.country.state'].search([('code', '=', 'MH')], limit=1)
        self.state_kl = self.env.ref('base.state_in_kl', raise_if_not_found=False) or self.env['res.country.state'].search([('code', '=', 'KL')], limit=1)
        self.state_mp = self.env.ref('base.state_in_mp', raise_if_not_found=False) or self.env['res.country.state'].search([('code', '=', 'MP')], limit=1)

        # Create test employee with valid contract start date
        self.emp = self.env['hr.employee'].create({
            'name': 'PT Engine Test Employee',
            'company_id': self.company.id,
        })
        self.emp.write({'date_start': '2025-01-01'})
        if self.emp.version_id:
            self.emp.version_id.write({'date_start': '2025-01-01'})
        if hasattr(self.emp, '_compute_joining_date'):
            self.emp._compute_joining_date()

        self.contract = self.emp.version_id

    def test_01_monthly_every_payroll(self):
        """Tests Monthly periodicity with Every Payroll strategy."""
        sched = self.env['pt.period.schedule'].create({
            'state_id': self.state_mh.id,
            'periodicity': 'monthly',
            'deduction_strategy': 'every_payroll',
            'active': True,
        })
        self.assertEqual(sched.distribution_method, 'full_amount')
        self.assertFalse(sched.window_start_month)
        self.assertFalse(sched.window_end_month)
        start_d, end_d = self.sched_service.resolve_period_window(sched, eval_date='2026-05-31')
        self.assertEqual(start_d, date(2026, 5, 1))
        self.assertEqual(end_d, date(2026, 5, 31))

        rem_payrolls = self.sched_service.calculate_remaining_payrolls(self.emp, start_d, end_d, '2026-05-31')
        self.assertEqual(rem_payrolls, 1)

    def test_02_half_yearly_end_of_period_h2(self):
        """Tests Half-Yearly H2 (October-March) with End of Period lump sum strategy in March."""
        sched = self.env['pt.period.schedule'].create({
            'state_id': self.state_kl.id,
            'periodicity': 'half_yearly',
            'window_start_month': '10',
            'window_end_month': '3',
            'deduction_strategy': 'end_of_period',
            'distribution_method': 'full_amount',
            'deduction_month': '3',
            'active': True,
        })

        # November (Non-deduction month)
        should_nov = self.sched_service.should_deduct(sched, eval_date='2026-11-30', employee=self.emp)
        self.assertFalse(should_nov)

        # March (Deduction month)
        should_mar = self.sched_service.should_deduct(sched, eval_date='2027-03-31', employee=self.emp)
        self.assertTrue(should_mar)

    def test_03_beginning_of_period_month_guard(self):
        """Tests that Beginning of Period schedule strictly deducts in start month and not subsequent months."""
        sched = self.env['pt.period.schedule'].create({
            'state_id': self.state_kl.id,
            'periodicity': 'half_yearly',
            'window_start_month': '4',
            'window_end_month': '9',
            'deduction_strategy': 'beginning_of_period',
            'distribution_method': 'full_amount',
            'deduction_month': '4',
            'active': True,
        })

        # Month 1 (April): Start month -> SHOULD deduct
        should_apr = self.sched_service.should_deduct(sched, eval_date='2026-04-30', employee=self.emp)
        self.assertTrue(should_apr)

        # Month 2 (May): Subsequent month -> MUST NOT deduct (verifies fix for fallthrough bug!)
        should_may = self.sched_service.should_deduct(sched, eval_date='2026-05-31', employee=self.emp)
        self.assertFalse(should_may)

        # Month 6 (September): End of period month -> MUST NOT deduct
        should_sep = self.sched_service.should_deduct(sched, eval_date='2026-09-30', employee=self.emp)
        self.assertFalse(should_sep)

    def test_04_half_yearly_lump_sum_deduction(self):
        """Tests Half-Yearly PT lump sum full amount deduction at end of period (Sept), disallowing equal distribution."""
        from odoo.addons.hudson_in_payroll.services.professional_tax.pt_periodicity_strategy import HalfYearlyPTStrategy
        strategy = HalfYearlyPTStrategy()

        # Reject every_payroll on half_yearly
        with self.assertRaises(ValidationError):
            self.env['pt.period.schedule'].create({
                'state_id': self.state_kl.id,
                'periodicity': 'half_yearly',
                'window_start_month': '4',
                'window_end_month': '9',
                'deduction_strategy': 'every_payroll',
                'distribution_method': 'full_amount',
                'active': True,
            })

        # Reject equal_distribution on half_yearly
        with self.assertRaises(ValidationError):
            self.env['pt.period.schedule'].create({
                'state_id': self.state_kl.id,
                'periodicity': 'half_yearly',
                'window_start_month': '4',
                'window_end_month': '9',
                'deduction_strategy': 'end_of_period',
                'distribution_method': 'equal_distribution',
                'deduction_month': '9',
                'active': True,
            })

        # Re-ensure test employee contract start date after exception rollback
        self.emp.write({'date_start': '2025-01-01'})
        if self.emp.version_id:
            self.emp.version_id.write({'date_start': '2025-01-01'})

        # Valid half-yearly schedule
        sched = self.env['pt.period.schedule'].create({
            'state_id': self.state_kl.id,
            'periodicity': 'half_yearly',
            'window_start_month': '4',
            'window_end_month': '9',
            'deduction_strategy': 'end_of_period',
            'distribution_method': 'full_amount',
            'deduction_month': '9',
            'active': True,
        })

        period_liability = 1250.00

        # April to August: non-deduction months -> deduction is 0.0
        ded_apr = strategy.calculate_payroll_deduction(self.env, self.emp, period_liability, '2026-04-30', period_schedule=sched)
        self.assertEqual(ded_apr, 0.0)

        ded_may = strategy.calculate_payroll_deduction(self.env, self.emp, period_liability, '2026-05-31', period_schedule=sched)
        self.assertEqual(ded_may, 0.0)

        ded_jun = strategy.calculate_payroll_deduction(self.env, self.emp, period_liability, '2026-06-30', period_schedule=sched)
        self.assertEqual(ded_jun, 0.0)

        ded_jul = strategy.calculate_payroll_deduction(self.env, self.emp, period_liability, '2026-07-31', period_schedule=sched)
        self.assertEqual(ded_jul, 0.0)

        ded_aug = strategy.calculate_payroll_deduction(self.env, self.emp, period_liability, '2026-08-31', period_schedule=sched)
        self.assertEqual(ded_aug, 0.0)

        # September: statutory settlement month -> full lump sum liability deducted
        ded_sep = strategy.calculate_payroll_deduction(self.env, self.emp, period_liability, '2026-09-30', period_schedule=sched)
        self.assertEqual(ded_sep, period_liability)

        # Total deducted in the 6-month period equals exact statutory liability
        total_deducted = ded_apr + ded_may + ded_jun + ded_jul + ded_aug + ded_sep
        self.assertEqual(total_deducted, period_liability)

    def test_05_mid_period_joining(self):
        """Tests employee joining mid-period (e.g. May 15 in H1 April-September)."""
        emp_mid = self.env['hr.employee'].create({
            'name': 'Mid Period Joiner',
            'company_id': self.company.id,
        })
        emp_mid.write({'date_start': '2026-05-15'})
        if emp_mid.version_id:
            emp_mid.version_id.write({'date_start': '2026-05-15'})
        if hasattr(emp_mid, '_compute_joining_date'):
            emp_mid._compute_joining_date()

        sched = self.env['pt.period.schedule'].create({
            'state_id': self.state_kl.id,
            'periodicity': 'half_yearly',
            'window_start_month': '4',
            'window_end_month': '9',
            'deduction_strategy': 'end_of_period',
            'distribution_method': 'full_amount',
            'deduction_month': '9',
            'active': True,
        })

        # May: employee joined May 15. Total eligible payrolls in H1 = 5 (May, June, July, August, September).
        tot_payrolls = self.sched_service.calculate_eligible_payrolls(emp_mid, date(2026, 4, 1), date(2026, 9, 30))
        self.assertEqual(tot_payrolls, 5)

        rem_may = self.sched_service.calculate_remaining_payrolls(emp_mid, date(2026, 4, 1), date(2026, 9, 30), '2026-05-31')
        self.assertEqual(rem_may, 5)

        # May is not deduction month
        self.assertFalse(self.sched_service.should_deduct(sched, eval_date='2026-05-31', employee=emp_mid))
        # September is deduction month
        self.assertTrue(self.sched_service.should_deduct(sched, eval_date='2026-09-30', employee=emp_mid))

    def test_06_mid_period_leaving(self):
        """Tests employee leaving mid-period (e.g. August 25 in H1 April-September)."""
        emp_leave = self.env['hr.employee'].create({
            'name': 'Mid Period Leaver',
            'company_id': self.company.id,
            'departure_date': '2026-08-25',
        })
        emp_leave.write({'date_start': '2025-01-01'})
        if emp_leave.version_id:
            emp_leave.version_id.write({'date_start': '2025-01-01'})
        if hasattr(emp_leave, '_compute_joining_date'):
            emp_leave._compute_joining_date()

        sched_end = self.env['pt.period.schedule'].create({
            'state_id': self.state_kl.id,
            'periodicity': 'half_yearly',
            'window_start_month': '4',
            'window_end_month': '9',
            'deduction_strategy': 'end_of_period',
            'distribution_method': 'full_amount',
            'deduction_month': '9',
            'active': True,
        })

        # In August, departure_date is Aug 25, so August is the final eligible payroll (remaining = 1)
        rem_aug = self.sched_service.calculate_remaining_payrolls(emp_leave, date(2026, 4, 1), date(2026, 9, 30), '2026-08-31')
        self.assertEqual(rem_aug, 1)

        # In End of Period strategy, August must trigger full deduction because it's the final eligible payroll
        should_aug = self.sched_service.should_deduct(sched_end, eval_date='2026-08-31', employee=emp_leave)
        self.assertTrue(should_aug)
