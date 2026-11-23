# -*- coding: utf-8 -*-
"""Drop the temporary column default added in pre-migrate."""


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = 'ir_ui_view' AND column_name = 'visibility'
    """)
    if cr.fetchone():
        cr.execute("UPDATE ir_ui_view SET visibility = 'public' WHERE visibility IS NULL")
        cr.execute("ALTER TABLE ir_ui_view ALTER COLUMN visibility DROP DEFAULT")
