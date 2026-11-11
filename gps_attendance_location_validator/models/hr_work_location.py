from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from .utils import parse_coordinate


class HrWorkLocation(models.Model):
    _inherit = 'hr.work.location'

    attendance_latitude = fields.Char(string="Attendance Latitude", required=True, default="0.0")
    attendance_longitude = fields.Char(string="Attendance Longitude", required=True, default="0.0")
    attendance_radius_km = fields.Float(string="Allowed Radius (km)", default=0.2, required=True)

    @api.constrains('attendance_latitude', 'attendance_longitude')
    def _check_latitude_longitude(self):
        for record in self:
            try:
                parse_coordinate(record.attendance_latitude)
            except ValueError:
                raise ValidationError(
                    _("Invalid Latitude format: '%s'. Please input a valid decimal coordinate.") 
                    % record.attendance_latitude
                )
            
            try:
                parse_coordinate(record.attendance_longitude)
            except ValueError:
                raise ValidationError(
                    _("Invalid Longitude format: '%s'. Please input a valid decimal coordinate.") 
                    % record.attendance_longitude
                )