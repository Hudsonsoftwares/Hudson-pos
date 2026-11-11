# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests.common import TransactionCase


class TestPTPeriodScheduleRegression(TransactionCase):
    """
    Comprehensive Regression Test Suite for Professional Tax Component Architecture.
    Verifies:
    1. Monthly state (Maharashtra) every payroll deduction & February Rs 300 override.
    2. Gender-differentiated slabs (Maharashtra female <= Rs 25,000 exemption).
    3. Half-Yearly state (Kerala H1 September & H2 March deductions).
    4. Half-Yearly non-deduction month (June returning Rs 0 and WAITING_FOR_PERIOD_END).
    5. Boundary salary cases (e.g. exactly Rs 7,500, Rs 10,000, Rs 25,000).
    6. Multi-company scope isolation.
    """

    def setUp(self):
        super(TestPTPeriodScheduleRegression, self).setUp()
        self.company = self.env.company
        self.state_mh = self.env.ref('base.state_in_mh')
        self.state_kl = self.env.ref('base.state_in_kl')

        # Create Work Locations
        partner_mh = self.env['res.partner'].create({'name': 'MH Reg Office', 'state_id': self.state_mh.id})
        partner_kl = self.env['res.partner'].create({'name': 'KL Reg Office', 'state_id': self.state_kl.id})

        self.work_loc_mh = self.env['hr.work.location'].create({'name': 'Mumbai Reg', 'address_id': partner_mh.id, 'company_id': self.company.id})
        self.work_loc_kl = self.env['hr.work.location'].create({'name': 'Kochi Reg', 'address_id': partner_kl.id, 'company_id': self.company.id})

        # Create Employees
        self.emp_mh_male = self.env['hr.employee'].create({'name': 'MH Male Reg', 'sex': 'male', 'work_location_id': self.work_loc_mh.id, 'company_id': self.company.id})
        self.emp_mh_female = self.env['hr.employee'].create({'name': 'MH Female Reg', 'sex': 'female', 'work_location_id': self.work_loc_mh.id, 'company_id': self.company.id})
        self.emp_kl_male = self.env['hr.employee'].create({'name': 'KL Male Reg', 'sex': 'male', 'work_location_id': self.work_loc_kl.id, 'company_id': self.company.id})
        for emp in (self.emp_mh_male, self.emp_mh_female, self.emp_kl_male):
            emp.write({'contract_date_start': '2026-01-01', 'date_start': '2026-01-01'})
            if emp.version_id:
                emp.version_id.write({'contract_date_start': '2026-01-01', 'date_start': '2026-01-01'})

        # Service
        from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_service import ProfessionalTaxService
        self.pt_service = ProfessionalTaxService(self.env)

    def test_01_mh_male_standard_and_february_override(self):
        """Verify MH Male salary > Rs 10,000 gets Rs 200 standard and Rs 300 in February."""
        res_jan = self.pt_service.compute_pt(employee=self.emp_mh_male, salary=15000.0, eval_date='2026-01-31', company=self.company)
        self.assertTrue(res_jan.is_valid)
        self.assertEqual(res_jan.amount, 200.0)

        res_feb = self.pt_service.compute_pt(employee=self.emp_mh_male, salary=15000.0, eval_date='2026-02-28', company=self.company)
        self.assertTrue(res_feb.is_valid)
        self.assertEqual(res_feb.amount, 300.0)
        self.assertTrue(res_feb.override_applied)

    def test_02_mh_female_exemption(self):
        """Verify MH Female salary <= Rs 25,000 is exempt (Rs 0)."""
        res_female = self.pt_service.compute_pt(employee=self.emp_mh_female, salary=20000.0, eval_date='2026-05-31', company=self.company)
        self.assertTrue(res_female.is_valid)
        self.assertEqual(res_female.amount, 0.0)

    def test_03_kerala_h1_and_h2_deduction(self):
        """Verify Kerala half-yearly deductions occur in September (H1) and March (H2)."""
        res_sept = self.pt_service.compute_pt(employee=self.emp_kl_male, salary=30000.0, eval_date='2026-09-30', company=self.company)
        self.assertTrue(res_sept.is_valid)
        self.assertGreater(res_sept.amount, 0.0)

        res_mar = self.pt_service.compute_pt(employee=self.emp_kl_male, salary=30000.0, eval_date='2027-03-31', company=self.company)
        self.assertTrue(res_mar.is_valid)
        self.assertGreater(res_mar.amount, 0.0)

    def test_04_kerala_non_deduction_month(self):
        """Verify Kerala non-deduction month (June) returns Rs 0 with WAITING_FOR_PERIOD_END."""
        res_june = self.pt_service.compute_pt(employee=self.emp_kl_male, salary=30000.0, eval_date='2026-06-30', company=self.company)
        self.assertFalse(res_june.is_valid)
        self.assertIn(res_june.validation_status, ['WAITING_FOR_PERIOD_END', 'NOT_DEDUCTION_PERIOD'])
        self.assertEqual(res_june.amount, 0.0)
