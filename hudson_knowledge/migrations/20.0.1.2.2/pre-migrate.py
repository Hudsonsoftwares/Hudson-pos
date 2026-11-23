# -*- coding: utf-8 -*-
"""Let new views be created while website's ir.ui.view fields are not loaded.

website adds ``ir.ui.view.visibility`` (required, default 'public'), so the
column is NOT NULL. hudson_knowledge does not depend on website and is loaded
before it during an upgrade: at that point the ORM does not know the field and
INSERTs new views without it -> NotNullViolation. A temporary column default
lets PostgreSQL fill it; post-migrate removes it again.
"""


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = 'ir_ui_view' AND column_name = 'visibility'
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE ir_ui_view ALTER COLUMN visibility SET DEFAULT 'public'")
