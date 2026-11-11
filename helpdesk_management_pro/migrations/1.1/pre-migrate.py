def migrate(cr, version):
    # The legacy knowledge link column only exists on databases that had it
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'helpdesk_management_team' AND column_name = 'article_id'
    """)
    if not cr.fetchone():
        return
    cr.execute("UPDATE helpdesk_management_team SET article_id = NULL")

    # Try to find and drop the constraint
    cr.execute("""
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'helpdesk_management_team'::regclass
        AND contype = 'f'
    """)
    constraints = cr.fetchall()
    for (conname,) in constraints:
        if 'article_id' in conname:
            cr.execute(f"ALTER TABLE helpdesk_management_team DROP CONSTRAINT {conname}")
