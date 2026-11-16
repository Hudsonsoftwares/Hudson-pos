from odoo import models, fields

class ReferralAlert(models.Model):
    _name = 'eh.hr.referral.alert'
    _description = 'Referral Alert'

    name = fields.Char(string='Alert', required=True)
    date_from = fields.Date(string='Date From')
    date_to = fields.Date(string='Date To')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    on_click = fields.Selection([
        ('not_clickable', 'Not Clickable'),
        ('all_jobs', 'Go to All Jobs'),
        ('url', 'Specify URL')
    ], string='On Click', default='not_clickable')
    url = fields.Char(string='URL')
