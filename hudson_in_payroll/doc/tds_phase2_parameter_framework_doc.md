# Hudson Indian Payroll – TDS Engine Phase 2 Technical Documentation
## Enterprise Tax Master & Rule Parameter Framework

---

## 1. Executive Architecture Summary

Phase 2 of the **Hudson Indian Payroll TDS Engine** establishes a complete, configuration-driven, effective-dated statutory parameter and tax master framework supporting both the **Old Tax Regime** and **New Tax Regime** (Section 115BAC / Finance Act 2025 / AY 2026-27).

All 31 scalar statutory parameters, income tax slabs, and surcharge rates are seeded via XML and resolved dynamically through a single service point (`TdsParameterService`). Future Finance Act amendments require only XML seed updates without changing Python source code.

---

## 2. Architectural Classification Framework

Before modeling any statutory deduction or exemption, every benefit is evaluated against the **Four Statutory Design Questions**:

1. Is this value a simple statutory constant?
2. Can it be represented by a single effective-dated scalar value?
3. Does eligibility depend only on the statutory amount?
4. Does it require employee-specific dates, documents, declarations, or historical records?

### Category A – Scalar Statutory Parameters
- **Criteria**: Answer to Q1-Q3 is *Yes*, Q4 is *No*.
- **Implementation**: Stored as effective-dated records in `hr.rule.parameter`.
- **Examples**: Standard Deduction, Cess, Sec 87A Limits/Rebates, Sec 80C Limit, Sec 80CCD(1B) Limit, Sec 80D Limits, Sec 24(b) Limit, Sec 80TTA/TTB Limits, HRA %s, Leave Encashment Ceiling, VRS Ceiling.

### Category B – Eligibility-Based Statutory Features
- **Criteria**: Answer to Q4 is *Yes* (eligibility depends on employee-specific facts like loan sanction date, stamp duty value, property type, or declaration proof).
- **Implementation**:
  - The monetary ceiling is stored in `hr.rule.parameter` (e.g. `HDS_IN_TDS_80EEA_MAX_LIMIT`).
  - **CRITICAL DESIGN RULE**: Downstream calculation engines MUST NOT apply the ceiling blindly. Calculation engines MUST invoke a dedicated Employee Eligibility Validation Service (Phase 3) that verifies employee-specific facts (e.g. Loan Sanction Date between 01-Apr-2019 and 31-Mar-2022, Stamp Value ≤ ₹45L, First-time Home Buyer) BEFORE applying the monetary limit.

---

## 3. Complete Parameter Classification Matrix (31 Parameters)

