from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    referral_background_image = fields.Binary(string='Referral Background Image')
