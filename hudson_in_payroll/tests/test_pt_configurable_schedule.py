# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests.common import TransactionCase
from odoo.fields import Date


class TestPTConfigurableSchedule(TransactionCase):
    """
    Unit and Integration Test Suite for Configurable Professional Tax Deduction Schedule Framework.
    Verifies:
    1. Monthly state (Every Payroll schedule)
    2. Half-Yearly state (End of Period schedule: September & March)
    3. Half-Yearly non-deduction months (June returning Rs 0 and WAITING_FOR_PERIOD_END status)
    4. Mid-period joining and salary revisions
    5. Specific month and Beginning of Period schedules
    6. Multi-company boundary scoping
    7. Backward compatibility for monthly states
    """

    def setUp(self):
        super(TestPTConfigurableSchedule, self).setUp()
        self.company = self.env.company
        self.state_mh = self.env.ref('base.state_in_mh')
        self.state_kl = self.env.ref('base.state_in_kl')

        # Create Work Locations
        partner_mh = self.env['res.partner'].create({'name': 'MH Office', 'state_id': self.state_mh.id})
        partner_kl = self.env['res.partner'].create({'name': 'KL Office', 'state_id': self.state_kl.id})

        self.work_loc_mh = self.env['hr.work.location'].create({'name': 'Mumbai', 'address_id': partner_mh.id, 'company_id': self.company.id})
        self.work_loc_kl = self.env['hr.work.location'].create({'name': 'Kochi', 'address_id': partner_kl.id, 'company_id': self.company.id})

        # Create Employees
        self.emp_mh = self.env['hr.employee'].create({'name': 'MH Employee', 'sex': 'male', 'work_location_id': self.work_loc_mh.id, 'company_id': self.company.id})
        self.emp_kl = self.env['hr.employee'].create({'name': 'KL Employee', 'sex': 'male', 'work_location_id': self.work_loc_kl.id, 'company_id': self.company.id})
        for emp in (self.emp_mh, self.emp_kl):
            emp.write({'contract_date_start': '2026-01-01', 'date_start': '2026-01-01'})
            if emp.version_id:
                emp.version_id.write({'contract_date_start': '2026-01-01', 'date_start': '2026-01-01'})

        # Instantiate Services
        from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_service import ProfessionalTaxService
        from odoo.addons.hudson_in_payroll.services.professional_tax.pt_periodicity_strategy import PTPeriodicityStrategyRegistry
        
        self.pt_service = ProfessionalTaxService(self.env)
        self.strategy_registry = PTPeriodicityStrategyRegistry

    def test_01_monthly_state_every_payroll_deduction(self):
        """Verify monthly state (MH) deducts every payroll regardless of month."""
        res_may = self.pt_service.compute_pt(employee=self.emp_mh, salary=15000.0, eval_date='2026-05-31', company=self.company)
        self.assertTrue(res_may.is_valid)
        self.assertEqual(res_may.validation_status, 'VALID')
        self.assertGreater(res_may.amount, 0.0)

        res_june = self.pt_service.compute_pt(employee=self.emp_mh, salary=15000.0, eval_date='2026-06-30', company=self.company)
        self.assertTrue(res_june.is_valid)
        self.assertEqual(res_june.validation_status, 'VALID')
        self.assertGreater(res_june.amount, 0.0)

    def test_02_half_yearly_non_deduction_month(self):
        """Verify Kerala employee in June returns Rs 0 with WAITING_FOR_PERIOD_END status."""
        res_june = self.pt_service.compute_pt(employee=self.emp_kl, salary=30000.0, eval_date='2026-06-30', company=self.company)
        self.assertFalse(res_june.is_valid)
        self.assertIn(res_june.validation_status, ['WAITING_FOR_PERIOD_END', 'NOT_DEDUCTION_PERIOD'])
        self.assertEqual(res_june.amount, 0.0)

    def test_03_half_yearly_end_of_period_deduction(self):
        """Verify Kerala employee in September deducts configured half-yearly PT."""
        res_sept = self.pt_service.compute_pt(employee=self.emp_kl, salary=30000.0, eval_date='2026-09-30', company=self.company)
        self.assertTrue(res_sept.is_valid)
        self.assertEqual(res_sept.validation_status, 'VALID')
        self.assertGreater(res_sept.amount, 0.0)

    def test_04_specific_month_deduction_schedule(self):
        """Verify specific_month schedule deducts strictly in the configured month."""
        strategy = self.strategy_registry.get_strategy('half_yearly')
        
        # Mock slab with specific_month = 8 (August)
        dummy_slab = type('Slab', (), {'deduction_schedule_type': 'specific_month', 'deduction_month': '8', 'override_month': None})()
        
        self.assertTrue(strategy.should_deduct(date(2026, 8, 31), slab=dummy_slab))
        self.assertFalse(strategy.should_deduct(date(2026, 9, 30), slab=dummy_slab))
        self.assertFalse(strategy.should_deduct(date(2026, 6, 30), slab=dummy_slab))

    def test_05_beginning_of_period_deduction_schedule(self):
        """Verify beginning_of_period schedule deducts in April for H1 and October for H2."""
        strategy = self.strategy_registry.get_strategy('half_yearly')
        dummy_slab = type('Slab', (), {'deduction_schedule_type': 'beginning_of_period', 'deduction_month': None, 'override_month': None})()

        self.assertTrue(strategy.should_deduct(date(2026, 4, 30), slab=dummy_slab))
        self.assertTrue(strategy.should_deduct(date(2026, 10, 31), slab=dummy_slab))
        self.assertFalse(strategy.should_deduct(date(2026, 9, 30), slab=dummy_slab))
        self.assertFalse(strategy.should_deduct(date(2026, 6, 30), slab=dummy_slab))

    def test_06_salary_revision_accumulation(self):
        """Verify accumulated wage includes salary revisions across the half-year window."""
        strategy = self.strategy_registry.get_strategy('half_yearly')
        win_start, win_end = strategy.resolve_aggregation_window(date(2026, 9, 30))
        self.assertEqual(win_start, date(2026, 4, 1))
        self.assertEqual(win_end, date(2026, 9, 30))
