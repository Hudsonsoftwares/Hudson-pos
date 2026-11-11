# -*- coding: utf-8 -*-
"""
Hudson Indian Payroll - Professional Tax (PT) Shell Verification Script
Run interactively via Odoo shell or python environment:
    python odoo-bin shell -c odoo.conf -d your_database < hudson_in_payroll/verify_pt_shell.py

Or execute directly in Python console:
    exec(open('d:/cistom_addon2/hudson_in_payroll/verify_pt_shell.py').read())
"""

import sys
import logging

_logger = logging.getLogger("verify_pt_shell")

def run_verification(env):
    _logger.info("=" * 80)
    _logger.info(" HUDSON INDIAN PAYROLL - PROFESSIONAL TAX (PT) VERIFICATION SUITE")
    _logger.info("=" * 80)

    pass_count = 0
    fail_count = 0

    def print_result(step_num, title, success, details=""):
        nonlocal pass_count, fail_count
        status = "PASS" if success else "FAIL"
        if success:
            pass_count += 1
        else:
            fail_count += 1
        _logger.info(f"[{step_num}] {title:<55} {status}")
        if details:
            _logger.info(f"    └─ {details}")

    # 1. Check Company Configuration
    try:
        company = env.company
        has_pt_enabled = hasattr(company, 'hds_in_enable_professional_tax')
        has_pt_reg = hasattr(company, 'hds_in_professional_tax_registration_no')
        success = has_pt_enabled and has_pt_reg
        print_result(1, "Company Configuration (res.company PT fields)", success, f"Enabled: {getattr(company, 'hds_in_enable_professional_tax', False)}")
    except Exception as e:
        print_result(1, "Company Configuration", False, str(e))

    # 2. Check State Slab Master Seed Data
    try:
        total_slabs = env['pt.state.slab'].search_count([])
        success = total_slabs >= 40
        print_result(2, "PT State Slab Master Data (40 confirmed slabs)", success, f"Found {total_slabs} total slab records in DB")
    except Exception as e:
        print_result(2, "PT State Slab Master Data", False, str(e))

    # 3. Check ProfessionalTaxSlabService
    try:
        from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_slab_service import ProfessionalTaxSlabService
        slab_svc = ProfessionalTaxSlabService(env)
        state_mh = env.ref('base.state_in_mh')
        res_mh = slab_svc.get_applicable_slab(salary=15000.0, state=state_mh, gender='male')
        success = res_mh is not None and res_mh.pt_amount == 200.0
        print_result(3, "ProfessionalTaxSlabService Lookup", success, f"MH ₹15k Male -> PT ₹{getattr(res_mh, 'pt_amount', 0)}")
    except Exception as e:
        print_result(3, "ProfessionalTaxSlabService Lookup", False, str(e))

    # 4. Check PTValidator
    try:
        from odoo.addons.hudson_in_payroll.services.professional_tax.pt_validator import PTValidator
        validator = PTValidator(env)
        state_mh = env.ref('base.state_in_mh')
        val_res = validator.validate(salary=15000.0, state=state_mh, company=env.company)
        success = val_res.is_valid and val_res.validation_status == 'VALID'
        print_result(4, "PTValidator Eligibility Check", success, f"Status: {getattr(val_res, 'validation_status', None)}")
    except Exception as e:
        print_result(4, "PTValidator Eligibility Check", False, str(e))

    # 5. Check PTCalculator (Standard & Feb Override)
    try:
        from odoo.addons.hudson_in_payroll.services.professional_tax.pt_calculator import PTCalculator
        calculator = PTCalculator(env)
        state_mh = env.ref('base.state_in_mh')
        res_mh = slab_svc.get_applicable_slab(salary=15000.0, state=state_mh, gender='male')
        calc_jan = calculator.calculate(slab=res_mh, eval_date='2026-01-15')
        calc_feb = calculator.calculate(slab=res_mh, eval_date='2026-02-15')
        success = calc_jan.pt_amount == 200.0 and calc_feb.pt_amount == 300.0 and calc_feb.override_applied
        print_result(5, "PTCalculator (Standard & Feb Override)", success, f"Jan: ₹{calc_jan.pt_amount}, Feb Override: ₹{calc_feb.pt_amount}")
    except Exception as e:
        print_result(5, "PTCalculator", False, str(e))

    # 6. Check ProfessionalTaxService Orchestrator
    try:
        from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_service import ProfessionalTaxService
        pt_svc = ProfessionalTaxService(env)
        state_mh = env.ref('base.state_in_mh')
        orch_res = pt_svc.compute_pt(salary=15000.0, state=state_mh, gender='male', eval_date='2026-06-01')
        success = orch_res.is_valid and orch_res.amount == 200.0
        print_result(6, "ProfessionalTaxService Orchestration", success, f"Amount: ₹{orch_res.amount}, Status: {orch_res.validation_status}")
    except Exception as e:
        print_result(6, "ProfessionalTaxService Orchestration", False, str(e))

    # 7. Check HrPayslip Integration & Salary Rule
    try:
        rule_pt = env.ref('hudson_in_payroll.hds_in_rule_pt')
        has_rule = rule_pt.code == 'PT'
        has_api = hasattr(env['hr.payslip'], 'hds_in_compute_professional_tax')
        success = has_rule and has_api
        print_result(7, "HrPayslip Integration & PT Salary Rule", success, f"Rule 'PT' Code: {rule_pt.code}, API Method: {has_api}")
    except Exception as e:
        print_result(7, "HrPayslip Integration & PT Salary Rule", False, str(e))

    _logger.info("=" * 80)
    _logger.info(f" VERIFICATION SUMMARY: {pass_count} PASSED, {fail_count} FAILED")
    _logger.info("=" * 80)

if 'env' in locals() or 'env' in globals():
    run_verification(env)
