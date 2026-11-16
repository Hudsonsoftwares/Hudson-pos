from odoo import models, fields

class ReferralLevel(models.Model):
    _name = 'eh.hr.referral.level'
    _description = 'Referral Level'
    _order = 'points, id'

    name = fields.Char(string='Level Name', required=True)
    points = fields.Integer(string='Requirements', required=True, default=0, help="Points required to reach this level")
    image = fields.Binary(string='Image')
