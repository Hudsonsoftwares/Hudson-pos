def migrate(cr, version):
    if not version:
        return
    # company_id is now related to the employee's company. Existing rows were
    # stamped with the creator's active company, so realign them.
    cr.execute("""
        UPDATE hr_appraisal a
        SET company_id = e.company_id
        FROM hr_employee e
        WHERE e.id = a.employee_id
        AND a.company_id IS DISTINCT FROM e.company_id;
    """)
    cr.execute("""
        UPDATE hr_appraisal_goal g
        SET company_id = e.company_id
        FROM hr_employee e
        WHERE e.id = g.employee_id
        AND g.company_id IS DISTINCT FROM e.company_id;
    """)
