# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.


def migrate(cr, version):
    """Rentability is now driven by the periodicity (blank = "Not for Rent") instead of the
    "Can be Rented" checkbox. Periodicity used to default to "day" on every product, so clear
    it on products that were not rentable, and make sure rentable ones keep a periodicity."""
    cr.execute("""
        UPDATE product_template
           SET rental_periodicity = NULL
         WHERE is_rental IS NOT TRUE
           AND rental_periodicity IS NOT NULL
    """)
    cr.execute("""
        UPDATE product_template
           SET rental_periodicity = 'day'
         WHERE is_rental IS TRUE
           AND rental_periodicity IS NULL
    """)
