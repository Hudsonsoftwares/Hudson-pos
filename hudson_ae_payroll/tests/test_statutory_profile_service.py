# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import common, tagged
from ..services.statutory_profile_service import UAEStatutoryProfileService


@tagged('post_install', '-at_install')
class TestUAEStatutoryProfileService(common.TransactionCase):

    def setUp(self):
        super(TestUAEStatutoryProfileService, self).setUp()
        self.service = UAEStatutoryProfileService(self.env)
        self.country_ae = self.env.ref('base.ae', raise_if_not_found=False) or self.env['res.country'].search([('code', '=', 'AE')], limit=1)
        if not self.country_ae:
            self.country_ae = self.env['res.country'].create({'name': 'United Arab Emirates', 'code': 'AE'})

        self.country_sa = self.env.ref('base.sa', raise_if_not_found=False) or self.env['res.country'].search([('code', '=', 'SA')], limit=1)
        if not self.country_sa:
            self.country_sa = self.env['res.country'].create({'name': 'Saudi Arabia', 'code': 'SA'})

        self.country_qa = self.env.ref('base.qa', raise_if_not_found=False) or self.env['res.country'].search([('code', '=', 'QA')], limit=1)
        if not self.country_qa:
            self.country_qa = self.env['res.country'].create({'name': 'Qatar', 'code': 'QA'})

        self.country_in = self.env.ref('base.in', raise_if_not_found=False) or self.env['res.country'].search([('code', '=', 'IN')], limit=1)
        if not self.country_in:
            self.country_in = self.env['res.country'].create({'name': 'India', 'code': 'IN'})

        # Load master data refs
        self.emirate_dxb = self.env.ref('hudson_ae_payroll.emirate_dxb', raise_if_not_found=False) or self.env['uae.emirate'].search([('code', '=', 'DXB')], limit=1)
        self.emirate_auh = self.env.ref('hudson_ae_payroll.emirate_auh', raise_if_not_found=False) or self.env['uae.emirate'].search([('code', '=', 'AUH')], limit=1)

        self.mohre = self.env.ref('hudson_ae_payroll.labour_authority_mohre', raise_if_not_found=False) or self.env['uae.labour.authority'].search([('code', '=', 'MOHRE')], limit=1)
        self.difc_auth = self.env.ref('hudson_ae_payroll.labour_authority_difc', raise_if_not_found=False) or self.env['uae.labour.authority'].search([('code', '=', 'DIFC_AUTH')], limit=1)

        self.jur_mainland_dxb = self.env.ref('hudson_ae_payroll.jurisdiction_mainland_dxb', raise_if_not_found=False) or self.env['uae.payroll.jurisdiction'].search([('code', '=', 'AE_MAINLAND_DXB')], limit=1)
        self.jur_fz_difc = self.env.ref('hudson_ae_payroll.jurisdiction_fz_difc', raise_if_not_found=False) or self.env['uae.payroll.jurisdiction'].search([('code', '=', 'AE_FZ_DIFC')], limit=1)

        self.gpssa = self.env.ref('hudson_ae_payroll.pension_authority_gpssa', raise_if_not_found=False) or self.env['uae.pension.authority'].search([('code', '=', 'GPSSA')], limit=1)
        self.adpf = self.env.ref('hudson_ae_payroll.pension_authority_adpf', raise_if_not_found=False) or self.env['uae.pension.authority'].search([('code', '=', 'ADPF')], limit=1)

        # Ensure emirates have pension authorities linked
        if self.emirate_auh and self.adpf and not self.emirate_auh.pension_authority_id:
            self.emirate_auh.pension_authority_id = self.adpf
        if self.emirate_dxb and self.gpssa and not self.emirate_dxb.pension_authority_id:
            self.emirate_dxb.pension_authority_id = self.gpssa

    def test_01_scenario_1_mainland_expatriate(self):
        """
        Scenario 1:
        Company: UAE, Private Sector, Mainland, Dubai
        Employee: Expatriate (Nationality: India)
        Expected: Profile resolves company & employee context without financial calculations.
        """
        company = self.env['res.company'].create({
            'name': 'Dubai Mainland Trading LLC',
            'country_id': self.country_ae.id,
            'uae_employment_sector': 'private',
            'uae_jurisdiction_id': self.jur_mainland_dxb.id if self.jur_mainland_dxb else False,
            'uae_jurisdiction_type': 'mainland',
            'uae_emirate_id': self.emirate_dxb.id if self.emirate_dxb else False,
            'uae_labour_authority_id': self.mohre.id if self.mohre else False,
        })

        employee = self.env['hr.employee'].create({
            'name': 'John Doe',
            'company_id': company.id,
            'country_id': self.country_in.id,
            'uae_overtime_eligibility': 'eligible',
            'uae_statutory_status': 'verified',
            'uae_continuous_service_start_date': fields.Date.from_string('2023-01-15'),
        })

        profile = self.service.get_statutory_profile(company, employee)

        self.assertEqual(profile['country'], 'AE')
        self.assertTrue(profile['is_uae_company'])
        self.assertEqual(profile['employment_sector'], 'private')
        self.assertEqual(profile['jurisdiction']['type'], 'mainland')
        if profile['emirate']:
            self.assertEqual(profile['emirate']['code'], 'DXB')
        self.assertEqual(profile['employee_category'], 'expatriate')
        self.assertEqual(profile['pension_registration_status'], 'not_applicable')
        self.assertIsNone(profile['pension_authority'])
        self.assertEqual(profile['continuous_service_start_date'], '2023-01-15')
        self.assertEqual(profile['statutory_status'], 'verified')
        self.assertNotIn('wage', profile)
        self.assertNotIn('basic_salary', profile)
        self.assertNotIn('pension_contribution', profile)

    def test_02_scenario_2_uae_national_pension_registered(self):
        """
        Scenario 2:
        Company: UAE, Private Sector, Mainland
        Employee: UAE National (country_id = AE), Pension Registration = Registered
        Expected: Context includes pension registration details and resolves GPSSA authority from Dubai emirate.
        """
        company = self.env['res.company'].create({
            'name': 'UAE National Services LLC',
            'country_id': self.country_ae.id,
            'uae_employment_sector': 'private',
            'uae_jurisdiction_type': 'mainland',
            'uae_emirate_id': self.emirate_dxb.id if self.emirate_dxb else False,
            'hds_ae_enable_gpssa': True,
            'hds_ae_gpssa_employer_number': 'GPSSA-1234',
        })

        employee = self.env['hr.employee'].create({
            'name': 'Rashid Al-Maktoum',
            'company_id': company.id,
            'country_id': self.country_ae.id,
            'uae_pension_registration_status': 'registered',
            'uae_pension_registration_number': 'GPSSA-7890123',
            'uae_continuous_service_start_date': fields.Date.from_string('2022-06-01'),
            'uae_statutory_status': 'verified',
        })

        profile = self.service.get_statutory_profile(company, employee)

        self.assertEqual(profile['employee_category'], 'uae_national')
        self.assertEqual(profile['pension_registration_status'], 'registered')
        self.assertEqual(profile['pension_registration_number'], 'GPSSA-7890123')
        if self.gpssa:
            self.assertIsNotNone(profile['pension_authority'])
            self.assertEqual(profile['pension_authority']['code'], 'GPSSA')
            self.assertEqual(profile['pension_authority']['authority_type'], 'federal')

    def test_03_scenario_3_free_zone_expatriate(self):
        """
        Scenario 3:
        Company: UAE, Private Sector, Free Zone (DIFC)
        Employee: Expatriate
        Expected: Free-zone jurisdiction is preserved in statutory profile.
        """
        company = self.env['res.company'].create({
            'name': 'DIFC Capital Advisors Ltd',
            'country_id': self.country_ae.id,
            'uae_employment_sector': 'private',
            'uae_jurisdiction_id': self.jur_fz_difc.id if self.jur_fz_difc else False,
            'uae_jurisdiction_type': 'free_zone',
            'uae_emirate_id': self.emirate_dxb.id if self.emirate_dxb else False,
            'uae_labour_authority_id': self.difc_auth.id if self.difc_auth else False,
        })

        employee = self.env['hr.employee'].create({
            'name': 'Sarah Connor',
            'company_id': company.id,
            'country_id': self.country_in.id,
        })

        profile = self.service.get_statutory_profile(company, employee)

        self.assertEqual(profile['jurisdiction']['type'], 'free_zone')
        if profile['labour_authority']:
            self.assertEqual(profile['labour_authority']['code'], 'DIFC_AUTH')
            self.assertEqual(profile['labour_authority']['authority_type'], 'free_zone')

    def test_04_scenario_4_multi_company_isolation(self):
        """
        Scenario 4: Multi-company environment
        Company A (Mainland Dubai) and Company B (Abu Dhabi)
        """
        company_a = self.env['res.company'].create({
            'name': 'Company A Mainland DXB',
            'country_id': self.country_ae.id,
            'uae_employment_sector': 'private',
            'uae_jurisdiction_type': 'mainland',
            'uae_emirate_id': self.emirate_dxb.id if self.emirate_dxb else False,
        })

        company_b = self.env['res.company'].create({
            'name': 'Company B Abu Dhabi',
            'country_id': self.country_ae.id,
            'uae_employment_sector': 'private',
            'uae_jurisdiction_type': 'mainland',
            'uae_emirate_id': self.emirate_auh.id if self.emirate_auh else False,
        })

        emp_a = self.env['hr.employee'].create({
            'name': 'Emp Company A',
            'company_id': company_a.id,
            'country_id': self.country_in.id,
        })

        emp_b = self.env['hr.employee'].create({
            'name': 'Emp Company B',
            'company_id': company_b.id,
            'country_id': self.country_sa.id,
        })

        profile_a = self.service.get_statutory_profile(company_a, emp_a)
        profile_b = self.service.get_statutory_profile(company_b, emp_b)

        self.assertEqual(profile_a['jurisdiction']['type'], 'mainland')
        if profile_a['emirate']:
            self.assertEqual(profile_a['emirate']['code'], 'DXB')
        self.assertEqual(profile_a['employee_category'], 'expatriate')

        if profile_b['emirate']:
            self.assertEqual(profile_b['emirate']['code'], 'AUH')
        self.assertEqual(profile_b['employee_category'], 'gcc_national')

    def test_05_emirate_to_authority_derivation(self):
        """
        Test that employee's applicable Emirate derives Pension Authority dynamically:
        Abu Dhabi -> ADPF
        Dubai / Other Emirates -> GPSSA
        """
        company = self.env['res.company'].create({
            'name': 'Emirate Mapping Test Corp',
            'country_id': self.country_ae.id,
            'uae_emirate_id': self.emirate_dxb.id if self.emirate_dxb else False,
        })

        # UAE National in Dubai
        emp_dxb = self.env['hr.employee'].create({
            'name': 'Dubai Employee',
            'company_id': company.id,
            'country_id': self.country_ae.id,
            'uae_emirate_id': self.emirate_dxb.id if self.emirate_dxb else False,
        })
        self.assertEqual(emp_dxb.uae_pension_authority_id.id, self.emirate_dxb.pension_authority_id.id)
        if self.gpssa:
            self.assertEqual(emp_dxb.uae_pension_authority_id.code, 'GPSSA')

        # UAE National in Abu Dhabi
        emp_auh = self.env['hr.employee'].create({
            'name': 'Abu Dhabi Employee',
            'company_id': company.id,
            'country_id': self.country_ae.id,
            'uae_emirate_id': self.emirate_auh.id if self.emirate_auh else False,
        })
        self.assertEqual(emp_auh.uae_pension_authority_id.id, self.emirate_auh.pension_authority_id.id)
        if self.adpf:
            self.assertEqual(emp_auh.uae_pension_authority_id.code, 'ADPF')

    def test_06_nationality_derives_category_and_defaults_gcc_country(self):
        """
        Test that Nationality automatically derives employee category:
        AE -> uae_national
        SA/KW/BH/OM/QA -> gcc_national (and defaults uae_gcc_country_id)
        Others -> expatriate
        """
        company = self.env['res.company'].create({
            'name': 'Nationality Derivation Corp',
            'country_id': self.country_ae.id,
        })

        # 1. UAE National
        emp_uae = self.env['hr.employee'].create({
            'name': 'UAE Citizen',
            'company_id': company.id,
            'country_id': self.country_ae.id,
        })
        self.assertEqual(emp_uae.uae_employee_category, 'uae_national')
        self.assertFalse(emp_uae.uae_gcc_country_id)

        # 2. GCC National (Saudi Arabia)
        emp_gcc = self.env['hr.employee'].create({
            'name': 'Saudi Citizen',
            'company_id': company.id,
            'country_id': self.country_sa.id,
        })
        self.assertEqual(emp_gcc.uae_employee_category, 'gcc_national')
        self.assertEqual(emp_gcc.uae_gcc_country_id.id, self.country_sa.id)

        # 3. Expatriate (India)
        emp_exp = self.env['hr.employee'].create({
            'name': 'Expatriate Citizen',
            'company_id': company.id,
            'country_id': self.country_in.id,
        })
        self.assertEqual(emp_exp.uae_employee_category, 'expatriate')
        self.assertFalse(emp_exp.uae_gcc_country_id)

    def test_07_gcc_country_validation_constraint(self):
        """
        Validation ensures GCC Country cannot differ from the employee's actual nationality:
        Nationality = Saudi Arabia -> GCC Country = Saudi Arabia (Valid)
        Nationality = Saudi Arabia -> GCC Country = Qatar (Invalid raises ValidationError)
        """
        company = self.env['res.company'].create({
            'name': 'GCC Validation Corp',
            'country_id': self.country_ae.id,
        })

        with self.assertRaises(ValidationError):
            self.env['hr.employee'].create({
                'name': 'Invalid GCC Country Employee',
                'company_id': company.id,
                'country_id': self.country_sa.id,
                'uae_gcc_country_id': self.country_qa.id,  # Mismatch!
            })

    def test_08_statutory_profile_resolves_pension_scheme(self):
        """
        Statutory profile service outputs the employee's configured pension scheme.
        """
        company = self.env['res.company'].create({
            'name': 'Scheme Test Company',
            'country_id': self.country_ae.id,
        })
        new_law = self.env.ref('hudson_ae_payroll.pension_scheme_new_law')
        employee = self.env['hr.employee'].create({
            'name': 'Scheme UAE National',
            'company_id': company.id,
            'country_id': self.country_ae.id,
            'uae_pension_scheme_id': new_law.id,
        })

        profile = self.service.get_statutory_profile(company, employee)
        self.assertIsNotNone(profile['pension_scheme'])
        self.assertEqual(profile['pension_scheme']['code'], 'new_law')
        self.assertEqual(profile['pension_scheme']['name'], 'New Law Scheme')
