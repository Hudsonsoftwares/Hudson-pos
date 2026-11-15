from odoo import fields, models
import random

class HudsonSignTemplateTag(models.Model):
    _name = "hudson.sign.template.tag"
    _description = "Sign Template Tag"

    def _get_default_color(self):
        return random.randint(1, 11)

    name = fields.Char('Tag Name', required=True)
    color = fields.Integer('Color Index', default=_get_default_color)
