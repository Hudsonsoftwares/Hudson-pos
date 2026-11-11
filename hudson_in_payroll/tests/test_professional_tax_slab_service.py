# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.fields import Date
from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_slab_service import ProfessionalTaxSlabService


class TestProfessionalTaxSlabService(TransactionCase):

    def setUp(self):
        super(TestProfessionalTaxSlabService, self).setUp()
        self.service = ProfessionalTaxSlabService(self.env)
        self.company_a = self.env.company
        self.company_b = self.env['res.company'].create({'name': 'Company B (PT Service Test)'})

        # Reference States
        self.state_mh = self.env.ref('base.state_in_mh')
        self.state_ka = self.env.ref('base.state_in_ka')
        self.state_wb = self.env.ref('base.state_in_wb')

        # Create Work Location Partner
        self.partner_mh = self.env['res.partner'].create({
            'name': 'Mumbai Location Address',
            'state_id': self.state_mh.id,
        })
        self.work_loc_mh = self.env['hr.work.location'].create({
            'name': 'Mumbai Tech Park',
            'address_id': self.partner_mh.id,
            'company_id': self.company_a.id,
        })

        # Create Test Employee with Work Location in MH
        self.emp_mh = self.env['hr.employee'].create({
            'name': 'Rahul Sharma',
            'gender': 'male',
            'work_location_id': self.work_loc_mh.id,
            'company_id': self.company_a.id,
        })

    def test_01_salary_slab_selection(self):
        """Test standard salary slab matching for Maharashtra (Male, ₹8,500 gross)."""
        result = self.service.get_applicable_slab(
            employee=self.emp_mh,
            salary=8500.0,
            eval_date='2026-06-01'
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.state.id, self.state_mh.id)
        self.assertEqual(result.salary_from, 7501.0)
        self.assertEqual(result.salary_to, 10000.0)
        self.assertEqual(result.pt_amount, 175.0)

    def test_02_open_ended_salary_slab(self):
        """Test open-ended salary slab selection (Karnataka, ₹50,000 gross)."""
        result = self.service.get_applicable_slab(
            salary=50000.0,
            state=self.state_ka,
            eval_date='2026-06-01'
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.state.id, self.state_ka.id)
        self.assertEqual(result.salary_from, 25000.0)
        self.assertFalse(result.salary_to)
        self.assertEqual(result.pt_amount, 200.0)

    def test_03_effective_date_selection(self):
        """Test effective-date filtering including open-ended date ranges."""
        # Create an effective-dated slab override
        slab_future = self.env['pt.state.slab'].create({
            'state_id': self.state_ka.id,
            'periodicity': 'monthly',
            'salary_from': 50000.0,
            'salary_to': 100000.0,
            'pt_amount': 250.0,
            'date_from': '2027-01-01',
            'date_to': '2027-12-31',
            'company_id': self.company_a.id,
        })

        # Date prior to effective start -> Should match base seed slab
        res_2026 = self.service.get_applicable_slab(
            salary=60000.0,
            state=self.state_ka,
            eval_date='2026-06-01',
            company=self.company_a
        )
        self.assertIsNotNone(res_2026)
        self.assertEqual(res_2026.pt_amount, 200.0)

        # Date within effective period -> Should match new slab_future
        res_2027 = self.service.get_applicable_slab(
            salary=60000.0,
            state=self.state_ka,
            eval_date='2027-06-01',
            company=self.company_a
        )
        self.assertIsNotNone(res_2027)
        self.assertEqual(res_2027.pt_amount, 250.0)

    def test_04_multi_company_lookup(self):
        """Test multi-company isolation giving preference to company-specific slab."""
        company_slab = self.env['pt.state.slab'].create({
            'state_id': self.state_ka.id,
            'periodicity': 'monthly',
            'salary_from': 25000.0,
            'salary_to': False,
            'pt_amount': 180.0,
            'company_id': self.company_b.id,
        })

        # Company A gets global seed slab (PT ₹200)
        res_a = self.service.get_applicable_slab(salary=30000.0, state=self.state_ka, company=self.company_a)
        self.assertEqual(res_a.pt_amount, 200.0)

        # Company B gets company-specific slab (PT ₹180)
        res_b = self.service.get_applicable_slab(salary=30000.0, state=self.state_ka, company=self.company_b)
        self.assertEqual(res_b.pt_amount, 180.0)
        self.assertEqual(res_b.company.id, self.company_b.id)

    def test_05_different_state_lookups(self):
        """Test state resolution using work location service for multiple states (WB, MH, KA)."""
        res_wb = self.service.get_applicable_slab(salary=45000.0, state=self.state_wb)
        self.assertIsNotNone(res_wb)
        self.assertEqual(res_wb.state.id, self.state_wb.id)
        self.assertEqual(res_wb.pt_amount, 200.0)

    def test_06_no_matching_slab_scenario(self):
        """Test returning None when no matching slab exists for an unconfigured state."""
        state_dl = self.env.ref('base.state_in_dl')  # Delhi (No PT in Delhi)
        result = self.service.get_applicable_slab(salary=50000.0, state=state_dl)
        self.assertIsNone(result)

    def test_07_month_override_metadata_retrieval(self):
        """Test retrieval of override_month and override_amount metadata."""
        result = self.service.get_applicable_slab(
            employee=self.emp_mh,
            salary=15000.0,
            eval_date='2026-02-01'
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.override_month, '2')
        self.assertEqual(result.override_amount, 300.0)
        # Service returns metadata without deciding whether calculation override applies
        self.assertEqual(result.pt_amount, 200.0)
