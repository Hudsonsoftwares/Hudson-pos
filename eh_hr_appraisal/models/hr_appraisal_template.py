from odoo import fields, models


class HrAppraisalTemplate(models.Model):
    _name = "hr.appraisal.template"
    _description = "Appraisal Template"
    _order = "id"

    name = fields.Char(string="Name", required=True, translate=True)
    company_id = fields.Many2one('res.company', string='Company')
    department_ids = fields.Many2many(
        'hr.department', string="Departments",
        help="Used by default for the employees of these departments. Leave empty to use it for everybody.")
    employee_feedback_template = fields.Html(string="Employee's Feedback")
    manager_feedback_template = fields.Html(string="Manager's Feedback")
