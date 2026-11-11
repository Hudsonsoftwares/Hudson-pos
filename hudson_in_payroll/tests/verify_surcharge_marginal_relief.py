# -*- coding: utf-8 -*-
"""
Standalone Verification Script for TDS Surcharge and Marginal Relief Engine.
Tests all statutory scenarios (Cases 1 - 6), syntax compilation, and XML validity.
"""
import py_compile
import sys
import os
import xml.etree.ElementTree as ET

# Add Odoo server to path
sys.path.insert(0, r"C:\Program Files\Odoo 19.0.20260717\server")
sys.path.insert(0, r"e:\New Payroll")

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def print_header(title):
    print("=" * 80)
    print(f" {title}")
    print("=" * 80)

def test_syntax():
    print_header("1. PYTHON SYNTAX & BYTECODE COMPILATION")
    files = [
        "services/tds/surcharge_engine_service.py",
        "services/tds/tds_orchestration_engine.py",
        "models/hr_payslip.py",
        "reports/report_statutory_tax_calculation.py",
        "tests/test_tds_surcharge_marginal_relief.py",
    ]
    for f in files:
        full_path = os.path.join(r"e:\New Payroll\hudson_in_payroll", f)
        try:
            py_compile.compile(full_path, doraise=True)
            print(f"  [PASS] Python Syntax OK: {f}")
        except Exception as e:
            print(f"  [FAIL] Python Syntax Error in {f}: {e}")
            return False
    return True

def test_xml():
    print_header("2. QWEB XML SYNTAX VALIDATION")
    xml_files = [
        "reports/report_payslip_custom_template.xml",
        "reports/report_statutory_tax_calculation_templates.xml",
    ]
    for f in xml_files:
        full_path = os.path.join(r"e:\New Payroll\hudson_in_payroll", f)
        try:
            tree = ET.parse(full_path)
            root = tree.getroot()
            print(f"  [PASS] XML Valid: {f} (Root tag: {root.tag})")
        except Exception as e:
            print(f"  [FAIL] XML Parse Error in {f}: {e}")
            return False
    return True

