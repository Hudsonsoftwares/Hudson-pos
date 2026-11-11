# Payroll Addons 20: Work Summary and Handoff

Last updated: 3 November 2026. This document summarises a long working session on the Hudson payroll addons for Odoo 20: what was built, the decisions made, how to work on the system, and what is still open. Read sections 1 and 8 first if you are picking up the work.

---

## 1. Environment and working procedures

### 1.1 Installation
| Item | Value |
|---|---|
| Odoo | 20.0, build `20.0.20260927`, installed at `C:\Program Files\Odoo 20.0.20260927` |
| Config | `server\odoo.conf` (addons path: Odoo addons, `D:\Payroll-addons-20`, `D:\Payroll-addons-20\hudson_accounting_bundle`, `D:\Barcode-test`, `D:\Document-addons`) |
| Service | Windows service `odoo-server-20.0`, runs as **LocalSystem** |
| Main database | `HUDSON` (several test companies; main company "My Company") |
| Test database | `demo_customer` (see section 6) |
| Repository | `D:\Payroll-addons-20`, branch `main` |

### 1.2 Running commands (Git Bash)
```bash
cd "/c/Program Files/Odoo 20.0.20260927"
# Upgrade a module and run tests (use a :Class suffix; prefix MSYS_NO_PATHCONV=1 so Git Bash does not mangle "/module")
MSYS_NO_PATHCONV=1 python/python.exe server/odoo-bin -c server/odoo.conf -d HUDSON -u hudson_in_payroll \
  --test-tags /hudson_in_payroll:TestDashboardGovtDeposit --stop-after-init --http-port=8099
# Odoo shell
python/python.exe server/odoo-bin shell -c server/odoo.conf -d HUDSON --no-http < script.py
```
- Every test run ends with a `tearDownClass` / `_gc_filestore` error: this is environmental (filestore permissions), not a test failure. Read the `0 failed, N error(s)` line and check the errors are only `tearDownClass`.
- Python warnings in test logs can look like tracebacks; check the result line.

### 1.3 Filestore caveat (important)
The service (LocalSystem) and command-line runs (user `dell`) use **different filestores**. Anything written by a command-line run (asset bundles, binary fields, attachments) cannot be read by the service, which causes white screens or HTTP 500.

After any command-line upgrade, test run or shell write on HUDSON:
1. Delete cached asset bundles:
   ```bash
   echo "env.cr.execute(\"DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%'\"); env.cr.commit()" \
     | python/python.exe server/odoo-bin shell -c server/odoo.conf -d HUDSON --no-http
   ```
2. **Then** restart the service (PowerShell: `Restart-Service odoo-server-20.0`). Do not run steps 1 and 2 at the same time: the shell fails with `KeyError: 'HUDSON'`.
3. New binary data loaded by a command-line install (e.g. the payroll spreadsheet dashboard JSON) must be moved into the database (`db_datas`) or the service returns 500 for it.

Databases created from the command line should use database storage: `ir.config_parameter` `set_str('ir_attachment.location', 'db')` then `ir.attachment.force_storage()` (done for `demo_customer`). In Odoo 20 the config-parameter API is `set_str` / `get_str` (`set_param` no longer exists).

### 1.4 Odoo 20 notes learned
- Security: `security/ir.access.csv` (columns `id,name,model_id,group_id/id,operation,domain`). A row **with a group grants** access (optionally filtered); a row **without a group only restricts**. Old `ir.model.access.csv` files in our modules are no longer loaded.
- A model class with only `_name` (no `_inherit`) **replaces** an existing model definition instead of extending it.
- `<template active="False">` applies only on first install; upgrades do not change a view's active state. Deleted views from module files are re-created on upgrade; edits made in Settings > Technical are overwritten on upgrade.
- Binary fields: `odoo.tools.BinaryBytes(data, filename)`; read with `.content`.
- `ir.actions.report` uses `group_ids` (no `report_file`). Icons: Material Symbols names (`fa-*` renders as "---").
- Header buttons in list/kanban control panels pass ids: do not decorate those methods with `@api.model`.
- Employee `departure_date` is related to `version_id.departure_id.departure_date` (an `hr.employee.departure` record); searching it for archived employees needs `active_test=False`.

### 1.5 Regression baseline
Full payroll suite (`hudson_in_payroll`, `hudson_payroll_base`, `hudson_in_final_settlement`) has around 35-44 failures and 131 errors that existed **before** this session (EPF service, gratuity, PT, Section 17(2)(vii)/80CCD(2), multi-company, bonus…). Several are order/data dependent. When checking a change, compare failure lists with and without the change rather than expecting zero.

