# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from ..services.payroll.work_location_service import PayrollWorkLocationService


class TestPayrollWorkLocationService(TransactionCase):

    def setUp(self):
        super().setUp()
        self.location_service = PayrollWorkLocationService(self.env)
        self.country_in = self.env.ref('base.in', raise_if_not_found=False) or self.env['res.country'].search([('code', '=', 'IN')], limit=1)

        # Create 3 distinct states
        self.state_mh = self.env['res.country.state'].create({
            'name': 'Maharashtra Test State',
            'code': 'MH_TST',
            'country_id': self.country_in.id,
        })
        self.state_ka = self.env['res.country.state'].create({
            'name': 'Karnataka Test State',
            'code': 'KA_TST',
            'country_id': self.country_in.id,
        })
        self.state_dl = self.env['res.country.state'].create({
            'name': 'Delhi Test State',
            'code': 'DL_TST',
            'country_id': self.country_in.id,
        })

        # Partners representing physical addresses
        self.partner_work_loc = self.env['res.partner'].create({
            'name': 'MH Work Location Address',
            'state_id': self.state_mh.id,
            'country_id': self.country_in.id,
        })
        self.partner_emp_addr = self.env['res.partner'].create({
            'name': 'KA Employee Direct Address',
            'state_id': self.state_ka.id,
            'country_id': self.country_in.id,
        })
        self.partner_company_addr = self.env['res.partner'].create({
            'name': 'DL Company Registered Address',
            'state_id': self.state_dl.id,
            'country_id': self.country_in.id,
        })

        # Company with registered partner state
        self.company = self.env['res.company'].create({
            'name': 'Test Statutory Company',
            'partner_id': self.partner_company_addr.id,
        })

        # Work Location record
        self.work_location = self.env['hr.work.location'].create({
            'name': 'Mumbai Tech Park',
            'address_id': self.partner_work_loc.id,
            'company_id': self.company.id,
        })

    def test_01_primary_work_address_state(self):
        """Should resolve state_ka via employee.address_id.state_id as Primary priority even if work_location_id is present."""
        employee = self.env['hr.employee'].create({
            'name': 'Employee Location Test 1',
            'company_id': self.company.id,
            'work_location_id': self.work_location.id,
            'address_id': self.partner_emp_addr.id,
        })
        state = self.location_service.get_work_state(employee)
        self.assertEqual(state, self.state_ka)

    def test_02_secondary_work_location_state(self):
        """Should resolve state_mh via employee.work_location_id.address_id.state_id when address_id is absent."""
        employee = self.env['hr.employee'].create({
            'name': 'Employee Location Test 2',
            'company_id': self.company.id,
            'work_location_id': self.work_location.id,
            'address_id': False,
        })
        state = self.location_service.get_work_state(employee)
        self.assertEqual(state, self.state_mh)

    def test_03_fallback_company_registered_state(self):
        """Should resolve state_dl via employee.company_id.partner_id.state_id when both locations are absent."""
        employee = self.env['hr.employee'].create({
            'name': 'Employee Location Test 3',
            'company_id': self.company.id,
            'work_location_id': False,
            'address_id': False,
        })
        state = self.location_service.get_work_state(employee)
        self.assertEqual(state, self.state_dl)

    def test_04_none_employee(self):
        """Should return False when employee is None or empty."""
        state = self.location_service.get_work_state(False)
        self.assertFalse(state)
