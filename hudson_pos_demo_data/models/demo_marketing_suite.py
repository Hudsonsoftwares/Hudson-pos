# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.
"""
Marketing Suite demo data for Resto Cafe Solutions: Blog, Events and Email Marketing.

- Blog: "From Our Kitchen" & "Café Culture & News" blogs, topic tags, published,
  scheduled and draft posts (recipes, coffee, festivals) with visit counts.
- Events: masterclasses, a 3-day Christmas Food & Wine Festival, kids' party, a past
  sold-out seafood night and a draft New Year's Eve gala - with event types, tags,
  ticket types & prices, registrations (confirmed / attended / cancelled), website pages
  and, when Event Tracks is installed, an agenda with talks, locations and a proposal.
- Email Marketing: mailing lists, subscribers (incl. an opt-out and a bounced address),
  sent campaigns with open/click/reply/bounce statistics, a scheduled and a draft
  mailing, UTM campaigns and - when SMS Marketing is installed - an SMS campaign.

Each app's file loads only when that app is installed, in its own savepoint. Every
record is owned by hudson_pos_demo_data, so Odoo removes it when the module is uninstalled.
"""

import logging

from odoo.tools import convert_file

_logger = logging.getLogger(__name__)

# (file, model that must exist, optional field check (model, field, selection value))
MARKETING_XML_FILES = [
    ('demo/marketing/blog_demo.xml', 'blog.post', None),
    ('demo/marketing/event_demo.xml', 'event.event.ticket', None),
    ('demo/marketing/event_track_demo.xml', 'event.track', None),
    ('demo/marketing/mass_mailing_demo.xml', 'mailing.mailing', None),
    ('demo/marketing/mass_mailing_sms_demo.xml', 'mailing.mailing', ('mailing.mailing', 'mailing_type', 'sms')),
]


def _is_available(env, model, selection_check):
    if model not in env:
        return False
    if selection_check:
        sel_model, field, value = selection_check
        selection = env[sel_model].fields_get([field]).get(field, {}).get('selection') or []
        return value in [key for key, _label in selection]
    return True


def load_marketing_suite_demo_data(env):
    """Load Blog / Events / Email Marketing demo data for the apps that are installed."""
    loaded = []
    for xml_file, model, selection_check in MARKETING_XML_FILES:
        if not _is_available(env, model, selection_check):
            _logger.info("Hudson Marketing Suite: skipping %s (app not installed)", xml_file)
            continue
        try:
            with env.cr.savepoint():
                convert_file(env, 'hudson_pos_demo_data', xml_file, idref={}, mode='init', noupdate=True)
            loaded.append(xml_file)
        except Exception:
            _logger.exception("Hudson Marketing Suite: could not load %s", xml_file)
    _logger.info("Hudson Marketing Suite: loaded %s", ", ".join(loaded) or "nothing")
    return loaded
