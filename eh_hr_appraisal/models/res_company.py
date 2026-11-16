from odoo import fields, models

PLAN_FIELDS = {'appraisal_plan', 'appraisal_plan_first_month', 'appraisal_plan_next_month', 'appraisal_plan_recurring_month'}


class ResCompany(models.Model):
    _inherit = 'res.company'

    appraisal_plan = fields.Boolean(string='Appraisals Plans', default=True)
    appraisal_plan_first_month = fields.Integer(string='First Appraisal (months)', default=6)
    appraisal_plan_next_month = fields.Integer(string='Second Appraisal (months)', default=6)
    appraisal_plan_recurring_month = fields.Integer(string='Recurring Appraisal (months)', default=12)
    appraisal_automation = fields.Boolean(string='Appraisals Automation', default=False)
    appraisal_360_feedback = fields.Boolean(string='360 Feedback', default=True)
    appraisal_survey_template_id = fields.Many2one(
        'survey.survey', string="360 Feedback Survey", domain=[('survey_type', '=', 'appraisal')])

    def write(self, vals):
        res = super().write(vals)
        if PLAN_FIELDS & set(vals):
            # Changing the plan updates every employee without a Next Appraisal Date
            employees = self.env['hr.employee'].sudo().search([
                ('company_id', 'in', self.filtered('appraisal_plan').ids),
                ('next_appraisal_date', '=', False),
            ])
            employees._set_next_appraisal_date_from_plan()
        return res
