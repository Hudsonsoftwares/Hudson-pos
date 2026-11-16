from odoo import models, fields, api

class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    ref_user_id = fields.Many2one('res.users', string='Referred By User', tracking=True)
    friend_id = fields.Many2one('eh.hr.referral.friend', string='Referral Avatar', tracking=True)

    @api.model
    def website_form_input_filter(self, request, values):
        values = super().website_form_input_filter(request, values)
        token = request.session.get('eh_referral_token')
        if token:
            employee = self.env['hr.employee'].sudo().search([('referral_token', '=', token)], limit=1)
            if employee and employee.user_id:
                values['ref_user_id'] = employee.user_id.id
        return values

    def _award_referral_points(self):
        for record in self:
            if record.ref_user_id and record.stage_id:
                points_to_award = record.stage_id.points
                if not points_to_award and getattr(record.stage_id, 'hired_stage', False):
                    points_to_award = 100
                elif not points_to_award and record.stage_id.name and record.stage_id.name.lower() == 'hired':
                    points_to_award = 100
                    
                if points_to_award > 0:
                    # Check for duplicates to prevent awarding points multiple times for the same stage
                    existing = self.env['eh.hr.referral.points'].sudo().search([
                        ('applicant_id', '=', record.id),
                        ('stage_id', '=', record.stage_id.id),
                    ])
                    if not existing:
                        self.env['eh.hr.referral.points'].sudo().create({
                            'user_id': record.ref_user_id.id,
                            'points': points_to_award,
                            'company_id': record.company_id.id or self.env.company.id,
                            'applicant_id': record.id,
                            'stage_id': record.stage_id.id,
                        })

    @api.model_create_multi
    def create(self, vals_list):
        applicants = super().create(vals_list)
        applicants._award_referral_points()
        return applicants

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' in vals:
            self._award_referral_points()
        return res
