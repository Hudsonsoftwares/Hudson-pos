from odoo import fields, models


class HrAppraisalScale(models.Model):
    _name = "hr.appraisal.scale"
    _description = "Evaluation Scale"
    _order = "sequence, id"

    name = fields.Char(string="Name", required=True, translate=True)
    sequence = fields.Integer(string="Sequence", default=10)
    company_id = fields.Many2one('res.company', string='Company')
