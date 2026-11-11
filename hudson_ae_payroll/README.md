# Hudson UAE Payroll Localization (`hudson_ae_payroll`)

## 1. Purpose
`hudson_ae_payroll` is the dedicated United Arab Emirates (UAE) payroll localization module for Hudson HRMS. It establishes the clean architectural foundation and country localization layer for managing UAE payroll operations.

## 2. UAE Payroll Localization
This module acts as the localization layer specifically for UAE statutory and business requirements, catering to both UAE/GCC national and expatriate employee payroll processing.

## 3. Generic Payroll Engine Extension
`hudson_ae_payroll` builds directly on top of the generic payroll ecosystem:
- `hr_payroll_community` (Generic payslip calculation engine)
- `hudson_payroll_core` (Shared payroll models and parameter framework)
- `hudson_payroll_payrun` (Payrun processing and payment advice workflows)

## 4. Decoupling & Independence from Other Country Localizations
The module is completely decoupled and independent from other country localizations (such as `hudson_in_payroll`). It does not import or depend on any India statutory models, rules, or calculation services, ensuring full modularity and isolation across jurisdictions.

## 5. Incremental Statutory Implementation
Statutory and localization features will be introduced incrementally across subsequent development phases:
- UAE eligibility and jurisdiction/nationality classification (GCC vs Expat)
- UAE wage basis mapping and allowances (Basic, Housing, Transport, etc.)
- GPSSA / UAE & GCC social insurance and pension contributions
- End of Service Benefits (EOSB) / Gratuity calculations
- UAE Labor Law overtime calculations
- WPS (Wages Protection System) / SIF file generation
- Final settlement calculations

## 6. Architecture & Localization Hook
Rather than overriding the generic payslip calculation engine (`_get_payslip_lines()`), this module leverages the generic extension hook:
```python
def _get_localization_context(self, localdict):
    localdict = super()._get_localization_context(localdict)
    # Inject UAE-specific calculation services into localdict
    return localdict
```
This architecture preserves the generic payslip engine integrity while allowing clean injection of UAE localization services into the payroll computation environment.
