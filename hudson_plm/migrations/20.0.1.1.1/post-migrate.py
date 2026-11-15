# -*- coding: utf-8 -*-


def migrate(cr, version):
    # Give ECO types without a color the default red one so every overview card has its colored border
    cr.execute("UPDATE mrp_eco_type SET color = 1 WHERE color IS NULL OR color = 0")
