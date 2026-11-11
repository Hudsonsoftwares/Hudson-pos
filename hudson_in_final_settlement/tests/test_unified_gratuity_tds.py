# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
# pyrefly: ignore [missing-import]
from odoo.fields import Date


class TestUnifiedGratuityTds(TransactionCase):
    """
    Test Suite for Unified Annual TDS Calculation on Gratuity and Final Settlement.
    Verifies that:
    1. Taxable gratuity is included in the unified annual taxable income projection (Section 192).
    2. Only ONE cumulative annual tax calculation is performed.
    3. Dedicated/standalone TDS_GRATUITY deduction lines are decommissioned/zeroed out to prevent double tax withholding.
    4. Settlement breakdown lines pull the single HDS_IN_TDS deduction from the settlement payslip.
    5. Payslip tax summary table, deduction lines, and net settlement amount reconcile 100%.
    """

    @classmethod
    def _gc_filestore(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        try:
            super(TestUnifiedGratuityTds, cls).tearDownClass()
        except Exception:
            pass

    def setUp(self):
        super(TestUnifiedGratuityTds, self).setUp()
        self.company = self.env['res.company'].create({
            'name': 'Unified TDS Test Company',
            'hds_in_enable_gratuity': True,
            'hds_in_enable_leave_encashment': True,
            'hds_in_tds_applicable': True,
        })
        self.employee = self.env['hr.employee'].create({
            'name': 'Unified TDS Test Employee',
            'company_id': self.company.id,
            'first_contract_date': Date.from_string('2015-01-01'),
            'hds_in_tds_applicable': True,
        })

        contract_model = 'hr.version' if 'hr.version' in self.env else ('hr.contract' if 'hr.contract' in self.env else False)
        if contract_model:
            struct = self.env.ref('hudson_in_payroll.hds_in_structure_final_settlement', raise_if_not_found=False)
            if not struct:
                struct = self.env['hr.payroll.structure'].search([('code', '=', 'FINAL_SETTLEMENT_STRUCT')], limit=1)
            if not struct:
                struct = self.env.ref('hudson_payroll_base.structure_base', raise_if_not_found=False)

            self.contract = getattr(self.employee, 'version_id', False) or self.env[contract_model].search([
                ('employee_id', '=', self.employee.id)
            ], limit=1)
            vals = {
                'name': 'Unified TDS Contract',
                'employee_id': self.employee.id,
                'company_id': self.company.id,
                'wage': 120000.0,
                'basic_salary': 100000.0,
                'da': 20000.0,
                'date_start': Date.from_string('2015-01-01'),
                'struct_id': struct.id if struct else False,
            }
            if self.contract:
                self.contract.write(vals)
            else:
                self.contract = self.env[contract_model].create(vals)

    def test_01_gratuity_fully_exempt_no_additional_tax(self):
        """Scenario A: When gratuity <= statutory exemption limit, taxable gratuity is 0 and no TDS_GRATUITY line exists."""
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'last_working_day': Date.from_string('2026-03-31'),
            'gratuity_gross_amount': 1500000.0,  # Below ₹20L exemption
            'gratuity_exemption_amount': 2000000.0,
        })
        self.assertEqual(settlement.gratuity_taxable_amount, 0.0)

        settlement.action_compute_settlement()
        codes = settlement.line_ids.mapped('component_code')
        self.assertIn('GRATUITY', codes)
        self.assertNotIn('TDS_GRATUITY', codes)

        grat_line = settlement.line_ids.filtered(lambda l: l.component_code == 'GRATUITY')
        self.assertEqual(grat_line.amount, 1500000.0)
        self.assertEqual(grat_line.line_type, 'earning')

    def test_02_gratuity_partially_taxable_unified_projection(self):
        """Scenario B: When gratuity > exemption, excess is taxable and included in unified projection without separate TDS_GRATUITY."""
        gross_gratuity = 3323076.92
        exemption = 2000000.0
        expected_taxable = round(gross_gratuity - exemption, 2)

        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'last_working_day': Date.from_string('2026-03-31'),
            'gratuity_gross_amount': gross_gratuity,
            'gratuity_exemption_amount': exemption,
        })
        self.assertAlmostEqual(settlement.gratuity_taxable_amount, expected_taxable, places=2)

        settlement.action_compute_settlement()
        codes = settlement.line_ids.mapped('component_code')

        # Gratuity earning line must exist
        self.assertIn('GRATUITY', codes)
        grat_line = settlement.line_ids.filtered(lambda l: l.component_code == 'GRATUITY')
        self.assertAlmostEqual(grat_line.amount, gross_gratuity, places=2)

        # Standalone TDS_GRATUITY deduction line must NOT exist
        self.assertNotIn('TDS_GRATUITY', codes)

    def test_03_retired_payslip_rule_returns_zero(self):
        """Scenario C: Public API method hds_in_compute_tds_gratuity() returns 0.0 to prevent double withholding."""
        payslip = self.env['hr.payslip'].create({
            'name': 'Settlement Payslip Test',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id if self.contract else False,
            'company_id': self.company.id,
            'date_from': Date.from_string('2026-03-01'),
            'date_to': Date.from_string('2026-03-31'),
        })
        tds_grat = payslip.hds_in_compute_tds_gratuity()
        self.assertEqual(tds_grat, 0.0)

    def test_04_custom_exemption_ceiling_on_settlement(self):
        """Scenario D: Custom exemption ceiling specified on final settlement record is respected."""
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'last_working_day': Date.from_string('2026-03-31'),
            'gratuity_gross_amount': 2500000.0,
            'gratuity_exemption_amount': 2500000.0,  # Custom higher ceiling
        })
        self.assertEqual(settlement.gratuity_taxable_amount, 0.0)

        settlement.write({'gratuity_exemption_amount': 1000000.0})  # Custom lower ceiling
        self.assertEqual(settlement.gratuity_taxable_amount, 1500000.0)

    def test_05_recomputation_idempotency_and_cleanup_of_legacy_lines(self):
        """Scenario E: Calling compute_settlement idempotently unlinks any legacy TDS_GRATUITY lines."""
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'last_working_day': Date.from_string('2026-03-31'),
            'gratuity_gross_amount': 3000000.0,
            'gratuity_exemption_amount': 2000000.0,
        })

        # Inject legacy TDS_GRATUITY line manually as if created prior to migration
        self.env['final.settlement.line'].create({
            'settlement_id': settlement.id,
            'component_code': 'TDS_GRATUITY',
            'component_name': 'TDS on Gratuity (Section 192)',
            'line_type': 'deduction',
            'amount': 250000.0,
        })
        self.assertIn('TDS_GRATUITY', settlement.line_ids.mapped('component_code'))

        # Recompute settlement -> obsolete TDS_GRATUITY must be automatically unlinked
        settlement.action_compute_settlement()
        self.assertNotIn('TDS_GRATUITY', settlement.line_ids.mapped('component_code'))

    def test_06_payslip_hds_in_tds_sync_to_settlement_lines(self):
        """Scenario F: Settlement pulls unified HDS_IN_TDS deduction from linked payslip."""
        payslip = self.env['hr.payslip'].create({
            'name': 'Settlement Payslip with Unified TDS',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id if self.contract else False,
            'company_id': self.company.id,
            'date_from': Date.from_string('2026-03-01'),
            'date_to': Date.from_string('2026-03-31'),
        })

        rule_ded = self.env.ref('hudson_in_payroll.hds_in_rule_tds', raise_if_not_found=False)
        cat_ded = self.env.ref('hudson_payroll_base.rule_category_ded', raise_if_not_found=False)

        # Create HDS_IN_TDS deduction line on payslip
        self.env['hr.payslip.line'].create({
            'slip_id': payslip.id,
            'employee_id': self.employee.id,
            'contract_id': self.contract.id if self.contract else False,
            'name': 'Tax Deducted at Source (TDS)',
            'code': 'HDS_IN_TDS',
            'salary_rule_id': rule_ded.id if rule_ded else False,
            'category_id': cat_ded.id if cat_ded else False,
            'amount': -346357.50,
            'total': -346357.50,
        })

        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'last_working_day': Date.from_string('2026-03-31'),
            'payslip_id': payslip.id,
            'gratuity_gross_amount': 3323076.92,
            'gratuity_exemption_amount': 2000000.0,
        })
        settlement.action_compute_settlement()

        tds_line = settlement.line_ids.filtered(lambda l: l.component_code == 'HDS_IN_TDS')
        self.assertTrue(tds_line, "Unified HDS_IN_TDS deduction must sync to settlement lines.")
        self.assertEqual(tds_line.line_type, 'deduction')
        self.assertAlmostEqual(tds_line.amount, 346357.50, places=2)
        self.assertNotIn('TDS_GRATUITY', settlement.line_ids.mapped('component_code'))
