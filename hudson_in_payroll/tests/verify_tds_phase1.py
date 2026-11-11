import re
import sys
import os

sys.path.insert(0, r"C:\Program Files\Odoo 19.0.20260717\server")
sys.path.insert(0, r"d:\cistom_addon2")


import logging

_logger = logging.getLogger("verify_tds_phase1")


def verify_tds_phase1_standalone():
    _logger.info("=" * 80)
    _logger.info(" HUDSON INDIAN PAYROLL - TDS ENGINE PHASE 1 VERIFICATION SUITE")
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
            _logger.info(f"    |- {details}")


    # 1. Test TAN Regex Pattern
    tan_pattern = re.compile(r'^[A-Z]{4}[0-9]{5}[A-Z]{1}$')
    valid_tans = ['ABCD12345E', 'MUMB12345A', 'DELA98765B', 'CHNA11223D']
    invalid_tans = ['12345', 'ABCDE12345', 'abcd123', 'ABCD123456', '1234ABCD5E', '']

    valid_ok = all(tan_pattern.match(t) for t in valid_tans)
    invalid_ok = all(not tan_pattern.match(t) for t in invalid_tans)
    print_result(1, "TAN Regex Pattern Matching", valid_ok and invalid_ok, f"Valid TANs OK: {valid_ok}, Invalid TANs Rejected: {invalid_ok}")

    # 2. Test TdsCompanyConfigValidator Import & Disabled Case
    try:
        from services.tds.tds_company_config_validator import TdsCompanyConfigValidator, TdsCompanyValidationResult

        class MockCompanyDisabled:
            name = "Test Company Disabled"
            hds_in_tds_applicable = False
            hds_in_tan = False
            hds_in_default_tax_regime = 'new'
            hds_in_default_tax_year = None

        validator = TdsCompanyConfigValidator()
        res_disabled = validator.validate(MockCompanyDisabled())
        success = res_disabled.is_valid and not res_disabled.is_enabled
        print_result(2, "TdsCompanyConfigValidator (Disabled TDS)", success, f"Reason: '{res_disabled.reason}'")
    except Exception as e:
        print_result(2, "TdsCompanyConfigValidator (Disabled TDS)", False, str(e))

    # 3. Test TdsCompanyConfigValidator (Enabled TDS & Valid TAN)
    try:
        class MockCompanyEnabledValid:
            name = "Test Company Enabled Valid"
            hds_in_tds_applicable = True
            hds_in_tan = "  mumb12345a  "
            hds_in_default_tax_regime = 'new'
            hds_in_default_tax_year = None

        res_valid = validator.validate(MockCompanyEnabledValid())
        success = res_valid.is_valid and res_valid.is_enabled and res_valid.tan == 'MUMB12345A'
        print_result(3, "TdsCompanyConfigValidator (Enabled TDS Valid TAN)", success, f"TAN Sanitized: {res_valid.tan}")
    except Exception as e:
        print_result(3, "TdsCompanyConfigValidator (Enabled TDS Valid TAN)", False, str(e))

    # 4. Test TdsCompanyConfigValidator (Enabled TDS & Invalid TAN)
    try:
        class MockCompanyEnabledInvalid:
            name = "Test Company Invalid TAN"
            hds_in_tds_applicable = True
            hds_in_tan = "INVALID123"
            hds_in_default_tax_regime = 'new'
            hds_in_default_tax_year = None

        res_invalid = validator.validate(MockCompanyEnabledInvalid())
        success = not res_invalid.is_valid and res_invalid.is_enabled
        print_result(4, "TdsCompanyConfigValidator (Invalid TAN Handling)", success, f"Reason: '{res_invalid.reason}'")
    except Exception as e:
        print_result(4, "TdsCompanyConfigValidator (Invalid TAN Handling)", False, str(e))

    # 5. Test Models File Reading & Syntax Check
    try:
        import py_compile
        py_compile.compile(r'd:\cistom_addon2\hudson_in_payroll\models\tds_financial_year.py', doraise=True)
        py_compile.compile(r'd:\cistom_addon2\hudson_in_payroll\models\res_company.py', doraise=True)
        py_compile.compile(r'd:\cistom_addon2\hudson_in_payroll\models\res_config_settings.py', doraise=True)
        print_result(5, "Model File Syntax Verification (tds_financial_year, res_company, res_config_settings)", True, "All model python files compiled without syntax errors")
    except Exception as e:
        print_result(5, "Model File Syntax Verification", False, str(e))

    # 6. Test Services File Syntax Check
    try:
        py_compile.compile(r'd:\cistom_addon2\hudson_in_payroll\services\tds\tds_company_config_validator.py', doraise=True)
        print_result(6, "Service File Syntax Verification (tds_company_config_validator)", True, "All service python files compiled without syntax errors")
    except Exception as e:
        print_result(6, "Service File Syntax Verification", False, str(e))

    # 7. Test Unit Test File Syntax Check
    try:
        py_compile.compile(r'd:\cistom_addon2\hudson_in_payroll\tests\test_tds_company_config.py', doraise=True)
        print_result(7, "Test Suite File Syntax Verification (test_tds_company_config)", True, "All test python files compiled without syntax errors")
    except Exception as e:
        print_result(7, "Test Suite File Syntax Verification", False, str(e))




    _logger.info("=" * 80)
    _logger.info(f" VERIFICATION SUMMARY: {pass_count} PASSED, {fail_count} FAILED")
    _logger.info("=" * 80)
    return fail_count == 0

if __name__ == '__main__':
    success = verify_tds_phase1_standalone()
    sys.exit(0 if success else 1)
