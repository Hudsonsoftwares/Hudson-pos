from odoo import models, api, _
from odoo.exceptions import ValidationError
from math import radians, cos, sin, asin, sqrt
from .utils import parse_coordinate


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    def _haversine_distance_km(self, lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = [round(v, 7) for v in [lat1, lon1, lat2, lon2]]
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        return c * 6371

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record, vals in zip(records, vals_list):
            record._validate_check_in_location(vals)
        return records

    def write(self, vals):
        result = super().write(vals)
        if any(key in vals for key in ('check_out', 'out_latitude', 'out_longitude')):
            self._validate_check_out_location(vals)
        return result

    def _is_gps_validation_exempt(self):
        """Determine if GPS validation can be bypassed (e.g. backend HR/Admin manual entry, crons, biometric sync)."""
        ctx = self.env.context
        if ctx.get('disable_gps_validation') or ctx.get('biometric_punch_processing'):
            return True
        if self.env.su or self.env.is_admin():
            return True
        user = self.env.user
        if user.id == 1:
            return True
        if user.has_group('base.group_system') or user.has_group('base.group_erp_manager'):
            return True
        if user.has_group('hr_attendance.group_hr_attendance_user') or user.has_group('hr_attendance.group_hr_attendance_officer'):
            return True
        return False

    def _validate_check_in_location(self, vals):
        for record in self:
            if record.employee_id.allow_remote_checkin:
                continue

            in_lat = vals.get('in_latitude', record.in_latitude)
            in_lon = vals.get('in_longitude', record.in_longitude)

            if not in_lat or not in_lon:
                if self._is_gps_validation_exempt():
                    continue
                raise ValidationError(
                    _("Location permission is required to perform check-in. "
                      "Please enable location services in your browser.")
                )

            work_location = record.employee_id.work_location_id
            if not work_location:
                raise ValidationError(
                    _("Work Location is not configured for employee %s.") % record.employee_id.name
                )

            try:
                target_lat = parse_coordinate(work_location.attendance_latitude)
                target_lon = parse_coordinate(work_location.attendance_longitude)
            except (ValueError, TypeError):
                raise ValidationError(
                    _("Invalid latitude/longitude format in Work Location settings for %s.") % work_location.name
                )

            if target_lat == 0.0 and target_lon == 0.0:
                raise ValidationError(
                    _("Coordinates are not set for Work Location: %s.") % work_location.name
                )

            radius = work_location.attendance_radius_km
            distance = self._haversine_distance_km(target_lat, target_lon, float(in_lat), float(in_lon))

            if distance > radius:
                raise ValidationError(
                    _("Check-in location is outside the allowed radius.\n"
                      "Distance: %.3f km | Allowed: %.3f km\n") % (distance, radius)
                )

    def _validate_check_out_location(self, vals):
        for record in self:
            if not record.check_out:
                continue

            # Auto check-out by cron/system is always exempt
            if vals.get('out_mode') == 'auto_check_out' or record.out_mode == 'auto_check_out':
                continue

            if record.employee_id.allow_remote_checkin:
                continue

            out_lat = vals.get('out_latitude', record.out_latitude)
            out_lon = vals.get('out_longitude', record.out_longitude)

            if not out_lat or not out_lon:
                if self._is_gps_validation_exempt():
                    continue
                raise ValidationError(
                    _("Location permission is required to perform check-out. "
                      "Please enable location services in your browser.")
                )

            work_location = record.employee_id.work_location_id
            if not work_location:
                raise ValidationError(
                    _("Work Location is not configured for employee %s.") % record.employee_id.name
                )

            try:
                target_lat = parse_coordinate(work_location.attendance_latitude)
                target_lon = parse_coordinate(work_location.attendance_longitude)
            except (ValueError, TypeError):
                raise ValidationError(
                    _("Invalid latitude/longitude format in Work Location settings for %s.") % work_location.name
                )

            if target_lat == 0.0 and target_lon == 0.0:
                raise ValidationError(
                    _("Coordinates are not set for Work Location: %s.") % work_location.name
                )

            radius = work_location.attendance_radius_km
            distance = self._haversine_distance_km(target_lat, target_lon, float(out_lat), float(out_lon))

            if distance > radius:
                raise ValidationError(
                    _("Check-out location is outside the allowed radius.\n"
                      "Distance: %.3f km | Allowed: %.3f km\n") % (distance, radius)
                )
