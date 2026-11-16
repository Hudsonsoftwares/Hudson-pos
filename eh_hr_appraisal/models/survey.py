from odoo import api, fields, models, _


class SurveySurvey(models.Model):
    _inherit = 'survey.survey'

    survey_type = fields.Selection(selection_add=[('appraisal', 'Appraisal')], ondelete={'appraisal': 'set default'})
    appraisal_feedback_count = fields.Integer(compute='_compute_appraisal_feedback_count')

    @api.depends_context('uid')
    def _compute_allowed_survey_types(self):
        super()._compute_allowed_survey_types()
        if self.env.user.has_group('eh_hr_appraisal.group_hr_appraisal_manager'):
            for survey in self:
                survey.allowed_survey_types = (survey.allowed_survey_types or []) + ['appraisal']

    def _compute_appraisal_feedback_count(self):
        data = self.env['survey.user_input'].sudo()._read_group(
            [('survey_id', 'in', self.ids), ('appraisal_id', '!=', False)], ['survey_id'], ['__count'])
        counts = {survey.id: count for survey, count in data}
        for survey in self:
            survey.appraisal_feedback_count = counts.get(survey.id, 0)

    def action_appraisal_feedbacks(self):
        """ Feedbacks button: every 360 feedback request sent with this survey. """
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('eh_hr_appraisal.action_hr_appraisal_feedback_inputs')
        action['domain'] = [('survey_id', '=', self.id), ('appraisal_id', '!=', False)]
        action['context'] = {'create': False}
        return action


class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

    appraisal_id = fields.Many2one('hr.appraisal', string="Appraisal", index='btree_not_null', ondelete='cascade')
    appraisal_employee_id = fields.Many2one(
        'hr.employee', string="Employee", index='btree_not_null', help="Colleague asked to give feedback.")
    appraised_employee_id = fields.Many2one(related='appraisal_id.employee_id', string="Appraised Employee")

    def action_appraisal_resend(self):
        """ Resend: reopen the Ask Feedback window for this colleague. """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Ask Feedback'),
            'res_model': 'hr.appraisal.ask.feedback',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_appraisal_id': self.appraisal_id.id,
                'default_employee_ids': self.appraisal_employee_id.ids,
                'default_survey_template_id': self.survey_id.id,
            },
        }
