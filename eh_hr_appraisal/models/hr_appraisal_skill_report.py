from odoo import fields, models, tools


class HrAppraisalSkillReport(models.Model):
    """ Appraisal Skills Report (Reporting > Skills Evolution).

    Only completed appraisals are reported. The first completed appraisal of an
    employee shows all their skills, the following ones only the skills whose
    level changed since the previous appraisal.
    """
    _name = "hr.appraisal.skill.report"
    _description = "Appraisal Skills Report"
    _auto = False
    _order = "date desc, employee_id, skill_type_id, skill_id"

    appraisal_id = fields.Many2one('hr.appraisal', string="Appraisal", readonly=True)
    employee_id = fields.Many2one('hr.employee', string="Employee", readonly=True)
    department_id = fields.Many2one('hr.department', string="Department", readonly=True)
    company_id = fields.Many2one('res.company', string="Company", readonly=True)
    date = fields.Date(string="Create Date", readonly=True)
    skill_type_id = fields.Many2one('hr.skill.type', string="Skill Type", readonly=True)
    skill_id = fields.Many2one('hr.skill', string="Skill", readonly=True)
    skill_level_id = fields.Many2one('hr.skill.level', string="Current Level", readonly=True)
    previous_level_progress = fields.Integer(string="Previous Progress", readonly=True, aggregator='avg')
    current_level_progress = fields.Integer(string="Current Progress", readonly=True, aggregator='avg')
    justification = fields.Char(string="Justification", readonly=True)
    evolution = fields.Selection([
        ('improvement', 'Improvement'),
        ('same', 'Unchanged'),
        ('regression', 'Regression'),
    ], string="Evolution", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    s.id AS id,
                    a.id AS appraisal_id,
                    a.employee_id AS employee_id,
                    a.department_id AS department_id,
                    a.company_id AS company_id,
                    COALESCE(a.date_done, a.date_appraisal) AS date,
                    s.skill_type_id AS skill_type_id,
                    s.skill_id AS skill_id,
                    s.skill_level_id AS skill_level_id,
                    COALESCE(s.previous_level_progress, 0) AS previous_level_progress,
                    COALESCE(s.level_progress, 0) AS current_level_progress,
                    s.justification AS justification,
                    CASE
                        WHEN s.previous_skill_level_id IS NULL OR COALESCE(s.level_progress, 0) > COALESCE(s.previous_level_progress, 0) THEN 'improvement'
                        WHEN COALESCE(s.level_progress, 0) < COALESCE(s.previous_level_progress, 0) THEN 'regression'
                        ELSE 'same'
                    END AS evolution
                FROM hr_appraisal_skill s
                JOIN hr_appraisal a ON a.id = s.appraisal_id
                WHERE a.state = 'done'
                  AND s.skill_level_id IS NOT NULL
                  AND (
                      s.previous_skill_level_id IS DISTINCT FROM s.skill_level_id
                      OR NOT EXISTS (
                          SELECT 1 FROM hr_appraisal prev
                          WHERE prev.employee_id = a.employee_id
                            AND prev.state = 'done'
                            AND prev.id != a.id
                            AND (COALESCE(prev.date_done, prev.date_appraisal), prev.id)
                                < (COALESCE(a.date_done, a.date_appraisal), a.id)
                      )
                  )
            )
        """)
