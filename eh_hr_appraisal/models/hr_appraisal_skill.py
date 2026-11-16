from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrAppraisalSkill(models.Model):
    """ Skill evaluated during an appraisal. Loaded from the employee (and the
    target job) on confirmation, written back to the employee once done. """
    _name = "hr.appraisal.skill"
    _description = "Appraisal Skill"
    _order = "skill_type_id, skill_id"

    appraisal_id = fields.Many2one('hr.appraisal', required=True, index=True, ondelete='cascade')
    employee_id = fields.Many2one(related='appraisal_id.employee_id', store=True, index=True)
    company_id = fields.Many2one(related='appraisal_id.company_id', store=True, index=True)
    skill_type_id = fields.Many2one('hr.skill.type', string="Skill Type", required=True, ondelete='cascade')
    skill_id = fields.Many2one(
        'hr.skill', string="Skill", required=True, ondelete='cascade', domain="[('skill_type_id', '=', skill_type_id)]")
    skill_level_id = fields.Many2one(
        'hr.skill.level', string="Skill Level", ondelete='restrict', domain="[('skill_type_id', '=', skill_type_id)]")
    level_progress = fields.Integer(string="Current", compute='_compute_level_progress', store=True)
    previous_skill_level_id = fields.Many2one('hr.skill.level', string="Previous Level", readonly=True)
    previous_level_progress = fields.Integer(string="Previous Progress", readonly=True)
    justification = fields.Char(string="Justification")
    job_skill_level_id = fields.Many2one('hr.skill.level', string="Job Target", compute='_compute_job_target')
    job_level_progress = fields.Integer(string="Job Target Progress", compute='_compute_job_target')

    _unique_skill = models.Constraint(
        'UNIQUE(appraisal_id, skill_id)', "A skill can only be evaluated once per appraisal.")

    @api.depends('skill_level_id.level_progress')
    def _compute_level_progress(self):
        for line in self:
            line.level_progress = line.skill_level_id.level_progress

    @api.depends('skill_id', 'appraisal_id.target_job_id')
    def _compute_job_target(self):
        for line in self:
            job_skill = line.appraisal_id.target_job_id.sudo().current_job_skill_ids.filtered(
                lambda s: s.skill_id == line.skill_id)[:1]
            line.job_skill_level_id = job_skill.skill_level_id
            line.job_level_progress = job_skill.skill_level_id.level_progress

    @api.onchange('skill_type_id')
    def _onchange_skill_type_id(self):
        if self.skill_id.skill_type_id != self.skill_type_id:
            self.skill_id = False
        if self.skill_level_id.skill_type_id != self.skill_type_id:
            levels = self.skill_type_id.skill_level_ids
            self.skill_level_id = levels.filtered('default_level')[:1] or levels[:1]

    def _check_appraisal_rights(self, appraisals):
        if self.env.su:
            return
        for appraisal in appraisals:
            if appraisal.state != 'ongoing':
                raise UserError(_("Skills can only be updated while the appraisal is confirmed."))
            if not (appraisal._is_appraiser() or appraisal._is_appraised_employee()):
                raise UserError(_("Only the employee and the appraisers can update the skills of this appraisal."))

    @api.model_create_multi
    def create(self, vals_list):
        appraisals = self.env['hr.appraisal'].browse({vals.get('appraisal_id') for vals in vals_list})
        self._check_appraisal_rights(appraisals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_appraisal_rights(self.appraisal_id)
        return super().write(vals)

    def unlink(self):
        self._check_appraisal_rights(self.appraisal_id)
        return super().unlink()
