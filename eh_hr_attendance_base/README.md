# Attendance Suite Base

Foundation module for the ERP Heritage attendance and people-operations
modules on Odoo 19 Community. Auto-installs as a dependency of any
`eh_hr_*` module so it does not need to be installed manually.

This module has no end-user UI for capture or matching by itself. It
provides the data model, security, audit trail, retention lifecycle,
and kiosk pairing endpoints that every capture-modality module
(face, fingerprint, badge, mobile, etc.) builds on top of.

## What it provides

| Concern | Where |
|---|---|
| Biometric and location consent lifecycle | `eh.hr.consent` model + retention cron |
| Kiosk physical site, optional geofence, multi-company scoped | `eh.hr.kiosk.site` |
| Registered kiosk device with rotating opaque token | `eh.hr.kiosk.device` |
| Append-only kiosk audit trail with retention | `eh.hr.kiosk.event` |
| Attendance exceptions: late, no-show, low confidence, geofence violation | `eh.hr.attendance.exception` |
| Employee fields: consent state, fallback PIN, default site, enrolled flag | `hr.employee` extension |
| Company settings: validity, retention, threshold, idle reset | `res.company` + `res.config.settings` |
| Privilege groups: User, Manager, Admin, Auditor (read-only) | `security/eh_hr_security.xml` |
| Per-company record rules, employee-scoped consent visibility | `security/eh_hr_isolation_rules.xml` |
| Pairing endpoint, heartbeat, whoami | `controllers/kiosk.py` |

## What does NOT live here

The base module is deliberately modality-agnostic. The following are
provided by other modules in the suite:

* **Face capture and match.** `eh_hr_face_kiosk` (Wave 1).
* **Job / cost code punch after match.** `eh_hr_attendance_jobcost` (Wave 1).
* **Dashboards, exception detection cron, audit PDF.** `eh_hr_attendance_reports` (Wave 1).
* **PWA mobile and geofence enforcement at clock-in.** `eh_hr_attendance_geofence` (Wave 2).
* **Rosters and shift comparison.** `eh_hr_attendance_roster` (Wave 2).
* **Visitor sign-in.** `eh_hr_visitor` (Wave 2).
* **AU Fair Work / Modern Award OT engine.** `eh_hr_attendance_award_au` (Wave 3).
* **Payroll exports.** `eh_hr_attendance_payroll_export` (Wave 3).
* **Vendor-neutral CSV migration importer.** `eh_hr_attendance_migrate` (Wave 2).
* **Health declaration, access control, active liveness.** Wave 4.

## Install

```
./odoo-bin -d <db> -i eh_hr_attendance_base --without-demo=all
```

No external Python dependencies beyond what `hr` and `hr_attendance`
already require. `pytz` is used for the kiosk site timezone selection
and is part of the Odoo dependency set.

## Apps Store readiness checklist

Before publishing, the following non-code assets must be added by an
operator (not committed by the assistant):

* `static/description/banner.png` (1200x630 recommended) - referenced
  by the manifest's `images` key.
* `static/description/icon.png` (140x140) - referenced by the menu
  `web_icon` and used as the apps store thumbnail.
* `static/description/index.html` - the apps store listing page,
  English-only, no external links.

The module name length is within the 25-character limit ("Attendance
Suite Base" = 22 chars).

## Engineering principles

* **Privacy by design.** Raw biometric images never persist on the
  server. Only embeddings live in the database (introduced by the
  capture-modality module), tied to a granted consent record. Consent
  withdrawal cascades to embedding deletion at the next kiosk match
  attempt.
* **Multi-company aware throughout.** Every model is company-scoped
  and guarded by record rules.
* **Defensible audit.** Every kiosk event is logged with a server
  timestamp the customer cannot edit; managers can read, never write.
  The `eh.hr.kiosk.event` model is intentionally write-blocked at
  the ACL layer for everyone except the daily retention cron.
* **No silent fallbacks.** Missing consent, missing site, missing
  device token each surface explicit messages.

## Public APIs for downstream modules

* `eh.hr.kiosk.event.log(event_type, **kwargs)` - single entry point
  for any module to write to the audit trail. `event_type` is the
  only required argument.
* `eh.hr.attendance.exception.raise_exception(employee, exception_type, ...)`
  - public API for raising an exception. Logs a kiosk event in the
  same call.
* `eh_hr_attendance_base.controllers.kiosk.issue_pairing_pin(site_code)`
  - generate a 5-minute one-shot pairing PIN bound to a site.

## Tests

Tests are added in a separate sweep across all Wave 1 modules so
fixtures and helpers can be shared. The `tests/` directory exists for
that sweep.

## Roadmap

`eh_hr_attendance_base` is the foundation for a 13-module suite that
replaces biometric T&A SaaS for Odoo 19 Community customers. Wave 1
ships the foundation, face kiosk, job costing, and reports. Subsequent
waves add geofence, rosters, visitor management, AU award engine, and
payroll exports. The base module's data model is designed so new
capture modalities (fingerprint, badge, mobile) can plug in without
schema migration.
