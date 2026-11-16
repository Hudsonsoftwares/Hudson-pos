from odoo import models, fields

class ReferralRewardLog(models.Model):
    _name = 'eh.hr.referral.reward.log'
    _description = 'Referral Reward Log'

    employee_id = fields.Many2one('hr.employee', string='Rewarded Employees', required=True)
    reward_id = fields.Many2one('eh.hr.referral.reward', string='Reward', required=True)
    points = fields.Integer(string='Points', related='reward_id.cost', store=True)