---

## 2. Work completed (by area)

### 2.1 Payroll dashboard (`hudson_in_payroll/models/payroll_dashboard.py`)
Design rule adopted: **cards show counts only; clicking a card opens a list view with the detailed breakdown**, and the list total always equals the card.

- **Removed:** Aadhaar/ID data-health card; duplicate "Active Employees" KPI card; "Payslips to Validate" card; New Joiners section; Statutory Obligations section; Employer Cost Composition section; Tax Regime card (Statutory Compliance); "Settlement Not Started" planner card; Payroll Cost Trend chart (the 6-month data loop is kept because header payslip chips use the current month).
- **Header strip** (Period / Tax Year / Employees / Payslips) enlarged about 15% (`payroll_dashboard_odoo.scss`).
- **KPI cards with breakdown lists** (shared helper `_hds_month_payslips()` = validated/paid payslips of the month, duplicates counted once, used by both the card totals and the lists):
  | Card | Card type | List view |
  |---|---|---|
  | Total Payroll Cost (CTC) | `ctc_breakdown` | `view_hr_payslip_list_ctc` |
  | Net Salary | `net_breakdown` | `view_hr_payslip_list_net` |
  | Govt Deposit | `govt_deposit` | `view_hr_payslip_list_govt_deposit` |
  | TDS This Month | `tds_breakdown` | `view_hr_payslip_list_tds` |
- New stored payslip fields (`hudson_in_payroll/models/hr_payslip.py`), computed from payslip lines with the dashboard's own code rules: `hds_in_govt_*` (employee/employer EPF, EDLI & admin, employee/employer ESIC, PT, employee/employer LWF, TDS, total), `hds_in_ctc_*` (gross, employer EPF/EDLI/admin/ESIC/LWF/other, employer cost, CTC), `hds_in_net_salary`, `hds_in_net_other_deductions`, related `hds_in_employee_pan`.
- **Joiners & Exits** split into "Joiners This Month" and "Exits This Month" (helper `_hds_employee_movements()`; exits include archived employees).
- **Tax Declarations** card: per selected month: Pending verification (proofs submitted that month), Awaiting proofs (declared that month), Not submitted (drafts created that month); each count opens its list. Footer "Nothing to review" replaces "All verified". New field `proof_submission_date` on `tds.employee.declaration`, set automatically when a declaration reaches Proof Submitted (any path).
- **Final Settlement Planner**: three count-only cards (In Draft, Approved – To Pay, Settled & Paid); buttons open `view_final_settlement_list_breakdown` (gratuity, leave encashment, other earnings, total earnings/deductions, net). New stored field `other_earnings_amount` on `final.settlement`.
- **Leave Encashment Requests**: order Draft → Pending approval → Approved → Paid; count-only cards; buttons open `view_hds_leave_encashment_request_list_breakdown` (days, daily rate, amount, payslip).
- **Employees Without Running Contract**: count-only cards; each reason opens its own employee list (`view_hr_employee_list_contract_status` in `hudson_in_payroll/views/hr_employee_views.xml`).
- Tests: `hudson_in_payroll/tests/test_dashboard_govt_deposit.py` (card vs list totals for every month with payslips, joiners/exits with a real departure, tax declaration card).
- A reported "BUG-5" (trend chart month/year) was analysed: **not a bug**; the proposed fix would have introduced one. Chart since removed.

### 2.2 Statutory lines follow company settings
`hudson_in_payroll/models/hr_salary_rule.py`: a statutory rule of an **Indian structure** (structure country IN) applies only when its company switch is on (TDS, PT, EPF family, ESIC, LWF, Gratuity, Leave Encashment). Amounts were already zero when off; now the zero lines are not created. Verified on all 51 HUDSON payslips: no amount changes. Test: `test_company_statutory_lines.py`.

### 2.3 Salary revision / Salary Increase (Odoo Online style)
- Compact "Salary Increase" dialog (rate %, applies on full or capped wage, extra amount, multi-employee) on the employee Action/gear menu.
- **Advanced** opens a read-only comparison (current vs new): salary summary, projected breakdown, PF, statutory (ESIC, PT, LWF); Confirm / Back / Discard.
- Each revision creates a dated `hr.version` (effective date must be the 1st of a month, today or later); payslips pick the version of their period (`employee._hds_payroll_version()`).
- Known gap (explained, not changed): the comparison's "New" ESIC column uses the wage ceiling only, not the contribution-period rule.

