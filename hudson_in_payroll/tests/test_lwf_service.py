# -*- coding: utf-8 -*-
from datetime import date
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
from ..services.payroll.work_location_service import PayrollWorkLocationService
from ..services.lwf.lwf_rate_service import LWFRateService
from ..services.lwf.lwf_service import LWFService


class TestLWFService(TransactionCase):

    def setUp(self):
        super().setUp()
        self.location_service = PayrollWorkLocationService(self.env)
        self.rate_service = LWFRateService(self.env)

        self.country_in = self.env.ref('base.in', raise_if_not_found=False) or self.env['res.country'].search([('code', '=', 'IN')], limit=1)

        # States
        self.state_mh = self.env['res.country.state'].create({
            'name': 'Maharashtra LWF State',
            'code': 'MH_LWF',
            'country_id': self.country_in.id,
        })
        self.state_ka = self.env['res.country.state'].create({
            'name': 'Karnataka LWF State',
            'code': 'KA_LWF',
            'country_id': self.country_in.id,
        })

        # Partners & Work Location
        self.partner_mh = self.env['res.partner'].create({
            'name': 'Mumbai Office Partner',
            'state_id': self.state_mh.id,
            'country_id': self.country_in.id,
        })
        self.work_loc_mh = self.env['hr.work.location'].create({
            'name': 'Mumbai Location',
            'address_id': self.partner_mh.id,
        })

        # LWF Rate Configurations
        # Maharashtra: EE ₹25, ER ₹75, Half-Yearly in June (6) & December (12)
        self.lwf_mh = self.env['lwf.state.rate'].create({
            'state_id': self.state_mh.id,
            'emp_contribution': 25.0,
            'empl_contribution': 75.0,
            'deduction_frequency': 'half_yearly',
            'deduction_month_1': '6',
            'deduction_month_2': '12',
            'date_from': '2026-01-01',
            'active': True,
        })

        # Karnataka: EE ₹50, ER ₹100, Annual in December (12)
        self.lwf_ka = self.env['lwf.state.rate'].create({
            'state_id': self.state_ka.id,
            'emp_contribution': 50.0,
            'empl_contribution': 100.0,
            'deduction_frequency': 'annual',
            'deduction_month_1': '12',
            'date_from': '2026-01-01',
            'active': True,
        })

        # Ensure company enables LWF and has valid state
        self.env.company.partner_id.write({'state_id': self.state_mh.id})
        self.env.company.write({
            'hds_in_enable_lwf': True,
            'hds_in_lwf_registration_no': 'LWF/MH/2026/001',
        })

        # Employee assigned to Mumbai Work Location
        self.emp_mh = self.env['hr.employee'].create({
            'name': 'Maharashtra Employee',
            'work_location_id': self.work_loc_mh.id,
            'hds_in_lwf_applicable': True,
        })
        contract = self.env['hr.version'].search([('employee_id', '=', self.emp_mh.id)], limit=1)
        if contract:
            contract.write({
                'wage': 30000.0,
                'pay_by_attendance': False,
            })

    def test_01_rate_service_lookup(self):
        """Verify active rate config lookup by state and date effectiveness."""
        rate_mh = self.rate_service.get_rate_config(self.state_mh, eval_date=date(2026, 6, 30))
        self.assertEqual(rate_mh, self.lwf_mh)

        rate_ka = self.rate_service.get_rate_config(self.state_ka, eval_date=date(2026, 12, 31))
        self.assertEqual(rate_ka, self.lwf_ka)

    def test_02_deduction_month_schedule(self):
        """Verify deduction month applicability."""
        # MH: June (6) and Dec (12) trigger LWF; April (4) does not.
        self.assertTrue(self.rate_service.is_deduction_scheduled(self.lwf_mh, eval_date=date(2026, 6, 30)))
        self.assertTrue(self.rate_service.is_deduction_scheduled(self.lwf_mh, eval_date=date(2026, 12, 31)))
        self.assertFalse(self.rate_service.is_deduction_scheduled(self.lwf_mh, eval_date=date(2026, 4, 30)))

        # KA: Dec (12) triggers LWF; June (6) does not.
        self.assertTrue(self.rate_service.is_deduction_scheduled(self.lwf_ka, eval_date=date(2026, 12, 31)))
        self.assertFalse(self.rate_service.is_deduction_scheduled(self.lwf_ka, eval_date=date(2026, 6, 30)))

    def test_03_lwf_service_june_deduction(self):
        """June 2026 payslip for MH Employee -> EE LWF = 25, ER LWF = 75."""
        payslip_june = self.env['hr.payslip'].create({
            'employee_id': self.emp_mh.id,
            'date_from': '2026-06-01',
            'date_to': '2026-06-30',
        })
        service = LWFService(self.env)
        ee_amount = service.compute_lwf_employee(payslip_june)
        er_amount = service.compute_lwf_employer(payslip_june)
        self.assertEqual(ee_amount, 25.0)
        self.assertEqual(er_amount, 75.0)

    def test_04_lwf_service_april_off_cycle(self):
        """April 2026 payslip for MH Employee -> LWF = 0 (Not a scheduled deduction month)."""
        payslip_april = self.env['hr.payslip'].create({
            'employee_id': self.emp_mh.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        })
        service = LWFService(self.env)
        ee_amount = service.compute_lwf_employee(payslip_april)
        er_amount = service.compute_lwf_employer(payslip_april)
        self.assertEqual(ee_amount, 0.0)
        self.assertEqual(er_amount, 0.0)

    def test_05_lwf_service_exempt_employee_uncheck(self):
        """June 2026 payslip for MH Employee with LWF Applicable unchecked -> LWF = 0."""
        self.emp_mh.hds_in_lwf_applicable = False
        payslip_june = self.env['hr.payslip'].create({
            'employee_id': self.emp_mh.id,
            'date_from': '2026-06-01',
            'date_to': '2026-06-30',
        })
        service = LWFService(self.env)
        ee_amount = service.compute_lwf_employee(payslip_june)
        er_amount = service.compute_lwf_employer(payslip_june)
        self.assertEqual(ee_amount, 0.0)
        self.assertEqual(er_amount, 0.0)

    def test_06_lwf_service_contractor_exempt(self):
        """June 2026 payslip for contractor -> LWF = 0."""
        self.emp_mh.hds_in_lwf_applicable = True
        contract_type = self.env.ref('hudson_payroll_base.employee_type_contract', raise_if_not_found=False)
        if not contract_type:
            contract_type = self.env['hr.employee.type'].create({'name': 'Contractor', 'code': 'CON'})
        self.emp_mh.employee_type_id = contract_type.id
        payslip_june = self.env['hr.payslip'].create({
            'employee_id': self.emp_mh.id,
            'date_from': '2026-06-01',
            'date_to': '2026-06-30',
        })
        service = LWFService(self.env)
        ee_amount = service.compute_lwf_employee(payslip_june)
        er_amount = service.compute_lwf_employer(payslip_june)
        self.assertEqual(ee_amount, 0.0)
        self.assertEqual(er_amount, 0.0)

    def test_07_state_scoped_headcount(self):
        """Verify that headcount is scoped to employee's state rather than nationwide total."""
        # KA requires min_employee_count = 50
        self.lwf_ka.min_employee_count = 50
        
        # Partner with KA state
        partner_ka = self.env['res.partner'].create({
            'name': 'KA Partner',
            'state_id': self.state_ka.id,
            'country_id': self.country_in.id,
        })
        
        # Create 2 employees in KA using address_id (primary priority)
        emp_ka1 = self.env['hr.employee'].create({
            'name': 'KA Employee 1',
            'address_id': partner_ka.id,
        })
        emp_ka2 = self.env['hr.employee'].create({
            'name': 'KA Employee 2',
            'address_id': partner_ka.id,
        })
        
        # Dec 2026 payslip for KA employee (Dec is scheduled month for KA)
        payslip_ka = self.env['hr.payslip'].create({
            'employee_id': emp_ka1.id,
            'date_from': '2026-12-01',
            'date_to': '2026-12-31',
        })
        service = LWFService(self.env)
        # Even though company may have other employees nationwide, KA headcount is only 2 (< 50)
        ee_amount = service.compute_lwf_employee(payslip_ka)
        er_amount = service.compute_lwf_employer(payslip_ka)
        self.assertEqual(ee_amount, 0.0)
        self.assertEqual(er_amount, 0.0)
