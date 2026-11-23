# -*- coding: utf-8 -*-
"""Items are now child articles (Odoo Online style).

Copy the stage and dates of the legacy knowledge.management.item records onto
their linked child article so they appear in the new embedded Odoo views.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE knowledge_management_article art
           SET stage_id = item.stage_id,
               item_date_start = COALESCE(art.item_date_start, item.date::timestamp + interval '9 hours'),
               item_date_end = COALESCE(art.item_date_end,
                                        COALESCE(item.date_end, item.date)::timestamp + interval '10 hours'),
               is_article_item = TRUE
          FROM knowledge_management_item item
         WHERE item.child_article_id = art.id
           AND art.stage_id IS NULL
    """)
