# Developed Module Documentation (Template: article-1.1)

| Metadata Attribute | Specification Value |
| :--- | :--- |
| **Document ID** | `DOC-HDS-PAY-1.1` |
| **Document Standard** | `Developed Module Documentation (Template: article-1.1)` |
| **Module Technical Name** | `hudson_in_payroll` |
| **Module Display Name** | Hudson Indian Statutory Payroll Localization |
| **Target Odoo Version** | 19.0 Community & Enterprise |
| **Module Version** | 19.0.1.0.0 |
| **Author / Vendor** | Hudson Software Solutions |
| **License** | LGPL-3 |
| **Category** | Human Resources / Payroll / Statutory Localization |
| **Review Status** | Remediated & Compliant |

---

## 1. Executive Summary & Functional Scope

The **Hudson Indian Statutory Payroll Localization (`hudson_in_payroll`)** module delivers an enterprise-grade statutory compliance engine tailored for Indian labor and tax legislations. Built upon a Domain-Driven Service-Oriented Architecture (SOA), the module seamlessly integrates with Odoo 19 core HR and Payroll models (`hr.employee`, `hr.contract`, `hr.payslip`, `hr.payslip.run`).

### Core Statutory Engines Covered:
1. **Income Tax TDS Calculation Engine**: Comprehensive computation under both **Old Tax Regime** and **New Tax Regime** (Finance Act provisions), including automatic 87A rebate, standard deduction, statutory surcharges, and 4% Health & Education Cess.
2. **Exemptions & Chapter VI-A Deductions**: Section 10(5) LTA, Section 10(13A) HRA, Section 24(b) Home Loan Interest, Section 80C, Section 80CCD(1B), Section 80D (Self & Senior Citizen Parents), Section 80DD (Dependent Disability), Section 80E (Higher Education Loan), Section 80EEA (Affordable Housing Interest), Section 80G (Donations), Section 80GG (Rent Paid Without HRA), and Section 80U (Person with Disability).
3. **Professional Tax (PT) Configurable Engine**: Comprehensive state-wise slabs for all Indian states and Union Territories, supporting Monthly, Quarterly, Half-Yearly, and Annual periodicities, gender-based rules (Maharashtra, Gujarat, etc.), and February statutory deduction overrides.
4. **Employee Provident Fund (EPF) & Statutory Ceiling Engine**: Statutory PF wages, employer pension (EPS), EPF administration charges, and EDLI calculations with statutory wage ceiling ceilings (₹15,000).
5. **Employees' State Insurance (ESIC) Engine**: Gross wage calculation, wage ceiling thresholds (₹21,000 standard / ₹25,000 disability), and multi-state compliance.
6. **Labour Welfare Fund (LWF)**: State-specific periodicity and employee/employer statutory contribution rates.
7. **Payment of Gratuity Act, 1972**: Statutory 15/26 formula, 5-year tenure validation, continuous service rules, and ₹20,00,000 statutory tax exemption ceiling.
8. **Leave Encashment**: Real-time virtual leave balance extraction from Odoo 19 allocation framework, 26-day divisor, and 300-day statutory cap.
9. **Statutory Bonus (Payment of Bonus Act, 1965)**: Multiple calculation methods (Basic %, Gross %, Fixed, Years of Service, and Python Formula).
10. **Full & Final Settlement (F&F)**: Automated generation, notice pay recovery/payment, leave encashment, gratuity, and reconciliation.
11. **Biometric Device Integration**: Webhook, REST API polling, and direct ZKTeco sync supporting automated punch deduplication, employee code mapping, and attendance line processing.

---

## 2. Architecture & Design Principles

```
+-------------------------------------------------------------------------------+
|                             PRESENTATION LAYER                                |
|  - ESS Tax Declaration Views        - Payslip Batch (Pay Run) Views           |
|  - Professional Tax Master Views    - Statutory Reports & PDF/XLSX Export     |
+---------------------------------------+---------------------------------------+
                                        |
+---------------------------------------v---------------------------------------+
|                               ORM MODEL LAYER                                 |
|  - res.company (TDS / PT fields)    - hr.employee / hr.contract               |
|  - tds.financial.year               - tds.employee.declaration                |
|  - tds.tax.regime / tds.tax.slab    - pt.state.slab / pt.period.schedule      |
|  - hds.in.bonus                     - final.settlement                        |
+---------------------------------------+---------------------------------------+
                                        |
+---------------------------------------v---------------------------------------+
|                         SERVICE / ENGINE LAYER (SOA)                          |
|  - TdsOrchestrationEngine           - ProfessionalTaxService                  |
|  - AnnualIncomeProjectionService    - GratuityService                         |
|  - DeductionCalculationService      - LeaveEncashmentDataService              |
|  - MonthlyTDSDistributionService    - FinalSettlementCalculationService       |
+---------------------------------------+---------------------------------------+
                                        |
+---------------------------------------v---------------------------------------+
|                         STATUTORY PARAMETER ENGINE                            |
|  - hr.rule.parameter lookup (Statutory Surcharges, Thresholds, Rebates, Cess) |
+-------------------------------------------------------------------------------+
```

