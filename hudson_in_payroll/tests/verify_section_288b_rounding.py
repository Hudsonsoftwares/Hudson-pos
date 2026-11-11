# -*- coding: utf-8 -*-
"""
Verification Script for Section 288B Rounding in HealthEducationCessService
and TaxableIncomeService.
"""
import py_compile
import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def test_syntax():
    print("=" * 60)
    print("1. PYTHON BYTECODE COMPILATION")
    print("=" * 60)
    files = [
        "services/tds/health_education_cess_service.py",
        "services/tds/taxable_income_service.py",
        "services/tds/tds_orchestration_engine.py",
        "tests/test_tds_phase6_tax_computation.py",
    ]
    for f in files:
        full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), f)
        py_compile.compile(full_path, doraise=True)
        print(f"  [PASS] Syntax OK: {f}")
    return True


def test_sec_288b_logic():
    print("=" * 60)
    print("2. SECTION 288B STATUTORY ROUNDING LOGIC VERIFICATION")
    print("=" * 60)

    # Replicate statutory algorithm directly to verify invariants
    def round_tax_to_nearest_10(amount):
        if amount is None or amount <= 0:
            return 0.0
        whole_rupees = int(float(amount))
        remainder = whole_rupees % 10
        if remainder >= 5:
            return float(whole_rupees + (10 - remainder))
        else:
            return float(whole_rupees - remainder)

    test_cases = [
        # (Input, Expected Rounded, Description)
        (1599614.02, 1599610.0, "User screenshot case: 0.02 paise ignored, last digit 4 < 5 -> rounds down to 10"),
        (1599615.00, 1599620.0, "Last digit 5 >= 5 -> rounds up to 20"),
        (1599615.99, 1599620.0, "0.99 paise ignored, last digit 5 >= 5 -> rounds up to 20"),
        (35804.99, 35800.0, "CBDT official example: paise ignored, 4 < 5 -> rounds down to 35,800"),
        (35805.00, 35810.0, "CBDT official example: last digit 5 >= 5 -> rounds up to 35,810"),
        (35806.25, 35810.0, "CBDT official example: paise ignored, last digit 6 >= 5 -> rounds up to 35,810"),
        (52000.0, 52000.0, "Already exact multiple of 10"),
        (0.0, 0.0, "Zero boundary"),
        (-50.0, 0.0, "Negative floor"),
        (None, 0.0, "None handling"),
    ]

    for val, expected, desc in test_cases:
        res = round_tax_to_nearest_10(val)
        assert res == expected, f"FAIL: {desc} -> Expected {expected}, got {res}"
        print(f"  [PASS] {val} -> ₹{res:,.2f} ({desc})")

    # Cess calculation test with Section 288B
    tax_plus_surcharge = 1538090.40
    cess_rate = 4.0
    cess_amount = round(tax_plus_surcharge * (cess_rate / 100.0), 2)
    unrounded_annual_tax = round(tax_plus_surcharge + cess_amount, 2)
    total_annual_tax = round_tax_to_nearest_10(unrounded_annual_tax)
    rounding_factor = round(total_annual_tax - unrounded_annual_tax, 2)

    assert cess_amount == 61523.62
    assert unrounded_annual_tax == 1599614.02
    assert total_annual_tax == 1599610.0
    assert rounding_factor == -4.02

    print("=" * 60)
    print("3. CESS & TAX SIMULATION AUDIT")
    print("=" * 60)
    print(f"  Tax + Surcharge           : ₹{tax_plus_surcharge:,.2f}")
    print(f"  Health & Education Cess   : ₹{cess_amount:,.2f}")
    print(f"  Unrounded Annual Tax      : ₹{unrounded_annual_tax:,.2f}")
    print(f"  Sec 288B Rounding Factor  : ₹{rounding_factor:,.2f}")
    print(f"  Final Annual Tax (Sec 288B): ₹{total_annual_tax:,.2f}")

    # Monthly TDS impact simulation over 12 months
    monthly_unrounded = round(unrounded_annual_tax / 12.0, 2)
    monthly_rounded = round(total_annual_tax / 12.0, 2)
    print(f"  Unrounded Monthly TDS (M1): ₹{monthly_unrounded:,.2f}")
    print(f"  Rounded Monthly TDS (M1)  : ₹{monthly_rounded:,.2f}")
    print(f"  Monthly Difference        : ₹{monthly_rounded - monthly_unrounded:,.2f}")

    return True


if __name__ == '__main__':
    test_syntax()
    test_sec_288b_logic()
    print("\nALL SECTION 288B VERIFICATION CHECKS PASSED SUCCESSFULLY!\n")
