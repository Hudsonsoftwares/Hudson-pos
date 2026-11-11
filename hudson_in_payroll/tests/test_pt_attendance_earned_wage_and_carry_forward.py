# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests.common import TransactionCase
from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_service import ProfessionalTaxService
from odoo.addons.hudson_in_payroll.services.professional_tax.pt_periodicity_strategy import PTPeriodicityStrategyRegistry


class TestPTAttendanceEarnedWageAndCarryForward(TransactionCase):
    """
    Test Suite for:
    1. Attendance-earned wage evaluation vs unadjusted contractual gross (shortage deduction SHORT & unpaid leaves UNPAID).
    2. Half-yearly deduction cycle accumulation and deduction at cycle end (September).
    3. Zero earned wage at deduction month triggering ZERO_WAGE guard.
    4. Carry-forward of uncollected periodic PT to upcoming eligible months (e.g. October).
    5. Ensuring carried-forward recovery does not reduce the subsequent period's statutory liability.
    6. Net Pay Guard capping carried-forward PT if net earnings are insufficient.
    """

    def setUp(self):
        super().setUp()
        self.pt_service = ProfessionalTaxService(self.env)
        self.company = self.env.company

        self.state_mh = self.env.ref('base.state_in_mh', raise_if_not_found=False) or self.env['res.country.state'].search([('code', '=', 'MH')], limit=1)
        self.state_kl = self.env.ref('base.state_in_kl', raise_if_not_found=False) or self.env['res.country.state'].search([('code', '=', 'KL')], limit=1)

        partner_mh = self.env['res.partner'].create({'name': 'MH Office Test', 'state_id': self.state_mh.id})
        partner_kl = self.env['res.partner'].create({'name': 'KL Office Test', 'state_id': self.state_kl.id})

        self.work_loc_mh = self.env['hr.work.location'].create({'name': 'Mumbai Test Loc', 'address_id': partner_mh.id, 'company_id': self.company.id})
        self.work_loc_kl = self.env['hr.work.location'].create({'name': 'Kochi Test Loc', 'address_id': partner_kl.id, 'company_id': self.company.id})

        # Create test employees with contract start dates in Jan 2026
        self.emp_mh = self.env['hr.employee'].create({
            'name': 'MH Earned Wage Employee',
            'sex': 'male',
            'work_location_id': self.work_loc_mh.id,
            'company_id': self.company.id,
            'hds_in_pt_applicable': True,
        })
        self.emp_mh.write({'contract_date_start': '2026-01-01', 'date_start': '2026-01-01'})
        if self.emp_mh.version_id:
            self.emp_mh.version_id.write({'contract_date_start': '2026-01-01', 'date_start': '2026-01-01'})

        self.emp_kl = self.env['hr.employee'].create({
            'name': 'KL Cycle Employee',
            'sex': 'male',
            'work_location_id': self.work_loc_kl.id,
            'company_id': self.company.id,
            'hds_in_pt_applicable': True,
        })
        self.emp_kl.write({'contract_date_start': '2026-01-01', 'date_start': '2026-01-01'})
        if self.emp_kl.version_id:
            self.emp_kl.version_id.write({'contract_date_start': '2026-01-01', 'date_start': '2026-01-01'})

        self.struct = self.env.ref('hudson_payroll_base.structure_base', raise_if_not_found=False) or self.env['hr.payroll.structure'].search([], limit=1)
        self.pt_rule = self.env.ref('hudson_in_payroll.hds_in_rule_pt', raise_if_not_found=False) or self.env['hr.salary.rule'].search([('code', '=', 'PT')], limit=1)
        self.gross_rule = self.env['hr.salary.rule'].search([('code', '=', 'GROSS')], limit=1)
        self.short_rule = self.env['hr.salary.rule'].search([('code', '=', 'SHORT')], limit=1)

    def test_01_contract_gross_vs_attendance_earned_wage_exemption(self):
        """
        Contractual Gross is Rs 20,000, but employee had attendance shortage (SHORT) of Rs 13,333.33.
        Actual attendance-earned wage is Rs 6,666.67.
        Under Maharashtra slabs (<= Rs 7,500 exempt):
        - Unadjusted contractual gross (Rs 20,000) would illegally deduct Rs 200.
        - Adjusted attendance-earned wage (Rs 6,666.67) falls into exempt slab -> Rs 0 PT.
        """
        class CategoryMock:
            GROSS = 20000.0
            DED = -13333.33

        # Simulate localdict with SHORT deduction
        localdict = {
            'categories': CategoryMock(),
            'SHORT': 13333.33,
        }

        res = self.pt_service.compute_pt(
            employee=self.emp_mh,
            eval_date=date(2026, 5, 31),
            company=self.company,
            localdict=localdict
        )

        self.assertTrue(res.is_valid)
        self.assertEqual(res.amount, 0.0, "Employee with earned wages Rs 6,666.67 should be exempt (Rs 0 PT).")

    def test_02_half_yearly_accumulation_and_deduction_month(self):
        """
        In Kerala (Half-Yearly H1: April 1 to September 30):
        - Non-deduction month (June) returns Rs 0 with WAITING_FOR_PERIOD_END.
        - Deduction month (September) aggregates earned wages across cycle and deducts PT.
        """
        # June (non-deduction month)
        res_june = self.pt_service.compute_pt(
            employee=self.emp_kl,
            salary=20000.0,
            eval_date=date(2026, 6, 30),
            company=self.company
        )
        self.assertFalse(res_june.is_valid)
        self.assertEqual(res_june.validation_status, 'WAITING_FOR_PERIOD_END')
        self.assertEqual(res_june.amount, 0.0)

        # September (deduction month) with positive wage
        # With single month Rs 20,000 (and no historical slips yet in test DB), salary basis is 20,000 -> Slab Rs 18k-30k -> Rs 180
        res_sep = self.pt_service.compute_pt(
            employee=self.emp_kl,
            salary=20000.0,
            eval_date=date(2026, 9, 30),
            company=self.company
        )
        self.assertTrue(res_sep.is_valid)
        self.assertEqual(res_sep.validation_status, 'VALID')
        self.assertGreater(res_sep.amount, 0.0)

    def test_03_zero_wage_in_deduction_month_triggers_zero_wage_guard(self):
        """
        In Kerala September payslip (deduction month):
        If employee has zero earned wage (e.g. 100% shortage or LOP), PT is Rs 0 with ZERO_WAGE guard.
        """
        class CategoryMockZero:
            GROSS = 0.0
            DED = 0.0

        localdict = {
            'categories': CategoryMockZero(),
            'salary': 0.0,
        }

        res_sep_zero = self.pt_service.compute_pt(
            employee=self.emp_kl,
            salary=0.0,
            eval_date=date(2026, 9, 30),
            company=self.company,
            localdict=localdict
        )
        self.assertFalse(res_sep_zero.is_valid)
        self.assertEqual(res_sep_zero.validation_status, 'ZERO_WAGE')
        self.assertEqual(res_sep_zero.amount, 0.0)

    def test_04_carry_forward_deduction_in_upcoming_eligible_month(self):
        """
        If employee had positive earned wages in H1 (April-August), but September payslip had zero wage,
        the uncollected H1 PT liability carries forward to October (the upcoming eligible month with positive wage).
        """
        contract = getattr(self.emp_kl, 'contract_id', False) or getattr(self.emp_kl, 'version_id', False)

        # 1. Create a historical payslip in August with Rs 20,000 earned wage in 'done' state
        slip_aug = self.env['hr.payslip'].create({
            'name': 'Done Slip Aug 2026',
            'employee_id': self.emp_kl.id,
            'contract_id': contract.id if contract else False,
            'date_from': '2026-08-01',
            'date_to': '2026-08-31',
            'struct_id': self.struct.id if self.struct else False,
            'state': 'done',
        })
        self.env['hr.payslip.line'].create({
            'slip_id': slip_aug.id,
            'employee_id': self.emp_kl.id,
            'contract_id': contract.id if contract else False,
            'salary_rule_id': self.gross_rule.id if self.gross_rule else False,
            'name': 'Gross',
            'code': 'GROSS',
            'amount': 20000.0,
            'quantity': 1.0,
            'total': 20000.0,
        })

        # 2. September payslip has 0 earned wage (full LOP) -> 0 PT deducted
        slip_sep = self.env['hr.payslip'].create({
            'name': 'Done Slip Sep 2026',
            'employee_id': self.emp_kl.id,
            'contract_id': contract.id if contract else False,
            'date_from': '2026-09-01',
            'date_to': '2026-09-30',
            'struct_id': self.struct.id if self.struct else False,
            'state': 'done',
        })
        # No PT line on Sep slip because wage was 0
        self.env.invalidate_all()

        # 3. October payslip (upcoming eligible month in H2 with positive wage)
        # Normally October is non-deduction month, but carries forward uncollected H1 PT
        strategy = PTPeriodicityStrategyRegistry.get_strategy('half_yearly')
        carried_forward = strategy.get_carried_forward_liability(
            self.env, employee=self.emp_kl, eval_date=date(2026, 10, 31), company=self.company
        )
        self.assertGreater(carried_forward, 0.0, "H1 uncollected liability should carry forward to October.")

        res_oct = self.pt_service.compute_pt(
            employee=self.emp_kl,
            salary=20000.0,
            eval_date=date(2026, 10, 31),
            company=self.company
        )
        self.assertTrue(res_oct.is_valid)
        self.assertEqual(res_oct.validation_status, 'VALID')
        self.assertEqual(res_oct.amount, carried_forward, "October payslip should deduct carried forward PT liability.")

    def test_05_carry_forward_recovery_does_not_reduce_subsequent_cycle_liability(self):
        """
        Verify that after carried-forward H1 PT is recovered on October payslip,
        the H2 cycle-end deduction in March is NOT reduced by the October recovery.
        """
        contract = getattr(self.emp_kl, 'contract_id', False) or getattr(self.emp_kl, 'version_id', False)

        # 1. Create August slip with Rs 20,000 gross
        slip_aug = self.env['hr.payslip'].create({
            'name': 'Done Slip Aug 2026',
            'employee_id': self.emp_kl.id,
            'contract_id': contract.id if contract else False,
            'date_from': '2026-08-01',
            'date_to': '2026-08-31',
            'struct_id': self.struct.id if self.struct else False,
            'state': 'done',
        })
        self.env['hr.payslip.line'].create({
            'slip_id': slip_aug.id,
            'employee_id': self.emp_kl.id,
            'contract_id': contract.id if contract else False,
            'salary_rule_id': self.gross_rule.id if self.gross_rule else False,
            'name': 'Gross',
            'code': 'GROSS',
            'amount': 20000.0,
            'quantity': 1.0,
            'total': 20000.0,
        })

        # 2. In October, carried-forward PT (Rs 180) is deducted and payslip is 'done'
        slip_oct = self.env['hr.payslip'].create({
            'name': 'Done Slip Oct 2026',
            'employee_id': self.emp_kl.id,
            'contract_id': contract.id if contract else False,
            'date_from': '2026-10-01',
            'date_to': '2026-10-31',
            'struct_id': self.struct.id if self.struct else False,
            'state': 'done',
        })
        self.env['hr.payslip.line'].create({
            'slip_id': slip_oct.id,
            'employee_id': self.emp_kl.id,
            'contract_id': contract.id if contract else False,
            'salary_rule_id': self.pt_rule.id if self.pt_rule else False,
            'name': 'Professional Tax',
            'code': 'PT',
            'amount': -180.0,
            'quantity': 1.0,
            'total': -180.0,
        })
        self.env['hr.payslip.line'].create({
            'slip_id': slip_oct.id,
            'employee_id': self.emp_kl.id,
            'contract_id': contract.id if contract else False,
            'salary_rule_id': self.gross_rule.id if self.gross_rule else False,
            'name': 'Gross',
            'code': 'GROSS',
            'amount': 20000.0,
            'quantity': 1.0,
            'total': 20000.0,
        })
        self.env.invalidate_all()

        # 3. In March 2027 (end of H2 cycle), evaluate March payslip with Rs 20,000 wage
        res_mar = self.pt_service.compute_pt(
            employee=self.emp_kl,
            salary=20000.0,
            eval_date=date(2027, 3, 31),
            company=self.company
        )
        self.assertTrue(res_mar.is_valid)
        self.assertEqual(res_mar.validation_status, 'VALID')
        # H2 liability should be evaluated independently (not reduced to 0 by October's 180 deduction)
        self.assertGreater(res_mar.amount, 0.0, "March H2 deduction should not be wiped out by October H1 recovery.")

    def test_06_net_pay_guard_capping(self):
        """
        Verify Net Pay Guard caps PT deduction when other deductions leave insufficient net available pay.
        """
        class CategoryMockCapped:
            GROSS = 20000.0
            DED = -19950.0  # Net available = 50.0

        localdict = {
            'categories': CategoryMockCapped(),
        }

        res = self.pt_service.compute_pt(
            employee=self.emp_mh,
            salary=20000.0,
            eval_date=date(2026, 5, 31),
            company=self.company,
            localdict=localdict
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.amount, 50.0, "PT deduction should be capped at net available pay (Rs 50.0).")
