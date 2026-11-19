# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.
"""Automatic, dependency-aware loading of the Hudson demo data.

The module depends only on ``base`` and is ``auto_install``, so it is installed with every new
database, whatever apps exist at that moment. Each demo *suite* declares:

  * ``requires`` - probes that must ALL be available before the suite can run at all, and
  * ``probes``   - optional probes the suite uses when available.

A probe is one of:
  * ``'model.name'``          - the model is in the registry,
  * ``'model.name/field'``    - the model exists and has that field,
  * ``'module:name'``         - the module is installed and loaded in the registry,
  * ``'@pos_core'``           - the core POS demo data (floors, products, POS shops...) is loadable.

The set of available probes is stored in ``ir.config_parameter`` after every run. Whenever the
registry is rebuilt after installing or upgrading modules (``_register_hook`` with
``registry.updated_modules``), the probes that became available since the last run are computed,
and every suite whose requirements are met and that uses one of those new probes is (re)loaded.
All suites are idempotent (records bound to xmlids or looked up by name), so re-running is safe.

Example: install this module on a database with only Contacts -> nothing to load. Install
Point of Sale later -> the core POS data and every suite using POS data load automatically.
Install Appraisals later -> the Appraisal suite loads automatically.
"""

import functools
import importlib
import json
import logging

from odoo import api, models

from .demo_guard import protect_existing

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
STATE_PARAM = 'hudson_pos_demo_data.autoload_state'

POS_CORE = '@pos_core'
# Point of Sale alone is enough (it brings Inventory). Floors/tables need POS Restaurant and the loyalty
# programs need Loyalty: when those are installed later, the POS core runs again and adds them.
POS_CORE_MODULES = ('point_of_sale',)

