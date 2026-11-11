# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo import fields


class TestTdsPhase5DeductionCalculation(TransactionCase):

    def setUp(self):
        super(TestTdsPhase5DeductionCalculation, self).setUp()
        self.fy = self.env['tds.financial.year'].search([('code', '=', '2025-2026')], limit=1)
        if not self.fy:
            self.fy = self.env['tds.financial.year'].create({
                'name': 'Financial Year 2025-2026',
                'code': '2025-2026',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
                'is_active': True,
            })

        self.regime_old = self.env['tds.tax.regime'].search([('code', '=', 'old')], limit=1)
        if not self.regime_old:
            self.regime_old = self.env['tds.tax.regime'].create({
                'name': 'Old Tax Regime',
                'code': 'old',
                'is_active': True,
            })

        self.regime_new = self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
        if not self.regime_new:
            self.regime_new = self.env['tds.tax.regime'].create({
                'name': 'New Tax Regime (Section 115BAC)',
                'code': 'new',
                'is_active': True,
            })

        self.employee = self.env['hr.employee'].create({
            'name': 'Phase 5 Deduction Test Employee',
            'birthday': '1992-08-20',
        })

    def test_01_standard_deduction_service_old_vs_new(self):
        """Test StandardDeductionService resolving ₹75,000 for New Regime vs ₹50,000 for Old Regime."""
        from hudson_in_payroll.services.tds.standard_deduction_service import StandardDeductionService
        std_svc = StandardDeductionService(self.env)

        # Old Regime: ₹50,000
        std_old = std_svc.calculate_standard_deduction('old', gross_payroll_income=600000.0)
        self.assertEqual(std_old, 50000.0)

        # New Regime: ₹75,000
        std_new = std_svc.calculate_standard_deduction('new', gross_payroll_income=600000.0)
        self.assertEqual(std_new, 75000.0)

        # Capped at gross payroll income if wage < std deduction limit
        std_low = std_svc.calculate_standard_deduction('new', gross_payroll_income=40000.0)
        self.assertEqual(std_low, 40000.0)

    def test_02_chapter6a_deduction_service_regime_restrictions(self):
        """Test Chapter6aDeductionService approving claims in Old Regime and rejecting in New Regime."""
        from hudson_in_payroll.services.tds.chapter6a_deduction_service import Chapter6aDeductionService
        c6a_svc = Chapter6aDeductionService(self.env)

        # Create investment declaration (80C, 80D, 80CCD1B)
        self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'declaration_line_ids': [
                (0, 0, {'category': '80c', 'description': 'PPF Contribution', 'declared_amount': 150000.0}),
                (0, 0, {'category': '80ccd1b', 'description': 'Voluntary NPS', 'declared_amount': 50000.0}),
                (0, 0, {'category': '80d_self', 'description': 'Medical Insurance Self', 'declared_amount': 25000.0}),
            ],
        })

        # Old Regime: Approved Total = 1.5L + 50k + 25k = 2.25L
        c6a_old = c6a_svc.calculate_chapter_6a_deductions(self.employee, self.fy, regime_code='old')
        self.assertEqual(c6a_old.section_80c, 150000.0)
        self.assertEqual(c6a_old.section_80ccd1b, 50000.0)
        self.assertEqual(c6a_old.section_80d, 25000.0)
        self.assertEqual(c6a_old.total_chapter_6a, 225000.0)

        # New Regime: Strictly 0.0
        c6a_new = c6a_svc.calculate_chapter_6a_deductions(self.employee, self.fy, regime_code='new')
        self.assertEqual(c6a_new.total_chapter_6a, 0.0)

    def test_03_deduction_calculation_service_orchestration(self):
        """Test master DeductionCalculationService orchestration and DTO summary generation."""
        from hudson_in_payroll.services.tds.deduction_calculation_service import DeductionCalculationService
        from hudson_in_payroll.services.tds.regime_routing_service import RegimeCalculationContext

        ded_svc = DeductionCalculationService(self.env)
        reg_ctx_old = RegimeCalculationContext(
            regime_code='old',
            gross_total_income=800000.0,
            standard_deduction_limit=50000.0,
            permitted_categories={'80c'},
            prohibited_categories=set(),
            pipeline_slots={}
        )

        summary_old = ded_svc.calculate_deductions(self.employee, self.fy, regime_context=reg_ctx_old)
        self.assertEqual(summary_old.regime_code, 'old')
        self.assertEqual(summary_old.standard_deduction, 50000.0)
        self.assertGreaterEqual(summary_old.total_allowable_deductions, 50000.0)

    def test_04_missing_employee_validation(self):
        """Test error handling when employee or financial year is missing."""
        from hudson_in_payroll.services.tds.deduction_calculation_service import DeductionCalculationService
        ded_svc = DeductionCalculationService(self.env)
        with self.assertRaises(ValidationError):
            ded_svc.calculate_deductions(False, self.fy)
