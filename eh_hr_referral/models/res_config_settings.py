from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    referral_background_image = fields.Binary(
        related='company_id.referral_background_image', 
        readonly=False, 
        string='Referral Background Image'
    )
