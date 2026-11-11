import logging
_logger = logging.getLogger(__name__)

# -*- coding: utf-8 -*-
"""
Standalone Verification Script for Hudson Indian Payroll - TDS Engine Phase 3
(Employee Tax Profile, FY Tax Regime Locking & Tax Declaration Framework)
"""
import py_compile
import sys
import xml.etree.ElementTree as ET

def print_header(title):
    _logger.info("=" * 80)
    _logger.info(f" {title}")
    _logger.info("=" * 80)

def test_python_syntax():
    files = [
        "models/hr_employee.py",
        "models/tds_employee_tax_regime.py",
        "models/tds_employee_declaration.py",
        "models/tds_employee_declaration_line.py",
        "models/tds_employee_income_declaration.py",
        "services/tds/employee_tax_declaration_validation_service.py",
        "services/tds/eligibility_rule_engine_service.py",
        "services/tds/salary_projection_service.py",
        "services/tds/payroll_income_projection_service.py",
        "services/tds/previous_employer_income_service.py",

        "services/tds/other_income_aggregation_service.py",
        "services/tds/regime_routing_service.py",
        "services/tds/annual_income_projection_service.py",
        "services/tds/standard_deduction_service.py",
        "services/tds/chapter6a_deduction_service.py",
        "services/tds/home_loan_deduction_service.py",
        "services/tds/deduction_calculation_service.py",
        "services/tds/taxable_income_service.py",
        "services/tds/income_tax_slab_service.py",
        "services/tds/rebate_engine_service.py",
        "services/tds/surcharge_engine_service.py",
        "services/tds/health_education_cess_service.py",
        "services/tds/previous_employer_tds_service.py",
        "services/tds/current_financial_year_tds_service.py",
        "services/tds/payroll_period_service.py",
        "services/tds/monthly_tds_distribution_service.py",
        "services/tds/tds_orchestration_engine.py",
        "tests/test_tds_phase3_declarations.py",
        "tests/test_tds_phase4_annual_income_projection.py",
        "tests/test_tds_phase5_deduction_calculation.py",
        "tests/test_tds_phase6_tax_computation.py",
        "tests/test_tds_phase10_monthly_distribution.py",
        "tests/test_tds_phase11_payroll_integration.py",
        "tests/test_tds_audit_logging.py",







    ]

    for f in files:
        try:
            py_compile.compile(f, doraise=True)
            _logger.info(f"  [PASS] Python Syntax OK: {f}")
        except Exception as e:
            _logger.info(f"  [FAIL] Python Syntax Error in {f}: {e}")
            return False
    return True

def test_xml_syntax():
    xml_files = [
        "views/tds_declaration_views.xml",
        "views/hr_employee_views.xml",
        "views/tds_configuration_views.xml",
    ]
    for f in xml_files:
        try:
            tree = ET.parse(f)
            root = tree.getroot()
            records = root.findall(".//record")
            _logger.info(f"  [PASS] XML Syntax OK: {f} ({len(records)} records found)")
        except Exception as e:
            _logger.info(f"  [FAIL] XML Syntax Error in {f}: {e}")
            return False
    return True

def test_declaration_disallowed_categories():
    with open("services/tds/employee_tax_declaration_validation_service.py", "r", encoding="utf-8") as f:
        content = f.read()
    expected = {'80c', '80ccd1b', '80d_self', '80d_parents', '80d_preventive', '80tta', '80ttb', '80dd', '24b', '80eea', 'hra', 'children_edu', 'hostel', 'lta'}
    missing = [c for c in expected if f"'{c}'" not in content]
    if missing:
        _logger.info(f"  [FAIL] Disallowed categories missing in validation service: {missing}")
        return False
    _logger.info(f"  [PASS] All {len(expected)} unpermitted New Regime categories registered cleanly in validation service.")
    return True


def main():
    print_header("HUDSON INDIAN PAYROLL - TDS ENGINE PHASE 3 VERIFICATION SUITE")
    passed = 0
    total = 3

    if test_python_syntax(): passed += 1
    if test_xml_syntax(): passed += 1
    if test_declaration_disallowed_categories(): passed += 1

    _logger.info("=" * 80)
    _logger.info(f" VERIFICATION SUMMARY: {passed}/{total} PASSED")
    _logger.info("=" * 80)

    if passed != total:
        sys.exit(1)

if __name__ == '__main__':
    main()
