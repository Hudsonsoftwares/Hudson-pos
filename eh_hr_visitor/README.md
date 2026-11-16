# Visitor Management

Self-hosted visitor management for Odoo 19 Community. The same
reception tablet that runs the face-attendance kiosk can also run
visitor sign-in by browsing a different URL.

## Install

```
./odoo-bin -d <db> -i eh_hr_visitor
```

Depends on `eh_hr_attendance_base`, `mail`, `hr`. Auto-pulls in the
shared kiosk site and device infrastructure from the base module.

## Pairing the reception tablet

Same flow as the attendance kiosk: an admin clicks **Issue pairing
PIN** on the kiosk site form, the receptionist opens
`/eh_hr/visitor/<site_code>` on the tablet, enters the PIN. From
then on, the tablet remembers itself and sign-ins / sign-outs are
attributed to that device.

## Visitor sign-in flow

1. Visitor taps **Sign in** on the home screen.
2. Enters name, organisation, optional email, picks host and
   purpose from autocomplete dropdowns.
3. If the chosen purpose is configured `nda_required`, the NDA
   text is shown and a tick box is required before continuing.
4. If `photo_required`, the camera activates and the visitor
   captures their own photo. The kiosk shows the configured
   photo consent text first.
5. Sign-in completes. Visit number is shown on screen for the
   visitor to remember (used for self-service sign-out at the end).
6. The host receives an email through the standard mail queue.

## Default purposes seeded

| Code | Name | NDA | Photo |
|---|---|---|---|
| meeting | Meeting | no | no |
| delivery | Delivery | no | no |
| contractor | Contractor | yes | yes |
| interview | Interview | yes | no |

Operators add or modify purposes under People Operations &gt;
Configuration &gt; Purposes.

## Auto check-out

Hourly cron looks at each company's configured cut-off hour
(default 18:00 local). Any visitor still signed in past that
hour is auto-signed-out, with `auto_signed_out=True` on the
record so the audit trail shows it was a system action, not a
manual one.

## Retention

Daily cron deletes signed-out visitor rows past the company's
retention window (default 365 days). The NDA snapshot, photo,
and notes are deleted with the row. A privacy promise enforced
in code, not paperwork.

## Endpoints

* `GET  /eh_hr/visitor/<site_code>`  public kiosk shell HTML
* `GET  /eh_hr/visitor/bootstrap`    purposes + hosts + NDA + photo
                                     consent text for the device
* `POST /eh_hr/visitor/sign_in`      create a visitor record + notify
* `POST /eh_hr/visitor/sign_out`     close by visit number

## Apps Store readiness checklist

Operator action: `static/description/banner.png`, `icon.png`,
`index.html`. Module display name "Visitor Management" is 18 chars.

## Honest gaps

* **No badge printing.** Customers using printed badges connect a
  network printer through the host OS; a future module can add
  direct printer integration if customer demand surfaces.
* **No SMS notification, only email.** Cleanest add via a
  generic SMS provider plugin, deferred.
* **No watchlist.** Restricting specific names from signing in
  is a Wave 3 candidate.
* **No multi-host or escort flow.** Visitor links to one host
  only. A future iteration adds an optional escort relationship
  for high-security sites.
