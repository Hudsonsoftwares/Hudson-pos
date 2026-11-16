from odoo import fields, models, _


class HrAppraisalGoalTemplate(models.Model):
    _name = "hr.appraisal.goal.template"
    _description = "Goal Template"
    _order = "name, id"

    name = fields.Char("Name", required=True)
    parent_id = fields.Many2one(
        'hr.appraisal.goal.template', string="Parent Goal Template", index=True, ondelete='set null',
        help="You can define this goal to be part of another one")
    timing = fields.Integer("Usual Timing", default=0, help="Usual time needed to reach the goal, in months. "
                            "Used to compute the deadline when the goal is assigned.")
    skill_ids = fields.Many2many('hr.skill', string="Expected Skills",
                                 help="This goal is recommended to employees working towards these skills.")
    tag_ids = fields.Many2many('hr.appraisal.goal.tag', string="Tags")
    description = fields.Html("Description")
    sub_goal_ids = fields.One2many('hr.appraisal.goal.template', 'parent_id', string="Sub Goal Template")

    def action_select_employees(self):
        """ Library > Continue: choose the employees receiving the selected goals. """
        return {
            'name': _('Select Employees'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.appraisal.goal.assign',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_template_ids': self.ids},
        }
