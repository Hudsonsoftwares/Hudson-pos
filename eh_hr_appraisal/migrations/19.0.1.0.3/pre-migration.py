def migrate(cr, version):
    if not version:
        return
    # Force the noupdate flag to False for the appraisal groups so that the XML changes
    # (removing category_id and adding privilege_id) are applied during the module upgrade.
    cr.execute("""
        UPDATE ir_model_data 
        SET noupdate = False 
        WHERE module = 'eh_hr_appraisal' 
        AND name IN ('group_hr_appraisal_user', 'group_hr_appraisal_manager', 'group_hr_appraisal_admin');
    """)
