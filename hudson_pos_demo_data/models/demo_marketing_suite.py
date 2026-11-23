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

import json
import logging

from .demo_xml import load_demo_xml as convert_file  # tolerant of apps not installed

_logger = logging.getLogger(__name__)

# (file, model that must exist, optional field check (model, field, selection value))
MARKETING_XML_FILES = [
    ('demo/marketing/blog_demo.xml', 'blog.post', None),
    ('demo/marketing/event_demo.xml', 'event.event', None),
    ('demo/marketing/event_track_demo.xml', 'event.track', None),
    ('demo/marketing/mass_mailing_demo.xml', 'mailing.mailing', None),
    ('demo/marketing/mass_mailing_sms_demo.xml', 'mailing.mailing', ('mailing.mailing', 'mailing_type', 'sms')),
    ('demo/marketing/marketing_card_demo.xml', 'card.campaign', None),
]

TINY_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4'
    b'\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)


def _card_images_available():
    """True when card images can be rendered (wkhtmltoimage 0.12+ found by Odoo)."""
    try:
        from odoo.addons.base_report_wkhtmltox.models.ir_actions_report import _wkhtml  # noqa: PLC0415
        from odoo.tools import parse_version  # noqa: PLC0415
        version = _wkhtml().wkhtmltoimage_version
        return bool(version) and version >= parse_version('0.12.0')
    except Exception:  # noqa: BLE001
        return False


def _is_available(env, model, selection_check):
    if model not in env:
        return False
    if selection_check:
        sel_model, field, value = selection_check
        selection = env[sel_model].fields_get([field]).get(field, {}).get('selection') or []
        return value in [key for key, _label in selection]
    return True


def load_marketing_suite_demo_data(env):
    """Load Blog / Events / Email Marketing / Marketing Cards demo data for installed apps."""
    loaded = []
    
    # Safe fallback patch for card.campaign image generation if wkhtmltoimage is absent
    orig_get_image_bin = None
    if 'card.campaign' in env and not _card_images_available():
        orig_get_image_bin = getattr(env['card.campaign'].__class__, '_get_image_bin', None)
        env['card.campaign'].__class__._get_image_bin = lambda self, rec: TINY_PNG

    try:
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
                
        # Generate sample card.card records for event attendees
        if 'card.card' in env and 'card.campaign' in env:
            try:
                with env.cr.savepoint():
                    camp = env.ref('hudson_pos_demo_data.rc_card_campaign_xmas_fest', raise_if_not_found=False)
                    if not camp:
                        camp = env['card.campaign'].search([], limit=1)
                    if camp:
                        lang = (env.user.lang or env.company.partner_id.lang or 'en_US')
                        regs = env['event.registration'].search([], limit=5)
                        for r in regs:
                            if not env['card.card'].sudo().search_count([('campaign_id', '=', camp.id), ('res_id', '=', r.id)]):
                                env['card.card'].sudo().create({
                                    'campaign_id': camp.id,
                                    'res_id': r.id,
                                    'lang': lang,
                                })
                        _logger.info("Hudson Marketing Suite: created sample card.card records for campaign %s", camp.name)
            except Exception:
                _logger.exception("Hudson Marketing Suite: could not create sample card.card")

        # Multi-website availability: ensure blogs and events are accessible on all websites
        if 'event.event' in env:
            try:
                with env.cr.savepoint():
                    events = env['event.event'].sudo().search([('name', 'in', [
                        'Kerala Sadya Cooking Masterclass', 'Monsoon Seafood Night',
                        'Latte Art Workshop for Beginners', 'Christmas Food & Wine Festival',
                        'Sunday Kids\' Pizza Making Party',
                    ])])
                    events.write({'website_id': False, 'company_id': env.company.id, 'is_published': True})
            except Exception:
                _logger.exception("Hudson Marketing Suite: could not update event website bindings")

        if 'blog.post' in env:
            try:
                with env.cr.savepoint():
                    post_covers = {
                        'The Art of the Onam Sadya: 26 Dishes on a Banana Leaf': "url('/theme_bistro/static/src/img/configurator/set_catalog_landscape_lg_1.webp')",
                        'From Bean to Cup: How We Brew Our Filter Coffee': "url('/theme_bistro/static/src/img/backgrounds/06.webp')",
                        'Soft Appam & Chicken Stew: A Family Recipe': "url('/theme_bistro/static/src/img/configurator/landscape_xl_1.webp')",
                        '5 Healthy Lunch Bowls Under 500 Calories': "url('/theme_bistro/static/src/img/backgrounds/16.webp')",
                        'Latte Art for Beginners: The Heart, Tulip and Rosetta': "url('/theme_bistro/static/src/img/content/s_image_hexagonal_1.webp')",
                        "Christmas Plum Cake Mixing Ceremony: You're Invited": "url('/theme_bistro/static/src/img/backgrounds/09.webp')",
                        'Sneak Peek: Our New Monsoon Menu (Draft)': "url('/theme_bistro/static/src/img/backgrounds/15.webp')",
                    }
                    for name, img_url in post_covers.items():
                        post = env['blog.post'].sudo().search([('name', '=', name)], limit=1)
                        if post:
                            props = {
                                "background_color_class": "o_cc3",
                                "background-image": img_url,
                                "opacity": "0.2",
                                "resize_class": "o_half_screen_height",
                            }
                            post.write({'cover_properties': json.dumps(props), 'website_id': False})

                    posts = env['blog.post'].sudo().search([('name', 'in', [
                        'The Art of the Onam Sadya: 26 Dishes on a Banana Leaf',
                        'From Bean to Cup: How We Brew Our Filter Coffee',
                        'Soft Appam & Chicken Stew: A Family Recipe',
                        '5 Healthy Lunch Bowls Under 500 Calories',
                        'Latte Art for Beginners: The Heart, Tulip and Rosetta',
                    ])])
                    posts.write({'website_id': False, 'is_published': True})
                    if 'blog.blog' in env:
                        blogs = env['blog.blog'].sudo().search([('name', 'in', ['From Our Kitchen', 'Café Culture & News'])])
                        blogs.write({'website_id': False})
            except Exception:
                _logger.exception("Hudson Marketing Suite: could not update blog website bindings")

        # Ensure top menu links exist for every website
        if 'website.menu' in env and 'website' in env:
            try:
                with env.cr.savepoint():
                    for website in env['website'].sudo().search([]):
                        top_menu = env['website.menu'].sudo().search([('website_id', '=', website.id), ('parent_id', '=', False)], limit=1)
                        if not top_menu:
                            continue
                        if 'event.event' in env and not env['website.menu'].sudo().search_count([('website_id', '=', website.id), ('url', '=', '/event')]):
                            env['website.menu'].sudo().create({
                                'name': 'Events',
                                'url': '/event',
                                'parent_id': top_menu.id,
                                'website_id': website.id,
                                'sequence': 55,
                            })
                        if 'blog.post' in env and not env['website.menu'].sudo().search_count([('website_id', '=', website.id), ('url', '=', '/blog')]):
                            env['website.menu'].sudo().create({
                                'name': 'Blog',
                                'url': '/blog',
                                'parent_id': top_menu.id,
                                'website_id': website.id,
                                'sequence': 60,
                            })
            except Exception:
                _logger.exception("Hudson Marketing Suite: could not create website menus")
    finally:
        if orig_get_image_bin:
            env['card.campaign'].__class__._get_image_bin = orig_get_image_bin

    _logger.info("Hudson Marketing Suite: loaded %s", ", ".join(loaded) or "nothing")
    return loaded
