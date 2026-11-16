from odoo import models, fields

class ReferralFriend(models.Model):
    _name = 'eh.hr.referral.friend'
    _description = 'Referral Friend'
    _order = 'id'

    name = fields.Char(string='Friend Name', required=True, help="e.g. Hero, Adventurer, Spacewoman, Dog, Batman")
    position = fields.Selection([
        ('front', 'Front'),
        ('back', 'Back')
    ], string='Position', default='back', required=True)
    image = fields.Binary(string='Dashboard Image', required=True)
    image_head = fields.Binary(string='Avatar Image', required=True)
