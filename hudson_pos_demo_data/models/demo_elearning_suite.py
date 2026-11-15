# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions eLearning demo data.

Loads, for the installed apps only:
  * demo/elearning_demo.xml       (website_slides)        courses, sections, articles, infographics,
                                                           videos, quizzes, tags and enrolled learners
  * demo/elearning_cert_demo.xml  (website_slides_survey) scored certification exam + certification lesson
  * demo/elearning_paid_demo.xml  (website_sale_slides)   paid course sold through the website shop
"""
import logging

from odoo.tools import convert_file

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'


def _installed(env, name):
    return bool(env['ir.module.module'].sudo().search_count([('name', '=', name), ('state', '=', 'installed')]))


def _load(env, xml_file):
    try:
        with env.cr.savepoint():
            convert_file(env, MODULE, xml_file, idref={}, mode='init', noupdate=True)
        _logger.info("Hudson POS: loaded eLearning demo file %s", xml_file)
        return True
    except Exception as e:
        _logger.error("Hudson POS: failed to load eLearning demo file %s: %s", xml_file, e)
        return False


def load_elearning_suite_demo_data(env):
    if 'slide.channel' not in env:
        _logger.info("Hudson POS: website_slides not installed, skipping eLearning demo data.")
        return
    if not _load(env, 'demo/elearning_demo.xml'):
        return
    if _installed(env, 'website_slides_survey'):
        _load(env, 'demo/elearning_cert_demo.xml')
    if _installed(env, 'website_sale_slides'):
        _load(env, 'demo/elearning_paid_demo.xml')
    # demo courses are always visible on /slides
    channels = env['slide.channel'].sudo().search([('id', 'in', [
        r.res_id for r in env['ir.model.data'].sudo().search([('module', '=', MODULE), ('model', '=', 'slide.channel')])
    ])])
    channels.filtered(lambda c: not c.is_published).write({'is_published': True})
    _set_learner_progress(env)


# learner xmlid, course xmlid, number of lessons completed (in course order)
LEARNER_PROGRESS = [
    ('rc_learner_anu', 'slide_channel_kerala_cuisine', 99),   # all lessons -> course completed + karma
    ('rc_learner_rahul', 'slide_channel_kerala_cuisine', 4),
    ('rc_learner_sana', 'slide_channel_barista_coffee', 2),
    ('rc_learner_anu', 'slide_channel_food_safety', 2),
]


def _set_learner_progress(env):
    """Mark real lessons as completed so Odoo computes completion %, status and karma itself."""
    SlidePartner = env['slide.slide.partner'].sudo()
    for partner_xid, channel_xid, count in LEARNER_PROGRESS:
        partner = env.ref(f'{MODULE}.{partner_xid}', raise_if_not_found=False)
        channel = env.ref(f'{MODULE}.{channel_xid}', raise_if_not_found=False)
        if not partner or not channel:
            continue
        slides = channel.slide_ids.filtered(lambda s: not s.is_category and s.is_published).sorted('sequence')[:count]
        done = SlidePartner.search([('partner_id', '=', partner.id), ('slide_id', 'in', slides.ids)]).slide_id
        todo = slides - done
        if todo:
            SlidePartner.create([{
                'slide_id': slide.id,
                'partner_id': partner.id,
                'completed': True,
                'quiz_attempts_count': 1 if slide.slide_category == 'quiz' else 0,
            } for slide in todo])
