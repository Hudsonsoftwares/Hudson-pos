from odoo import models, api
from markupsafe import Markup

class IrQwebFieldMonetary(models.AbstractModel):
    _inherit = 'ir.qweb.field.monetary'

    @api.model
    def value_to_html(self, value, options):
        res = super(IrQwebFieldMonetary, self).value_to_html(value, options)
        if isinstance(value, (int, float)) and value < 0:
            return Markup(f'<span style="color: #dc3545 !important;" class="text-danger">{res}</span>')
        return res

    @api.model
    def record_to_html(self, record, field_name, options):
        res = super(IrQwebFieldMonetary, self).record_to_html(record, field_name, options)
        val = record[field_name]
        if isinstance(val, (int, float)) and val < 0:
            return Markup(f'<span style="color: #dc3545 !important;" class="text-danger">{res}</span>')
        return res


class IrQwebFieldFloat(models.AbstractModel):
    _inherit = 'ir.qweb.field.float'

    @api.model
    def value_to_html(self, value, options):
        res = super(IrQwebFieldFloat, self).value_to_html(value, options)
        if isinstance(value, (int, float)) and value < 0:
            return Markup(f'<span style="color: #dc3545 !important;" class="text-danger">{res}</span>')
        return res

    @api.model
    def record_to_html(self, record, field_name, options):
        res = super(IrQwebFieldFloat, self).record_to_html(record, field_name, options)
        val = record[field_name]
        if isinstance(val, (int, float)) and val < 0:
            return Markup(f'<span style="color: #dc3545 !important;" class="text-danger">{res}</span>')
        return res
