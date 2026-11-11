# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase# pyrefly: ignore [missing-import]
# pyrefly: ignore [missing-import]
from odoo.fields import Date


class TestFinalSettlementFoundation(TransactionCase):

    @classmethod
    def _gc_filestore(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        try:
            super(TestFinalSettlementFoundation, cls).tearDownClass()
        except Exception:
            pass

    def setUp(self):
        super(TestFinalSettlementFoundation, self).setUp()
        self.company = self.env['res.company'].create({
            'name': 'Final Settlement Test Company'
        })
        self.employee = self.env['hr.employee'].create({
            'name': 'Final Settlement Exiting Employee',
            'company_id': self.company.id,
            'first_contract_date': Date.from_string('2019-01-01'),
        })

    def test_01_final_settlement_creation_and_sequence(self):
        """Test master record creation and auto sequence generation."""
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'exit_reason': 'resignation',
            'last_working_day': Date.from_string('2026-03-31'),
            'settlement_date': Date.from_string('2026-03-31'),
        })
        self.assertTrue(settlement.name.startswith('FSET/'))
        self.assertEqual(settlement.state, 'draft')
        self.assertEqual(settlement.employee_id, self.employee)
        self.assertEqual(settlement.company_id, self.company)

    def test_02_optional_resignation_linkage(self):
        """Test optional linked resignation request field."""
        resignation = self.env['hr.resignation'].create({
            'employee_id': self.employee.id,
            'resignation_type': 'resigned',
            'joined_date': Date.from_string('2019-01-01'),
            'expected_revealing_date': Date.from_string('2026-03-31'),
            'reason': 'Career advancement',
        })
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'resignation_id': resignation.id,
            'last_working_day': Date.from_string('2026-03-31'),
        })
        self.assertEqual(settlement.resignation_id, resignation)
        self.assertEqual(settlement.employee_id, self.employee)

    def test_03_status_workflow_transitions(self):
        """Test status workflow field values."""
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'last_working_day': Date.from_string('2026-03-31'),
        })
        self.assertEqual(settlement.state, 'draft')

        settlement.write({'state': 'approved'})
        self.assertEqual(settlement.state, 'approved')

        settlement.write({'state': 'cancel'})
        self.assertEqual(settlement.state, 'cancel')

    def test_04_notice_shortfall_working_schedule_calculation(self):
        """Test notice shortfall recovery calculates on working schedule (resource.calendar) days."""
        contract = self.employee.version_id
        if contract:
            contract.write({
                'wage': 60000.0,
                'basic_salary': 50000.0,
                'da': 10000.0,
            })
        else:
            contract = self.env['hr.version'].create({
                'name': 'Settlement Contract',
                'employee_id': self.employee.id,
                'wage': 60000.0,
                'basic_salary': 50000.0,
                'da': 10000.0,
                'date_start': Date.from_string('2019-01-01'),
            })

        # Resignation with 15 unserved days (Approved Oct 15 vs Expected Oct 31)
        resignation = self.env['hr.resignation'].create({
            'employee_id': self.employee.id,
            'resignation_type': 'resigned',
            'joined_date': Date.from_string('2019-01-01'),
            'expected_revealing_date': Date.from_string('2026-10-31'),
            'approved_revealing_date': Date.from_string('2026-10-15'),
            'reason': 'Relocating',
        })
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'resignation_id': resignation.id,
            'last_working_day': Date.from_string('2026-10-15'),
        })

        # pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_final_settlement.services.final_settlement_calculation_service import FinalSettlementCalculationService
        svc = FinalSettlementCalculationService(self.env)
        notice_line = svc._compute_notice_pay_component(settlement, self.employee, Date.from_string('2026-10-15'))

        self.assertIsNotNone(notice_line)
        self.assertEqual(notice_line['component_code'], 'NOTICE_RECOVERY')
        self.assertEqual(notice_line['line_type'], 'deduction')
        # In Oct 2026, 40h/week calendar: 22 working days in month, 11 unserved working days between Oct 16 and Oct 31
        # Daily rate = 60,000 / 22 = 2727.27, 11 days = 30,000.0 (Exactly 50% of monthly salary)
        self.assertEqual(notice_line['amount'], 30000.0)

    def test_05_final_month_salary_working_schedule_proration(self):
        """Test final month worked salary calculates on working schedule (resource.calendar) days."""
        contract = self.employee.version_id
        if contract:
            contract.write({
                'wage': 60000.0,
                'basic_salary': 50000.0,
                'da': 10000.0,
                'date_start': Date.from_string('2019-01-01'),
                'pay_by_attendance': False,
            })
        else:
            contract = self.env['hr.version'].create({
                'name': 'Settlement Contract',
                'employee_id': self.employee.id,
                'wage': 60000.0,
                'basic_salary': 50000.0,
                'da': 10000.0,
                'date_start': Date.from_string('2019-01-01'),
                'pay_by_attendance': False,
            })

        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'last_working_day': Date.from_string('2026-10-15'),
        })

        # pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_final_settlement.services.final_settlement_calculation_service import FinalSettlementCalculationService
        svc = FinalSettlementCalculationService(self.env)
        salary_line = svc._compute_final_month_salary_component(settlement, self.employee, Date.from_string('2026-10-15'))

        self.assertIsNotNone(salary_line)
        self.assertEqual(salary_line['component_code'], 'FINAL_MONTH_SALARY')
        self.assertEqual(salary_line['line_type'], 'earning')
        # In Oct 2026, 40h/week calendar: 22 working days in month, 11 worked days between Oct 1 and Oct 15
        # Prorated wage = 60,000 * (11 / 22) = 30,000.0
        self.assertEqual(salary_line['amount'], 30000.0)

    def test_06_final_settlement_computation_includes_worked_salary(self):
        """Test full compute_settlement includes final month worked salary in breakdown lines and totals."""
        contract = self.employee.version_id
        if contract:
            contract.write({
                'wage': 60000.0,
                'basic_salary': 50000.0,
                'da': 10000.0,
                'date_start': Date.from_string('2019-01-01'),
                'pay_by_attendance': False,
            })
        else:
            contract = self.env['hr.version'].create({
                'name': 'Settlement Contract',
                'employee_id': self.employee.id,
                'wage': 60000.0,
                'basic_salary': 50000.0,
                'da': 10000.0,
                'date_start': Date.from_string('2019-01-01'),
                'pay_by_attendance': False,
            })

        resignation = self.env['hr.resignation'].create({
            'employee_id': self.employee.id,
            'resignation_type': 'resigned',
            'joined_date': Date.from_string('2019-01-01'),
            'expected_revealing_date': Date.from_string('2026-10-31'),
            'approved_revealing_date': Date.from_string('2026-10-15'),
            'reason': 'Relocating',
        })
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'resignation_id': resignation.id,
            'last_working_day': Date.from_string('2026-10-15'),
        })

        settlement.action_compute_settlement()

        codes = settlement.line_ids.mapped('component_code')
        self.assertIn('FINAL_MONTH_SALARY', codes)
        self.assertIn('NOTICE_RECOVERY', codes)

        sal_line = settlement.line_ids.filtered(lambda l: l.component_code == 'FINAL_MONTH_SALARY')
        self.assertEqual(sal_line.amount, 30000.0)
        self.assertEqual(sal_line.line_type, 'earning')

        # Total earnings includes at least the 30,000 worked salary
        self.assertGreaterEqual(settlement.total_earnings, 30000.0)
        # Net settlement = earnings - deductions
        self.assertEqual(settlement.net_settlement_amount, settlement.total_earnings - settlement.total_deductions)

    def test_07_final_month_salary_sync_from_linked_payslip(self):
        """Test final month salary synchronizes accurately from linked payslip lines."""
        contract = self.employee.version_id
        if contract:
            contract.write({
                'wage': 60000.0,
                'basic_salary': 50000.0,
                'da': 10000.0,
                'date_start': Date.from_string('2019-01-01'),
            })
        else:
            contract = self.env['hr.version'].create({
                'name': 'Settlement Contract',
                'employee_id': self.employee.id,
                'wage': 60000.0,
                'basic_salary': 50000.0,
                'da': 10000.0,
                'date_start': Date.from_string('2019-01-01'),
            })

        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'last_working_day': Date.from_string('2026-10-15'),
        })

        # Create a mock payslip linked to settlement with regular lines and gratuity line
        cat_basic = self.env.ref('hudson_payroll_base.rule_category_basic', raise_if_not_found=False)
        cat_alw = self.env.ref('hudson_payroll_base.rule_category_alw', raise_if_not_found=False)
        rule_basic = self.env.ref('hudson_payroll_base.hr_rule_basic', raise_if_not_found=False) or self.env['hr.salary.rule'].search([], limit=1)
        rule_da = self.env.ref('hudson_in_payroll.hr_rule_da_india', raise_if_not_found=False) or rule_basic
        rule_grat = self.env.ref('hudson_in_payroll.hds_in_rule_gratuity', raise_if_not_found=False) or rule_basic

        payslip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'contract_id': contract.id,
            'date_from': Date.from_string('2026-10-01'),
            'date_to': Date.from_string('2026-10-15'),
            'name': 'Test Settlement Payslip',
        })
        self.env['hr.payslip.line'].create([
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Basic Salary',
                'code': 'BASIC',
                'salary_rule_id': rule_basic.id if rule_basic else False,
                'category_id': cat_basic.id if cat_basic else False,
                'amount': 25000.0,
                'total': 25000.0,
            },
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Dearness Allowance',
                'code': 'DA',
                'salary_rule_id': rule_da.id if rule_da else False,
                'category_id': cat_alw.id if cat_alw else False,
                'amount': 5000.0,
                'total': 5000.0,
            },
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Gratuity',
                'code': 'GRATUITY',
                'salary_rule_id': rule_grat.id if rule_grat else False,
                'category_id': cat_alw.id if cat_alw else False,
                'amount': 100000.0,
                'total': 100000.0,
            },
        ])
        settlement.payslip_id = payslip.id

        # pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_final_settlement.services.final_settlement_calculation_service import FinalSettlementCalculationService
        svc = FinalSettlementCalculationService(self.env)
        salary_line = svc._compute_final_month_salary_component(settlement, self.employee, Date.from_string('2026-10-15'))

        # Must sync BASIC (25k) + DA (5k) = 30k, and exclude GRATUITY (100k)
        self.assertEqual(salary_line['amount'], 30000.0)
        self.assertIn('synced from settlement payslip', salary_line['description'])

    def test_08_settlement_syncs_payslip_deductions_and_matches_net(self):
        """Test final settlement pulls statutory employee deductions (EPF, PT, TDS) from linked payslip."""
        contract = self.employee.version_id
        if contract:
            contract.write({
                'wage': 60000.0,
                'basic_salary': 50000.0,
                'da': 10000.0,
                'date_start': Date.from_string('2019-01-01'),
            })
        else:
            contract = self.env['hr.version'].create({
                'name': 'Settlement Contract',
                'employee_id': self.employee.id,
                'wage': 60000.0,
                'basic_salary': 50000.0,
                'da': 10000.0,
                'date_start': Date.from_string('2019-01-01'),
            })

        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'last_working_day': Date.from_string('2026-10-31'),
        })

        cat_basic = self.env.ref('hudson_payroll_base.rule_category_basic', raise_if_not_found=False)
        cat_alw = self.env.ref('hudson_payroll_base.rule_category_alw', raise_if_not_found=False)
        cat_ded = self.env.ref('hudson_payroll_base.rule_category_ded', raise_if_not_found=False)
        rule_basic = self.env.ref('hudson_payroll_base.hr_rule_basic', raise_if_not_found=False) or self.env['hr.salary.rule'].search([], limit=1)
        rule_alw = self.env['hr.salary.rule'].search([('category_id.code', '=', 'ALW')], limit=1) or rule_basic
        rule_ded = self.env['hr.salary.rule'].search([('category_id.code', '=', 'DED')], limit=1) or rule_basic

        payslip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'contract_id': contract.id,
            'date_from': Date.from_string('2026-10-01'),
            'date_to': Date.from_string('2026-10-31'),
            'name': 'Test Settlement Payslip with Deductions',
        })
        self.env['hr.payslip.line'].create([
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Basic Salary',
                'code': 'BASIC',
                'salary_rule_id': rule_basic.id if rule_basic else False,
                'category_id': cat_basic.id if cat_basic else False,
                'amount': 50000.0,
                'total': 50000.0,
            },
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Dearness Allowance',
                'code': 'DA',
                'salary_rule_id': rule_alw.id if rule_alw else False,
                'category_id': cat_alw.id if cat_alw else False,
                'amount': 10000.0,
                'total': 10000.0,
            },
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Employee Provident Fund (EPF)',
                'code': 'EPF',
                'salary_rule_id': rule_ded.id if rule_ded else False,
                'category_id': cat_ded.id if cat_ded else False,
                'amount': -1800.0,
                'total': -1800.0,
            },
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Professional Tax',
                'code': 'PT',
                'salary_rule_id': rule_ded.id if rule_ded else False,
                'category_id': cat_ded.id if cat_ded else False,
                'amount': -200.0,
                'total': -200.0,
            },
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Tax Deducted at Source (TDS)',
                'code': 'HDS_IN_TDS',
                'salary_rule_id': rule_ded.id if rule_ded else False,
                'category_id': cat_ded.id if cat_ded else False,
                'amount': -3000.0,
                'total': -3000.0,
            },
        ])
        settlement.write({'payslip_id': payslip.id})
        settlement.action_compute_settlement()

        codes = settlement.line_ids.mapped('component_code')
        self.assertIn('FINAL_MONTH_SALARY', codes)
        self.assertIn('EPF', codes)
        self.assertIn('PT', codes)
        self.assertIn('HDS_IN_TDS', codes)

        epf_line = settlement.line_ids.filtered(lambda l: l.component_code == 'EPF')
        self.assertEqual(epf_line.line_type, 'deduction')
        self.assertEqual(epf_line.amount, 1800.0)

        pt_line = settlement.line_ids.filtered(lambda l: l.component_code == 'PT')
        self.assertEqual(pt_line.line_type, 'deduction')
        self.assertEqual(pt_line.amount, 200.0)

        tds_line = settlement.line_ids.filtered(lambda l: l.component_code == 'HDS_IN_TDS')
        self.assertEqual(tds_line.line_type, 'deduction')
        self.assertEqual(tds_line.amount, 3000.0)

        self.assertGreaterEqual(settlement.total_earnings, 60000.0)
        self.assertGreaterEqual(settlement.total_deductions, 5000.0)
        self.assertEqual(settlement.net_settlement_amount, settlement.total_earnings - settlement.total_deductions)

    def test_09_settlement_shows_both_exit_and_normal_leave_encashment(self):
        """Test settlement distinctly lists both Normal Leave Encashment and Exit Leave Encashment."""
        contract = self.employee.version_id
        if contract:
            contract.write({
                'wage': 50000.0,
                'basic_salary': 50000.0,
                'date_start': Date.from_string('2026-01-01'),
            })

        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'last_working_day': Date.from_string('2026-11-30'),
        })

        rule_alw = self.env['hr.salary.rule'].search([('category_id.code', '=', 'ALW')], limit=1)
        rule_basic = self.env['hr.salary.rule'].search([('category_id.code', '=', 'BASIC')], limit=1)
        rule_ded = self.env['hr.salary.rule'].search([('category_id.code', '=', 'DED')], limit=1)
        cat_alw = rule_alw.category_id if rule_alw else False
        cat_basic = rule_basic.category_id if rule_basic else False
        cat_ded = rule_ded.category_id if rule_ded else False

        payslip = self.env['hr.payslip'].create({
            'name': 'Test Settlement Slip With Both Encashes',
            'employee_id': self.employee.id,
            'contract_id': contract.id if contract else False,
            'date_from': Date.from_string('2026-11-01'),
            'date_to': Date.from_string('2026-11-30'),
        })

        self.env['hr.payslip.line'].create([
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Basic Salary',
                'code': 'BASIC',
                'salary_rule_id': rule_basic.id if rule_basic else False,
                'category_id': cat_basic.id if cat_basic else False,
                'amount': 50000.0,
                'total': 50000.0,
            },
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Normal Leave Encashment',
                'code': 'LEAVE_ENCASH',
                'salary_rule_id': rule_alw.id if rule_alw else False,
                'category_id': cat_alw.id if cat_alw else False,
                'amount': 5000.0,
                'total': 5000.0,
            },
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Exit Leave Encashment',
                'code': 'EXIT_LEAVE_ENCASH',
                'salary_rule_id': rule_alw.id if rule_alw else False,
                'category_id': cat_alw.id if cat_alw else False,
                'amount': 20000.0,
                'total': 20000.0,
            },
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Gratuity',
                'code': 'GRATUITY',
                'salary_rule_id': rule_alw.id if rule_alw else False,
                'category_id': cat_alw.id if cat_alw else False,
                'amount': 30000.0,
                'total': 30000.0,
            },
            {
                'slip_id': payslip.id,
                'employee_id': self.employee.id,
                'contract_id': contract.id,
                'name': 'Employee Provident Fund (EPF)',
                'code': 'EPF',
                'salary_rule_id': rule_ded.id if rule_ded else False,
                'category_id': cat_ded.id if cat_ded else False,
                'amount': -1800.0,
                'total': -1800.0,
            },
        ])

        settlement.write({'payslip_id': payslip.id})
        settlement.action_compute_settlement()

        codes = settlement.line_ids.mapped('component_code')
        self.assertIn('FINAL_MONTH_SALARY', codes)
        self.assertIn('LEAVE_ENCASH', codes)
        self.assertIn('EXIT_LEAVE_ENCASH', codes)
        self.assertIn('GRATUITY', codes)
        self.assertIn('EPF', codes)

        norm_line = settlement.line_ids.filtered(lambda l: l.component_code == 'LEAVE_ENCASH')
        self.assertEqual(norm_line.line_type, 'earning')
        self.assertEqual(norm_line.amount, 5000.0)

        exit_line = settlement.line_ids.filtered(lambda l: l.component_code == 'EXIT_LEAVE_ENCASH')
        self.assertEqual(exit_line.line_type, 'earning')
        self.assertEqual(exit_line.amount, 20000.0)

        sal_line = settlement.line_ids.filtered(lambda l: l.component_code == 'FINAL_MONTH_SALARY')
        self.assertEqual(sal_line.amount, 50000.0)

        epf_line = settlement.line_ids.filtered(lambda l: l.component_code == 'EPF')
        self.assertEqual(epf_line.amount, 1800.0)

        self.assertEqual(settlement.total_earnings, 105000.0)
        self.assertEqual(settlement.total_deductions, 1800.0)
        self.assertEqual(settlement.net_settlement_amount, 103200.0)

    def test_10_manual_custom_lines_preserved_on_recompute(self):
        """Test HR manual custom deduction/earning lines are preserved during recomputation."""
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'last_working_day': Date.from_string('2026-11-30'),
        })
        settlement.action_compute_settlement()

        # Simulate HR manually adding a custom recovery line (e.g. Asset Damage)
        self.env['final.settlement.line'].create({
            'settlement_id': settlement.id,
            'component_code': 'ASSET_DAMAGE',
            'component_name': 'Laptop Damage Recovery',
            'line_type': 'deduction',
            'sequence': 80,
            'amount': 4500.0,
            'description': 'Deduction for broken screen per company property policy.',
        })

        ded_before = settlement.total_deductions
        # Trigger recomputation
        settlement.action_compute_settlement()

        codes = settlement.line_ids.mapped('component_code')
        self.assertIn('ASSET_DAMAGE', codes, "Manual line must not be wiped out on recompute.")
        damage_line = settlement.line_ids.filtered(lambda l: l.component_code == 'ASSET_DAMAGE')
        self.assertEqual(damage_line.amount, 4500.0)
        self.assertEqual(settlement.net_settlement_amount, settlement.total_earnings - settlement.total_deductions)

    def test_11_exit_leave_deduction_on_approve_and_restore_on_reset_draft(self):
        """Test exit leave encashment days are deducted from Time Off allocations on approve and restored on reset draft."""
        alloc_model = self.env['hr.leave.allocation']
        alloc_field = 'work_entry_type_id' if 'work_entry_type_id' in alloc_model._fields else 'holiday_status_id'
        leave_type = self.env['hr.work.entry.type'].search([('include_in_leave_encashment', '=', True)], limit=1)
        if not leave_type:
            leave_type = self.env['hr.work.entry.type'].create({
                'name': 'Test Encashable Leave',
                'code': 'TEL',
                'include_in_leave_encashment': True,
            })
        else:
            leave_type.write({'include_in_leave_encashment': True})

        # Remove existing allocations for test employee to isolate
        existing_allocs = alloc_model.search([('employee_id', '=', self.employee.id)])
        existing_allocs.sudo().unlink()

        alloc = alloc_model.create({
            'name': 'Test Annual Leave 10 Days',
            'employee_id': self.employee.id,
            alloc_field: leave_type.id,
            'number_of_days': 10.0,
        })
        if hasattr(alloc, 'action_approve'):
            try:
                alloc.action_approve()
            except Exception:
                alloc.state = 'validate'
        else:
            alloc.state = 'validate'
        self.assertEqual(alloc.number_of_days, 10.0)

        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'last_working_day': Date.from_string('2026-11-30'),
            'settlement_date': Date.from_string('2026-11-30'),
        })

        # Step 1: Compute in draft (Preview only - allocations NOT deducted yet)
        settlement.action_compute_settlement()
        self.assertEqual(settlement.state, 'draft')
        self.assertFalse(settlement.is_exit_leave_deducted)
        self.assertEqual(settlement.exit_leave_encash_days, 10.0)
        self.assertEqual(alloc.number_of_days, 10.0, "Allocations must NOT be modified in draft.")

        # Step 2: Direct 1-Click Approve (Deduction committed to Time Off allocations)
        settlement.action_approve()
        self.assertEqual(settlement.state, 'approved')
        self.assertTrue(settlement.is_exit_leave_deducted)
        alloc.invalidate_recordset(['number_of_days'])
        self.assertEqual(alloc.number_of_days, 0.0, "10 encashed days must be deducted from allocation.")

        # Step 4: Reset to Draft (Allocations automatically restored)
        settlement.action_reset_draft()
        self.assertEqual(settlement.state, 'draft')
        self.assertFalse(settlement.is_exit_leave_deducted)
        alloc.invalidate_recordset(['number_of_days'])
        self.assertEqual(alloc.number_of_days, 10.0, "Allocations must be fully restored when reset to draft.")

    def test_18b_reset_to_draft_with_unconfirmed_payslip_cancellation(self):
        """Test Reset to Draft cancels unconfirmed payslip, restores leave allocations, and re-enables recalculation."""
        if 'hr.leave.type' not in self.env or 'hr.leave.allocation' not in self.env:
            return
        holiday_type = self.env['hr.leave.type'].search([], limit=1)
        if not holiday_type:
            holiday_type = self.env['hr.leave.type'].create({
                'name': 'Reset Test Earned Leave',
                'time_type': 'leave',
                'allocation_validation_type': 'no_validation',
            })
        if 'include_in_leave_encashment' in holiday_type._fields:
            holiday_type.include_in_leave_encashment = True

        alloc = self.env['hr.leave.allocation'].create({
            'name': 'Reset Test Allocation',
            'holiday_status_id': holiday_type.id,
            'employee_id': self.employee.id,
            'number_of_days': 5.0,
            'state': 'validate',
        })

        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'last_working_day': Date.from_string('2026-11-30'),
            'settlement_date': Date.from_string('2026-11-30'),
        })
        self.env['final.settlement.line'].create({
            'settlement_id': settlement.id,
            'component_code': 'EXIT_LEAVE_ENCASH',
            'component_name': 'Exit Leave Encashment',
            'line_type': 'earning',
            'amount': 25000.0,
        })
        settlement.exit_leave_encash_days = 5.0

        # Approve: Deducts Time Off leave days
        settlement.action_approve()
        self.assertEqual(settlement.state, 'approved')
        self.assertTrue(settlement.is_exit_leave_deducted)
        alloc.invalidate_recordset(['number_of_days'])
        self.assertEqual(alloc.number_of_days, 0.0)

        # Generate draft settlement payslip
        settlement.action_generate_settlement_payslip()
        self.assertTrue(settlement.payslip_id)
        slip = settlement.payslip_id
        self.assertIn(slip.state, ('draft', 'verify'))

        # Reset to Draft
        settlement.action_reset_draft()
        self.assertEqual(settlement.state, 'draft')
        self.assertFalse(settlement.is_exit_leave_deducted)
        alloc.invalidate_recordset(['number_of_days'])
        self.assertEqual(alloc.number_of_days, 5.0, "Leave allocations must be fully restored upon reset.")

        # Payslip must be cancelled and unlinked
        slip.invalidate_recordset(['state'])
        self.assertEqual(slip.state, 'cancel', "Unconfirmed settlement payslip must be cancelled.")
        self.assertFalse(settlement.payslip_id, "Linked payslip reference must be cleared.")

        # Re-enables editing and recalculation in draft
        settlement.write({'last_working_day': Date.from_string('2026-12-15')})
        settlement.action_compute_settlement()
        self.assertEqual(settlement.state, 'draft')

    def test_19_settlement_report_action_and_rendering(self):
        """Test Full & Final Settlement PDF report action and data preparation."""
        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'exit_reason': 'resignation',
            'last_working_day': Date.from_string('2026-03-31'),
            'settlement_date': Date.from_string('2026-03-31'),
        })
        self.env['final.settlement.line'].create({
            'settlement_id': settlement.id,
            'component_code': 'GRATUITY',
            'component_name': 'Gratuity',
            'line_type': 'earning',
            'amount': 50000.0,
        })
        self.env['final.settlement.line'].create({
            'settlement_id': settlement.id,
            'component_code': 'EPF',
            'component_name': 'EPF Deduction',
            'line_type': 'deduction',
            'amount': 1800.0,
        })
        # Check report data helper
        data = settlement._get_settlement_report_data()
        self.assertIn('emp_code', data)
        self.assertIn('exit_reason_label', data)
        self.assertIn('amount_in_words', data)

        # Check action_print_settlement_report
        action = settlement.action_print_settlement_report()
        self.assertEqual(action.get('type'), 'ir.actions.report')
        self.assertEqual(action.get('report_name'), 'hudson_in_final_settlement.report_final_settlement_document')

        # Check QWeb HTML rendering
        report_action = self.env.ref('hudson_in_final_settlement.action_report_final_settlement')
        html, _ = report_action._render_qweb_html('hudson_in_final_settlement.report_final_settlement_document', [settlement.id])
        self.assertTrue(len(html) > 0)
        self.assertIn(b'Final Settlement Statement', html)

    def test_14_final_month_salary_zero_attendance_pay_by_attendance(self):
        """Test final month salary evaluates to 0.0 upfront when pay_by_attendance is True and attendance is 0."""
        # Use June 2026 where there are no public holidays to guarantee zero earned hours
        contract = self.employee.version_id
        if contract:
            contract.write({
                'wage': 50000.0,
                'basic_salary': 40000.0,
                'da': 10000.0,
                'date_start': Date.from_string('2019-01-01'),
                'pay_by_attendance': True,
            })
        else:
            contract = self.env['hr.version'].create({
                'name': 'Settlement Contract June',
                'employee_id': self.employee.id,
                'wage': 50000.0,
                'basic_salary': 40000.0,
                'da': 10000.0,
                'date_start': Date.from_string('2019-01-01'),
                'pay_by_attendance': True,
            })

        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'last_working_day': Date.from_string('2026-06-15'),
        })

        # pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_final_settlement.services.final_settlement_calculation_service import FinalSettlementCalculationService
        svc = FinalSettlementCalculationService(self.env)
        salary_line = svc._compute_final_month_salary_component(settlement, self.employee, Date.from_string('2026-06-15'))

        self.assertIsNotNone(salary_line)
        self.assertEqual(salary_line['component_code'], 'FINAL_MONTH_SALARY')
        self.assertEqual(salary_line['amount'], 0.0)
        self.assertIn('No attendance records found', salary_line['description'])

    def test_22_settlement_payslip_deductions_sync_and_no_paid_stage(self):
        """Test generating settlement payslip computes sheet and fetches statutory deductions into settlement lines."""
        contract = self.employee.version_id
        if contract:
            contract.write({
                'wage': 60000.0,
                'basic_salary': 50000.0,
                'da': 10000.0,
                'date_start': Date.from_string('2019-01-01'),
            })

        settlement = self.env['final.settlement'].create({
            'employee_id': self.employee.id,
            'last_working_day': Date.from_string('2026-03-31'),
            'gratuity_gross_amount': 150000.0,
            'gratuity_exemption_amount': 2000000.0,
        })
        self.assertEqual(settlement.state, 'draft')

        # Approve
        settlement.action_approve()
        self.assertEqual(settlement.state, 'approved')

        # Generate Settlement Payslip
        settlement.action_generate_settlement_payslip()
        self.assertTrue(settlement.payslip_id)
        slip = settlement.payslip_id

        # Verify deductions are fetched
        deduction_lines = settlement.line_ids.filtered(lambda l: l.line_type == 'deduction')
        slip_deductions = slip.line_ids.filtered(lambda l: l.category_id.code in ('DED', 'DEDUCTION') and l.total != 0.0)
        if slip_deductions:
            self.assertTrue(len(deduction_lines) > 0, "Statutory deductions must be synced to settlement breakdown.")

        # Verify net settlement amount
        self.assertEqual(settlement.net_settlement_amount, settlement.total_earnings - settlement.total_deductions)

        # Verify 'paid' is not a valid workflow stage
        valid_states = dict(settlement._fields['state'].selection).keys()
        self.assertNotIn('paid', valid_states)

    def test_33_employee_company_alignment(self):
        """Test strict enforcement of employee and settlement company alignment."""
        from odoo.exceptions import ValidationError
        company2 = self.env['res.company'].create({'name': 'Separate Legal Entity Co'})
        employee2 = self.env['hr.employee'].create({
            'name': 'Company 2 Unique Employee',
            'company_id': company2.id,
        })

        # 1. Attempting to create settlement with mismatched company must raise ValidationError
        with self.assertRaises(ValidationError):
            self.env['final.settlement'].create({
                'employee_id': employee2.id,
                'company_id': self.company.id,  # Mismatched!
                'last_working_day': Date.from_string('2026-03-31'),
            })

        # 2. Creating with matching company succeeds
        settlement = self.env['final.settlement'].create({
            'employee_id': employee2.id,
            'company_id': company2.id,
            'last_working_day': Date.from_string('2026-03-31'),
        })
        self.assertEqual(settlement.company_id, company2)

        # 3. Writing a mismatched company must raise ValidationError
        with self.assertRaises(ValidationError):
            settlement.write({'company_id': self.company.id})

        # 4. Onchange employee_id syncs company_id
        new_settlement = self.env['final.settlement'].new({
            'company_id': self.company.id,
        })
        new_settlement.employee_id = employee2
        new_settlement._onchange_employee_id()
        self.assertEqual(new_settlement.company_id, company2)

        # 5. Onchange company_id clears mismatched employee
        new_settlement.company_id = self.company
        new_settlement._onchange_company_id()
        self.assertFalse(new_settlement.employee_id)

        # 6. action_generate_settlement_payslip verifies alignment and creates payslip under employee company
        settlement.action_approve()
        settlement.action_generate_settlement_payslip()
        self.assertTrue(settlement.payslip_id)
        self.assertEqual(settlement.payslip_id.company_id, company2)
