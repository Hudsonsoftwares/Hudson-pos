====================================
Hudson Indian Payroll Compliance & TDS Engine
====================================

Overview
--------
`hudson_in_payroll` is a comprehensive Indian statutory payroll and Tax Deducted at Source (TDS) calculation engine for Odoo 19.0.
It provides complete automation for Chapter VI-A deductions, Section 24(b) Let-Out and Self-Occupied House Property loss carry-forwards, Section 10 exemptions (HRA, LTA, Gratuity), Professional Tax (PT), Employee Provident Fund (EPF), Labor Welfare Fund (LWF), and Employee State Insurance (ESI).

Key Functional Modules & Architecture
--------------------------------------

1. **Tax Deducted at Source (TDS) Computation Architecture**
   - **Orchestration Engine**: `services/tds/tds_orchestration_engine.py` runs statutory calculations sequentially across 8 evaluation phases.
   - **Regime Evaluation**: Evaluates Old Tax Regime vs New Tax Regime (Section 115BAC) and selects the optimal statutory regime for the employee.
   - **Rule Parameter Engine**: Statutory caps (e.g. Section 80C ₹1.5L cap, Section 80CCD(1B) ₹50k cap, Section 80D limits) are dynamically loaded from `hr.rule.parameter` records.

2. **Deductions & Exemptions (Chapter VI-A & Section 10)**
   - **Section 80C & 80CCD(1B)**: Deductions for EPF, PPF, ELSS, Life Insurance, Tuition Fees, and NPS.
   - **Section 80D**: Health Insurance and Preventive Health Checkup deductions with Senior Citizen bucket calculations.
   - **Section 80G**: Charitable Donations with 100% / 50% limit and ATI-capped categories.
   - **Section 80GG**: Rent paid deduction without HRA allowance.
   - **Section 80U & 80DD**: Disability deductions with severe disability thresholds.
   - **Section 71B**: House Property Loss Carry-Forward ledger embedded in the Employee Form view (`hr.employee`).

3. **Statutory Audit & Traceability**
   - **`hds.in.payroll.audit`**: Captures step-by-step statutory evaluation traces and formula inputs for statutory audit compliance.
   - **`hds.in.statutory.report`**: Provides SQL view reporting for company-wide tax compliance analysis.

Configuration & Setup
---------------------
1. Go to **Payroll ➔ Configuration ➔ TDS Configuration** to set active Financial Years, Assessment Years, and Section Configurations.
2. Update statutory limits via **Payroll ➔ Configuration ➔ Statutory Rules / Rule Parameters** (`hr.rule.parameter`).
3. Maintain Employee Carry-Forward history under **Employees ➔ Employee Form ➔ Income Tax / Tax Declarations** section.

License & Support
-----------------
Developed for Hudson Softwares Indian Payroll Suite. License: LGPL-3.
