from odoo import models, fields

class ReferralOnboarding(models.Model):
    _name = 'eh.hr.referral.onboarding'
    _description = 'Referral Onboarding'
    _order = 'sequence'

    name = fields.Char(string='Text', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    image = fields.Binary(string='Image', required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
