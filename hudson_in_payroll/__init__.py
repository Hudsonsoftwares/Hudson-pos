# -*- coding: utf-8 -*-
import sys
for _mod_name in list(sys.modules.keys()):
    if _mod_name.startswith('odoo.addons.hudson_in_payroll.'):
        del sys.modules[_mod_name]

from . import services
from . import models
from . import wizard
from . import reports


def post_init_hook(env):
    """
    Automatically ensures an Indian localization company is configured/created upon module installation.
    If the default/main company has no country set, it is configured as the Indian company.
    If the default company already belongs to another country, a dedicated 'My Company (IN)' company is created.
    Populates default Indian statutory payroll structures, TDS year, and compliance flags.
    """
    country_india = env.ref('base.in', raise_if_not_found=False) or env['res.country'].search([('code', '=', 'IN')], limit=1)
    if not country_india:
        return

    currency_inr = env.ref('base.INR', raise_if_not_found=False) or env['res.currency'].search([('name', '=', 'INR')], limit=1)

    # Check if an Indian company already exists
    all_companies = env['res.company'].search([])
    indian_company = all_companies.filtered(lambda c: c.country_id and c.country_id.code == 'IN')[:1]
    main_company = env.ref('base.main_company', raise_if_not_found=False) or (all_companies and all_companies[0])

    if not indian_company:
        if main_company and not main_company.country_id:
            # Main company has no country set; configure it as India
            vals = {'country_id': country_india.id}
            if currency_inr:
                vals['currency_id'] = currency_inr.id
            main_company.sudo().write(vals)
            indian_company = main_company
        else:
            # Main company belongs to another country; create a dedicated Indian company
            base_name = main_company.name if main_company else 'My Company'
            company_name = f"{base_name} (IN)"
            company_vals = {
                'name': company_name,
                'country_id': country_india.id,
            }
            if currency_inr:
                company_vals['currency_id'] = currency_inr.id

            indian_company = env['res.company'].sudo().create(company_vals)

            # Grant allowed company access to administrative users
            admin_user = env.ref('base.user_admin', raise_if_not_found=False)
            if admin_user and indian_company not in admin_user.company_ids:
                admin_user.sudo().write({'company_ids': [(4, indian_company.id)]})

            root_user = env.ref('base.user_root', raise_if_not_found=False)
            if root_user and indian_company not in root_user.company_ids:
                root_user.sudo().write({'company_ids': [(4, indian_company.id)]})

            if env.user and indian_company not in env.user.company_ids:
                env.user.sudo().write({'company_ids': [(4, indian_company.id)]})

    if indian_company:
        comp_vals = {}
        regular_struct = env.ref('hudson_payroll_base.structure_base', raise_if_not_found=False)
        if regular_struct and not indian_company.hds_in_regular_struct_id:
            comp_vals['hds_in_regular_struct_id'] = regular_struct.id

        tax_year = env['tds.financial.year'].sudo().search([('active', '=', True)], limit=1)
        if tax_year and not indian_company.hds_in_default_tax_year:
            comp_vals['hds_in_default_tax_year'] = tax_year.id

        if not indian_company.hds_in_default_tax_regime:
            comp_vals['hds_in_default_tax_regime'] = 'new'

        comp_vals['hds_in_epf_applicable'] = True
        comp_vals['hds_in_eps_applicable'] = True
        comp_vals['hds_in_edli_applicable'] = True
        comp_vals['hds_in_esic_applicable'] = True
        comp_vals['hds_in_enable_lwf'] = False
        comp_vals['hds_in_enable_statutory_audit'] = True

        indian_company.sudo().with_context(skip_statutory_threshold_check=True, install_mode=True).write(comp_vals)

    # Ensure structure and structure type names match Indian localization
    reg_struct = env.ref('hudson_payroll_base.structure_base', raise_if_not_found=False)
    if reg_struct and reg_struct.name != 'India: Regular Pay':
        reg_struct.sudo().write({'name': 'India: Regular Pay'})

    emp_type = env.ref('hr.structure_type_employee', raise_if_not_found=False)
    if emp_type:
        emp_vals = {}
        if emp_type.name != 'India: Employee Pay':
            emp_vals['name'] = 'India: Employee Pay'
        if country_india and emp_type.country_id != country_india:
            emp_vals['country_id'] = country_india.id
        if reg_struct and emp_type.default_struct_id != reg_struct:
            emp_vals['default_struct_id'] = reg_struct.id
        if emp_vals:
            emp_type.sudo().write(emp_vals)

    worker_struct = env.ref('hudson_payroll_base.structure_worker', raise_if_not_found=False)
    if worker_struct and worker_struct.name != 'India: Worker Pay':
        worker_struct.sudo().write({'name': 'India: Worker Pay'})

    worker_type = env.ref('hr.structure_type_worker', raise_if_not_found=False)
    if worker_type:
        worker_vals = {}
        if worker_type.name != 'India: Worker Pay':
            worker_vals['name'] = 'India: Worker Pay'
        if country_india and worker_type.country_id != country_india:
            worker_vals['country_id'] = country_india.id
        if worker_vals:
            worker_type.sudo().write(worker_vals)

    # Ensure standard salary structures, categories, and rules are company-agnostic (company_id=NULL)
    # so they remain globally accessible across all companies in multi-company setups.
    try:
        env.cr.execute("""
            UPDATE hr_payroll_structure
            SET company_id = NULL
            WHERE code IN ('REGULAR', 'WORKER', 'FINAL_SETTLEMENT_STRUCT');

            UPDATE hr_salary_rule
            SET company_id = NULL
            WHERE struct_id IN (
                SELECT id FROM hr_payroll_structure WHERE code IN ('REGULAR', 'WORKER', 'FINAL_SETTLEMENT_STRUCT')
            );

            UPDATE hr_salary_rule_category
            SET company_id = NULL
            WHERE code IN ('BASIC', 'ALW', 'GROSS', 'DED', 'NET', 'COMP', 'PF_CALC', 'ESIC_CALC');
        """)
    except Exception:
        pass