### 2.4 TDS, Challans, Form 138
- TDS Financial Year: choosing "Recalculation From Month" sets "Distribution Months" automatically.
- TDS Challans: import paid payslips of the period; TDS and total paid computed; Form 138 link.
- Form 138 quarterly return: Q1–Q4 generation, text file (form number 138), Regular Statement tab, penalty in CD record. **Validation added:** cannot mark Done or generate the text file with zero challans. HUDSON has one Done return without challans ("Form 138 2026-2027 Q4", My Company) that a manager can reset to Draft.

### 2.5 Pay run, email, reports
- Pay run "Send by Email" (validated and paid runs; one email per employee with own PDF; employees without email are listed).
- Email content: template `hudson_payroll_base.mail_template_payslip` in `hudson_payroll_base/data/mail_template_data.xml` (noupdate, editable in Settings > Technical > Email Templates). Buttons: `action_payslip_send_email` (`hr_payslip.py`), `action_send_payslips_email` (`hr_payslip_run.py`). PDF: report `action_report_payslip` (`hudson_payroll_base/reports/hr_payslip_report.xml`), page replaced by the Indian design `report_payslip_page_content` (`hudson_in_payroll/reports/report_payslip_custom_template.xml`).
- Salary Certificate PDF from the employee Print menu.
- Tax Calculation Report viewer: duplicate buttons removed, dark theme fixed.

### 2.6 Accounting (`hudson_payroll_account`)
Draft journal entry on payslip validation (per payslip, or consolidated per pay run when enabled), Post, smart buttons, default payroll account mapping to the Indian chart (`l10n_in` codes 210100, 300007…), journal entry list cleaned up. HUDSON companies have no chart of accounts yet, so no entries are created there until a fiscal localization is applied.

### 2.7 Payment Mode moved to the shared layer (first step of the UAE refactor)
- `hds.payment.mode` (model, screens, menu, Settings link, access rows) and the `hds_in_payment_mode` fields on Employee and Payslip moved from `hudson_in_payroll` to `hudson_payroll_base` (version 20.0.1.0.1). Technical names unchanged, so no data conversion.
- Default modes: Bank Transfer, Cheque, Cash in the base; NEFT / RTGS and UPI stay in `hudson_in_payroll` (version 20.0.1.0.8).
- Ownership of the existing records is transferred by an identical pre-migration in both modules (`migrations/20.0.1.0.1` and `migrations/20.0.1.0.8`), so upgrading either module first is safe.
- Employee form: the field now sits under Private Contact, above Bank Accounts (was in the Indian "Statutory Information" group). Payslip form: after Payment Date. Settings: "Payment Modes" link in the Payroll block.
- Verified on copies of HUDSON (both upgrade orders) and fresh databases (base alone, base with India), then applied to HUDSON: the 6 modes and the 55 payslips' modes are unchanged.
- Pattern to reuse for the next shared features (salary revision, audit log, dashboard framework…): keep technical names, move code and files, transfer `ir_model_data` ownership with a migration in both modules.

### 2.8 Documents (DMS) and the Payroll → Documents bridge
- DMS modules are now in this repository (commit `cab5243`), with teammate Nandu's corrections (`a5fe3ae`, `dms_enterprise_features` 20.0.1.0.2): unique employee folder names, folder reuse, employee folders linked to the employee, backfill of folders for existing employees, avatars no longer routed into Documents, SharePoint-style permission inheritance, Trash. `D:\Document-addons` is no longer on the addons path.
- HUDSON upgraded to this DMS version on 4 Nov 2026: all 29 employees have a folder; creating employees works again.
- New bridge module **`hudson_payroll_dms`** (installed on HUDSON): when a payslip is validated, its PDF (the same as Print / Email) is stored in `Employees / <employee> / Payroll / <tax year> / <Employee> - <Month Year>.pdf`.
  - Generated in the background (cron "Payroll: Store Payslips in Documents", triggered at validation); a failure never blocks validation and is retried (up to 5 times; "Store now" button on the payslip).
  - Reset to draft or cancel → the file goes to the Documents Trash; validating again restores and replaces the same file.
  - Created by the system (OdooBot); payslip tags from the Documents setting; employees see only their own folder.
  - Payslip form: Documents status + "Document" button; filters "Documents: Not Stored / Failed"; Payroll Settings: "Store Payslips in Documents" (per company, on by default) and "Store existing payslips".
  - Verified: 9 module tests; payroll suites identical with and without the bridge; rehearsal on a copy stored all 46 validated payslips.
  - Existing payslips on HUDSON were **not** stored yet: use Payroll Settings → "Store existing payslips" (runs inside the service).

