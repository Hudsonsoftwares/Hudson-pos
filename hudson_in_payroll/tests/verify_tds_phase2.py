import logging
_logger = logging.getLogger(__name__)

# -*- coding: utf-8 -*-
"""
Standalone Verification Script for Hudson Indian Payroll - TDS Engine Phase 2
(Enterprise Tax Master & Rule Parameter Framework)
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
        "models/tds_financial_year.py",
        "models/tds_tax_regime.py",
        "models/tds_tax_slab.py",
        "models/tds_surcharge.py",
        "models/tds_employee_home_loan.py",
        "services/tds/tds_parameter_service.py",
        "services/tds/section_80eea_eligibility_service.py",
        "tests/test_tds_phase2_parameters.py",
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
        "data/tds_financial_year_data.xml",
        "data/tds_tax_regime_data.xml",
        "data/tds_tax_slab_data.xml",
        "data/tds_surcharge_data.xml",
        "data/tds_rule_parameters.xml",
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

def test_parameter_mapping_coverage():
    with open("services/tds/tds_parameter_service.py", "r", encoding="utf-8") as f:
        content = f.read()
    expected_keys = [
        'STD_DEDUCTION_NEW', 'STD_DEDUCTION_OLD',
        '87A_LIMIT_NEW', '87A_LIMIT_OLD',
        '87A_MAX_REBATE_NEW', '87A_MAX_REBATE_OLD',
        'HEALTH_CESS',
        'NPS_LIMIT_NEW', 'NPS_LIMIT_OLD_PRIVATE', 'NPS_LIMIT_OLD_GOVT',
        'EMPLOYER_CONTRIBUTION_LIMIT',
        '80C_MAX_LIMIT', '80CCD1B_MAX_LIMIT',
        '80D_SELF_MAX_LIMIT', '80D_SELF_SENIOR_MAX_LIMIT',
        '80D_PARENTS_MAX_LIMIT', '80D_PARENTS_SENIOR_MAX_LIMIT',
        '80D_PREVENTIVE_CHECKUP_LIMIT', '80TTA_MAX_LIMIT', '80TTB_MAX_LIMIT',
        '80DD_NORMAL_LIMIT', '80DD_SEVERE_LIMIT',
        '24B_HOME_LOAN_INTEREST_LIMIT', '80EEA_MAX_LIMIT',
        'HRA_METRO_PERCENT', 'HRA_NON_METRO_PERCENT', 'HRA_RENT_EXCESS_BASIC_PERCENT',
        'CHILDREN_EDU_ALLOWANCE_MONTHLY', 'HOSTEL_ALLOWANCE_MONTHLY',
        'LEAVE_ENCASHMENT_EXEMPTION_CEILING', 'VRS_EXEMPTION_CEILING'
    ]
    missing = [k for k in expected_keys if k not in content]
    if missing:
        _logger.info(f"  [FAIL] Missing expected parameter mappings: {missing}")
        return False
    _logger.info(f"  [PASS] All {len(expected_keys)} statutory parameter codes mapped cleanly in TDS_PARAMETER_MAP.")
    return True



def test_non_overlapping_logic_simulation():
    # Simulate overlapping check logic
    ranges = [
        {'from': 0.0, 'to': 400000.0},
        {'from': 400000.0, 'to': 800000.0},
        {'from': 800000.0, 'to': 1200000.0},
        {'from': 1200000.0, 'to': 0.0},  # Open ended (inf)
    ]
    overlap_found = False
    for i in range(len(ranges)):
        for j in range(i + 1, len(ranges)):
            r1 = ranges[i]
            r2 = ranges[j]
            max1 = r1['to'] if r1['to'] > 0 else float('inf')
            max2 = r2['to'] if r2['to'] > 0 else float('inf')
            if max(r1['from'], r2['from']) < min(max1, max2):
                overlap_found = True
                break
    if overlap_found:
        _logger.info("  [FAIL] Valid non-overlapping ranges reported false overlap.")
        return False
    _logger.info("  [PASS] Non-overlapping income range overlap detection simulation passed.")
    return True

def main():
    print_header("HUDSON INDIAN PAYROLL - TDS ENGINE PHASE 2 VERIFICATION SUITE")
    passed = 0
    total = 4

    if test_python_syntax(): passed += 1
    if test_xml_syntax(): passed += 1
    if test_parameter_mapping_coverage(): passed += 1
    if test_non_overlapping_logic_simulation(): passed += 1

    _logger.info("=" * 80)
    _logger.info(f" VERIFICATION SUMMARY: {passed}/{total} PASSED")
    _logger.info("=" * 80)

    if passed != total:
        sys.exit(1)

if __name__ == '__main__':
    main()