def test_statutory_engine():
    print_header("3. STATUTORY SURCHARGE & MARGINAL RELIEF ENGINE AUDIT")

    # Setup mock env
    class MockRecord:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def __bool__(self):
            return True

    class MockEnv:
        def __init__(self):
            self.context = {}
        def __getitem__(self, item):
            class MockModel:
                def search(self, domain, order=None, limit=None):
                    return []
                def get_parameter(self, code, date=None, as_decimal=False):
                    return 4.0
            return MockModel()

    import odoo.addons
    if r"e:\New Payroll" not in odoo.addons.__path__:
        odoo.addons.__path__.append(r"e:\New Payroll")

    from odoo.addons.hudson_in_payroll.services.tds.surcharge_engine_service import SurchargeEngineService
    from odoo.addons.hudson_in_payroll.services.tds.income_tax_slab_service import IncomeTaxSlabService
    from odoo.addons.hudson_in_payroll.services.tds.health_education_cess_service import HealthEducationCessService

    env = MockEnv()
    surcharge_svc = SurchargeEngineService(env)
    slab_svc = IncomeTaxSlabService(env)
    cess_svc = HealthEducationCessService(env)
    fy = MockRecord(id=1, code='2025-2026')

    all_passed = True

    # ── CASE 1: Below threshold (< 50L) ──────────────────────────────────────
    print("\n--- CASE 1: Below ₹50 Lakh (Income = ₹45,00,000) ---")
    tax_45l = slab_svc.calculate_base_tax(4500000.0, fy, 'old').base_tax_liability
    res_1 = surcharge_svc.calculate_surcharge(4500000.0, tax_45l, fy, 'old')
    c1_ok = (not res_1.is_applicable and res_1.surcharge_amount == 0.0 and res_1.marginal_relief == 0.0)
    print(f"  Base Tax: ₹{tax_45l:,.2f} | Surcharge: ₹{res_1.surcharge_amount:,.2f} | Marginal Relief: ₹{res_1.marginal_relief:,.2f}")
    print(f"  [STATUS]: {'PASS' if c1_ok else 'FAIL'}")
    all_passed = all_passed and c1_ok

    # ── CASE 2: Just above 50L (50,10,000) ───────────────────────────────────
    print("\n--- CASE 2: Just above ₹50 Lakh (Income = ₹50,10,000) ---")
    tax_501 = slab_svc.calculate_base_tax(5010000.0, fy, 'old').base_tax_liability
    tax_500 = slab_svc.calculate_base_tax(5000000.0, fy, 'old').base_tax_liability
    res_2 = surcharge_svc.calculate_surcharge(5010000.0, tax_501, fy, 'old')
    excess_inc = 10000.0
    max_tax_sur = tax_500 + excess_inc
    c2_rate_ok = (res_2.surcharge_rate_pct == 10.0 and res_2.is_applicable)
    c2_relief_ok = (res_2.marginal_relief > 0.0)
    c2_invariant_ok = abs(res_2.tax_plus_surcharge - max_tax_sur) < 0.01
    cess_2 = cess_svc.calculate_cess(res_2.tax_plus_surcharge)
    c2_cess_ok = (cess_2.cess_amount == round(res_2.tax_plus_surcharge * 0.04, 2))
    print(f"  Base Tax: ₹{tax_501:,.2f} | Pre-Relief Surcharge: ₹{res_2.surcharge_before_relief:,.2f}")
    print(f"  Marginal Relief: ₹{res_2.marginal_relief:,.2f} | Final Surcharge: ₹{res_2.surcharge_amount:,.2f}")
    print(f"  Tax + Final Surcharge: ₹{res_2.tax_plus_surcharge:,.2f} (Max Limit: ₹{max_tax_sur:,.2f})")
    print(f"  4% Cess: ₹{cess_2.cess_amount:,.2f} | Total Liability: ₹{cess_2.total_annual_tax_liability:,.2f}")
    c2_ok = c2_rate_ok and c2_relief_ok and c2_invariant_ok and c2_cess_ok
    print(f"  [STATUS]: {'PASS' if c2_ok else 'FAIL'}")
    all_passed = all_passed and c2_ok

    # ── CASE 3: ₹50 Lakh Boundary Testing ────────────────────────────────────
    print("\n--- CASE 3: ₹50 Lakh Boundary (₹49,99,999 / ₹50,00,000 / ₹50,00,001) ---")
    t_4999 = slab_svc.calculate_base_tax(4999999.0, fy, 'old').base_tax_liability
    r_4999 = surcharge_svc.calculate_surcharge(4999999.0, t_4999, fy, 'old')
    t_5000 = slab_svc.calculate_base_tax(5000000.0, fy, 'old').base_tax_liability
    r_5000 = surcharge_svc.calculate_surcharge(5000000.0, t_5000, fy, 'old')
    t_5001 = slab_svc.calculate_base_tax(5000001.0, fy, 'old').base_tax_liability
    r_5001 = surcharge_svc.calculate_surcharge(5000001.0, t_5001, fy, 'old')

    c3_1 = (not r_4999.is_applicable and r_4999.surcharge_amount == 0.0)
    c3_2 = (not r_5000.is_applicable and r_5000.surcharge_amount == 0.0)
    c3_3 = (r_5001.is_applicable and r_5001.surcharge_rate_pct == 10.0 and r_5001.marginal_relief > 0.0)
    c3_inv = abs(r_5001.tax_plus_surcharge - (t_5000 + 1.0)) < 0.01

    print(f"  ₹49,99,999 -> Surcharge: ₹{r_4999.surcharge_amount:,.2f}, Applicable: {r_4999.is_applicable}")
    print(f"  ₹50,00,000 -> Surcharge: ₹{r_5000.surcharge_amount:,.2f}, Applicable: {r_5000.is_applicable}")
    print(f"  ₹50,00,001 -> Surcharge: ₹{r_5001.surcharge_amount:,.2f}, Relief: ₹{r_5001.marginal_relief:,.2f}, Applicable: {r_5001.is_applicable}")
    c3_ok = c3_1 and c3_2 and c3_3 and c3_inv
    print(f"  [STATUS]: {'PASS' if c3_ok else 'FAIL'}")
    all_passed = all_passed and c3_ok

    # ── CASE 4: ₹1 Crore Threshold ───────────────────────────────────────────
    print("\n--- CASE 4: ₹1 Crore Threshold (₹1,00,00,000 vs ₹1,01,00,000) ---")
    t_1cr = slab_svc.calculate_base_tax(10000000.0, fy, 'old').base_tax_liability
    r_1cr = surcharge_svc.calculate_surcharge(10000000.0, t_1cr, fy, 'old')
    t_101 = slab_svc.calculate_base_tax(10100000.0, fy, 'old').base_tax_liability
    r_101 = surcharge_svc.calculate_surcharge(10100000.0, t_101, fy, 'old')

    max_101 = t_1cr + round(t_1cr * 0.10, 2) + 100000.0
    c4_1 = (r_1cr.surcharge_rate_pct == 10.0)
    c4_2 = (r_101.surcharge_rate_pct == 15.0 and r_101.marginal_relief > 0.0)
    c4_inv = abs(r_101.tax_plus_surcharge - max_101) < 0.01

    print(f"  ₹1,00,00,000 -> Surcharge Rate: {r_1cr.surcharge_rate_pct}%, Amount: ₹{r_1cr.surcharge_amount:,.2f}")
    print(f"  ₹1,01,00,000 -> Surcharge Rate: {r_101.surcharge_rate_pct}%, Pre-Relief: ₹{r_101.surcharge_before_relief:,.2f}")
    print(f"                 Marginal Relief: ₹{r_101.marginal_relief:,.2f}, Final Surcharge: ₹{r_101.surcharge_amount:,.2f}")
    print(f"                 Tax + Final Sur: ₹{r_101.tax_plus_surcharge:,.2f} (Limit: ₹{max_101:,.2f})")
    c4_ok = c4_1 and c4_2 and c4_inv
    print(f"  [STATUS]: {'PASS' if c4_ok else 'FAIL'}")
    all_passed = all_passed and c4_ok

    # ── CASE 5: ₹2 Crore & ₹5 Crore Regimes ──────────────────────────────────
    print("\n--- CASE 5: ₹2 Crore & ₹5 Crore Boundaries (Old vs New Regimes) ---")
    t_2cr = slab_svc.calculate_base_tax(20000000.0, fy, 'old').base_tax_liability
    t_201 = slab_svc.calculate_base_tax(20100000.0, fy, 'old').base_tax_liability
    r_201 = surcharge_svc.calculate_surcharge(20100000.0, t_201, fy, 'old')
    max_201 = t_2cr + round(t_2cr * 0.15, 2) + 100000.0
    c5_2cr = (r_201.surcharge_rate_pct == 25.0 and abs(r_201.tax_plus_surcharge - max_201) < 0.01)
    print(f"  ₹2,01,00,000 (Old) -> Rate: {r_201.surcharge_rate_pct}%, Relief: ₹{r_201.marginal_relief:,.2f}, Tax+Sur: ₹{r_201.tax_plus_surcharge:,.2f}")

    # 5 Crore Old Regime (37%)
    t_5cr_old = slab_svc.calculate_base_tax(50000000.0, fy, 'old').base_tax_liability
    t_501_old = slab_svc.calculate_base_tax(50100000.0, fy, 'old').base_tax_liability
    r_501_old = surcharge_svc.calculate_surcharge(50100000.0, t_501_old, fy, 'old')
    max_501_old = t_5cr_old + round(t_5cr_old * 0.25, 2) + 100000.0
    c5_5cr_old = (r_501_old.surcharge_rate_pct == 37.0 and abs(r_501_old.tax_plus_surcharge - max_501_old) < 0.01)
    print(f"  ₹5,01,00,000 (Old) -> Rate: {r_501_old.surcharge_rate_pct}%, Relief: ₹{r_501_old.marginal_relief:,.2f}, Tax+Sur: ₹{r_501_old.tax_plus_surcharge:,.2f}")

    # 5 Crore New Regime (25% capped)
    t_501_new = slab_svc.calculate_base_tax(50100000.0, fy, 'new').base_tax_liability
    r_501_new = surcharge_svc.calculate_surcharge(50100000.0, t_501_new, fy, 'new')
    c5_5cr_new = (r_501_new.surcharge_rate_pct == 25.0)
    print(f"  ₹5,01,00,000 (New) -> Rate: {r_501_new.surcharge_rate_pct}% (Capped at 25%)")
    c5_ok = c5_2cr and c5_5cr_old and c5_5cr_new
    print(f"  [STATUS]: {'PASS' if c5_ok else 'FAIL'}")
    all_passed = all_passed and c5_ok

    # ── CASE 6: DTO and Payslip Summary Structure ───────────────────────────
    print("\n--- CASE 6: DTO & Payslip Summary Dictionary Alignment ---")
    d = res_2.to_dict()
    keys_required = ['net_taxable_income', 'tax_after_rebate', 'surcharge_rate_pct',
                     'surcharge_before_relief', 'marginal_relief', 'surcharge',
                     'surcharge_amount', 'tax_plus_surcharge']
    c6_keys_ok = all(k in d for k in keys_required)
    c6_math_ok = (d['surcharge_amount'] == round(d['surcharge_before_relief'] - d['marginal_relief'], 2) and
                  d['tax_plus_surcharge'] == round(d['tax_after_rebate'] + d['surcharge_amount'], 2))
    print(f"  DTO Keys present: {c6_keys_ok}")
    print(f"  Surcharge Before Relief - Marginal Relief == Final Surcharge: {c6_math_ok}")
    c6_ok = c6_keys_ok and c6_math_ok
    print(f"  [STATUS]: {'PASS' if c6_ok else 'FAIL'}")
    all_passed = all_passed and c6_ok

    print_header("FINAL VERIFICATION SUMMARY")
    if all_passed:
        print("  >>> ALL STATUTORY SURCHARGE & MARGINAL RELIEF TESTS PASSED! <<<")
    else:
        print("  >>> SOME TESTS FAILED! CHECK OUTPUT ABOVE. <<<")
    return all_passed

if __name__ == "__main__":
    ok_syntax = test_syntax()
    ok_xml = test_xml()
    ok_statutory = test_statutory_engine()
    sys.exit(0 if (ok_syntax and ok_xml and ok_statutory) else 1)