### Key Design Standards:
- **Separation of Concerns**: Business logic and statutory computations reside strictly within dedicated Service classes under `services/`, keeping ORM model files lightweight and maintainable.
- **Defensive & Resilient Exception Handling**: Specific exception hierarchies (`(UserError, ValidationError, ValueError, TypeError, AttributeError)`) are caught, logged via `_logger.exception()` / `_logger.warning()`, and never swallowed silently.
- **Enterprise Audit Logging**: Complete trace history and intermediate breakdown records are maintained for statutory audits.
- **Clean Production Packaging**: Verification scripts are strictly isolated inside `tests/manual_verification/`, and standard unit tests reside in `tests/`.

---

## 3. Data Model Hierarchy & Relationships

### 3.1 TDS & Income Tax Models
| Model Name | Table | Description |
| :--- | :--- | :--- |
| `tds.financial.year` | `tds_financial_year` | Indian Financial Year (e.g. FY 2026-27 / AY 2027-28) with statutory date windows. |
| `tds.tax.regime` | `tds_tax_regime` | Old vs New Tax Regime configurations. |
| `tds.tax.slab` | `tds_tax_slab` | Progressive tax rates per taxable income slab for active regimes. |
| `tds.surcharge` | `tds_surcharge` | Statutory surcharge tiers (10%, 15%, 25%, 37%) based on taxable income. |
| `tds.employee.declaration` | `tds_employee_declaration` | Employee yearly tax declaration master with approval lifecycle. |
| `tds.employee.declaration.line` | `tds_employee_declaration_line` | Chapter VI-A investment declaration line items with proof attachments. |
| `tds.employee.home.loan` | `tds_employee_home_loan` | Home loan records for Section 24(b) and Section 80EEA verification. |

### 3.2 Professional Tax & Statutory Models
| Model Name | Table | Description |
| :--- | :--- | :--- |
| `pt.state.slab` | `pt_state_slab` | State-wise salary brackets, fixed PT amounts, and February overrides. |
| `pt.period.schedule` | `pt_period_schedule` | Periodicity schedules (Monthly, Quarterly, Half-Yearly, Annual). |
| `lwf.state.rate` | `lwf_state_rate` | State-wise LWF contribution amounts for employee and employer. |
| `hds.in.bonus` | `hds_in_bonus` | Annual/Performance bonus distribution master and employee line allocation. |
| `final.settlement` | `final_settlement` | Full and Final exit settlement master record. |

---

## 4. Statutory Calculation Rules & Formulas

### 4.1 TDS Tax Computation Workflow
1. **Gross Salary Projection**:
   $$\text{Gross Annual Income} = \text{YTD Earned Gross} + (\text{Monthly Projected Wage} \times \text{Remaining Months}) + \text{Previous Employer Gross}$$
2. **Standard Deduction**:
   - New Regime: Statutory ₹75,000 (Finance Act 2024 onwards) or ₹50,000.
   - Old Regime: Statutory ₹50,000.
3. **Chapter VI-A & Other Deductions (Old Regime Only)**:
   - Section 80C + 80CCC + 80CCD(1): Capped at statutory ₹1,50,000.
   - Section 80CCD(1B) NPS: Additional deduction up to ₹50,000.
   - Section 80D: Self & Family (₹25,000 / Senior Citizen ₹50,000) + Parents (₹25,000 / Senior Citizen ₹50,000).
   - Section 24(b): Self-occupied home loan interest capped at ₹2,00,000.
4. **Tax Calculation on Slabs**:
   $$\text{Base Tax} = \sum_{\text{slabs}} (\text{Taxable Slab Amount} \times \text{Slab Rate})$$
