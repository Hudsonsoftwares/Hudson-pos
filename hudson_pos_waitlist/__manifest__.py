# -*- coding: utf-8 -*-
{
    'name': 'Hudson POS Waitlist - QR Self Join',
    'version': '20.0.1.11.0',
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
- Guests see their own estimated wait as a range (the queue position is never shown to guests).

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

Phase 6 - Review fixes
- QR join creates or reuses the res.partner customer (same mobile number) and links it;
  "Seat and Open Table" puts that customer on the new order.
- Name (letters and spaces) and phone number validated on the phone and on the server.
  Any country: country picker next to the number, validated with the phonenumbers rules of
  that country (Indian numbers: 10-digit mobile starting 7/8/9). Stored in international form.
- Sound & vibration On/Off switch on the status page, remembered on the phone.
- Tracking ends at Seated: the status page shows the final state (with the table) and stops;
  Track My Waitlist and Find My Place only ever return a waiting entry.
- "Anything we should know" free-text note, shown to the host and used as a table hint.
- Maximum party size per POS (0 = largest floor's total seats), same rule on phone and server.
- Parties larger than one table: suggested same-floor table combinations, host multi-select,
  tables merged under one main table with the standard POS table merge.
- Floors / tables always read live from the POS floor plan; suggestions ranked by party
  size, availability, preferred floor (only when suitable), sharing, then notes / tags.

Phase 7 - Dynamic waiting time
- Each guest's estimate replays the live queue against the POS's own table state (draft order =
  occupied; the standard payment flow frees the table): free / suitable tables, party size,
  table combinations for large parties, preferred floor and sharing when suitable, guests ahead.
- Busy tables free up, longest-occupied first, at the recent Waiting -> Seated pace (median
  gap, rolling window); the POS Average Waiting Time is the baseline / fallback. Never
  position x minutes. When recent guests actually waited (seated - joined) longer than they
  were quoted, estimates are stretched (never shortened, capped).
- Shown as a conservative range (~0-5, ~5-10, ~10-15, ~15-20, ~20-30, 30+ min) on the guest
  page, the POS and the backend list / form, all from the same server method; recomputed on
  every read, and POS / backend screens refresh when an order opens / is paid on a table or a
  table changes.

Phase 8 - Closed visits, customers, shared tables
- A Seated / Left / Cancelled / No Show visit is never reused: its tracking cookie is dropped,
  its status JSON answers 410 (polling stops), its page stays final and links back to the QR
  join form; joining again is a new entry.
- Table release is Odoo's own: a table is taken while it has a draft order; paying it (POS
  validation) releases it and un-merges combined tables. The waitlist only reads that state.
- One res.partner per mobile number and company, also under concurrent joins (per-number lock).
- Guests sharing a table each get their own POS order (uuid issued at seating, kept separate
  from the table's other orders at sync): separate bills, paid independently.
- A private waitlist seating keeps its whole table; shareable seatings report the remaining seats.
    """,
    'author': 'Hudson Group',
    'website': 'https://hudsongrouponline.com',
    'license': 'LGPL-3',
    'external_dependencies': {'python': ['phonenumbers']},
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
