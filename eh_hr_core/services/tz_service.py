# -*- coding: utf-8 -*-
"""DST-safe timezone arithmetic for the platform.

All event timestamps in the platform are stored in UTC.  Computing the
employee's local civil date - the date a payroll cut-off would assign an
event to - is the single most error-prone operation in HR systems.

This service centralises that logic so it is correct in one place.
"""
from datetime import datetime, date as date_cls, time as time_cls
import pytz

from .base import HrService, register_service


@register_service('eh.hr.tz.service')
class TimezoneService(HrService):

    def employee_tz(self, employee):
        """Return a pytz tz for an employee, falling back to company / UTC."""
        tz_name = employee.tz or employee.company_id.partner_id.tz or 'UTC'
        try:
            return pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            return pytz.UTC

    def local_civil_date(self, employee, utc_dt: datetime) -> date_cls:
        """The civil date the event "belongs to" in the employee's locale.

        Note: an overnight shift may attribute a 02:00 local event to the
        previous civil date - that's a policy decision, applied above this
        service via ``shift.overnight_anchor`` (handled in ComputeService).
        Here we return the strict locale-local date.
        """
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=pytz.UTC)
        return utc_dt.astimezone(self.employee_tz(employee)).date()

    def day_window_utc(self, employee, civil_date: date_cls):
        """Return the (start_utc, end_utc) datetimes that bound the civil
        date for this employee.  Handles DST jumps where the day is
        23 or 25 hours long.
        """
        tz = self.employee_tz(employee)
        start_local = tz.localize(datetime.combine(civil_date, time_cls(0, 0)))
        end_local = tz.localize(datetime.combine(civil_date, time_cls(23, 59, 59)))
        return start_local.astimezone(pytz.UTC), end_local.astimezone(pytz.UTC)
