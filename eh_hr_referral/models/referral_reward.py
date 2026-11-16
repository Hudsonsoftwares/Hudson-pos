from odoo import models, fields

class ReferralReward(models.Model):
    _name = 'eh.hr.referral.reward'
    _description = 'Referral Reward'

    name = fields.Char(string='Product Name', required=True)
    cost = fields.Integer(string='Cost (Points)', required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    gift_responsible_id = fields.Many2one('res.users', string='Gift Responsible')
    image_1920 = fields.Binary(string='Image')
    description = fields.Html(string='Description')
    user_points = fields.Integer(string='User Points', compute='_compute_user_points')
    points_missing = fields.Integer(string='Points Missing', compute='_compute_user_points')

    def _compute_user_points(self):
        for record in self:
            employee = self.env['hr.employee'].sudo().search([('user_id', '=', self.env.user.id)], limit=1)
            total_points = sum(self.env['eh.hr.referral.points'].sudo().search([('user_id', '=', self.env.user.id)]).mapped('points'))
            spent_points = sum(self.env['eh.hr.referral.reward.log'].sudo().search([('employee_id', '=', employee.id)]).mapped('points')) if employee else 0
            to_spend = total_points - spent_points
            
            record.user_points = to_spend
            record.points_missing = record.cost - to_spend if record.cost > to_spend else 0

    def action_dummy(self):
        return True

    def action_buy_reward(self):
        self.ensure_one()
        employee = self.env['hr.employee'].search([('user_id', '=', self.env.user.id)], limit=1)
        if not employee:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'Error', 'message': 'You must be linked to an employee to buy rewards.', 'type': 'danger', 'sticky': False}
            }
            
        if self.points_missing > 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'Error', 'message': 'Not enough points!', 'type': 'danger', 'sticky': False}
            }
            
        self.env['eh.hr.referral.reward.log'].create({
            'employee_id': employee.id,
            'reward_id': self.id,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success', 
                'message': 'Reward successfully purchased!', 
                'type': 'success', 
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'}
            }
        }
