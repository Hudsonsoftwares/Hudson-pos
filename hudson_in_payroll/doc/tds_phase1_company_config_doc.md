# Hudson Indian Payroll – TDS Engine Phase 1 Technical Documentation
## Company-Level TDS Configuration Architecture & Technical Reference

---

### Executive Overview

Phase 1 of the Hudson Indian Payroll Tax Deducted at Source (TDS) Engine implements **Company-Level TDS Configuration** adhering strictly to Service-Oriented Architecture (SOA), Domain-Driven Design (DDD), and SOLID principles. 

This implementation aligns with the architectural standards of existing statutory modules (**EPF, ESIC, Professional Tax, LWF, and Gratuity**) in Hudson Payroll.

---

### 1. New Company Configuration Fields

The `res.company` model and the `res.config.settings` transient model have been extended with four new company configuration fields:

| Field Technical Name | UI Label | Data Type | Default | Business Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `hds_in_tds_applicable` | Enable TDS | `Boolean` | `False` | Master switch to enable or disable TDS calculations for the company. When `False`, all downstream TDS calculation services skip processing. |
| `hds_in_tan` | TAN | `Char(10)` | `False` | Stores the company's Tax Deduction and Collection Account Number allotted by the Income Tax Department for statutory Form 16 / Form 24Q compliance. |
| `hds_in_default_tax_regime` | Default Tax Regime | `Selection` | `'new'` | Specifies company-level default tax regime (`'new'` for New Tax Regime under Sec 115BAC, `'old'` for Old Tax Regime) assigned to new employees. |
| `hds_in_default_tax_year` | Default Tax Year | `Many2one` | `False` | References the active/default `tds.financial.year` master record for company tax computations. |

---

### 2. Validation Logic & Server Constraints

#### A. Server-Side Constraints (`res.company._check_hds_in_tds_configuration`)
Whenever company settings are saved, the ORM constraint evaluates:
1. **Mandatory TAN Check**: If `hds_in_tds_applicable = True`, `hds_in_tan` cannot be empty or whitespace.
2. **TAN Syntax Regex Validation**: TAN format must match `^[A-Z]{4}[0-9]{5}[A-Z]{1}$` (10 uppercase characters: 4 letters, 5 digits, 1 letter, e.g. `ABCD12345E`).
3. **Data Sanitization**: Input characters are automatically stripped of leading/trailing spaces and converted to uppercase prior to validation check.
4. **Mandatory Default Tax Regime**: Default Tax Regime selection is validated when TDS is enabled.

#### B. Service Layer Validator (`TdsCompanyConfigValidator`)
Located in `hudson_in_payroll/services/tds/tds_company_config_validator.py`.
- Implements `validate(company)` returning `TdsCompanyValidationResult`.
- Pure Python class decoupled from Odoo ORM registry for zero-overhead validation in payslip processing and unit tests.
- Provides immediate exit (`is_valid=True`, `is_enabled=False`) when TDS is disabled for a company.

---

### 3. User Interface Integration

The configuration UI is rendered under **Payroll → Configuration → Settings**:
- Located in a dedicated **Tax Deducted at Source (TDS)** section.
- Completely isolated from EPF, ESIC, PT, LWF, and Gratuity settings.
- Features dynamic UI visibility (TAN, Default Tax Regime, and Default Tax Year inputs are hidden when TDS toggle is disabled).

---

### 4. Security & Access Control

Access control rules strictly follow Hudson Payroll security hierarchy:

| User Group | Model `tds.financial.year` Access | Settings Access |
| :--- | :--- | :--- |
| **Payroll Manager** (`group_hr_payroll_community_manager`) | Full Access (`1, 1, 1, 1`) | Can edit and save TDS company settings |
| **Payroll Officer** (`group_hr_payroll_community_user`) | Read Only (`1, 0, 0, 0`) | Read only access |
| **Normal Employee** | No Access (`0, 0, 0, 0`) | No access |

---

### 5. Future Integration Points (Phase 2 Roadmap)

This Phase 1 implementation provides a clean foundation for Phase 2:
1. **Financial Year Master (`tds.financial.year`)**:
   The `tds.financial.year` placeholder model will be expanded with assessment year mappings, quarters, and active status rules.
2. **Tax Slabs (`tds.tax.slab`) & Declarations**:
   Company default regime preferences will automatically seed `hr.employee` tax profile declarations.
3. **TDS Calculation Engine (`TdsCalculationService`)**:
   Engine services will call `TdsCompanyConfigValidator(env).validate(company)` to determine TDS applicability before executing tax slab evaluations.

---

### 6. Automated Unit Test Suite

Covered by unit and functional test class `TestTdsCompanyConfig` in `hudson_in_payroll/tests/test_tds_company_config.py`:
- `test_01_tds_default_values`: Asserts default values.
- `test_02_enable_tds_with_valid_tan`: Validates enabling TDS with valid TAN.
- `test_03_enable_tds_missing_tan_raises`: Asserts `ValidationError` on missing TAN.
- `test_04_enable_tds_invalid_tan_raises`: Asserts `ValidationError` on malformed TAN strings.
- `test_05_tan_auto_uppercase_and_trim`: Tests automatic string trimming and upper-casing.
- `test_06_res_config_settings_tds_integration`: Tests save/load persistence via `res.config.settings`.
- `test_07_tds_company_validator_service`: Tests `TdsCompanyConfigValidator` service outputs.
- `test_08_tds_financial_year_model_relation`: Tests relationship with `tds.financial.year`.
