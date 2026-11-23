# -*- coding: utf-8 -*-
"""1.0 -> 1.1: 'Enable Waitlist QR' became 'Enable QR Self Join'. Keep each POS's flag.

Tokens (waitlist_token) are kept as-is, so printed QR codes keep working.
The old base-URL / URL / welcome-message / QR-attachment fields are dropped by Odoo.
"""


def migrate(cr, version):
    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'pos_config'
           AND column_name IN ('waitlist_enabled', 'enable_qr_self_join')
    """)
    cols = {r[0] for r in cr.fetchall()}
    if 'waitlist_enabled' in cols and 'enable_qr_self_join' not in cols:
        cr.execute("ALTER TABLE pos_config RENAME COLUMN waitlist_enabled TO enable_qr_self_join")
