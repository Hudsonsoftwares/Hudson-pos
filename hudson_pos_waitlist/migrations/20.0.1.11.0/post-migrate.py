# -*- coding: utf-8 -*-
"""-> 1.11: one POS order per party at a shared table.

Before, a guest seated at a shared table was attached to the other party's open order
(``pos_order_id``). Those entries are flagged ``shared_seating`` so they keep following that
order until it is closed; new shared seatings get their own order.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE pos_waitlist_entry
           SET shared_seating = TRUE
         WHERE pos_order_id IS NOT NULL AND pos_order_uuid IS NULL
    """)
