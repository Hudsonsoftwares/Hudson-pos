def migrate(cr, version):
    if not version:
        return
    
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    try:
        group_ids = [
            env.ref('eh_hr_appraisal.group_hr_appraisal_user', raise_if_not_found=False),
            env.ref('eh_hr_appraisal.group_hr_appraisal_manager', raise_if_not_found=False),
            env.ref('eh_hr_appraisal.group_hr_appraisal_admin', raise_if_not_found=False),
        ]
        group_ids = [g.id for g in group_ids if g]
        if not group_ids:
            return
            
        groups = env['res.groups'].browse(group_ids)
        
        if 'privilege_id' in groups._fields:
            hr_cat = env.ref('base.module_category_human_resources', raise_if_not_found=False)
            if hr_cat:
                priv = env['res.groups.privilege'].search([('name', '=', 'Appraisal'), ('category_id', '=', hr_cat.id)], limit=1)
                if not priv:
                    priv = env['res.groups.privilege'].create({
                        'name': 'Appraisal',
                        'category_id': hr_cat.id,
                        'sequence': 15,
                    })
                
                # Write privilege_id to all groups
                groups.sudo().write({'privilege_id': priv.id})
    except Exception as e:
        pass
