from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Former Administrators keep the Administrator level
    cr.execute("SELECT to_regclass('eh_hr_appraisal_mig_admins')")
    if cr.fetchone()[0]:
        cr.execute("SELECT DISTINCT uid FROM eh_hr_appraisal_mig_admins")
        uids = [row[0] for row in cr.fetchall()]
        if uids:
            admin_group = env.ref('eh_hr_appraisal.group_hr_appraisal_manager')
            env['res.users'].browse(uids).exists().write({'group_ids': [(4, admin_group.id)]})
        cr.execute("DROP TABLE eh_hr_appraisal_mig_admins")

    # Goal status is now derived from the progress
    goals = env['hr.appraisal.goal'].with_context(active_test=False).search([])
    goals._compute_state()

    # Department and job are now copied from the employee once, not mirrored
    appraisals = env['hr.appraisal'].with_context(active_test=False).search([])
    for appraisal in appraisals.filtered(lambda a: not a.department_id or not a.job_id):
        appraisal._compute_employee_data()

    # Every company starts with the default 360 feedback survey
    survey = env.ref('eh_hr_appraisal.survey_360_feedback', raise_if_not_found=False)
    if survey:
        env['res.company'].search([('appraisal_survey_template_id', '=', False)]).write(
            {'appraisal_survey_template_id': survey.id})
    env.flush_all()
