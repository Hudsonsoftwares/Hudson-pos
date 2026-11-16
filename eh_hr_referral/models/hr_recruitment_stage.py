from odoo import models, fields

class RecruitmentStage(models.Model):
    _inherit = 'hr.recruitment.stage'

    points = fields.Integer(string='Referral Points', default=0, help="Points awarded to the referrer when an applicant reaches this stage.")
