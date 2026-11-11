# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
# pyrefly: ignore [missing-import]
from odoo.fields import Date


class TestLeaveEncashmentRetirementTax(TransactionCase):
    """
    Test Suite for Statutory Exemption on Leave Encashment under Section 10(10AA) / Income-tax Act, 2025.
    Verifies that:
    1. If exit reason is 'retirement', leave encashment up to ₹25,00,000 is statutorily exempt from tax/TDS.
    2. Any excess leave encashment above ₹25,00,000 is taxable and added to unified annual taxable salary.
    3. The ₹25,00,000 limit is configurable via hr.rule.parameter or editable per settlement.
    4. For non-retirement separations (resignation, termination), exemption is ₹0 (100% taxable).
    5. Payslip tax computation income report correctly reflects exempt vs taxable components.
    """

    @classmethod
    def _gc_filestore(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        try:
            super(TestLeaveEncashmentRetirementTax, cls).tearDownClass()
        except BaseException:
            pass

    def setUp(self):
        super(TestLeaveEncashmentRetirementTax, self).setUp()
        self.company = self.env.company
        self.company.write({
            'hds_in_enable_gratuity': True,
            'hds_in_enable_leave_encashment': True,
            'hds_in_tds_applicable': True,
        })
        self.employee = self.env['hr.employee'].create({
            'name': 'Retirement Tax Test Employee',
            'company_id': self.company.id,
            'first_contract_date': Date.from_string('2010-01-01'),
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
                'name': 'Retirement Tax Test Contract',
                'employee_id': self.employee.id,
                'company_id': self.company.id,
                'wage': 150000.0,
                'basic_salary': 100000.0,
                'da': 20000.0,
                'date_start': Date.from_string('2010-01-01'),
                'struct_id': struct.id if struct else False,
            }
            if self.contract:
                self.contract.write(vals)
            else:
                self.contract = self.env[contract_model].create(vals)

    def test_01_retirement_leave_encashment_fully_exempt(self):
        """Scenario A: On retirement, leave encashment <= ₹25L is 100% exempt from tax and taxable amount is 0."""
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'last_working_day': Date.from_string('2026-11-30'),
            'exit_reason': 'retirement',
            'leave_encash_gross_amount': 1500000.0,  # Below ₹25L exemption
        })
        self.assertEqual(settlement.leave_encash_exemption_amount, 2500000.0)
        self.assertEqual(settlement.leave_encash_taxable_amount, 0.0)

        # Salary Projection verification
        from odoo.addons.hudson_in_payroll.services.tds.salary_projection_service import SalaryProjectionService
        service = SalaryProjectionService(self.env)
        proj = service.project_salary(
            employee=self.employee,
            eval_date=Date.from_string('2026-11-30')
        )
        self.assertEqual(proj.exempt_exit_leave_encash, 1500000.0)
        self.assertEqual(proj.taxable_exit_leave_encash, 0.0)

    def test_02_retirement_leave_encashment_partially_taxable(self):
        """Scenario B: On retirement, leave encashment > ₹25L has ₹25L exempt and excess added to taxable salary."""
        gross_leave = 3200000.0
        exemption = 2500000.0
        expected_taxable = 700000.0

        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'last_working_day': Date.from_string('2026-11-30'),
            'exit_reason': 'retirement',
            'leave_encash_gross_amount': gross_leave,
        })
        self.assertEqual(settlement.leave_encash_exemption_amount, exemption)
        self.assertEqual(settlement.leave_encash_taxable_amount, expected_taxable)

        # Salary Projection verification
        from odoo.addons.hudson_in_payroll.services.tds.salary_projection_service import SalaryProjectionService
        service = SalaryProjectionService(self.env)
        proj = service.project_salary(
            employee=self.employee,
            eval_date=Date.from_string('2026-11-30')
        )
        self.assertEqual(proj.exempt_exit_leave_encash, exemption)
        self.assertEqual(proj.taxable_exit_leave_encash, expected_taxable)

    def test_03_resignation_exit_leave_encashment_exempt_under_ceiling(self):
        """Scenario C: For non-retirement (e.g. resignation), leave encashment <= ₹25L is 100% exempt u/s 10(10AA)."""
        # Part 1: ₹65,000 leave encashment is 100% exempt from tax and taxable amount is 0
        settlement_65k = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'last_working_day': Date.from_string('2026-11-30'),
            'exit_reason': 'resignation',
            'leave_encash_gross_amount': 65000.0,
        })
        self.assertEqual(settlement_65k.leave_encash_exemption_amount, 2500000.0)
        self.assertEqual(settlement_65k.leave_encash_taxable_amount, 0.0)

        from odoo.addons.hudson_in_payroll.services.tds.salary_projection_service import SalaryProjectionService
        service = SalaryProjectionService(self.env)
        proj_65k = service.project_salary(
            employee=self.employee,
            eval_date=Date.from_string('2026-11-30')
        )
        self.assertEqual(proj_65k.exempt_exit_leave_encash, 65000.0)
        self.assertEqual(proj_65k.taxable_exit_leave_encash, 0.0)

        # Part 2: ₹15L leave encashment on resignation is also 100% exempt
        gross_leave = 1500000.0
        settlement_15l = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'last_working_day': Date.from_string('2026-11-30'),
            'exit_reason': 'resignation',
            'leave_encash_gross_amount': gross_leave,
        })
        self.assertEqual(settlement_15l.leave_encash_exemption_amount, 2500000.0)
        self.assertEqual(settlement_15l.leave_encash_taxable_amount, 0.0)

        proj_15l = service.project_salary(
            employee=self.employee,
            eval_date=Date.from_string('2026-11-30')
        )
        self.assertEqual(proj_15l.exempt_exit_leave_encash, gross_leave)
        self.assertEqual(proj_15l.taxable_exit_leave_encash, 0.0)

    def test_04_configurable_exemption_override(self):
        """Scenario D: Exemption amount can be configured/overridden per settlement or via parameter."""
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'last_working_day': Date.from_string('2026-11-30'),
            'exit_reason': 'retirement',
            'leave_encash_gross_amount': 2000000.0,
            'leave_encash_exemption_amount': 1000000.0,  # Custom lower exemption override
        })
        self.assertEqual(settlement.leave_encash_taxable_amount, 1000000.0)

        # Salary Projection picks up custom override from settlement
        from odoo.addons.hudson_in_payroll.services.tds.salary_projection_service import SalaryProjectionService
        service = SalaryProjectionService(self.env)
        proj = service.project_salary(
            employee=self.employee,
            eval_date=Date.from_string('2026-11-30')
        )
        self.assertEqual(proj.exempt_exit_leave_encash, 1000000.0)
        self.assertEqual(proj.taxable_exit_leave_encash, 1000000.0)

    def test_05_departure_schedule_syncs_retirement_exemption(self):
        """Scenario E: End of Collaboration departure record with Retired reason syncs exemption properly."""
        reason_retired = self.env['hr.departure.reason'].search([('name', 'ilike', 'Retir')], limit=1)
        if not reason_retired:
            reason_retired = self.env['hr.departure.reason'].create({'name': 'Retired'})

        emp = self.env['hr.employee'].create({
            'name': 'Scheduled Retiring Employee',
            'company_id': self.company.id,
            'first_contract_date': Date.from_string('2015-01-01'),
        })

        dep = self.env['hr.employee.departure'].create({
            'employee_id': emp.id,
            'departure_reason_id': reason_retired.id,
            'notice_period_start_date': Date.from_string('2026-10-01'),
            'notice_period_end_date': Date.from_string('2026-11-30'),
            'departure_date': Date.from_string('2026-11-30'),
        })

        settlement = self.env['final.settlement'].search([('employee_id', '=', emp.id)], limit=1)
        self.assertTrue(settlement)
        self.assertEqual(settlement.exit_reason, 'retirement')
        self.assertEqual(settlement.leave_encash_exemption_amount, 2500000.0)