# (key, python module, function, requires, probes) - in loading order
SUITES = [
    ('pos_core', 'demo_data_loader', 'load_pos_core_demo_data',
     (POS_CORE,), ('module:pos_restaurant', 'module:pos_loyalty', 'module:loyalty', 'module:pos_sale',
                   'module:product_expiry', 'product.combo', 'pos.preset')),
    ('recruitment_jobs', 'demo_data_loader', 'load_recruitment_jobs_demo_data',
     ('hr.job/is_published',), ()),
    ('elearning', 'demo_elearning_suite', 'load_elearning_suite_demo_data',
     ('slide.channel',), ('module:website_slides_survey', 'module:website_sale_slides')),
    ('hr', 'demo_hr_suite', 'load_hr_suite_demo_data',
     ('hr.employee',), ('hr.version', 'hr.attendance', 'hr.leave', 'hr.payslip', 'hr.payslip.run',
                        'hr.expense', 'fleet.vehicle', 'lunch.order')),
    ('business', 'demo_business_suite', 'load_business_suite_demo_data',
     ('product.product',), ('crm.lead', 'sale.order', 'stock.quant', 'purchase.order', 'mrp.production',
                            'maintenance.request', 'event.event', 'survey.survey', 'project.project',
                            'account.analytic.line', 'hr.employee', 'repair.order', 'quality.team',
                            'appointment.booking', 'approval.request')),
    ('inventory', 'demo_inventory_suite', 'load_inventory_suite_demo_data',
     ('product.product', 'stock.quant'), ('mrp.bom', 'mrp.production', 'purchase.order',
                                          'stock.warehouse.orderpoint', 'stock.scrap.reason.tag')),
    ('crm', 'demo_crm_suite', 'load_crm_suite_demo_data',
     ('crm.lead',), ()),
    ('marketing', 'demo_marketing_suite', 'load_marketing_suite_demo_data',
     (), ('blog.post', 'event.event', 'event.event.ticket', 'event.track', 'mailing.mailing', 'module:mass_mailing_sms')),
    ('ecommerce', 'demo_ecommerce_suite', 'load_ecommerce_suite_demo_data',
     ('product.template/public_categ_ids',), ('stock.quant', 'pos.config')),
    ('sales', 'demo_sales_suite', 'load_sales_suite_demo_data',
     ('sale.order',), ('product.document', 'quotation.document', 'loyalty.program', 'delivery.carrier',
                       'crm.lead', 'sale.order.template/template_type')),
    ('purchase', 'demo_purchase_suite', 'load_purchase_suite_demo_data',
     ('purchase.order',), ('stock.quant',)),
    ('mrp', 'demo_mrp_suite', 'load_mrp_suite_demo_data',
     ('mrp.production',), ('hr.employee', 'mrp.workcenter.productivity')),
    ('quality_maintenance', 'demo_quality_maintenance_suite', 'load_quality_maintenance_suite_demo_data',
     (), ('quality.point', 'quality.tag', 'quality.reason', 'maintenance.equipment', 'hr.employee',
          'mrp.routing.workcenter')),
    ('inventory_features', 'demo_inventory_features_suite', 'load_inventory_features_suite_demo_data',
     ('stock.warehouse',), ('purchase.order', 'quality.point', 'uom.uom/package_type_id')),
    ('fefo', 'demo_fefo_suite', 'load_fefo_suite_demo_data',
     ('stock.warehouse', 'stock.lot/expiration_date'), ('purchase.order', 'product.supplierinfo',
                                                        'stock.scrap.reason.tag')),
    ('rental_subscription', 'demo_rental_subscription_suite', 'load_rental_subscription_suite_demo_data',
     ('sale.order',), ('rental.pricing', 'sale.order/is_rental_order', 'sale.subscription.plan',
                       'sale.order/is_subscription')),
    ('planning', 'demo_planning_suite', 'load_planning_suite_demo_data',
     ('fs.planning.slot',), ('hr.employee',)),
    ('project', 'demo_project_suite', 'load_project_suite_demo_data',
     ('project.project',), ('account.analytic.line/project_id', 'sale.order.line', 'hr.employee')),
    ('fleet_lunch_expense', 'demo_fleet_lunch_expense_suite', 'load_fleet_lunch_expense_suite_demo_data',
     (), ('fleet.vehicle', 'lunch.order', 'hr.expense', 'maintenance.equipment/vehicle_id')),
    ('approvals_plm', 'demo_approvals_plm_suite', 'load_approvals_plm_suite_demo_data',
     (), ('approval.request', 'mrp.eco')),
    ('helpdesk', 'demo_helpdesk_suite', 'load_helpdesk_suite_demo_data',
     ('helpdesk.management.ticket',), ('project.project', 'helpdesk.ticket.refund', 'helpdesk.ticket.coupon',
                                       'helpdesk.ticket.giftcard', 'slide.channel', 'crm.lead',
                                       'loyalty.program')),
    ('hr_people', 'demo_hr_people_suite', 'load_hr_people_suite_demo_data',
     ('hr.employee',), ('hr.skill', 'hr.leave', 'hr.attendance', 'hr.payroll.structure.type')),
    ('recruitment_payroll', 'demo_recruitment_payroll_suite', 'load_recruitment_payroll_suite_demo_data',
     (), ('hr.applicant', 'hr.payslip.run', 'hr.payroll.structure', 'calendar.event')),
    ('collaboration', 'demo_collaboration_suite', 'load_collaboration_suite_demo_data',
     (), ('dms.directory', 'im_livechat.channel', 'mail.canned.response', 'survey.survey',
          'gamification.challenge', 'crm.lead', 'calendar.event')),
    ('company_setup', 'demo_company_setup_suite', 'load_company_setup_suite_demo_data',
     ('product.template',), ('product.template/l10n_in_hsn_code', 'data_recycle.model', 'payment.provider',
                             'pos.config', 'account.journal')),
    ('field_service', 'demo_field_service_suite', 'load_field_service_suite_demo_data',
     ('field.service.order', 'fs.planning.slot'), ('account.analytic.line/project_id',)),
    ('visitor', 'demo_visitor_suite', 'load_visitor_suite_demo_data',
     ('eh.hr.visitor',), ()),
    ('referral', 'demo_referral_suite', 'load_referral_suite_demo_data',
     ('eh.hr.referral.alert', 'hr.applicant'), ()),
    ('appraisal', 'demo_appraisal_suite', 'load_appraisal_suite_demo_data',
     ('hr.appraisal',), ('calendar.event',)),
    ('appointment_venue', 'demo_appointment_venue_suite', 'load_appointment_venue_suite_demo_data',
     ('appointment.resource', 'appointment.booking'), ('restaurant.table', 'module:hudson_pos_booking')),
]

# Suites that load demo XML files: every model and field those files use is a probe too, so
# installing an app that adds a model/field used by a file (e.g. Event Tracks adds website_track
# on events) reloads that file and completes the existing records. (key -> (python module, constant))
XML_FILE_SOURCES = {
    'pos_core': ('demo_data_loader', 'DEMO_XML_FILES'),
    'recruitment_jobs': ('demo_data_loader', 'RECRUITMENT_XML_FILE'),
    'elearning': ('demo_elearning_suite', 'ELEARNING_XML_FILES'),
    'crm': ('demo_crm_suite', 'CRM_XML_FILES'),
    'marketing': ('demo_marketing_suite', 'MARKETING_XML_FILES'),
    'ecommerce': ('demo_ecommerce_suite', 'XML_FILE'),
}


def _xml_files(key):
    source = XML_FILE_SOURCES.get(key)
    if not source:
        return ()
    module = importlib.import_module(f'odoo.addons.{MODULE}.models.{source[0]}')
    files = getattr(module, source[1], ())
    if isinstance(files, str):
        return (files,)
    # MARKETING_XML_FILES holds (file, model, check) tuples
    return tuple(f[0] if isinstance(f, (tuple, list)) else f for f in files)