5. **Section 87A Rebate**:
   - New Regime: 100% rebate if Taxable Income $\le$ ₹7,00,000 (Finance Act 2023) or ₹12,00,000 (amendments).
   - Old Regime: Rebate up to ₹12,500 if Taxable Income $\le$ ₹5,00,000.
6. **Surcharge & Health/Education Cess**:
   $$\text{Total Annual Tax} = (\text{Net Tax} + \text{Surcharge}) \times 1.04$$
7. **Monthly TDS Deduction Distribution**:
   $$\text{Current Month TDS} = \frac{\text{Total Annual Tax} - \text{YTD TDS Paid} - \text{Prev Employer TDS}}{\text{Remaining Payroll Months}}$$

### 4.2 Professional Tax (PT) Formula
$$\text{PT Deducted} = \begin{cases} 
\text{February Override Amount} & \text{if Month is February and State has override} \\
\text{Standard Slab Amount} & \text{otherwise}
\end{cases}$$

### 4.3 Gratuity Formula
$$\text{Gratuity} = \frac{15 \times \text{Last Drawn (Basic + DA)} \times \text{Completed Years of Service}}{26}$$
*(Capped at statutory ceiling of ₹20,00,000)*

### 4.4 Leave Encashment Formula
$$\text{Leave Encashment} = \frac{\text{Last Drawn (Basic + DA)}}{26} \times \min(\text{Eligible Leave Days}, 300)$$

---

## 5. Service Layer Catalog

| Service Class | File Path | Primary Function |
| :--- | :--- | :--- |
| `TdsOrchestrationEngine` | `services/tds/tds_orchestration_engine.py` | Top-level orchestrator executing the 11-step TDS calculation pipeline. |
| `AnnualIncomeProjectionService` | `services/tds/annual_income_projection_service.py` | Computes YTD + future projected salary earnings. |
| `DeductionCalculationService` | `services/tds/deduction_calculation_service.py` | Resolves all Chapter VI-A statutory caps. |
| `MonthlyTDSDistributionService` | `services/tds/monthly_tds_distribution_service.py` | Calculates exact monthly TDS deduction from annual liability. |
| `ProfessionalTaxService` | `services/professional_tax/professional_tax_service.py` | Evaluates applicable PT state slabs and periodicities. |
| `GratuityService` | `services/gratuity/gratuity_service.py` | Computes statutory gratuity with eligibility checks. |
| `LeaveEncashmentDataService` | `services/leave_encashment/leave_encashment_data_service.py` | Extracts live leave allocations and prepares encashment data. |
| `FinalSettlementCalculationService` | `services/final_settlement_calculation_service.py` | Full & Final exit settlement line coordinator. |

---

## 6. Testing & Quality Assurance

The module features a dual-tier testing infrastructure:

1. **Automated Unit & Integration Test Suite (`tests/`)**:
   - 40+ unit test modules covering salary revision engine, statutory reporting, TDS phases 1 through 11, PT schedules, and gratuity calculators.
   - Automatically executed with Odoo test runner:
     ```bash
     python odoo-bin -c odoo.conf -d <db_name> -i hudson_in_payroll --test-enable --stop-after-init
     ```
2. **Manual & Shell Verification Suite (`tests/manual_verification/`)**:
   - Isolated verification scripts using Python `logging` for interactive shell verification:
     - `verify_pt_shell.py`
     - `verify_tds_phase1.py`
     - `verify_tds_phase2.py`
     - `verify_tds_phase3.py`
     - `verify_80u_fixes.py`

---

## 7. Security & Access Control

| Group Name | Access Level | Description |
| :--- | :--- | :--- |
| `base.group_user` (Employee) | Read, Create, Write (Draft Declarations) | Access to personal ESS Tax Declarations and Proof Uploads. |
| `hr_payroll_community.group_hr_payroll_user` (Payroll Officer) | Read, Write, Compute | Full access to Tax Declarations, Pay Runs, PT Slabs, and Settlements. |
| `hr_payroll_community.group_hr_payroll_manager` (Payroll Manager) | Full (CRUD + State Transition) | Master configuration rights, Statutory Rule Parameter overrides, and batch approval. |

---

## 8. Version History & Changelog

| Version | Release Date | Highlights |
| :--- | :--- | :--- |
| **19.0.1.0.0** | 2026-08-29 | - Initial production release for Odoo 19.<br>- Remediated code review observations: isolated verification scripts to `tests/manual_verification/`, eliminated bare and broad exception handling, added structured logging, and created full article-1.1 documentation. |
