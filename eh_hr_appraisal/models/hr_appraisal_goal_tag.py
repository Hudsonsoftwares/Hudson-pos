from odoo import models, fields

class HrAppraisalGoalTag(models.Model):
    _name = "hr.appraisal.goal.tag"
    _description = "Goal Tag"

    name = fields.Char("Name", required=True)
    color = fields.Integer("Color")