| Parameter Code | Description | Model Framework | Category | Default Value | Tax Regime |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `HDS_IN_TDS_STD_DEDUCTION_NEW` | Standard Deduction | `hr.rule.parameter` | `ceiling` (Cat A) | ₹75,000 | New Regime |
| `HDS_IN_TDS_STD_DEDUCTION_OLD` | Standard Deduction | `hr.rule.parameter` | `ceiling` (Cat A) | ₹50,000 | Old Regime |
| `HDS_IN_TDS_87A_LIMIT_NEW` | Sec 87A Taxable Income Limit | `hr.rule.parameter` | `threshold` (Cat A) | ₹12,00,000 | New Regime |
| `HDS_IN_TDS_87A_LIMIT_OLD` | Sec 87A Taxable Income Limit | `hr.rule.parameter` | `threshold` (Cat A) | ₹5,00,000 | Old Regime |
| `HDS_IN_TDS_87A_MAX_REBATE_NEW` | Sec 87A Max Tax Rebate | `hr.rule.parameter` | `threshold` (Cat A) | ₹60,000 | New Regime |
| `HDS_IN_TDS_87A_MAX_REBATE_OLD` | Sec 87A Max Tax Rebate | `hr.rule.parameter` | `threshold` (Cat A) | ₹12,500 | Old Regime |
| `HDS_IN_TDS_HEALTH_CESS` | Health & Education Cess | `hr.rule.parameter` | `rate` (Cat A) | 4% | Shared |
| `HDS_IN_TDS_NPS_LIMIT_NEW` | Employer NPS Limit % | `hr.rule.parameter` | `rate` (Cat A) | 14% | New Regime |
| `HDS_IN_TDS_NPS_LIMIT_OLD_PRIVATE` | Employer NPS Limit % | `hr.rule.parameter` | `rate` (Cat A) | 10% | Old Regime (Private) |
| `HDS_IN_TDS_NPS_LIMIT_OLD_GOVT` | Employer NPS Limit % | `hr.rule.parameter` | `rate` (Cat A) | 14% | Old Regime (Govt) |
| `HDS_IN_TDS_EMPLOYER_CONTRIBUTION_LIMIT` | Combined Employer Ceiling | `hr.rule.parameter` | `ceiling` (Cat A) | ₹7,50,000 | Shared |
| `HDS_IN_TDS_80C_MAX_LIMIT` | Section 80C Max Limit | `hr.rule.parameter` | `ceiling` (Cat A) | ₹1,50,000 | Old Regime |
| `HDS_IN_TDS_80CCD1B_MAX_LIMIT` | Section 80CCD(1B) NPS Limit | `hr.rule.parameter` | `ceiling` (Cat A) | ₹50,000 | Old Regime |
| `HDS_IN_TDS_80D_SELF_MAX_LIMIT` | Sec 80D Health Self Limit | `hr.rule.parameter` | `ceiling` (Cat A) | ₹25,000 | Old Regime |
| `HDS_IN_TDS_80D_SELF_SENIOR_MAX_LIMIT` | Sec 80D Health Self Senior Limit | `hr.rule.parameter` | `ceiling` (Cat A) | ₹50,000 | Old Regime |
| `HDS_IN_TDS_80D_PARENTS_MAX_LIMIT` | Sec 80D Health Parents Limit | `hr.rule.parameter` | `ceiling` (Cat A) | ₹25,000 | Old Regime |
| `HDS_IN_TDS_80D_PARENTS_SENIOR_MAX_LIMIT` | Sec 80D Health Parents Senior | `hr.rule.parameter` | `ceiling` (Cat A) | ₹50,000 | Old Regime |
| `HDS_IN_TDS_80D_PREVENTIVE_CHECKUP_LIMIT` | Sec 80D Preventive Checkup | `hr.rule.parameter` | `ceiling` (Cat A) | ₹5,000 | Old Regime |
| `HDS_IN_TDS_80TTA_MAX_LIMIT` | Sec 80TTA Savings Interest Limit | `hr.rule.parameter` | `ceiling` (Cat A) | ₹10,000 | Old Regime |
| `HDS_IN_TDS_80TTB_MAX_LIMIT` | Sec 80TTB Senior Interest Limit | `hr.rule.parameter` | `ceiling` (Cat A) | ₹50,000 | Old Regime |
| `HDS_IN_TDS_80DD_NORMAL_LIMIT` | Sec 80DD Disability Normal Limit | `hr.rule.parameter` | `ceiling` (Cat A) | ₹75,000 | Old Regime |
| `HDS_IN_TDS_80DD_SEVERE_LIMIT` | Sec 80DD Disability Severe Limit | `hr.rule.parameter` | `ceiling` (Cat A) | ₹1,25,000 | Old Regime |
| `HDS_IN_TDS_24B_HOME_LOAN_INTEREST_LIMIT` | Sec 24(b) Home Loan Interest | `hr.rule.parameter` | `ceiling` (Cat A) | ₹2,00,000 | Old Regime |
| `HDS_IN_TDS_80EEA_MAX_LIMIT` | Sec 80EEA First-time Home Loan | `hr.rule.parameter` | `ceiling` (Cat B) | ₹1,50,000 | Old Regime |
| `HDS_IN_TDS_HRA_METRO_PERCENT` | HRA Metro City % | `hr.rule.parameter` | `rate` (Cat A) | 50% | Old Regime |
| `HDS_IN_TDS_HRA_NON_METRO_PERCENT` | HRA Non-Metro City % | `hr.rule.parameter` | `rate` (Cat A) | 40% | Old Regime |
| `HDS_IN_TDS_HRA_RENT_EXCESS_BASIC_PERCENT` | HRA Rent Excess over Basic % | `hr.rule.parameter` | `rate` (Cat A) | 10% | Old Regime |
| `HDS_IN_TDS_CHILDREN_EDU_ALLOWANCE_MONTHLY` | Children Education Allowance | `hr.rule.parameter` | `ceiling` (Cat A) | ₹100/mo | Shared |
| `HDS_IN_TDS_HOSTEL_ALLOWANCE_MONTHLY` | Hostel Expenditure Allowance | `hr.rule.parameter` | `ceiling` (Cat A) | ₹300/mo | Shared |
| `HDS_IN_TDS_LEAVE_ENCASHMENT_EXEMPTION_CEILING` | Leave Encashment Ceiling | `hr.rule.parameter` | `ceiling` (Cat A) | ₹25,00,000 | Shared |
| `HDS_IN_TDS_VRS_EXEMPTION_CEILING` | VRS Exemption Ceiling | `hr.rule.parameter` | `ceiling` (Cat A) | ₹5,00,000 | Shared |

