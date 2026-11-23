# -*- coding: utf-8 -*-
{
    'name': 'Hudson POS Waitlist - QR Self Join',
    'version': '20.0.1.8.0',
    'category': 'Point of Sale',
    'summary': 'QR Self Join: guests join the restaurant waitlist from their phone and track their place',
    'description': """
Hudson POS Waitlist - QR Self Join
==================================
Phase 1 - QR access
- "Enable QR Self Join" checkbox per POS (Settings page and POS form).
- Read-only QR Join URL built from Odoo's web.base.url + a permanent random POS token
  (no database name, internal IDs or hard-coded hosts).
- Generate / Download / Print the QR code. Regenerating never changes the token.
- Public route /waitlist/join/<token> (multi-database resolution via hudson_kitchen_display).

Phase 2 - Join Waitlist + Track My Waitlist
- Mobile Join Waitlist form (name, phone, party size, seating, table sharing, tags).
- Server-side validation; restaurant/POS taken from the QR token only.
- pos.waitlist.entry with a daily per-POS queue number (W-001...) that is concurrency-safe.
- One waiting entry per POS and phone: repeated joins recover it. Once the visit is closed
  (seated, cancelled, left, no show) the same phone can join again as a new visit.
- Random access token -> /waitlist/s/<access_token> status page (position, estimated wait, state).
- waitlist_created / waitlist_updated events on the POS bus channel.

Phase 3 - Find My Place
- "Already on the waitlist? Find My Place" on the join form: phone lookup recovers the
  guest's waiting entry for this POS on a new phone/browser, re-sets the
  tracking cookie and opens the existing status page. Rate limited per IP.
- Guests see one Estimated Average Wait: the POS's Average Waiting Time (never position x minutes;
  the queue position is never shown to guests).

Phase 4 - POS Waitlist screen
- "Waitlist" button with a live active-count badge in the POS top bar.
- Waitlist panel (a dialog: never leaves the current screen) with the waiting guests.
- Status flow: Waiting -> Seated; closed states Cancelled, Left, No Show.
- Host actions on a waiting guest: Seat Guest, Cancel, Mark Left, Mark No Show.
- Transitions are validated server-side with a row lock; between two terminals the first wins.
- Every POS of the config refreshes over the bus; the guest status page follows on its next poll.

Phase 5 - Seat at a table
- Seat Guest opens a picker of the POS's own floors and tables, matched to the guest
  (preferred floor, party size, table sharing, availability). The host picks the table.
- The server re-checks the guest (still waiting) and the table (free) under row locks.
- Two terminals can never seat two guests at the same table; the loser picks again.
- The table is stored on the entry; "Seat and Open Table" continues in the normal order flow.
    """,
    'author': 'Hudson Group',
    'website': 'https://hudsongrouponline.com',
    'license': 'LGPL-3',
    'depends': [
        'point_of_sale',
        'pos_restaurant',
        'web',
    ],
    'data': [
        'security/ir.access.csv',
        'data/pos_waitlist_tag_data.xml',
        'views/pos_config_views.xml',
        'views/res_config_settings_views.xml',
        'views/pos_waitlist_entry_views.xml',
        'views/waitlist_templates.xml',
        'views/waitlist_qr_report.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'hudson_pos_waitlist/static/src/pos/waitlist.scss',
            'hudson_pos_waitlist/static/src/pos/waitlist_store.js',
            'hudson_pos_waitlist/static/src/pos/waitlist_table_picker.js',
            'hudson_pos_waitlist/static/src/pos/waitlist_panel.js',
            'hudson_pos_waitlist/static/src/pos/waitlist_panel.xml',
            'hudson_pos_waitlist/static/src/pos/navbar_patch.js',
        ],
        # Backend Waitlist menu: list / form reload live when the POS or a guest changes an entry.
        'web.assets_backend': [
            'hudson_pos_waitlist/static/src/backend/waitlist_live_views.js',
        ],
        'web.assets_tests': [
            'hudson_pos_waitlist/static/tests/tours/**/*',
        ],
    },
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
