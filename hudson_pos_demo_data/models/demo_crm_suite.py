# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.
"""
CRM Suite demo data for Resto Cafe Solutions.

Covers every CRM feature with restaurant & cafe business content (Kochi):
- Leads (qualification) and Opportunities in every pipeline stage
- Won deals, Lost deals with lost reasons, priorities, expected & recurring revenue
- Scheduled activities (overdue, today, upcoming), email history with an attachment
- Tags (Catering, Wedding, Corporate Lunch...), UTM campaigns/mediums/sources
- "Catering & Events" sales team with the "Arjun Nair" salesperson, client companies & contacts
- Activity plans: enquiry follow-up, wedding countdown, corporate onboarding, bulk bakery,
  franchise evaluation and lost-customer re-engagement
- An enquiry welcome email template

Everything is created under hudson_pos_demo_data, so Odoo removes it automatically
when the module is uninstalled. The only existing records touched are CRM settings
(rotting days on "Proposition", lead assignment rules on the Sales team).
"""

import logging

from .demo_xml import load_demo_xml as convert_file  # tolerant of apps not installed

_logger = logging.getLogger(__name__)

# Load order matters: customers -> salesperson -> utm -> tags -> teams -> leads.
CRM_XML_FILES = [
    'demo/crm/res_partner_demo.xml',
    'demo/crm/res_users_demo.xml',
    'demo/crm/mail_activity_plan_demo.xml',
    'demo/crm/utm_demo.xml',
    'demo/crm/crm_tag_demo.xml',
    'demo/crm/crm_team_demo.xml',
    'demo/crm/crm_stage_demo.xml',
    'demo/crm/mail_template_demo.xml',
    'demo/crm/crm_lead_demo.xml',
]

# xmlid prefixes of the generic Odoo CRM demo (furniture/software) loaded by version 20.0.1.0.5.
_GENERIC_ODOO_DEMO_PREFIXES = (
    'crm_', 'base_res_partner', 'base_partner_demo', 'base_user_demo',
    'sales_team_', 'utm_utm_campaign', 'utm_campaign_stage',
)
# Unlink order: dependent records first.
_GENERIC_UNLINK_ORDER = (
    'mail.activity', 'mail.message', 'ir.attachment', 'crm.lead', 'crm.team.member',
    'crm.team', 'crm.tag', 'mail.template', 'utm.campaign', 'utm.stage',
    'res.users', 'res.partner', 'res.partner.category',
)


def _remove_generic_odoo_crm_demo(env):
    """Remove the generic Odoo CRM demo records, keeping only Resto Cafe content."""
    imd = env['ir.model.data'].sudo().search([
        ('module', '=', 'hudson_pos_demo_data'),
        ('model', 'in', list(_GENERIC_UNLINK_ORDER)),
    ]).filtered(lambda d: d.name.startswith(_GENERIC_ODOO_DEMO_PREFIXES))
    if not imd:
        return
    _logger.info("Hudson CRM Suite: removing %s generic Odoo CRM demo records", len(imd))
    # Read everything first: unlinking a record also deletes its ir.model.data entry.
    by_model = {}
    for d in imd:
        by_model.setdefault(d.model, []).append(d.res_id)
    imd_ids = imd.ids
    for model in _GENERIC_UNLINK_ORDER:
        res_ids = by_model.get(model)
        if not res_ids:
            continue
        records = env[model].sudo().with_context(active_test=False).browse(res_ids).exists()
        try:
            with env.cr.savepoint():
                records.unlink()
        except Exception as e:
            # e.g. a demo user/partner referenced elsewhere: archive instead of deleting
            _logger.info("Hudson CRM Suite: archiving %s %s instead of deleting (%s)", model, records.ids, e)
            if 'active' in records._fields:
                try:
                    with env.cr.savepoint():
                        records.exists().write({'active': False})
                except Exception as e2:
                    _logger.info("Hudson CRM Suite: kept %s %s (%s)", model, records.ids, e2)
    # Drop the remaining xmlids so the generic records are no longer tied to this module.
    env['ir.model.data'].sudo().browse(imd_ids).exists().unlink()


def load_crm_suite_demo_data(env):
    """Load the Resto Cafe Solutions CRM demo dataset when the CRM app is installed.

    All files load in one savepoint: they reference each other, so either the
    whole dataset is loaded or nothing is.
    """
    if 'crm.lead' not in env:
        _logger.info("Hudson CRM Suite: skipped, CRM is not installed.")
        return False

    with env.cr.savepoint():
        _remove_generic_odoo_crm_demo(env)

    idref = {}
    with env.cr.savepoint():
        for xml_file in CRM_XML_FILES:
            _logger.info("Hudson CRM Suite: loading %s", xml_file)
            convert_file(
                env,
                'hudson_pos_demo_data',
                xml_file,
                idref=idref,
                mode='init',
                noupdate=True,
            )
    _logger.info("Hudson CRM Suite: Resto Cafe Solutions CRM demo data loaded.")
    return True
