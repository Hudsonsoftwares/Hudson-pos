from odoo import models, fields

class Users(models.Model):
    _inherit = 'res.users'

    eh_referral_onboarding_completed = fields.Boolean(string="Referral Onboarding Completed", default=False)
