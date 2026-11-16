from odoo import models, fields

class ReferralPoints(models.Model):
    _name = 'eh.hr.referral.points'
    _description = 'Referral Points'

    user_id = fields.Many2one('res.users', string='User', required=True)
    points = fields.Integer(string='Points', required=True, default=0)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    applicant_id = fields.Many2one('hr.applicant', string='Applicant')
    stage_id = fields.Many2one('hr.recruitment.stage', string='Stage')
