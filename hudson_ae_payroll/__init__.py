# -*- coding: utf-8 -*-
from . import models
from . import services


def post_init_hook(env):
    """
    Automatically ensures a UAE localization company is configured/created upon module installation.
    If the default/main company has no country set, it is configured as UAE.
    If the default company already belongs to another country, a dedicated 'My Company (UAE)' company is created.
    Populates default UAE jurisdiction and emirate if available.
    """
    country_uae = env.ref('base.ae', raise_if_not_found=False) or env['res.country'].search([('code', '=', 'AE')], limit=1)
    if not country_uae:
        return

    currency_aed = env.ref('base.AED', raise_if_not_found=False) or env['res.currency'].search([('name', '=', 'AED')], limit=1)

    all_companies = env['res.company'].search([])
    uae_company = all_companies.filtered(lambda c: c.country_id and c.country_id.code == 'AE')[:1]
    main_company = env.ref('base.main_company', raise_if_not_found=False) or (all_companies and all_companies[0])

    if not uae_company:
        if main_company and not main_company.country_id:
            vals = {'country_id': country_uae.id}
            if currency_aed:
                vals['currency_id'] = currency_aed.id
            main_company.sudo().write(vals)
            uae_company = main_company
        else:
            base_name = main_company.name if main_company else 'My Company'
            company_name = f"{base_name} (UAE)"
            company_vals = {
                'name': company_name,
                'country_id': country_uae.id,
            }
            if currency_aed:
                company_vals['currency_id'] = currency_aed.id

            uae_company = env['res.company'].sudo().create(company_vals)

            admin_user = env.ref('base.user_admin', raise_if_not_found=False)
            if admin_user and uae_company not in admin_user.company_ids:
                admin_user.sudo().write({'company_ids': [(4, uae_company.id)]})

            root_user = env.ref('base.user_root', raise_if_not_found=False)
            if root_user and uae_company not in root_user.company_ids:
                root_user.sudo().write({'company_ids': [(4, uae_company.id)]})

            if env.user and uae_company not in env.user.company_ids:
                env.user.sudo().write({'company_ids': [(4, uae_company.id)]})

    if uae_company:
        comp_vals = {}
        if not uae_company.uae_employment_sector:
            comp_vals['uae_employment_sector'] = 'private'
        dubai = env['uae.emirate'].sudo().search([('code', '=', 'DXB')], limit=1)
        if dubai and not uae_company.uae_emirate_id:
            comp_vals['uae_emirate_id'] = dubai.id
        if not uae_company.uae_jurisdiction_type:
            comp_vals['uae_jurisdiction_type'] = 'mainland'
        if comp_vals:
            uae_company.sudo().write(comp_vals)
