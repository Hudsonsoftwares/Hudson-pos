SCALES = {
    'hr_appraisal_scale_needs_improvement': ('Needs improvement', 10),
    'hr_appraisal_scale_meets_expectations': ('Meets expectations', 20),
    'hr_appraisal_scale_exceeds_expectations': ('Exceeds expectations', 30),
    'hr_appraisal_scale_strongly_exceeds_expectations': ('Strongly Exceeds Expectations', 40),
}


def _group_id(cr, name):
    cr.execute("SELECT res_id FROM ir_model_data WHERE module = 'eh_hr_appraisal' AND name = %s AND model = 'res.groups'", [name])
    row = cr.fetchone()
    return row and row[0]


def migrate(cr, version):
    if not version:
        return

    # Access levels move from User / Manager / Administrator to the standard
    #   No / Officer: Access all appraisals / Administrator.
    # The xmlids group_hr_appraisal_user and group_hr_appraisal_manager now hold
    # Officer and Administrator, group_hr_appraisal_admin disappears. Former
    # Users and Managers only reached their own team, which every internal
    # user now does: they fall back to "No". Administrators stay Administrators
    # (restored in post-migration).
    # The groups were loaded as noupdate in older versions: release them so the
    # new names apply and the obsolete Administrator group gets removed.
    cr.execute("""
        UPDATE ir_model_data SET noupdate = false
        WHERE module = 'eh_hr_appraisal'
          AND model IN ('res.groups', 'res.groups.privilege')
    """)

    admin_gid = _group_id(cr, 'group_hr_appraisal_admin')
    cr.execute("DROP TABLE IF EXISTS eh_hr_appraisal_mig_admins")
    cr.execute("CREATE TABLE eh_hr_appraisal_mig_admins (uid integer)")
    if admin_gid:
        cr.execute("INSERT INTO eh_hr_appraisal_mig_admins SELECT uid FROM res_groups_users_rel WHERE gid = %s", [admin_gid])
    old_gids = [gid for gid in (_group_id(cr, 'group_hr_appraisal_user'), _group_id(cr, 'group_hr_appraisal_manager'), admin_gid) if gid]
    if old_gids:
        cr.execute("DELETE FROM res_groups_users_rel WHERE gid = ANY(%s)", [old_gids])
        cr.execute("DELETE FROM res_groups_implied_rel WHERE gid = ANY(%s) OR hid = ANY(%s)", [old_gids, old_gids])

    # Bind the existing evaluation scale values to the new data records instead of duplicating them
    for xmlid, (name, sequence) in SCALES.items():
        cr.execute("SELECT 1 FROM ir_model_data WHERE module = 'eh_hr_appraisal' AND name = %s", [xmlid])
        if cr.fetchone():
            continue
        cr.execute("""
            SELECT s.id FROM hr_appraisal_scale s
            WHERE lower(s.name->>'en_US') = lower(%s)
              AND NOT EXISTS (SELECT 1 FROM ir_model_data d WHERE d.model = 'hr.appraisal.scale' AND d.res_id = s.id)
            ORDER BY s.id LIMIT 1
        """, [name])
        row = cr.fetchone()
        if row:
            cr.execute("""
                INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
                VALUES ('eh_hr_appraisal', %s, 'hr.appraisal.scale', %s, true)
            """, [xmlid, row[0]])
            cr.execute("UPDATE hr_appraisal_scale SET sequence = %s WHERE id = %s", [sequence, row[0]])