---

## 4. Dedicated Tax Master Models

### 4.1 `tds.financial.year`
- **Fields**: `name`, `code`, `assessment_year`, `start_date`, `end_date`, `is_closed`, `active`, `tax_slab_ids`, `surcharge_ids`.
- **Validation**: Enforces `start_date < end_date` and unique financial year code.

### 4.2 `tds.tax.regime`
- **Fields**: `name`, `code` (`new`, `old`), `description`, `sequence`, `is_default`, `active`.

### 4.3 `tds.tax.slab`
- **AY 2026-27 New Regime Slabs**:
  1. ₹0 - ₹4,00,000 @ 0%
  2. ₹4,00,000 - ₹8,00,000 @ 5%
  3. ₹8,00,000 - ₹12,00,000 @ 10%
  4. ₹12,00,000 - ₹16,00,000 @ 15%
  5. ₹16,00,000 - ₹20,00,000 @ 20%
  6. ₹20,00,000 - ₹24,00,000 @ 25%
  7. Above ₹24,00,000 @ 30%
- **Validation**: `@api.constrains` prevents overlapping income ranges for the same FY and regime.

### 4.4 `tds.surcharge`
- **New Regime Surcharge**: Capped at 25% for income exceeding ₹2 Crore.
- **Old Regime Surcharge**: Ranges from 10% (₹50L-1Cr) up to 37% (Above ₹5Cr).
- **Validation**: `@api.constrains` prevents overlapping surcharge income ranges.

---

## 5. Centralized Resolver: `TdsParameterService`

Located in `services/tds/tds_parameter_service.py`:
- `get_parameter(code_or_key, eval_date=None, regime='new', employer_type='private', as_decimal=False)`
- `get_80c_limit(eval_date=None)`
- `get_80ccd1b_limit(eval_date=None)`
- `get_hra_percentage(is_metro=True, eval_date=None, as_decimal=False)`
- `get_80d_limit(is_senior=False, is_parents=False, eval_date=None)`
- `get_home_loan_interest_limit(eval_date=None)`
- `get_leave_encashment_ceiling(eval_date=None)`
- `get_employer_nps_limit(regime='new', employer_type='private', eval_date=None)`
- `get_combined_employer_contribution_limit(eval_date=None)`
- `get_financial_year(eval_date=None)`
- `get_tax_slabs(financial_year=None, regime='new', eval_date=None)`
- `get_surcharge_slabs(financial_year=None, regime='new', eval_date=None)`

---

## 6. UI Navigation
- **Menu Location**: **Payroll → Configuration → India Tax Configuration**
- **Submenus**:
  1. **Financial Years** (`action_tds_financial_year`)
  2. **Tax Regimes** (`action_tds_tax_regime`)
  3. **Tax Slabs** (`action_tds_tax_slab`)
  4. **Surcharge Slabs** (`action_tds_surcharge`)