### 2.9 Other
- Country-based auto-install: installing Payroll Base auto-installs the Indian modules when the company country is India.
- Dark theme fixes (pay run, More menu, tax report).
- Spreadsheet dashboard: values verified, clickable KPI cards, Final Settlement and Leave Encashment section.

---

## 3. Investigations and explanations (no code change)
- **Settings crash `documents_binary_max_size`**: DMS modules were installed but `D:\Document-addons` had been removed from the addons path. Path restored by the user.
- **Tester install error `KeyError: 'schedule_pay'`** (tester on Odoo build 20.0.**20260928**): could not be reproduced on build 20260927 (fresh database with Website, installed via the Apps button: OK). It is now fine on the tester's database. Underlying weakness: `hudson_payroll_base/models/hr_payroll_structure_type.py` uses `_name = 'hr.payroll.structure.type'`, which **replaces** Odoo's own model (drops its `country_code` field) instead of extending it. Recommended fix: switch to `_inherit` (not done yet).
- **Tax Declarations card showing 0**: correct by design (no declarations were in the HR review stages); led to the card redesign above. NPS TEST declaration is Draft but has submission/approval dates (probably reset).
- **"Settlement Not Started"**: End of Collaboration automatically creates a draft final settlement. PRINCE TST and Gino have departures but no settlement (development-era data).
- **Net Salary vs CTC gross**: for payslips with zero gross, the dashboard's Gross/CTC uses the contract wage (April 2026: ₹4,80,000 for four ₹0 payslips). Existing behaviour, not changed; the Net list uses the actual payslip gross.

---

## 4. Payroll user roles and security findings
Roles (Settings > Users > Human Resources > Payroll):
- **Officer** (`hudson_payroll_base.group_payroll_user`): runs payroll (payslips, pay runs, inputs), reports, declaration verification; read-only on setup.
- **Administrator** (`group_payroll_manager`): everything, plus setup (rules, structures), salary revisions, final settlements, Form 138 reset; implies HR Officer.
- Ordinary employees: no Payroll app.

**Open security issue (tested, not fixed; awaiting decision):** a plain employee user can read and edit **all employees' tax declarations and tax regimes**, read their company's **final settlements** and **salary statement lines**. Cause: unfiltered `base.group_user` rows in `hudson_in_payroll/security/ir.access.csv` and `hudson_in_final_settlement/security/ir.access.csv` alongside the "own records" rows (Odoo combines grants, so the unfiltered one wins). Proposed fix: remove the unfiltered rows, restrict final settlements to payroll roles (or own read-only), salary statement lines to payroll roles, delete unused `ir.model.access.csv` files. **Question pending:** should employees see their own final settlement (read-only) or not at all?

---

## 5. Cloud hosting and per-customer report designs
Plan: **one database per customer company** (not multi-company).

Decisions and guidance:
- Never customise reports by editing views in Settings > Technical (lost on upgrade, not in git). Never delete our report views in a customer database.
- **Chosen approach: customer-only design module** (XML only), installed only in that customer's database. It swaps the payslip page template; amounts come from `get_payslip_pdf_data()`, so figures are identical to the standard design.
- Installing by upload works: **Apps > Import Module** (developer mode) loads a zipped XML-only module into **that database only**; other databases do not see it. Verified by the user.
- Keep each customer design's source in git (e.g. a `customers/` folder). Customers should not get administrator rights. Use `dbfilter` per subdomain; disable the database manager.
- Possible later features: a "Payslip PDF Layout" setting with ready-made designs; a "Report Design" upload screen with validation and version rollback.

---

