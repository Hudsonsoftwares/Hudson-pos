# EH HR Platform Core

`eh_hr_core`  -  Part of the EH HR Platform by ERP Heritage.

> Foundational platform module for the EH HR Platform: mixins, services, audit log, OWL component kit.

HR Platform Core (eh_hr_core)
Thin, dependency-light platform module that every other HR feature module
builds on.

Provides:
- Abstract mixins (audited, company-aware, platform-base).
- The audit log (append-only, hash-chained), independent of mail.thread.
- A service base class and tiny service registry/locator.
- Settings + feature flag scaffolding (per-company key/value).
- Timezone helpers and company-scoped query helpers.
- OWL component kit primitives (HrCard, HrStat, HrSkeleton, ...).

Explicitly NOT here:
- Workflow logic            → eh_hr_engine_workflow
- Approval chains           → eh_hr_engine_approval
- Policy DSL                → eh_hr_engine_policy
- Notification dispatch     → eh_hr_engine_notification
- Any feature surface       → eh_hr_attendance_pro, eh_hr_leave_pro, ...

## Models added

- `eh.hr.audit.log`
- `eh.hr.audited.mixin`
- `eh.hr.company.aware.mixin`
- `eh.hr.feature.flag`
- `eh.hr.platform.mixin`
- `eh.hr.settings.entry`

## Standard Odoo models extended

- `res.config.settings`

## Dependencies

- Odoo: `base`, `mail`, `hr`
- Platform: `eh_hr_compat`

## Compatibility

Odoo 16, 17, 18 and 19 (Community). The module installs natively on 18 and 19; the 16 and 17 view layers are produced from the same source by `tools/backport_views.py`. The full platform test suite runs green on all four series.

## Licence

LGPL-3. Author: ERP Heritage.