@functools.cache
def suites():
    """SUITES with the probes of their demo XML files added: (key, module, func, requires, probes)."""
    from .demo_xml import xml_probes
    result = []
    for key, py_module, func_name, requires, probes in SUITES:
        files = _xml_files(key)
        extra = xml_probes(*files) if files else ()
        result.append((key, py_module, func_name, tuple(requires), tuple(probes) + extra))
    return tuple(result)


@functools.cache
def all_probes():
    return tuple(sorted({POS_CORE} | {p for s in suites() for p in s[3] + s[4]}))


# --------------------------------------------------------------------------- probes
def _probe_available(env, probe):
    if probe == POS_CORE:
        return all(m in env.registry._init_modules for m in POS_CORE_MODULES)
    if probe.startswith('module:'):
        return probe[7:] in env.registry._init_modules
    model, _sep, field = probe.partition('/')
    if model not in env.registry:
        return False
    return not field or field in env[model]._fields


def available_probes(env):
    return {p for p in all_probes() if _probe_available(env, p)}


# --------------------------------------------------------------------------- state
def _get_state(env):
    """Return the probes available at the last run, or None if nothing was ever loaded."""
    env.cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", (STATE_PARAM,))
    row = env.cr.fetchone()
    if not row or not row[0]:
        return None
    try:
        return set(json.loads(row[0]).get('probes', []))
    except (ValueError, AttributeError):
        return None


def save_state(env, probes):
    env['ir.config_parameter'].sudo().set_param(STATE_PARAM, json.dumps({'probes': sorted(probes)}))


def reset_state(env):
    """Forget what was loaded (module installed or uninstalled): the next run loads everything."""
    from .demo_xml import LOADED_PARAM
    env['ir.config_parameter'].sudo().search([('key', 'in', (STATE_PARAM, LOADED_PARAM))]).unlink()


# --------------------------------------------------------------------------- runner
def _last_mail_id(env):
    if 'mail.mail' not in env.registry:
        return None
    env.cr.execute("SELECT COALESCE(MAX(id), 0) FROM mail_mail")
    return env.cr.fetchone()[0]


def _purge_queued_mails(env, last_mail_id):
    """Demo records trigger assignment/approval notifications; never e-mail them to real users."""
    if last_mail_id is None or 'mail.mail' not in env.registry:
        return
    try:
        with env.cr.savepoint():
            queued = env['mail.mail'].sudo().search([
                ('id', '>', last_mail_id), ('state', 'in', ('outgoing', 'exception')),
            ])
            if queued:
                _logger.info("Hudson POS demo: removing %s e-mails queued by the demo data load", len(queued))
                queued.unlink()
    except Exception as e:  # noqa: BLE001
        _logger.warning("Hudson POS demo: could not clean the demo e-mail queue: %s", e)


def run_autoload(env, force=False, pos_config_ids=None):
    """Load every demo suite that became loadable since the last run (all of them if ``force``).

    Never raises: each suite runs in its own savepoint and failures are only logged, so a demo
    problem can never block the installation of a module.
    """
    present = available_probes(env)
    seen = None if force else _get_state(env)
    new = present if seen is None else present - seen

    to_run = []
    for key, py_module, func_name, requires, probes in suites():
        if not all(r in present for r in requires):
            continue
        # every suite builds on the POS core data (products, shops, floors) when it exists
        if seen is None or new & (set(requires) | set(probes) | {POS_CORE}):
            to_run.append((key, py_module, func_name))

    if to_run:
        _logger.info("Hudson POS demo: newly available %s -> loading suites: %s",
                     sorted(new), ", ".join(k for k, _m, _f in to_run))
        last_mail_id = _last_mail_id(env)
        for key, py_module, func_name in to_run:
            try:
                # never modify or delete records that existed before this install run (demo_guard.py)
                with env.cr.savepoint(), protect_existing(env):
                    module = importlib.import_module(f'odoo.addons.{MODULE}.models.{py_module}')
                    func = getattr(module, func_name)
                    if key == 'pos_core':
                        func(env, pos_config_ids=pos_config_ids)
                    else:
                        func(env)
                    env.flush_all()
                _logger.info("Hudson POS demo: suite '%s' loaded", key)
            except Exception as e:  # noqa: BLE001
                _logger.exception("Hudson POS demo: suite '%s' failed: %s", key, e)
        _purge_queued_mails(env, last_mail_id)

    if seen != present:
        save_state(env, present)
    return [k for k, _m, _f in to_run]


class HudsonPosDemoAutoloader(models.AbstractModel):
    _name = 'hudson.pos.demo.autoloader'
    _description = 'Hudson Demo Data Auto-loader'

    def _register_hook(self):
        super()._register_hook()
        try:
            seen = _get_state(self.env)
            present = available_probes(self.env)
            # If state was never saved, or new modules/probes became available, or modules were updated:
            if seen is None or bool(present - seen) or self.env.registry.updated_modules:
                run_autoload(self.env)
            else:
                if seen is not None and (seen - present):
                    save_state(self.env, seen & present)
        except Exception as e:  # noqa: BLE001
            _logger.exception("Hudson POS demo: auto-load failed: %s", e)
