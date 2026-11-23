# -*- coding: utf-8 -*-
"""-> 1.10: phone numbers of any country; matched on their international form.

``phone_normalized`` becomes country code + national number (E.164 without "+"), read with
the restaurant company's country for numbers typed without a country code, so Find My Place
and repeated joins keep finding existing entries. A waiting entry is left untouched when
another waiting entry of the same POS already has the new value (the partial unique index
would refuse it).
"""
from odoo.addons.hudson_pos_waitlist.models.pos_waitlist_entry import normalize_phone


def migrate(cr, version):
    cr.execute("""
        SELECT e.id, e.config_id, e.state, e.phone, country.code
          FROM pos_waitlist_entry e
          JOIN pos_config config ON config.id = e.config_id
          JOIN res_company company ON company.id = config.company_id
          JOIN res_partner partner ON partner.id = company.partner_id
     LEFT JOIN res_country country ON country.id = partner.country_id
         WHERE e.phone IS NOT NULL
    """)
    for entry_id, config_id, state, phone, country_code in cr.fetchall():
        value = normalize_phone(phone, country_code)
        if state == 'waiting':
            cr.execute("""
                SELECT 1 FROM pos_waitlist_entry
                 WHERE config_id = %s AND state = 'waiting' AND phone_normalized = %s AND id <> %s
            """, (config_id, value, entry_id))
            if cr.fetchone():
                continue
        cr.execute("UPDATE pos_waitlist_entry SET phone_normalized = %s WHERE id = %s", (value, entry_id))
