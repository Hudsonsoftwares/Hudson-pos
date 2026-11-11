# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'TestCompanyEmployeeStatutoryLink')
class TestCompanyEmployeeStatutoryLink(TransactionCase):
    """
    Audit and verification test suite for data flow connection:
    Company Emirate -> Jurisdiction -> Jurisdiction Type -> Pension Authority Enablement
    -> Employee Applicable Emirate -> Employee Pension Authority -> Applicable Pension Scheme.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Company = cls.env['res.company']
        cls.Employee = cls.env['hr.employee']
        cls.WorkLocation = cls.env['hr.work.location']
        cls.Emirate = cls.env['uae.emirate']
        cls.Authority = cls.env['uae.pension.authority']
        cls.Scheme = cls.env['uae.pension.scheme']
        cls.Jurisdiction = cls.env['uae.payroll.jurisdiction']
        cls.Country = cls.env['res.country']

        cls.uae = cls.Country.search([('code', '=', 'AE')], limit=1)
        cls.saudi = cls.Country.search([('code', '=', 'SA')], limit=1)

        cls.auh = cls.Emirate.search([('code', '=', 'AUH')], limit=1)
        cls.dxb = cls.Emirate.search([('code', '=', 'DXB')], limit=1)
        cls.shj = cls.Emirate.search([('code', '=', 'SHJ')], limit=1)

        cls.adpf = cls.Authority.search([('code', '=', 'ADPF')], limit=1)
        cls.gpssa = cls.Authority.search([('code', '=', 'GPSSA')], limit=1)

        cls.legacy = cls.Scheme.with_context(active_test=False).search([('code', '=', 'legacy')], limit=1)
        cls.new_law = cls.Scheme.with_context(active_test=False).search([('code', '=', 'new_law')], limit=1)

    def test_01_emirate_master_maps_to_pension_authorities_via_data(self):
        """
        Verify Emirate master correctly maps to pension_authority_id:
        Abu Dhabi resolves to ADPF; other configured Emirates resolve to GPSSA via master data, not hardcoding.
        """
        # AUH -> ADPF
        self.assertTrue(self.auh.pension_authority_id, "Abu Dhabi Emirate must have a mapped pension authority.")
        self.assertEqual(self.auh.pension_authority_id.code, 'ADPF', "Abu Dhabi Emirate must resolve to ADPF.")

        # DXB, SHJ, and all other Emirates -> GPSSA
        for code in ('DXB', 'SHJ', 'AJM', 'UAQ', 'RAK', 'FUJ'):
            emirate = self.Emirate.search([('code', '=', code)], limit=1)
            self.assertTrue(emirate, f"Emirate {code} must exist.")
            self.assertEqual(
                emirate.pension_authority_id.code, 'GPSSA',
                f"Emirate {code} must resolve to GPSSA via master mapping."
            )

    def test_02_employee_emirate_derived_from_company_and_work_location(self):
        """
        Employee Applicable Emirate is correctly derived from company and work location configuration:
        Priority 1: Work Location Emirate
        Priority 2: Company Emirate
        """
        company_auh = self.Company.create({
            'name': 'Abu Dhabi Legal Entity',
            'uae_emirate_id': self.auh.id,
            'hds_ae_enable_adpf': True,
            'hds_ae_adpf_employer_number': 'ADPF-1001',
        })

        # Employee 1: No work location -> derives company emirate (Abu Dhabi)
        emp_comp_default = self.Employee.create({
            'name': 'Employee HQ Abu Dhabi',
            'company_id': company_auh.id,
            'country_id': self.uae.id,
        })
        self.assertEqual(emp_comp_default.uae_emirate_id, self.auh)
        self.assertEqual(emp_comp_default.uae_pension_authority_id, self.adpf)

        # Employee 2: Work location set to Dubai branch -> derives Dubai
        branch_dxb = self.WorkLocation.create({
            'name': 'Dubai Branch Office',
            'company_id': company_auh.id,
            'address_id': company_auh.partner_id.id,
            'uae_emirate_id': self.dxb.id,
        })
        emp_branch = self.Employee.create({
            'name': 'Employee Dubai Branch',
            'company_id': company_auh.id,
            'country_id': self.uae.id,
            'work_location_id': branch_dxb.id,
        })
        self.assertEqual(emp_branch.uae_emirate_id, self.dxb)
        self.assertEqual(emp_branch.uae_pension_authority_id, self.gpssa)

    def test_03_resolved_pension_authority_validated_against_company_enablement(self):
        """
        Resolved Pension Authority is validated against authorities enabled for the Company.
        Resolved Authority = ADPF
        Company ADPF Enabled = False
               ↓
        Validation Status = AUTHORITY_NOT_ENABLED_AT_COMPANY
               ↓
        Show clear warning/status
               ↓
        Block pension calculation/registration when required (e.g. marking verified).
        """
        # Company registered in Abu Dhabi, but ADPF is NOT enabled
        company_auh_unregistered = self.Company.create({
            'name': 'AUH Startup Co (Unregistered)',
            'uae_emirate_id': self.auh.id,
            'hds_ae_enable_adpf': False,
        })

        # Employee record can still exist during onboarding / incomplete setup
        emp = self.Employee.create({
            'name': 'New Joiner UAE National',
            'company_id': company_auh_unregistered.id,
            'country_id': self.uae.id,
        })

        # Derives AUH and ADPF
        self.assertEqual(emp.uae_emirate_id, self.auh)
        self.assertEqual(emp.uae_pension_authority_id, self.adpf)

        # Validation status is authority_not_enabled_at_company and warning is populated
        self.assertEqual(emp.uae_pension_authority_status, 'authority_not_enabled_at_company')
        self.assertTrue(emp.uae_pension_authority_warning)
        self.assertIn("ADPF", emp.uae_pension_authority_warning)
        self.assertIn("is not enabled for company", emp.uae_pension_authority_warning)

        # Attempting to mark statutory status as 'verified' is BLOCKED
        with self.assertRaises(ValidationError) as ctx:
            emp.write({'uae_statutory_status': 'verified'})
        self.assertIn("is not enabled for company", str(ctx.exception))

        # Once company enables ADPF with employer number, status becomes valid
        company_auh_unregistered.write({
            'hds_ae_enable_adpf': True,
            'hds_ae_adpf_employer_number': 'ADPF-7788',
        })
        emp._compute_uae_pension_authority_status()
        self.assertEqual(emp.uae_pension_authority_status, 'valid')
        self.assertFalse(emp.uae_pension_authority_warning)

        # Now marking verified succeeds
        emp.write({'uae_statutory_status': 'verified'})
        self.assertEqual(emp.uae_statutory_status, 'verified')

    def test_04_applicable_pension_schemes_filtered_by_company_enabled_schemes(self):
        """
        Applicable Pension Schemes are filtered by company-enabled schemes:
        If company restricts permitted schemes to New Law only, Legacy cannot be assigned.
        """
        company = self.Company.create({
            'name': 'New Law Only Co',
            'uae_emirate_id': self.dxb.id,
            'hds_ae_enable_gpssa': True,
            'hds_ae_gpssa_employer_number': 'GPSSA-2001',
            'uae_pension_scheme_ids': [(6, 0, [self.new_law.id])],
        })

        # Assigning permitted New Law scheme succeeds
        emp = self.Employee.create({
            'name': 'Employee New Cohort',
            'company_id': company.id,
            'country_id': self.uae.id,
            'uae_pension_scheme_id': self.new_law.id,
        })
        self.assertEqual(emp.uae_pension_scheme_id, self.new_law)

        # Attempting to assign unpermitted Legacy scheme fails validation
        with self.assertRaises(ValidationError) as ctx:
            self.Employee.create({
                'name': 'Employee Incompatible Cohort',
                'company_id': company.id,
                'country_id': self.uae.id,
                'uae_pension_scheme_id': self.legacy.id,
            })
        self.assertIn("is not enabled for company", str(ctx.exception))

    def test_05_applicable_pension_schemes_filtered_by_authority(self):
        """
        Applicable Pension Schemes are filtered by the resolved pension authority:
        A scheme specific to GPSSA cannot be assigned to an employee under ADPF.
        """
        gpssa_only_scheme = self.Scheme.create({
            'name': 'GPSSA Specialized Scheme',
            'code': 'gpssa_spec',
            'pension_authority_ids': [(6, 0, [self.gpssa.id])],
        })

        company_auh = self.Company.create({
            'name': 'Abu Dhabi Entity Co',
            'uae_emirate_id': self.auh.id,
            'hds_ae_enable_adpf': True,
            'hds_ae_adpf_employer_number': 'ADPF-3344',
        })

        # Employee under ADPF cannot be assigned a GPSSA-only scheme
        with self.assertRaises(ValidationError) as ctx:
            self.Employee.create({
                'name': 'ADPF Employee Invalid Scheme',
                'company_id': company_auh.id,
                'country_id': self.uae.id,
                'uae_pension_scheme_id': gpssa_only_scheme.id,
            })
        self.assertIn("which does not match employee's resolved authority", str(ctx.exception))

    def test_06_changing_company_emirate_cascades_to_employees(self):
        """
        Changing Company Emirate correctly affects employee applicability:
        When company changes from Dubai to Abu Dhabi, employees defaulting from company
        have their applicable Emirate and Pension Authority automatically re-evaluated.
        """
        company = self.Company.create({
            'name': 'Relocating Entity',
            'uae_emirate_id': self.dxb.id,
            'hds_ae_enable_gpssa': True,
            'hds_ae_gpssa_employer_number': 'GPSSA-5555',
            'hds_ae_enable_adpf': True,
            'hds_ae_adpf_employer_number': 'ADPF-5555',
        })

        emp = self.Employee.create({
            'name': 'HQ Employee',
            'company_id': company.id,
            'country_id': self.uae.id,
        })
        self.assertEqual(emp.uae_emirate_id, self.dxb)
        self.assertEqual(emp.uae_pension_authority_id, self.gpssa)

        # Company relocates / updates registered Emirate to Abu Dhabi
        company.write({'uae_emirate_id': self.auh.id})

        # Employee applicability is automatically updated
        emp.invalidate_recordset(['uae_emirate_id', 'uae_pension_authority_id'])
        self.assertEqual(emp.uae_emirate_id, self.auh)
        self.assertEqual(emp.uae_pension_authority_id, self.adpf)

    def test_07_jurisdiction_context_pension_authority_resolution(self):
        """
        Verify Pension Authority Resolver driven by configured mapping:
        Applicable Emirate + Applicable Jurisdiction / Jurisdiction Type -> Pension Authority.

        1. Jurisdiction with explicit Pension Authority overrides emirate default.
        2. Jurisdiction without explicit Pension Authority defaults to Emirate mapping.
        3. Validation status (AUTHORITY_NOT_ENABLED_AT_COMPANY) evaluates accurately
           against the authority resolved from the jurisdiction context.
        """
        # Create a specialized jurisdiction in Abu Dhabi that configures GPSSA instead of ADPF
        special_jur_auh_gpssa = self.Jurisdiction.create({
            'name': 'Federal Free Zone in AUH',
            'code': 'AE_FZ_AUH_FEDERAL',
            'jurisdiction_type': 'free_zone',
            'emirate_id': self.auh.id,
            'pension_authority_id': self.gpssa.id,  # Configured override: GPSSA
        })

        company_auh = self.Company.create({
            'name': 'Federal Zone AUH Co',
            'uae_emirate_id': self.auh.id,
            'uae_jurisdiction_type': 'free_zone',
            'uae_jurisdiction_id': special_jur_auh_gpssa.id,
            'hds_ae_enable_gpssa': True,
            'hds_ae_gpssa_employer_number': 'GPSSA-8800',
            'hds_ae_enable_adpf': False,
        })

        # Employee belongs to this company in Abu Dhabi, but under the special GPSSA jurisdiction
        emp = self.Employee.create({
            'name': 'Federal Zone Employee',
            'company_id': company_auh.id,
            'country_id': self.uae.id,
        })

        # Emirate is Abu Dhabi, but Jurisdiction maps to GPSSA!
        self.assertEqual(emp.uae_emirate_id, self.auh)
        self.assertEqual(emp.uae_jurisdiction_id, special_jur_auh_gpssa)
        self.assertEqual(
            emp.uae_pension_authority_id, self.gpssa,
            "Authority must resolve to GPSSA via the Jurisdiction mapping, not ADPF purely from Emirate!"
        )

        # Since company enabled GPSSA, status is valid (and not blocked by disabled ADPF)
        self.assertEqual(emp.uae_pension_authority_status, 'valid')
        self.assertFalse(emp.uae_pension_authority_warning)

    def test_08_jurisdiction_authority_resolution_precedence_mainland_auh(self):
        """
        Verify jurisdiction authority resolution precedence:
        Resolution order:
        1. Employee Applicable Jurisdiction.pension_authority_id
        2. Company Applicable Jurisdiction.pension_authority_id
        3. Employee Applicable Emirate.pension_authority_id
        4. Company Emirate.pension_authority_id

        Current case:
        Emirate = Abu Dhabi -> default ADPF
        Jurisdiction = Mainland Abu Dhabi -> configured GPSSA
        Expected resolved authority must be GPSSA, because jurisdiction-specific mapping overrides Emirate default.
        """
        mainland_auh = self.Jurisdiction.search([('code', '=', 'AE_MAINLAND_AUH')], limit=1)
        self.assertTrue(mainland_auh, "Mainland Abu Dhabi jurisdiction record must exist.")
        self.assertEqual(
            mainland_auh.pension_authority_id, self.gpssa,
            "Mainland Abu Dhabi must be configured with GPSSA pension authority."
        )
        self.assertEqual(
            self.auh.pension_authority_id, self.adpf,
            "Emirate Abu Dhabi must have ADPF as default pension authority."
        )

        # Company with both GPSSA and ADPF enabled for clean testing
        company = self.Company.create({
            'name': 'Abu Dhabi Multi-Authority Co',
            'uae_emirate_id': self.auh.id,
            'hds_ae_enable_gpssa': True,
            'hds_ae_gpssa_employer_number': 'GPSSA-777',
            'hds_ae_enable_adpf': True,
            'hds_ae_adpf_employer_number': 'ADPF-777',
        })

        # 1. Employee with no jurisdiction -> resolves to Abu Dhabi Emirate default (ADPF)
        emp = self.Employee.create({
            'name': 'Emirate-Only Employee',
            'company_id': company.id,
            'country_id': self.uae.id,
            'uae_emirate_id': self.auh.id,
            'uae_jurisdiction_id': False,
        })
        self.assertEqual(emp.uae_pension_authority_id, self.adpf, "Without jurisdiction, should resolve to Emirate ADPF.")

        # 2. Employee selects Mainland Abu Dhabi -> overrides Emirate ADPF with GPSSA
        emp.write({'uae_jurisdiction_id': mainland_auh.id})
        emp.invalidate_recordset(['uae_pension_authority_id'])
        self.assertEqual(
            emp.uae_pension_authority_id, self.gpssa,
            "Mainland Abu Dhabi jurisdiction mapping (GPSSA) must override Emirate default (ADPF)."
        )

        # 3. Test onchange reactivity: changing jurisdiction immediately recomputes authority
        emp_form = self.Employee.new({
            'name': 'UI Onchange Test Employee',
            'company_id': company,
            'country_id': self.uae,
            'uae_emirate_id': self.auh,
            'uae_employee_category': 'uae_national',
        })
        emp_form._compute_uae_pension_authority_id()
        self.assertEqual(emp_form.uae_pension_authority_id, self.adpf)

        # Simulate user selecting Mainland Abu Dhabi in form view
        emp_form.uae_jurisdiction_id = mainland_auh
        emp_form._onchange_uae_jurisdiction_id()
        self.assertEqual(
            emp_form.uae_pension_authority_id, self.gpssa,
            "Onchange on uae_jurisdiction_id must immediately recompute pension authority to GPSSA in UI."
        )

        # 4. Test precedence order:
        # Precedence 2: Company Applicable Jurisdiction over Employee Emirate
        comp_with_jur = self.Company.create({
            'name': 'Company with Jurisdiction',
            'uae_emirate_id': self.auh.id,
            'uae_jurisdiction_id': mainland_auh.id,
            'hds_ae_enable_gpssa': True,
            'hds_ae_gpssa_employer_number': 'GPSSA-888',
        })
        emp_comp_jur = self.Employee.create({
            'name': 'Employee deriving from Company Jurisdiction',
            'company_id': comp_with_jur.id,
            'country_id': self.uae.id,
            'uae_emirate_id': self.auh.id,
        })
        # Resolves to GPSSA via Company Jurisdiction (or employee jurisdiction context defaulted from company)
        self.assertEqual(emp_comp_jur.uae_pension_authority_id, self.gpssa)


