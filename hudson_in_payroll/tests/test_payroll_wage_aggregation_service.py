# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.fields import Date
from odoo.addons.hudson_in_payroll.services.payroll.payroll_wage_aggregation_service import PayrollWageAggregationService


class TestPayrollWageAggregationService(TransactionCase):

    def setUp(self):
        super(TestPayrollWageAggregationService, self).setUp()
        self.aggregation_service = PayrollWageAggregationService(self.env)
        self.company = self.env.company

        self.employee = self.env['hr.employee'].create({
            'name': 'Aggregation Test Employee',
            'company_id': self.company.id,
        })

        self.contract = self.env['hr.version'].create({
            'name': 'Aggregation Test Contract',
            'employee_id': self.employee.id,
            'date_start': Date.from_string('2025-01-01'),
            'wage': 25000.0,
        })

        # Category GROSS reference
        self.category_gross = self.env.ref('hudson_payroll_base.rule_category_gross')

    def test_01_single_payslip_aggregation(self):
        """Test aggregation of a single done payslip."""
        slip = self.env['hr.payslip'].create({
            'name': 'Apr Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'company_id': self.company.id,
            'date_from': Date.from_string('2026-04-01'),
            'date_to': Date.from_string('2026-04-30'),
            'state': 'done',
        })
        self.env['hr.payslip.line'].create({
            'name': 'Gross Salary Line',
            'code': 'GROSS',
            'category_id': self.category_gross.id,
            'slip_id': slip.id,
            'amount': 25000.0,
            'quantity': 1.0,
            'rate': 100.0,
            'total': 25000.0,
        })

        total = self.aggregation_service.get_aggregated_wage(
            employee=self.employee,
            start_date=Date.from_string('2026-04-01'),
            end_date=Date.from_string('2026-09-30'),
            category_code='GROSS',
            company=self.company
        )
        self.assertEqual(total, 25000.0)

    def test_02_multiple_payslips_aggregation_with_current_gross(self):
        """Test aggregation across past 4 payslips plus current transient payslip gross."""
        for m in range(4, 8):  # April, May, June, July
            m_str = f"0{m}" if m < 10 else str(m)
            slip = self.env['hr.payslip'].create({
                'name': f'Month {m} Payslip',
                'employee_id': self.employee.id,
                'contract_id': self.contract.id,
                'company_id': self.company.id,
                'date_from': Date.from_string(f'2026-{m_str}-01'),
                'date_to': Date.from_string(f'2026-{m_str}-28'),
                'state': 'done',
            })
            self.env['hr.payslip.line'].create({
                'name': 'Gross Line',
                'code': 'GROSS',
                'category_id': self.category_gross.id,
                'slip_id': slip.id,
                'total': 25000.0,
            })

        # August current payslip (transient context gross = 25,000.0)
        current_slip = self.env['hr.payslip'].create({
            'name': 'Aug Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'company_id': self.company.id,
            'date_from': Date.from_string('2026-08-01'),
            'date_to': Date.from_string('2026-08-31'),
            'state': 'draft',
        })

        total_h1 = self.aggregation_service.get_aggregated_wage(
            employee=self.employee,
            start_date=Date.from_string('2026-04-01'),
            end_date=Date.from_string('2026-09-30'),
            category_code='GROSS',
            company=self.company,
            current_slip=current_slip,
            current_slip_gross=25000.0
        )
        # 4 past payslips * 25,000 + 1 current slip gross 25,000 = 125,000.0
        self.assertEqual(total_h1, 125000.0)
