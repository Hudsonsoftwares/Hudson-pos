# -*- coding: utf-8 -*-
"""1.6 -> 1.7: Seating Preference (Indoor / Outdoor / Any) became Preferred Floor / Area.

``floor_pref`` (selection) is replaced by ``preferred_floor_id`` (restaurant.floor, empty =
Any Floor). Existing entries keep loading:

* ``any``                -> Any Floor (empty)
* ``indoor`` / ``outdoor`` -> the entry's own POS floor whose name contains that word
                             (e.g. "Indoor Hall", "Outdoor Patio"), when exactly one exists;
                             otherwise Any Floor, so no guest is ever restricted to a floor
                             that the POS does not have.

The old column is dropped by Odoo afterwards, with the field.
"""


def migrate(cr, version):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'pos_waitlist_entry' AND column_name = 'floor_pref'
    """)
    if not cr.fetchone():
        return
    cr.execute("ALTER TABLE pos_waitlist_entry ADD COLUMN IF NOT EXISTS preferred_floor_id integer")

    # pos.config.floor_ids (pos_restaurant): many2many pos_config <-> restaurant_floor.
    cr.execute("""
        SELECT 1 FROM information_schema.tables WHERE table_name = 'pos_config_restaurant_floor_rel'
    """)
    if not cr.fetchone():
        return
    for word in ('indoor', 'outdoor'):
        cr.execute("""
            WITH candidates AS (
                SELECT e.id AS entry_id, min(f.id) AS floor_id, count(*) AS n
                  FROM pos_waitlist_entry e
                  JOIN pos_config_restaurant_floor_rel rel ON rel.pos_config_id = e.config_id
                  JOIN restaurant_floor f ON f.id = rel.restaurant_floor_id AND f.active
                 WHERE e.floor_pref = %(word)s
                   AND e.preferred_floor_id IS NULL
                   AND f.name ILIKE %(like)s
                 GROUP BY e.id
            )
            UPDATE pos_waitlist_entry e
               SET preferred_floor_id = c.floor_id
              FROM candidates c
             WHERE c.entry_id = e.id AND c.n = 1
        """, {'word': word, 'like': f'%{word}%'})
