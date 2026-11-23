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
import time
from datetime import datetime

from odoo import api, models

from .demo_guard import protect_existing, run_start, set_param

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
STATE_PARAM = 'hudson_pos_demo_data.autoload_state'
QUEUE_PARAM = 'hudson_pos_demo_data.autoload_queue'
CRON_XMLID = 'hudson_pos_demo_data.ir_cron_load_demo_queue'
MAX_ATTEMPTS = 3          # a suite interrupted this many times (worker killed) is skipped
SUITE_TIME_MARGIN = 75    # seconds kept for the next suite before the cron run stops
MAX_RUN_SECONDS = 45      # outside a cron run (e.g. 'Run Manually'): stay below request limits

POS_CORE = '@pos_core'
# Point of Sale alone is enough (it brings Inventory). Floors/tables need POS Restaurant and the loyalty
# programs need Loyalty: when those are installed later, the POS core runs again and adds them.
POS_CORE_MODULES = ('point_of_sale',)

# (key, python module, function, requires, probes) - in loading order
SUITES = [
    ('company_setup', 'demo_company_setup_suite', 'load_company_setup_suite_demo_data',
     (), ('product.template', 'product.template/l10n_in_hsn_code', 'data_recycle.model', 'payment.provider',
          'pos.config', 'account.journal')),
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
    ('purchase_agreements', 'demo_purchase_agreements_suite', 'load_purchase_agreements_suite_demo_data',
     ('purchase.order',), ('purchase.requisition/requisition_type', 'purchase.order.group',
                           'purchase.order/purchase_group_id', 'stock.quant')),
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
    ('inventory_rules', 'demo_inventory_rules_suite', 'load_inventory_rules_suite_demo_data',
     ('stock.warehouse',), ('purchase.order',)),
    ('rental_subscription', 'demo_rental_subscription_suite', 'load_rental_subscription_suite_demo_data',
     ('sale.order',), ('rental.pricing', 'sale.order/is_rental_order', 'sale.subscription.plan',
                       'sale.order/is_subscription')),
    ('planning', 'demo_planning_suite', 'load_planning_suite_demo_data',
     ('fs.planning.slot',), ('hr.employee',)),
    ('project', 'demo_project_suite', 'load_project_suite_demo_data',
     ('project.project',), ('account.analytic.line/project_id', 'sale.order.line', 'hr.employee')),
    ('project_templates', 'demo_project_template_suite', 'load_project_template_suite_demo_data',
     ('project.project/is_template', 'product.template/project_template_id', 'sale.order'),
     ('sale.order.line/project_id', 'account.analytic.line/project_id', 'crm.lead', 'module:sale_timesheet')),
    ('fleet_lunch_expense', 'demo_fleet_lunch_expense_suite', 'load_fleet_lunch_expense_suite_demo_data',
     (), ('fleet.vehicle', 'lunch.order', 'hr.expense', 'maintenance.equipment/vehicle_id')),
    # after the fleet suite: batches use its vehicles; Stock Transport (stock_fleet) adds vehicle/driver/payload
    ('batch_transfer', 'demo_batch_transfer_suite', 'load_batch_transfer_suite_demo_data',
     ('stock.picking.batch', 'stock.warehouse'), ('fleet.vehicle', 'stock.picking.batch/vehicle_id',
                                                  'fleet.vehicle.model.category/weight_capacity', 'module:sale_stock')),
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
    ('field_service', 'demo_field_service_suite', 'load_field_service_suite_demo_data',
     ('field.service.order', 'fs.planning.slot'), ('account.analytic.line/project_id',)),
    ('visitor', 'demo_visitor_suite', 'load_visitor_suite_demo_data',
     ('eh.hr.visitor',), ()),
    ('referral', 'demo_referral_suite', 'load_referral_suite_demo_data',
     ('eh.hr.referral.alert', 'hr.applicant'), ()),
    ('appraisal', 'demo_appraisal_suite', 'load_appraisal_suite_demo_data',
     ('hr.appraisal',), ('calendar.event',)),
    ('sign', 'demo_sign_knowledge_suite', 'load_sign_suite_demo_data',
     ('hudson.sign.template', 'hudson.sign.template.role'), ()),
    ('knowledge', 'demo_sign_knowledge_suite', 'load_knowledge_suite_demo_data',
     ('knowledge.management.article/is_article_item',), ()),
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
    set_param(env, STATE_PARAM, json.dumps({'probes': sorted(probes)}))


def reset_state(env):
    """Forget what was loaded (module installed or uninstalled): the next run loads everything."""
    from .demo_xml import LOADED_PARAM
    env['ir.config_parameter'].sudo().search([('key', 'in', (STATE_PARAM, LOADED_PARAM, QUEUE_PARAM))]).unlink()


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


def _suites_to_run(env, force=False):
    """(present probes, last saved probes, keys of the suites to (re)load) in loading order."""
    present = available_probes(env)
    seen = None if force else _get_state(env)
    new = present if seen is None else present - seen
    to_run = []
    for key, _py_module, _func_name, requires, probes in suites():
        if not all(r in present for r in requires):
            continue
        # every suite builds on the POS core data (products, shops, floors) when it exists
        if seen is None or new & (set(requires) | set(probes) | {POS_CORE}):
            to_run.append(key)
    return present, seen, to_run


# --------------------------------------------------------------------------- queue
# The demo data is NOT loaded inside the install/upgrade request: loading every suite takes minutes
# (80-170 s on a small server), far beyond the request limits of a hosted server (limit_time_real,
# proxy timeouts). Those kill the worker -> 502 Bad Gateway, the install is rolled back and retried.
# Install/upgrade only queues the suites; the scheduled action "Hudson Demo Data: load queued demo
# suites" loads them in the background, one suite per committed transaction.
def _get_queue(env):
    env.cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", (QUEUE_PARAM,))
    row = env.cr.fetchone()
    try:
        queue = json.loads(row[0]) if row and row[0] else None
    except ValueError:
        queue = None
    if not isinstance(queue, dict) or not queue.get('suites'):
        return None
    queue.setdefault('attempts', {})
    return queue


def _save_queue(env, queue):
    value = json.dumps(queue) if queue and queue.get('suites') else False
    set_param(env, QUEUE_PARAM, value)


def _trigger_cron(env):
    cron = env.ref(CRON_XMLID, raise_if_not_found=False)
    if cron:
        cron.sudo()._trigger()


def enqueue_suites(env, keys, pos_config_ids=None):
    """Add suites to the background queue (kept in loading order) and wake the scheduled action up."""
    if not keys:
        return []
    queue = _get_queue(env) or {'suites': [], 'attempts': {}}
    start = run_start(env).isoformat()
    queue['run_start'] = min(queue.get('run_start') or start, start)
    if pos_config_ids:
        queue['pos_config_ids'] = sorted(set(queue.get('pos_config_ids') or []) | set(pos_config_ids))
    wanted = set(queue['suites']) | set(keys)
    queue['suites'] = [s[0] for s in suites() if s[0] in wanted]
    for key in keys:  # queued again: give it fresh attempts
        queue['attempts'].pop(key, None)
    _save_queue(env, queue)
    _trigger_cron(env)
    _logger.info("Hudson POS demo: queued for background loading: %s", ", ".join(queue['suites']))
    return list(keys)


def run_autoload(env, force=False, pos_config_ids=None):
    """Queue every demo suite that became loadable since the last run (all of them if ``force``).

    The suites are loaded in the background by the scheduled action (``load_queue``), never inside
    the current transaction, so installing/upgrading a module stays fast. Never raises.
    """
    try:
        present, seen, to_run = _suites_to_run(env, force=force)
        if to_run:
            enqueue_suites(env, to_run, pos_config_ids=pos_config_ids)
        if seen != present:
            save_state(env, present)
        return to_run
    except Exception as e:  # noqa: BLE001
        _logger.exception("Hudson POS demo: could not queue the demo data: %s", e)
        return []


def _execute_suite(env, key, start, pos_config_ids=None):
    entry = next((s for s in suites() if s[0] == key), None)
    if not entry:
        return
    _key, py_module, func_name, requires, _probes = entry
    if not all(_probe_available(env, r) for r in requires):  # app uninstalled meanwhile
        _logger.info("Hudson POS demo: suite '%s' skipped, its apps are no longer installed", key)
        return
    try:
        # never modify or delete records that existed before the install run (demo_guard.py)
        with env.cr.savepoint(), protect_existing(env, start=start):
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


def load_queue(env, cron=None):
    """Load the queued suites, committing after each one. Returns the number of suites left."""
    started = time.monotonic()
    while True:
        queue = _get_queue(env)
        if not queue:
            return 0
        key = queue['suites'][0]
        attempts = queue['attempts'].get(key, 0) + 1
        if attempts > MAX_ATTEMPTS:
            # the suite was interrupted (worker killed by a time/memory limit) too often: give up on it
            _logger.error("Hudson POS demo: suite '%s' did not finish in %s attempts, skipped",
                          key, MAX_ATTEMPTS)
            queue['suites'].pop(0)
            _save_queue(env, queue)
            env.cr.commit()
            continue
        # record the attempt first: if the worker is killed while loading, the next run knows it
        queue['attempts'][key] = attempts
        _save_queue(env, queue)
        env.cr.commit()

        start = datetime.fromisoformat(queue['run_start']) if queue.get('run_start') else None
        last_mail_id = _last_mail_id(env)
        _execute_suite(env, key, start, pos_config_ids=queue.get('pos_config_ids'))
        _purge_queued_mails(env, last_mail_id)

        queue = _get_queue(env) or queue
        if key in queue['suites']:
            queue['suites'].remove(key)
        queue['attempts'].pop(key, None)
        _save_queue(env, queue)
        remaining = len(queue['suites'])
        if cron is not None:
            time_left = cron._commit_progress(1, remaining=remaining)
        else:
            env.cr.commit()
            time_left = float('inf')
        if not remaining:
            _logger.info("Hudson POS demo: all queued demo suites loaded")
            return 0
        # keep a margin for the next suite; the scheduled action runs again right away for the rest
        if time_left < SUITE_TIME_MARGIN or time.monotonic() - started > MAX_RUN_SECONDS:
            return remaining


class HudsonPosDemoAutoloader(models.AbstractModel):
    _name = 'hudson.pos.demo.autoloader'
    _description = 'Hudson Demo Data Auto-loader'

    def _register_hook(self):
        super()._register_hook()
        try:
            seen = _get_state(self.env)
            present = available_probes(self.env)
            # If state was never saved, or new modules/probes became available, or modules were updated:
            is_module_update = bool(self.env.registry.updated_modules and MODULE in self.env.registry.updated_modules)
            if seen is None or bool(present - seen) or is_module_update:
                # only queues the suites: the scheduled action loads them, outside this request
                run_autoload(self.env, force=is_module_update)
            elif seen - present:
                save_state(self.env, seen & present)
            if _get_queue(self.env):  # left over by an interrupted run
                _trigger_cron(self.env)
        except Exception as e:  # noqa: BLE001
            _logger.exception("Hudson POS demo: auto-load failed: %s", e)

    @api.model
    def _cron_load_queue(self):
        """Scheduled action: load the queued demo suites in the background."""
        env = self.env(user=api.SUPERUSER_ID, su=True)
        cron = env['ir.cron'] if env.context.get('ir_cron_progress_id') else None
        remaining = load_queue(env, cron=cron)
        if remaining and cron is None:
            _trigger_cron(env)
