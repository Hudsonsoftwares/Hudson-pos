Attendance Location Validator
=============================

Enforce attendance check-in and check-out only from a configured office location
using GPS-based radius validation with the Haversine formula.

Features
--------
* **GPS Radius Validation** — Validates employee location against the configured
  Work Location coordinates and radius during check-in and check-out.
* **Remote Check-in Exception** — Per-employee toggle to allow check-in/out from
  any location (for remote workers, field agents, etc.).
* **Configurable Per Location** — Set latitude, longitude, and allowed radius (km)
  directly on each ``hr.work.location`` record.
* **Graceful Geocoding** — Handles geocoding service failures without blocking
  attendance operations.
* **Toast Notifications** — Displays validation errors as non-blocking toast
  notifications instead of modal dialogs.

Configuration
-------------
1. Go to **Employees > Configuration > Work Locations**.
2. Open a Work Location and fill in:
   - **Latitude** / **Longitude** — The GPS coordinates of your office.
   - **Radius (km)** — The maximum allowed distance for check-in/out.
3. On the **Employee** form, toggle **Allow Remote Check-In** for employees who
   should be exempt from location validation.

Dependencies
------------
* ``hr``
* ``hr_attendance``
* ``base_geolocalize``
* ``web``

License
-------
LGPL-3
