import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class BaseGeocoder(models.AbstractModel):
    _inherit = 'base.geocoder'

    @api.model
    def _call_openstreetmap_reverse(self, lat, lon):
        try:
            return super()._call_openstreetmap_reverse(lat, lon)
        except Exception as e:
            _logger.warning("Geocoding service unavailable: %s", e)
            return None
