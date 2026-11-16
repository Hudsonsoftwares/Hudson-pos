from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    appraisal_plan = fields.Boolean(related='company_id.appraisal_plan', readonly=False)
    appraisal_plan_first_month = fields.Integer(related='company_id.appraisal_plan_first_month', readonly=False)
    appraisal_plan_next_month = fields.Integer(related='company_id.appraisal_plan_next_month', readonly=False)
    appraisal_plan_recurring_month = fields.Integer(related='company_id.appraisal_plan_recurring_month', readonly=False)
    appraisal_automation = fields.Boolean(related='company_id.appraisal_automation', readonly=False)
    appraisal_360_feedback = fields.Boolean(related='company_id.appraisal_360_feedback', readonly=False)
    appraisal_survey_template_id = fields.Many2one(related='company_id.appraisal_survey_template_id', readonly=False)
