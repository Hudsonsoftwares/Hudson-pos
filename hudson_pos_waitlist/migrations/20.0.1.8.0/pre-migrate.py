# -*- coding: utf-8 -*-
"""1.7 -> 1.8: the ``called`` status is removed. Flow is now Waiting -> Seated.

* Entries still ``called`` go back to ``waiting`` (they were never seated): they keep their
  W-number, join time and table preferences, and appear again in the POS queue.
* The partial unique index "one active entry per phone" covered ('waiting', 'called'); it is
  dropped here and Odoo recreates it on ``state = 'waiting'`` only, so a closed visit
  (seated / cancelled / left / no show) never blocks the same phone from joining again.
"""


def migrate(cr, version):
    cr.execute("SELECT to_regclass('pos_waitlist_entry')")
    if not cr.fetchone()[0]:
        return
    cr.execute("UPDATE pos_waitlist_entry SET state = 'waiting', end_time = NULL WHERE state = 'called'")
    cr.execute("""
        SELECT indexname FROM pg_indexes
         WHERE tablename = 'pos_waitlist_entry' AND indexdef ILIKE '%called%'
    """)
    for (name,) in cr.fetchall():
        cr.execute(f'DROP INDEX IF EXISTS "{name}"')
