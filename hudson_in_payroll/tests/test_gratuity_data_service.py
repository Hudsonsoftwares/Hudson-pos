# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
# pyrefly: ignore [missing-import]
from odoo.fields import Date
# pyrefly: ignore [missing-import]
from odoo.addons.hudson_in_payroll.services.gratuity.gratuity_data_service import GratuityDataService


class TestGratuityDataService(TransactionCase):

    def setUp(self):
        super(TestGratuityDataService, self).setUp()
        self.data_service = GratuityDataService(self.env)
        
        self.company = self.env['res.company'].create({
            'name': 'Gratuity Data Service Test Company',
            'hds_in_enable_gratuity': True,
        })

        self.employee = self.env['hr.employee'].create({
            'name': 'Data Service Employee',
            'company_id': self.company.id,
            'first_contract_date': Date.from_string('2018-01-01'),
        })

        if self.employee.version_id:
            self.contract = self.employee.version_id
            self.contract.write({
                'name': 'Data Service Contract',
                'date_start': Date.from_string('2018-01-01'),
                'wage': 40000.0,
                'basic_salary': 30000.0,
                'da': 5000.0,
            })
        else:
            self.contract = self.env['hr.version'].create({
                'name': 'Data Service Contract',
                'employee_id': self.employee.id,
                'date_start': Date.from_string('2018-01-01'),
                'wage': 40000.0,
                'basic_salary': 30000.0,
                'da': 5000.0,
            })

    def test_01_joining_date_resolution(self):
        """Test resolving original joining date from employee/contract."""
        joining_date = self.data_service._resolve_joining_date(self.employee, self.contract)
        self.assertEqual(joining_date, Date.from_string('2018-01-01'))

    def test_02_separation_date_resolution(self):
        """Test resolving separation date with fallback hierarchy."""
        sep_date = self.data_service._resolve_separation_date(
            self.employee, self.contract, explicit_date='2024-03-31'
        )
        self.assertEqual(sep_date, Date.from_string('2024-03-31'))

    def test_03_completed_service_calculation(self):
        """Test statutory service duration calculation (6 years 3 months = 6 completed years)."""
        joining = Date.from_string('2018-01-01')
        separation = Date.from_string('2024-04-15')
        duration = self.data_service._calculate_service_duration(joining, separation)
        self.assertEqual(duration['total_years'], 6)
        self.assertEqual(duration['remaining_months'], 3)
        self.assertEqual(duration['completed_years'], 6)

    def test_03b_service_below_threshold_no_fraction_rounding(self):
        """Test that 4 years 7 months does NOT round up to 5 completed years under Section 4(1)."""
        joining = Date.from_string('2019-01-01')
        separation = Date.from_string('2023-08-15')
        duration = self.data_service._calculate_service_duration(joining, separation)
        self.assertEqual(duration['total_years'], 4)
        self.assertEqual(duration['remaining_months'], 7)
        self.assertEqual(duration['completed_years'], 4)

    def test_03c_service_meeting_threshold_rounds_up(self):
        """Test that 5 years 7 months rounds up to 6 completed years under Section 4(2)."""
        joining = Date.from_string('2018-01-01')
        separation = Date.from_string('2023-08-15')
        duration = self.data_service._calculate_service_duration(joining, separation)
        self.assertEqual(duration['total_years'], 5)
        self.assertEqual(duration['remaining_months'], 7)
        self.assertEqual(duration['completed_years'], 6)

    def test_03d_death_disablement_exception_rounds_up(self):
        """Test that 2 years 7 months with death/disablement exception rounds up to 3 completed years."""
        joining = Date.from_string('2021-01-01')
        separation = Date.from_string('2023-08-15')
        duration = self.data_service._calculate_service_duration(joining, separation, is_death_or_disablement=True)
        self.assertEqual(duration['total_years'], 2)
        self.assertEqual(duration['remaining_months'], 7)
        self.assertEqual(duration['completed_years'], 3)

    def test_04_last_drawn_salary_retrieval(self):
        """Test last drawn Basic + DA component retrieval."""
        salary = self.data_service._retrieve_last_drawn_salary(self.employee, self.contract)
        self.assertEqual(salary['basic'], 30000.0)
        self.assertEqual(salary['da'], 5000.0)
        self.assertEqual(salary['wage_base'], 35000.0)

    def test_04b_prorated_payslip_does_not_overwrite_contract_wage(self):
        """Test that mid-month prorated payslip lines do not overwrite unprorated contract wage rate under Sec 4(2)."""
        rule_basic = self.env['hr.salary.rule'].search([('code', '=', 'BASIC')], limit=1)
        rule_da = self.env['hr.salary.rule'].search([('code', '=', 'DA')], limit=1)
        any_rule = rule_basic or self.env['hr.salary.rule'].search([], limit=1)
        slip = self.env['hr.payslip'].create({
            'name': 'Prorated Slip Test',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'company_id': self.company.id,
            'date_from': Date.from_string('2024-03-01'),
            'date_to': Date.from_string('2024-03-05'),
        })
        self.env['hr.payslip.line'].create({
            'slip_id': slip.id,
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'salary_rule_id': (rule_basic or any_rule).id,
            'name': 'Basic Salary (5 days prorated)',
            'code': 'BASIC',
            'amount': 5000.0,
            'total': 5000.0,
        })
        self.env['hr.payslip.line'].create({
            'slip_id': slip.id,
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'salary_rule_id': (rule_da or any_rule).id,
            'name': 'Dearness Allowance (5 days prorated)',
            'code': 'DA',
            'amount': 833.33,
            'total': 833.33,
        })
        salary = self.data_service._retrieve_last_drawn_salary(self.employee, self.contract, payslip=slip)
        # Contract has 30,000 basic + 5,000 DA = 35,000. Must NOT be overwritten by 5,000 + 833.33!
        self.assertEqual(salary['basic'], 30000.0)
        self.assertEqual(salary['da'], 5000.0)
        self.assertEqual(salary['wage_base'], 35000.0)

    def test_04c_fallback_to_payslip_when_contract_wage_is_zero(self):
        """Test fallback to payslip lines when contract wage base is missing or zero."""
        rule_basic = self.env['hr.salary.rule'].search([('code', '=', 'BASIC')], limit=1)
        any_rule = rule_basic or self.env['hr.salary.rule'].search([], limit=1)
        zero_emp = self.env['hr.employee'].create({
            'name': 'Zero Wage Employee',
            'company_id': self.company.id,
            'first_contract_date': Date.from_string('2018-01-01'),
        })
        zero_contract = zero_emp.version_id
        if zero_contract:
            zero_contract.write({
                'name': 'Zero Wage Contract',
                'wage': 0.0,
                'basic_salary': 0.0,
                'da': 0.0,
            })
        else:
            zero_contract = self.env['hr.version'].create({
                'name': 'Zero Wage Contract',
                'employee_id': zero_emp.id,
                'date_start': Date.from_string('2018-01-01'),
                'wage': 0.0,
                'basic_salary': 0.0,
                'da': 0.0,
            })
        slip = self.env['hr.payslip'].create({
            'name': 'Fallback Slip Test',
            'employee_id': zero_emp.id,
            'contract_id': zero_contract.id,
            'company_id': self.company.id,
            'date_from': Date.from_string('2024-03-01'),
            'date_to': Date.from_string('2024-03-31'),
        })
        self.env['hr.payslip.line'].create({
            'slip_id': slip.id,
            'employee_id': zero_emp.id,
            'contract_id': zero_contract.id,
            'salary_rule_id': any_rule.id,
            'name': 'Basic Salary',
            'code': 'BASIC',
            'amount': 25000.0,
            'total': 25000.0,
        })
        salary = self.data_service._retrieve_last_drawn_salary(zero_emp, zero_contract, payslip=slip)
        self.assertEqual(salary['basic'], 25000.0)
        self.assertEqual(salary['wage_base'], 25000.0)

    def test_05_rule_parameters_resolution(self):
        """Test resolving statutory gratuity parameters via lookup engine."""
        params = self.data_service._resolve_rule_parameters(Date.today())
        self.assertEqual(params['days_multiplier'], 15.0)
        self.assertEqual(params['month_divisor'], 26.0)
        self.assertEqual(params['min_service_years'], 5.0)
        self.assertEqual(params['statutory_ceiling'], 2000000.0)

    def test_06_prepare_calculation_data_dto(self):
        """Test complete data preparation returning structured DTO object."""
        dto = self.data_service.prepare_calculation_data(
            employee=self.employee,
            contract=self.contract,
            separation_date='2024-03-31'
        )
        self.assertEqual(dto.employee_id, self.employee.id)
        self.assertEqual(dto.completed_years, 6)
        self.assertEqual(dto.last_drawn_basic, 30000.0)
        self.assertEqual(dto.last_drawn_da, 5000.0)
        self.assertEqual(dto.wage_base, 35000.0)
        self.assertEqual(dto.days_multiplier, 15.0)
        self.assertEqual(dto.month_divisor, 26.0)
        self.assertEqual(dto.statutory_ceiling, 2000000.0)
        
        dto_dict = dto.to_dict()
        self.assertIsInstance(dto_dict, dict)
        self.assertEqual(dto_dict['wage_base'], 35000.0)
