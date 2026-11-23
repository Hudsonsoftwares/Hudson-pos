# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
#
# 20.0.1.0.27: Comprehensive demo data autoloader migration:
# - SMS & Email Marketing: sent campaigns, cards, traces
# - Products/Variants: POS variant configurator support and variant generation
# - Quotation Templates: sale order templates and live counter sections
# - Company Documents: Report header & footer branding
# - Rental: Dynamic dates for dashboard tiles (Today, Pickups, Returns, Late, To Confirm, To Invoice)
# - Helpdesk: 4 teams & 25 demo tickets across all stages
# - Employees: Full cafe and kitchen staff across departments with skills and attendances
# - Payroll: Indian payroll structures, contracts, payslips, and runs

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _logger.info("Hudson POS demo: starting 20.0.1.0.27 migration...")

    # 1. Product variants & combos
    try:
        with cr.savepoint():
            from odoo.addons.hudson_pos_demo_data.models.demo_data_loader import (
                _configure_product_variants,
                _configure_combos,
            )
            _configure_product_variants(env)
            _configure_combos(env)
            env.flush_all()
    except Exception as e:
        _logger.exception("Hudson POS demo 20.0.1.0.27: variant configuration warning: %s", e)

    # 2. Company Documents Branding & B2C HSN
    try:
        with cr.savepoint():
            company = env.company.sudo()
            if not company.report_header:
                company.report_header = "Kerala flavours, made fresh every day | Authentic Arabian & Multicuisine"
            if not company.report_footer:
                company.report_footer = "Resto Cafe Solutions • 26th Mile Bridge, Kanjirappally, Kerala • Phone: +91 484 400 1234 • GSTIN: 32AAKCR7342M1Z5 • Email: hello@restocafe.example"
            if 'l10n_in_disable_b2c_hsn_reporting' in company._fields:
                company.l10n_in_disable_b2c_hsn_reporting = True
            env.flush_all()
    except Exception as e:
        _logger.exception("Hudson POS demo 20.0.1.0.27: company branding warning: %s", e)

    # 3. Run full demo suite autoloader with force=True
    try:
        with cr.savepoint():
            from odoo.addons.hudson_pos_demo_data.models.demo_autoloader import run_autoload
            run_autoload(env, force=True)
            env.flush_all()
        _logger.info("Hudson POS demo 20.0.1.0.27: full demo autoload completed.")
    except Exception as e:
        _logger.exception("Hudson POS demo 20.0.1.0.27: autoload warning: %s", e)

    # 4. Refresh Rental Dashboard dates
    try:
        with cr.savepoint():
            from odoo.addons.hudson_pos_demo_data.models.demo_rental_subscription_suite import (
                _refresh_rental_dashboard_dates,
            )
            _refresh_rental_dashboard_dates(env)
            env.flush_all()
    except Exception as e:
        _logger.exception("Hudson POS demo 20.0.1.0.27: rental refresh warning: %s", e)

    # 5. Fix any open POS order lines missing HSN
    try:
        with cr.savepoint():
            if 'pos.order.line' in env and 'l10n_in_hsn_code' in env['pos.order.line']._fields:
                missing_lines = env['pos.order.line'].search([('l10n_in_hsn_code', '=', False)])
                for pol in missing_lines:
                    pol.l10n_in_hsn_code = pol.product_id.l10n_in_hsn_code or '996331'
            env.flush_all()
    except Exception as e:
        _logger.exception("Hudson POS demo 20.0.1.0.27: HSN fix warning: %s", e)

    _logger.info("Hudson POS demo 20.0.1.0.27: migration finished successfully.")
