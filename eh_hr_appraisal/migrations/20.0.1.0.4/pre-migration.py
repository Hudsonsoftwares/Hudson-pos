def migrate(cr, version):
    if not version:
        return
    # The appraisal record rules used to be loaded as noupdate, which froze them
    # in installed databases. Release them so the corrected rules are applied.
    cr.execute("""
        UPDATE ir_model_data
        SET noupdate = False
        WHERE module = 'eh_hr_appraisal'
        AND name IN (
            'hr_appraisal_rule_user', 'hr_appraisal_goal_rule_user',
            'hr_appraisal_rule_manager', 'hr_appraisal_goal_rule_manager',
            'hr_appraisal_rule_admin', 'hr_appraisal_goal_rule_admin'
        );
    """)