## 6. Demo customer module and test database
- Module: `D:\Payroll-addons-20\hudson_payslip_demo_customer\` ("Payslip Design - Demo Customer", depends on `hudson_in_payroll`; one XML file `reports/report_payslip_demo_customer.xml`: blue header band, employee card, separate earnings/deductions tables, Net Pay box with amount in words). Currently **uninstalled** everywhere. A zip was made in the session scratchpad for the Import Module test.
- Database `demo_customer`: company "Demo Customer Pvt Ltd" (India, Kerala, INR), attachments stored in the database, Indian payroll installed, employee **Arun Kumar** (PAN, UAN, bank, ₹50,000 contract), validated **October 2026** payslip (gross ₹50,000, EPF ₹3,000, net ₹47,000). Login `admin` / `admin`.
- Cleanup when finished: uninstall the module, delete the folder and zip, drop `demo_customer`.

---

## 7. UAE localisation (next major work)
Current state of `hudson_ae_payroll`: **uninstallable**. Written for the old stack (Odoo 19; depends on missing `hr_payroll_community`, `hudson_payroll_core`, `hudson_payroll_payrun`). Contains useful work: masters (7 Emirates, 44 labour authorities, 50 jurisdictions, 4 pension authorities, 2 schemes), employee classification (UAE / GCC / expat), GPSSA / ADPF / GCC pension service with about 60 date-based rate parameters, 76 tests. Weaknesses: 35 of 37 salary rules are manual input placeholders; structures reference old-stack rule ids; an unloaded pension-rate data file and view. Our `hudson_payroll_base` already provides `hr.rule.parameter` and the `_get_localization_context` hook.

**Recommended approach (Option C):** a clean `hudson_ae_payroll` following the Indian module's architecture on `hudson_payroll_base`, reusing the old module's masters, pension service, parameters and tests; not a copy of `hudson_in_payroll`.

**Key architecture step first:** move generic features out of `hudson_in_payroll` into the shared layer (`hudson_payroll_base` or a new `hudson_payroll_common`): salary revision, payment modes, audit log, payroll dashboard framework, salary statement/register, contract salary breakdown, leave encashment framework. Otherwise UAE customers would get Indian TDS/PF menus.

**Planned UAE modules:**
| Module | Purpose |
|---|---|
| `hudson_ae_payroll` | Masters, classification, contract components (Basic, Housing, Transport…), GPSSA/ADPF/GCC pension, DEWS, overtime, leave salary, air ticket, structures and rules, settings, UAE payslip PDF, auto-install for UAE companies |
| `hudson_ae_final_settlement` | End of Service Benefit (UAE Labour Law), notice pay, leave settlement, final settlement |
| `hudson_ae_wps` | WPS / SIF salary file, establishment ID, bank/agent routing codes |
| `hudson_ae_reports` (optional) | Payroll register, pension contribution, labour reports |
| Accounting | Make `hudson_payroll_account` country-aware (UAE chart `l10n_ae`) |

Not needed for UAE: income tax (no personal income tax), PF, ESIC, PT, LWF.

**Order of work:** 1) shared foundation refactor, 2) `hudson_ae_payroll` core, 3) final settlement / EOSB, 4) WPS, 5) PDF, reports, dashboard, accounting.

**Inputs requested from the user before planning:** sample UAE payslip, WPS bank/exchange format, Emirates / free zones of first customers, employee mix (nationals / GCC / expats); confirmation of rule sources (UAE Labour Law Federal Decree-Law 33/2021; current GPSSA / ADPF rules), or permission to research and show official sources first.

---

## 8. Open items and pending decisions
| # | Item | Status |
|---|---|---|
| 1 | Security fix for declarations / final settlements / salary statement lines (section 4) | Awaiting decision on employee access to own final settlement |
| 2 | Structure Type `_name` → `_inherit` (and check Payroll Structure) | Recommended, not done |
| 3 | UAE localisation (section 7) | Awaiting inputs; step 1 plan not yet written |
| 4 | Dashboard: November "6 relieving" counts employees without settlement (PRINCE TST, Gino) but no card shows them; top "Final Settlements" card still shows "not started" | Offered, not decided |
| 5 | Dashboard Gross/CTC uses contract wage for ₹0 payslips | Offered, not decided |
| 6 | Salary Increase "Advanced" ESIC column should follow the contribution-period rule | Offered, not decided |
| 7 | Trim the dashboard's 6-month data loop to the current month (performance) | Optional |
| 8 | Form 138 2026-2027 Q4 (My Company) Done without challans | Data: reset to Draft if needed |
| 9 | Create missing draft settlements for PRINCE TST / Gino if real | Data |
| 10 | Pre-existing failing tests (section 1.5) | Not investigated |
| 11 | Parked: DMS employee folder clash ("A directory with the same name already exists") | Fix designed, not implemented |
| 12 | Parked: leave encashment "paid" requests whose payslips were deleted; Gino duplicate LE; LAP gratuity above ₹20L cap (policy) | Parked |
| 13 | Cleanup of demo module, zip and `demo_customer` database | When testing is finished |
| 14 | Commit the session's changes to git (many modified and new files are uncommitted) | Pending; nothing was committed in this session |
| 15 | DMS employee-folder clash | **Fixed** by the teammate's DMS corrections, upgraded on HUDSON 4 Nov 2026 |
| 16 | Store HUDSON's existing validated payslips in Documents | User action: Payroll Settings → "Store existing payslips" |
| 17 | Commit `hudson_payroll_dms` to git | Pending |
