# Hudson Indian Payroll – TDS Engine Phase 3 Technical Documentation
## Enterprise Employee Tax Profile & Declaration Framework

---

## 1. Executive Architecture Summary

Phase 3 of the **Hudson Indian Payroll TDS Engine** establishes a complete, modular, enterprise-grade **Employee Tax Profile**, **Financial Year Tax Regime Selection & Server-Side Locking Framework**, and **Employee Tax Declaration Engine**.

This phase is strictly responsible for capturing and validating employee-specific tax information required for future TDS computation. It does **NOT** perform income projection, taxable income calculation, or payroll deductions.

---

## 2. Decoupled Business Domains Architecture

Phase 3 strictly enforces domain separation:

```
                          ┌───────────────────────────┐
                          │ Module 1: Permanent Tax   │
                          │ Identity Profile (PAN,    │
                          │ Aadhaar, Residential St.) │
                          └─────────────┬─────────────┘
                                        │
             ┌──────────────────────────┼──────────────────────────┐
             ▼                          ▼                          ▼
┌──────────────────────────┐┌──────────────────────────┐┌──────────────────────────┐
│ Financial Year Tax       ││ Module 2: Regime-Neutral ││ Module 3: Regime-Aware   │
│ Selection (FY 26-27 ->   ││ Income Decl. (Other      ││ Deduction Decl. (80C,    │
│ Old, FY 27-28 -> New)    ││ Sources, Let-Out, Prev)  ││ 80D, HRA, Sec 24b)       │
└──────────────────────────┘└────────────┬─────────────┘└────────────┬─────────────┘
                                         │                          │
                                         └────────────┬─────────────┘
                                                      ▼
                                        ┌───────────────────────────┐
                                        │ Module 4: Eligibility     │
                                        │ (tds.employee.home.loan)  │
                                        └─────────────┬─────────────┘
                                                      ▼
                                        ┌───────────────────────────┐
                                        │ Module 5: Validation Svc  │
                                        │ (ParameterService Limits) │
                                        └───────────────────────────┘
```

---

## 3. Module Breakdown

### 3.1 Module 1 – Permanent Employee Tax Profile (`hr.employee`)
- **Location**: **Income Tax (TDS)** notebook page on Employee form.
- **Fields**:
  - `hds_in_pan`: PAN Number (validated via strict regex `^[A-Z]{5}[0-9]{4}[A-Z]{1}$` with duplicate prevention).
  - `hds_in_aadhaar`: Aadhaar Number (12-digit format check).
  - `hds_in_tds_applicable`: Boolean trigger.
  - `hds_in_residential_status`: Selection (`ror`, `rnor`, `nre`).
- **Design Rule**: Lightweight permanent identity master. Contains NO financial year data, NO declarations, and NO previous employer figures.

### 3.2 Financial Year Tax Selection (`tds.employee.tax.regime`)
- **Location**: **Payroll → Tax Declarations → Employee Tax Profiles** (and inline child list on Employee form).
- **Domain**: Maps an employee to their selected income tax regime (`new` Section 115BAC or `old` Regime) per Financial Year.
- **Server-Side Tax Regime Locking**: Once a processed/confirmed payslip (`hr.payslip`) exists for an employee within the target Financial Year, regime selection is locked (`is_locked = True`). Any arbitrary edit raises a `ValidationError` unless executed via an authorized Payroll Manager override (`ignore_regime_lock` context).

### 3.3 Module 2 – Regime-Neutral Income Declaration (`tds.employee.income.declaration`)
- **Location**: **Payroll → Tax Declarations → Income Declarations (Regime Neutral)**.
- **Domain**: Captures non-payroll income sources relevant regardless of selected tax regime:
  1. *Income from Other Sources*: Savings Interest, FD Interest, Dividend Income, Miscellaneous Income.
  2. *Let-Out House Property*: Gross Rent Received, Municipal Taxes Paid, Net Annual Value (NAV), Statutory 30% NAV Deduction (Sec 24a), Mortgage Interest Paid (Sec 24b).
  3. *Previous Employer Salary & Tax*: Previous Taxable Salary, Previous TDS, Previous PT, Previous EPF.

### 3.4 Module 3 – Regime-Aware Deduction Declaration (`tds.employee.declaration` & `tds.employee.declaration.line`)
- **Location**: **Payroll → Tax Declarations → Deduction Declarations**.
- **Supported Statutory Categories**: Section 80C, 80CCD(1B), 80D Self/Parents, 80D Preventive Checkup, 80TTA, 80TTB, 80DD, 24(b) Home Loan Interest, Section 80EEA, HRA, Children Education Allowance, Hostel Allowance, LTA, Leave Encashment, VRS, NPS.
- **Regime Compatibility Engine**:
  - **New Tax Regime (Section 115BAC)**: Automatically rejects unpermitted deduction lines (`80c`, `80d`, `hra`, `24b`, etc.), marking them `is_regime_permitted = False` and `approved_amount = ₹0`.
  - **Old Tax Regime**: Validates declaration limits dynamically via `TdsParameterService` (e.g. cumulative 80C capped at ₹1,50,000, 80CCD(1B) at ₹50,000, Section 24(b) at ₹2,00,000).

### 3.5 Module 4 – Eligibility-Based Declarations (`tds.employee.home.loan`)
- **Location**: **Payroll → Configuration → India Tax Configuration → Housing Loan & 80EEA**.
- Decouples statutory facts (Loan Sanction Date, Loan Amount, Property Stamp Duty Value, First-Time Home Buyer status) from parameter monetary ceilings via `Section80EEAEligibilityService`.

### 3.6 Module 5 – Supporting Proof Documents & Approval Workflow
- Upload attachments (`ir.attachment`) on declaration headers and line items.
- Workflow: **Draft → Submitted → Under Review → Approved / Rejected**.
- Audit logging via `hds.in.payroll.audit`.

---

## 4. Centralized Validation Service (`EmployeeTaxDeclarationValidationService`)

Located in `services/tds/employee_tax_declaration_validation_service.py`:
- `validate_declaration(declaration_record, eval_date=None)`
- Resolves active tax regime for the employee and financial year.
- Validates regime compatibility (rejecting unpermitted lines under New Regime).
- Resolves statutory ceilings exclusively through `TdsParameterService`.
- Invokes `Section80EEAEligibilityService` for home loan declarations.
- Updates line-item `approved_amount`, `validation_status`, and `validation_remarks`.
