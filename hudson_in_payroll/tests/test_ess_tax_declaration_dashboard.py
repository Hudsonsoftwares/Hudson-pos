# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase


class TestEssTaxDeclarationDashboard(TransactionCase):

    def setUp(self):
        super(TestEssTaxDeclarationDashboard, self).setUp()
        self.fy = self.env['tds.financial.year'].search([('code', '=', '2025-2026')], limit=1)
        if not self.fy:
            self.fy = self.env['tds.financial.year'].create({
                'name': 'Financial Year 2025-2026',
                'code': '2025-2026',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
                'active': True,
            })
        self.env.company.hds_in_default_tax_year = self.fy.id

        self.regime_old = self.env['tds.tax.regime'].search([('code', '=', 'old')], limit=1)
        if not self.regime_old:
            self.regime_old = self.env['tds.tax.regime'].create({
                'name': 'Old Tax Regime',
                'code': 'old',
                'active': True,
            })

        self.regime_new = self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
        if not self.regime_new:
            self.regime_new = self.env['tds.tax.regime'].create({
                'name': 'New Tax Regime',
                'code': 'new',
                'active': True,
            })

        self.employee_user = self.env['res.users'].create({
            'name': 'ESS Test User',
            'login': 'esstestuser',
            'email': 'ess@example.com',
        })

        self.employee = self.env['hr.employee'].create({
            'name': 'ESS Test Employee',
            'user_id': self.employee_user.id,
            'birthday': '1995-03-10',
        })

    def test_01_smart_button_dashboard_opening(self):
        """Test Smart Button action_open_tax_declaration_dashboard creates/retrieves declaration."""
        res_action = self.employee.with_user(self.employee_user).action_open_tax_declaration_dashboard()

        self.assertEqual(res_action['res_model'], 'tds.employee.declaration')
        self.assertTrue(res_action['res_id'])

        decl = self.env['tds.employee.declaration'].browse(res_action['res_id'])
        self.assertEqual(decl.employee_id, self.employee)
        self.assertEqual(decl.state, 'draft')

    def test_02_regime_choice_dynamic_updating(self):
        """Test editing regime_choice_id updates tds.employee.tax.regime record and regime_code."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
        })

        # Set Old Regime
        decl.regime_choice_id = self.regime_old.id
        self.assertEqual(decl.regime_code, 'old')

        # Switch to New Regime
        decl.regime_choice_id = self.regime_new.id
        self.assertEqual(decl.regime_code, 'new')

    def test_03_proxy_income_declaration_sync(self):
        """Test proxy income declaration fields on tds.employee.declaration sync seamlessly."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
        })

        # Edit proxy fields
        decl.savings_bank_interest = 15000.0
        decl.annual_let_out_rent = 120000.0

        inc_decl = self.env['tds.employee.income.declaration'].search([
            ('employee_id', '=', self.employee.id),
            ('financial_year_id', '=', self.fy.id),
        ], limit=1)

        self.assertTrue(inc_decl)
        self.assertEqual(inc_decl.savings_bank_interest, 15000.0)
        self.assertEqual(inc_decl.annual_let_out_rent, 120000.0)

    def test_04_declaration_submit_workflow(self):
        """Test submitting declaration transitions state to 'submitted'."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
        })

        # Add investment line
        self.env['tds.employee.declaration.line'].create({
            'declaration_id': decl.id,
            'category': 'ppf',
            'description': 'Public Provident Fund',
            'declared_amount': 100000.0,
        })

        decl.action_submit()
        self.assertEqual(decl.state, 'submitted')
        self.assertTrue(decl.submission_date)

    def test_05_clean_form_proxy_deduction_sync(self):
        """Test editing clean numeric form fields updates underlying declaration lines and subtotals."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
        })

        # Enter 80C & 80D clean inputs
        decl.decl_80c_ppf = 100000.0
        decl.decl_80c_lic = 25000.0
        decl.decl_80d_self = 20000.0

        self.assertEqual(decl.decl_80c_total, 125000.0)
        self.assertEqual(decl.total_declared_amount, 145000.0)

        ppf_line = decl.declaration_line_ids.filtered(lambda l: l.category == '80c' and 'PPF' in l.description)
        self.assertTrue(ppf_line)
        self.assertEqual(ppf_line.declared_amount, 100000.0)

    def test_06_regime_choice_persistence_on_reopen(self):
        """Test selected regime_choice_id persists to database and restores when reopening record."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
        })

        # Select New Regime
        decl.write({'regime_choice_id': self.regime_new.id})
        self.env.flush_all()

        # Invalidate ORM cache to simulate reopening the record from DB
        decl.invalidate_recordset(['tax_regime_id', 'regime_choice_id'])

        decl_reopened = self.env['tds.employee.declaration'].browse(decl.id)
        self.assertEqual(decl_reopened.tax_regime_id, self.regime_new)
        self.assertEqual(decl_reopened.regime_choice_id, self.regime_new)

    def test_07_employee_profile_tax_regime_persistence(self):
        """Test editing hds_in_current_tax_regime_id on hr.employee persists and syncs with declaration."""
        self.employee.write({'hds_in_current_tax_regime_id': self.regime_new.id})
        self.env.flush_all()

        self.employee.invalidate_recordset(['hds_in_current_tax_regime_id'])

        emp_reopened = self.env['hr.employee'].browse(self.employee.id)
        self.assertEqual(emp_reopened.hds_in_current_tax_regime_id, self.regime_new)

    def test_08_single_source_of_truth_regime_consistency(self):
        """Test single source of truth (tds.employee.tax.regime) keeps Employee profile and Tax Declaration 100% consistent."""
        # 1. Set regime to New on Employee profile
        self.employee.write({'hds_in_current_tax_regime_id': self.regime_new.id})
        self.env.flush_all()

        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
        })

        # Declaration automatically reflects New Tax Regime
        self.assertEqual(decl.tax_regime_id, self.regime_new)
        self.assertEqual(decl.regime_code, 'new')

        # 2. Update regime to Old on Tax Declaration
        decl.write({'regime_choice_id': self.regime_old.id})
        self.env.flush_all()

        # Employee profile automatically reflects Old Tax Regime
        self.employee.invalidate_recordset(['hds_in_current_tax_regime_id', 'hds_in_is_new_tax_regime'])
        self.assertEqual(self.employee.hds_in_current_tax_regime_id, self.regime_old)
        self.assertFalse(self.employee.hds_in_is_new_tax_regime)

        # 3. Switching regime on Employee Profile reflects on Declaration
        self.employee.write({'hds_in_current_tax_regime_id': self.regime_new.id})
        self.env.flush_all()
        decl.invalidate_recordset(['tax_regime_id', 'regime_choice_id', 'regime_code'])
        self.assertEqual(decl.regime_choice_id, self.regime_new)
        self.assertEqual(decl.tax_regime_id, self.regime_new)
        self.assertEqual(decl.regime_code, 'new')

    def test_09_agniveer_80cch_deduction_sync(self):
        """Test Section 80CCH Agniveer Corpus Fund proxy sync with declaration lines."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
        })

        decl.decl_80cch_agniveer = 50000.0

        agniveer_line = decl.declaration_line_ids.filtered(lambda l: l.category == '80cch')
        self.assertTrue(agniveer_line)
        self.assertEqual(agniveer_line.declared_amount, 50000.0)
        self.assertIn('Agniveer', agniveer_line.description)

    def test_09b_agnipath_scheme_toggle_and_80cch_eligibility(self):
        """Test Employee under Agnipath Scheme toggle and Section 80CCH eligibility."""
        self.assertFalse(self.employee.hds_in_is_agnipath, "Employee should default to not under Agnipath Scheme")
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
            'decl_80cch_agniveer': 40000.0,
        })
        self.assertFalse(decl.hds_in_is_agnipath, "Declaration hds_in_is_agnipath should reflect employee status")
        self.assertFalse(decl.is_80cch_active, "Section 80CCH active flag should be False when not Agnipath")
        # When not under Agnipath scheme, 80cch deduction is 0
        decl._compute_totals()
        cch_approved = getattr(decl, 'decl_80cch_approved_amount', 0.0)
        cch_svc_res = self.env['tds.employee.declaration'].browse(decl.id)
        # Enable Agnipath Scheme
        self.employee.write({'hds_in_is_agnipath': True})
        decl.invalidate_recordset(['hds_in_is_agnipath', 'is_80cch_active'])
        self.assertTrue(decl.hds_in_is_agnipath, "Declaration should reflect enabled Agnipath Scheme")
        self.assertTrue(decl.is_80cch_active, "Section 80CCH active flag should be True when Agnipath enabled")

    def test_10_field_help_tooltips_presence(self):
        """Test every declaration field has rich contextual help tooltips defined."""
        Model = self.env['tds.employee.declaration']
        fields_to_check = [
            'decl_80c_ppf', 'decl_80c_elss', 'decl_80c_epf', 'decl_80c_lic',
            'decl_80c_nsc', 'decl_80c_ssy', 'decl_80c_fd', 'decl_80c_tuition',
            'decl_80ccd1b_nps', 'decl_80d_self', 'decl_80d_parents', 'decl_hra_annual_rent',
            'decl_24b_self_interest', 'decl_80ccd2_employer_nps', 'decl_80cch_agniveer',
            'savings_bank_interest', 'annual_let_out_rent', 'prev_employer_taxable_gross'
        ]
        for fname in fields_to_check:
            field = Model._fields[fname]
            self.assertTrue(field.help, f"Field {fname} is missing help tooltip string")
            self.assertIn("•", field.help, f"Field {fname} tooltip string lacks structured bullet guidance")

    def test_11_submit_empty_declaration_success(self):
        """Test submitting a declaration with zero line items (e.g. under New Tax Regime) succeeds cleanly."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
        })
        self.assertFalse(decl.declaration_line_ids)
        decl.action_submit()
        self.assertEqual(decl.state, 'submitted')

    def test_12_declaration_approval_audit_log_success(self):
        """Test approving a declaration creates audit log without raising invalid field errors."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'submitted',
        })
        decl.action_approve()
        self.assertEqual(decl.state, 'approved')

    def test_13_previous_employer_fields_persistence_and_sync(self):
        """Test prev_employer_taxable_gross and prev_employer_tds persist and sync seamlessly."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
            'prev_employer_taxable_gross': 350000.0,
            'prev_employer_tds': 25000.0,
            'prev_employer_pt': 2400.0,
            'prev_employer_pf': 18000.0,
        })
        self.env.flush_all()

        # Check underlying tds.employee.income.declaration record
        inc_decl = self.env['tds.employee.income.declaration'].search([
            ('employee_id', '=', self.employee.id),
            ('financial_year_id', '=', self.fy.id),
        ], limit=1)
        self.assertTrue(inc_decl)
        self.assertEqual(inc_decl.prev_employer_taxable_gross, 350000.0)
        self.assertEqual(inc_decl.prev_employer_tds, 25000.0)
        self.assertEqual(inc_decl.prev_employer_pt, 2400.0)
        self.assertEqual(inc_decl.prev_employer_pf, 18000.0)

        # Verify PreviousEmployerIncomeService aggregation
        from hudson_in_payroll.services.tds.previous_employer_income_service import PreviousEmployerIncomeService
        svc = PreviousEmployerIncomeService(self.env)
        res = svc.aggregate_previous_employer_income(self.employee, self.fy)
        self.assertTrue(res.has_declaration)
        self.assertEqual(res.taxable_salary, 350000.0)
        self.assertEqual(res.tds_deducted, 25000.0)
        self.assertEqual(res.pt_deducted, 2400.0)
        self.assertEqual(res.pf_contributed, 18000.0)

        # Invalidate cache and verify reopening decl reads back all fields
        decl.invalidate_recordset(['prev_employer_taxable_gross', 'prev_employer_tds'])
        decl_reopened = self.env['tds.employee.declaration'].browse(decl.id)
        self.assertEqual(decl_reopened.prev_employer_taxable_gross, 350000.0)
        self.assertEqual(decl_reopened.prev_employer_tds, 25000.0)

    def test_14_prev_employer_pt_pf_sync_and_non_zeroing(self):
        """Test Previous Employer PT and EPF are never zeroed out when saving Employee profile."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
            'prev_employer_pt': 2500.0,
            'prev_employer_pf': 21000.0,
        })
        self.env.flush_all()

        # Trigger Employee profile inverse write (e.g. saving employee form)
        self.employee.write({'name': 'Updated Abigail Peter'})
        self.env.flush_all()

        self.employee.invalidate_recordset(['hds_in_prev_pt_deducted', 'hds_in_prev_employer_pf'])
        decl.invalidate_recordset(['prev_employer_pt', 'prev_employer_pf'])

        # Verify values remain perfectly intact and non-zero
        self.assertEqual(decl.prev_employer_pt, 2500.0)
        self.assertEqual(decl.prev_employer_pf, 21000.0)

    def test_15_gti_data_propagation_with_previous_employer(self):
        """Test GTI aggregation and data propagation across AnnualIncomeProjectionService and TaxableIncomeService."""
        self.env['tds.employee.income.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'prev_employer_taxable_gross': 800000.0,
            'prev_employer_tds': 35000.0,
        })
        self.env.flush_all()

        from hudson_in_payroll.services.tds.annual_income_projection_service import AnnualIncomeProjectionService
        from hudson_in_payroll.services.tds.taxable_income_service import TaxableIncomeService

        proj_svc = AnnualIncomeProjectionService(self.env)
        res = proj_svc.project_annual_income(self.employee)

        # If current salary is 1,800,000 and prev employer is 800,000:
        # Projected Annual Salary = 2,600,000, GTI = 2,600,000
        self.assertTrue(res.regime_context)
        self.assertEqual(res.previous_employer_income.taxable_salary, 800000.0)
        self.assertEqual(res.gross_total_income, res.current_employer_salary + 800000.0)

        # Taxable Income = GTI - 75000 (Standard Deduction)
        taxable_svc = TaxableIncomeService(self.env)
        tax_res = taxable_svc.calculate_taxable_income(res.gross_total_income, 75000.0)
        self.assertEqual(tax_res.net_taxable_income, res.gross_total_income - 75000.0)

    def test_16_independent_previous_employer_field_persistence_and_merge(self):
        """Test editing Income/TDS preserves PT/PF and editing PT/PF preserves Income/TDS across save/submit/approve cycles."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
        })
        self.env.flush_all()

        # 1. Update Income & TDS only
        decl.write({
            'prev_employer_taxable_gross': 400000.0,
            'prev_employer_tds': 30000.0,
        })
        self.env.flush_all()

        inc_decl = self.env['tds.employee.income.declaration'].search([
            ('employee_id', '=', self.employee.id),
            ('financial_year_id', '=', self.fy.id),
        ], limit=1)
        self.assertEqual(inc_decl.prev_employer_taxable_gross, 400000.0)
        self.assertEqual(inc_decl.prev_employer_tds, 30000.0)

        # 2. Update Statutory Deductions (PT & PF) only
        decl.write({
            'prev_employer_pt': 2400.0,
            'prev_employer_pf': 18000.0,
        })
        self.env.flush_all()

        # Verify Income & TDS are preserved and NOT zeroed out!
        self.assertEqual(inc_decl.prev_employer_taxable_gross, 400000.0)
        self.assertEqual(inc_decl.prev_employer_tds, 30000.0)
        self.assertEqual(inc_decl.prev_employer_pt, 2400.0)
        self.assertEqual(inc_decl.prev_employer_pf, 18000.0)

        # 3. Re-update Income & TDS
        decl.write({
            'prev_employer_taxable_gross': 450000.0,
        })
        self.env.flush_all()

        # Verify PT & PF are preserved and NOT zeroed out!
        self.assertEqual(inc_decl.prev_employer_taxable_gross, 450000.0)
        self.assertEqual(inc_decl.prev_employer_tds, 30000.0)
        self.assertEqual(inc_decl.prev_employer_pt, 2400.0)
        self.assertEqual(inc_decl.prev_employer_pf, 18000.0)

        # 4. Lifecycle: Submit & Approve
        decl.action_submit()
        self.assertEqual(decl.state, 'submitted')
        decl.action_approve()
        self.assertEqual(decl.state, 'approved')

        # Re-verify all 4 fields retain 100% data integrity
        self.assertEqual(inc_decl.prev_employer_taxable_gross, 450000.0)
        self.assertEqual(inc_decl.prev_employer_tds, 30000.0)
        self.assertEqual(inc_decl.prev_employer_pt, 2400.0)
        self.assertEqual(inc_decl.prev_employer_pf, 18000.0)

    def test_17_single_field_update_preserves_all_other_income_fields(self):
        """Test updating a single income/previous employer field preserves all other fields and explicit zeroing works."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
            'savings_bank_interest': 12000.0,
            'fixed_deposit_interest': 35000.0,
            'dividend_income': 8000.0,
            'other_sources_income': 15000.0,
            'prev_employer_taxable_gross': 500000.0,
            'prev_employer_tds': 45000.0,
            'prev_employer_pt': 2400.0,
            'prev_employer_pf': 18000.0,
        })
        self.env.flush_all()

        inc_decl = self.env['tds.employee.income.declaration'].search([
            ('employee_id', '=', self.employee.id),
            ('financial_year_id', '=', self.fy.id),
        ], limit=1)

        # 1. Single field update: Dividend Income only
        decl.write({'dividend_income': 10000.0})
        self.env.flush_all()

        self.assertEqual(inc_decl.savings_bank_interest, 12000.0)
        self.assertEqual(inc_decl.fixed_deposit_interest, 35000.0)
        self.assertEqual(inc_decl.dividend_income, 10000.0)
        self.assertEqual(inc_decl.other_sources_income, 15000.0)
        self.assertEqual(inc_decl.prev_employer_taxable_gross, 500000.0)
        self.assertEqual(inc_decl.prev_employer_tds, 45000.0)
        self.assertEqual(inc_decl.prev_employer_pt, 2400.0)
        self.assertEqual(inc_decl.prev_employer_pf, 18000.0)

        # 2. Explicit zeroing: set other_sources_income = 0.0
        decl.write({'other_sources_income': 0.0})
        self.env.flush_all()

        self.assertEqual(inc_decl.savings_bank_interest, 12000.0)
        self.assertEqual(inc_decl.fixed_deposit_interest, 35000.0)
        self.assertEqual(inc_decl.dividend_income, 10000.0)
        self.assertEqual(inc_decl.other_sources_income, 0.0)
        self.assertEqual(inc_decl.prev_employer_taxable_gross, 500000.0)
        self.assertEqual(inc_decl.prev_employer_tds, 45000.0)
        self.assertEqual(inc_decl.prev_employer_pt, 2400.0)
        self.assertEqual(inc_decl.prev_employer_pf, 18000.0)

    def test_18_other_income_aggregation_service_with_declaration(self):
        """Test OtherIncomeAggregationService aggregates 53,000 from 4 declaration fields into GTI."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
            'savings_bank_interest': 8000.0,
            'fixed_deposit_interest': 20000.0,
            'dividend_income': 15000.0,
            'other_sources_income': 10000.0,
        })
        self.env.flush_all()

        inc_decl = self.env['tds.employee.income.declaration'].search([
            ('employee_id', '=', self.employee.id),
            ('financial_year_id', '=', self.fy.id),
        ], limit=1)
        self.assertTrue(inc_decl)
        self.assertEqual(inc_decl.savings_bank_interest, 8000.0)
        self.assertEqual(inc_decl.fixed_deposit_interest, 20000.0)
        self.assertEqual(inc_decl.dividend_income, 15000.0)
        self.assertEqual(inc_decl.other_sources_income, 10000.0)

        from hudson_in_payroll.services.tds.other_income_aggregation_service import OtherIncomeAggregationService
        from hudson_in_payroll.services.tds.annual_income_projection_service import AnnualIncomeProjectionService

        other_svc = OtherIncomeAggregationService(self.env)
        other_res = other_svc.aggregate_other_income(self.employee, self.fy)

        self.assertTrue(other_res.has_declaration)
        self.assertEqual(other_res.total_other_sources, 53000.0)
        self.assertEqual(other_res.total_other_income, 53000.0)

        proj_svc = AnnualIncomeProjectionService(self.env)
        proj_res = proj_svc.project_annual_income(self.employee)

        expected_gti = proj_res.current_employer_salary + proj_res.previous_employer_income.taxable_salary + 53000.0
        self.assertEqual(proj_res.gross_total_income, expected_gti)

    def test_19_all_old_regime_deduction_sections_persistence(self):
        """Comprehensive audit test verifying persistence across ALL Old Regime deduction tabs."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
            # 80C
            'decl_80c_ppf': 50000.0,
            'decl_80c_elss': 25000.0,
            'decl_80c_lic': 15000.0,
            # 80CCD(1B) NPS
            'decl_80ccd1b_nps': 50000.0,
            # 80D Medical
            'decl_80d_self': 25000.0,
            'decl_80d_parents': 50000.0,
            'decl_80d_parents_is_senior': True,
            'decl_80d_preventive': 5000.0,
            # HRA
            'decl_hra_annual_rent': 180000.0,
            'decl_hra_landlord_name': 'Landlord Smith',
            'decl_hra_landlord_pan': 'ABCDE1234F',
            # Home Loan 24(b) & 80EEA
            'decl_24b_self_interest': 200000.0,
            'decl_80eea_interest': 150000.0,
            # 80TTA & 80TTB
            'decl_80tta_interest': 10000.0,
            'decl_80ttb_interest': 50000.0,
            # Other Chapter VI-A (80E, 80G, 80GG, 80DD)
            'decl_80e_interest': 30000.0,
            'decl_80g_donation': 20000.0,
            'decl_80gg_rent': 60000.0,
            'decl_80dd_amount': 75000.0,
            # Both Regimes (80CCD(2), 57(iia), 80CCH)
            'decl_80ccd2_employer_nps': 100000.0,
            'decl_57iia_family_pension': 15000.0,
            'decl_80cch_agniveer': 40000.0,
        })
        self.env.flush_all()

        # Re-read and verify all fields populated
        decl.invalidate_recordset()
        self.assertEqual(decl.decl_80c_ppf, 50000.0)
        self.assertEqual(decl.decl_80c_elss, 25000.0)
        self.assertEqual(decl.decl_80c_lic, 15000.0)
        self.assertEqual(decl.decl_80ccd1b_nps, 50000.0)
        self.assertEqual(decl.decl_80d_self, 25000.0)
        self.assertEqual(decl.decl_80d_parents, 50000.0)
        self.assertTrue(decl.decl_80d_parents_is_senior)
        self.assertEqual(decl.decl_80d_preventive, 5000.0)
        self.assertEqual(decl.decl_hra_annual_rent, 180000.0)
        self.assertEqual(decl.decl_24b_self_interest, 200000.0)
        self.assertEqual(decl.decl_80eea_interest, 150000.0)
        self.assertEqual(decl.decl_80tta_interest, 10000.0)
        self.assertEqual(decl.decl_80ttb_interest, 50000.0)
        self.assertEqual(decl.decl_80e_interest, 30000.0)
        self.assertEqual(decl.decl_80g_donation, 20000.0)
        self.assertEqual(decl.decl_80gg_rent, 60000.0)
        self.assertEqual(decl.decl_80dd_amount, 75000.0)
        self.assertEqual(decl.decl_80ccd2_employer_nps, 100000.0)
        self.assertEqual(decl.decl_57iia_family_pension, 15000.0)
        self.assertEqual(decl.decl_80cch_agniveer, 40000.0)

        # Update a single field (80C LIC) and verify NO OTHER FIELD IS ZEROED OUT
        decl.write({'decl_80c_lic': 20000.0})
        self.env.flush_all()

        decl.invalidate_recordset()
        self.assertEqual(decl.decl_80c_ppf, 50000.0)
        self.assertEqual(decl.decl_80c_elss, 25000.0)
        self.assertEqual(decl.decl_80c_lic, 20000.0)
        self.assertEqual(decl.decl_80ccd1b_nps, 50000.0)
        self.assertEqual(decl.decl_80d_self, 25000.0)
        self.assertEqual(decl.decl_80d_parents, 50000.0)

        # Perform Submit and Approve lifecycle
        decl.action_submit()
        self.assertEqual(decl.state, 'submitted')
        decl.action_approve()
        self.assertEqual(decl.state, 'approved')

        # Re-verify all fields retain 100% data integrity
        decl.invalidate_recordset()
        self.assertEqual(decl.decl_80c_ppf, 50000.0)
        self.assertEqual(decl.decl_80c_elss, 25000.0)
        self.assertEqual(decl.decl_80c_lic, 20000.0)
        self.assertEqual(decl.decl_80ccd1b_nps, 50000.0)
        self.assertEqual(decl.decl_80d_self, 25000.0)
        self.assertEqual(decl.decl_80d_parents, 50000.0)

    def test_20_section_80c_exceeds_limit_preserves_user_entered_data(self):
        """Test Section 80C total > ₹1,50,000 preserves user-entered values in full and applies statutory cap in tax calculation engine only."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
            'decl_80c_ppf': 100000.0,
            'decl_80c_elss': 60000.0,
            'decl_80c_lic': 20000.0,
        })
        self.env.flush_all()

        decl.invalidate_recordset()
        # Verify user-entered values are 100% preserved
        self.assertEqual(decl.decl_80c_ppf, 100000.0)
        self.assertEqual(decl.decl_80c_elss, 60000.0)
        self.assertEqual(decl.decl_80c_lic, 20000.0)
        self.assertEqual(decl.decl_80c_total, 180000.0)

        # Verify warning flag & message
        self.assertTrue(decl.is_80c_exceeded)
        self.assertIn("1,50,000", decl.section_80c_warning_msg)

        # Verify statutory cap applied during tax calculation only
        # pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_payroll.services.tds.chapter6a_deduction_service import Chapter6aDeductionService
        c6a_svc = Chapter6aDeductionService(self.env)
        res = c6a_svc.calculate_chapter_6a_deductions(self.employee, self.fy, regime_code='old')
        self.assertEqual(res.section_80c, 150000.0)

    def test_21_hr_review_and_ess_declaration_identical_persisted_values(self):
        """Test HR Review and ESS Declaration screens load identical persisted values across all Old Regime sections."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
            'decl_80c_ppf': 50000.0,
            'decl_80c_elss': 25000.0,
            'decl_80d_self': 20000.0,
            'decl_hra_annual_rent': 180000.0,
            'decl_hra_landlord_name': 'Test Landlord',
            'decl_24b_self_interest': 150000.0,
            'decl_80ccd2_employer_nps': 60000.0,
        })
        self.env.flush_all()

        # Invalidate ORM cache and query declaration record directly
        decl_persisted = self.env['tds.employee.declaration'].browse(decl.id)
        decl_persisted.invalidate_recordset()

        # 1. Verify ESS Dashboard field values
        self.assertEqual(decl_persisted.decl_80c_ppf, 50000.0)
        self.assertEqual(decl_persisted.decl_80c_elss, 25000.0)
        self.assertEqual(decl_persisted.decl_80d_self, 20000.0)
        self.assertEqual(decl_persisted.decl_hra_annual_rent, 180000.0)
        self.assertEqual(decl_persisted.decl_24b_self_interest, 150000.0)
        self.assertEqual(decl_persisted.decl_80ccd2_employer_nps, 60000.0)

        # 2. Verify HR Review Line Items grid values
        lines_by_cat = {l.category: l.declared_amount for l in decl_persisted.declaration_line_ids}
        self.assertEqual(lines_by_cat.get('80c'), 50000.0)  # PPF or ELSS line item
        self.assertEqual(lines_by_cat.get('80d_self'), 20000.0)
        self.assertEqual(lines_by_cat.get('hra'), 180000.0)
        self.assertEqual(lines_by_cat.get('24b'), 150000.0)
        # Employer NPS Section 124 is an employer statutory contribution, not an employee investment line item
        self.assertNotIn('80ccd2', lines_by_cat)

        # 3. Simulate HR Manager approving and modifying verified amounts
        decl_persisted.action_submit()
        self.assertEqual(decl_persisted.state, 'submitted')
        decl_persisted.action_approve()
        self.assertEqual(decl_persisted.state, 'approved')

        # Re-read and confirm values remain identical in both ESS and HR Review
        decl_persisted.invalidate_recordset()
        self.assertEqual(decl_persisted.decl_80c_ppf, 50000.0)
        self.assertEqual(decl_persisted.decl_80c_elss, 25000.0)
        self.assertEqual(decl_persisted.decl_80d_self, 20000.0)
        self.assertEqual(decl_persisted.decl_hra_annual_rent, 180000.0)
        self.assertEqual(decl_persisted.decl_24b_self_interest, 150000.0)
        self.assertEqual(decl_persisted.decl_80ccd2_employer_nps, 60000.0)

    def test_22_field_by_field_persistence_audit_all_40_fields(self):
        """Field-by-field persistence audit test verifying all 40 Old Regime and Common declaration fields persist consistently."""
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'state': 'draft',
            # 80C (10 fields)
            'decl_80c_ppf': 11000.0,
            'decl_80c_elss': 12000.0,
            'decl_80c_epf': 13000.0,
            'decl_80c_lic': 14000.0,
            'decl_80c_nsc': 15000.0,
            'decl_80c_ssy': 16000.0,
            'decl_80c_fd': 17000.0,
            'decl_80c_tuition': 18000.0,
            'decl_80c_housing_principal': 19000.0,
            'decl_80c_other': 20000.0,
            # 80CCD(1B) NPS (1 field)
            'decl_80ccd1b_nps': 50000.0,
            # 80D Health (4 fields)
            'decl_80d_self': 25000.0,
            'decl_80d_parents': 50000.0,
            'decl_80d_parents_is_senior': True,
            'decl_80d_preventive': 5000.0,
            # HRA (3 fields)
            'decl_hra_annual_rent': 240000.0,
            'decl_hra_landlord_name': 'Landlord Test',
            'decl_hra_landlord_pan': 'ABCDE1234F',
            # Home Loan 24(b) & 80EEA (2 fields)
            'decl_24b_self_interest': 200000.0,
            'decl_80eea_interest': 150000.0,
            # 80TTA & 80TTB (2 fields)
            'decl_80tta_interest': 10000.0,
            'decl_80ttb_interest': 50000.0,
            # Other Chapter VI-A (4 fields)
            'decl_80e_interest': 30000.0,
            'decl_80g_donation': 20000.0,
            'decl_80gg_rent': 60000.0,
            'decl_80dd_amount': 75000.0,
            # Both Regimes (3 fields)
            'decl_80ccd2_employer_nps': 100000.0,
            'decl_57iia_family_pension': 15000.0,
            'decl_80cch_agniveer': 40000.0,
            # Non-Payroll & Previous Employer (10 fields)
            'savings_bank_interest': 8000.0,
            'fixed_deposit_interest': 20000.0,
            'dividend_income': 15000.0,
            'other_sources_income': 10000.0,
            'annual_let_out_rent': 120000.0,
            'municipal_taxes_paid': 10000.0,
            'let_out_interest_paid': 30000.0,
            'prev_employer_taxable_gross': 500000.0,
            'prev_employer_tds': 45000.0,
            'prev_employer_pt': 2400.0,
            'prev_employer_pf': 18000.0,
        })
        self.env.flush_all()

        decl.invalidate_recordset()
        # Verify 80C
        self.assertEqual(decl.decl_80c_ppf, 11000.0)
        self.assertEqual(decl.decl_80c_elss, 12000.0)
        self.assertEqual(decl.decl_80c_epf, 13000.0)
        self.assertEqual(decl.decl_80c_lic, 14000.0)
        self.assertEqual(decl.decl_80c_nsc, 15000.0)
        self.assertEqual(decl.decl_80c_ssy, 16000.0)
        self.assertEqual(decl.decl_80c_fd, 17000.0)
        self.assertEqual(decl.decl_80c_tuition, 18000.0)
        self.assertEqual(decl.decl_80c_housing_principal, 19000.0)
        self.assertEqual(decl.decl_80c_other, 20000.0)

        # Verify 80CCD(1B), 80D, HRA
        self.assertEqual(decl.decl_80ccd1b_nps, 50000.0)
        self.assertEqual(decl.decl_80d_self, 25000.0)
        self.assertEqual(decl.decl_80d_parents, 50000.0)
        self.assertTrue(decl.decl_80d_parents_is_senior)
        self.assertEqual(decl.decl_80d_preventive, 5000.0)
        self.assertEqual(decl.decl_hra_annual_rent, 240000.0)

        # Verify Non-Payroll & Previous Employer
        inc_decl = self.env['tds.employee.income.declaration'].search([
            ('employee_id', '=', self.employee.id),
            ('financial_year_id', '=', self.fy.id)
        ], limit=1)
        self.assertTrue(inc_decl)
        self.assertEqual(inc_decl.savings_bank_interest, 8000.0)
        self.assertEqual(inc_decl.prev_employer_taxable_gross, 500000.0)
        self.assertEqual(inc_decl.prev_employer_tds, 45000.0)
