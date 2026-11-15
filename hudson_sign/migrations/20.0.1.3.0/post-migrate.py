from odoo import SUPERUSER_ID, api

OLD_DEFAULT_COLORS = ('#d1fae5', '#10b981', '#065f46')
NEW_DEFAULT_COLORS = ('#e2dcf3', '#a495d6', '#2e2252')

STAMP_PLACEHOLDER = "Company Name\nCompany Address\nCompany Phone"


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # The first signer colour changed from emerald to lavender
    color, border, text = OLD_DEFAULT_COLORS
    env['hudson.sign.template.role'].search([
        ('color', '=', color), ('border_color', '=', border), ('text_color', '=', text),
    ]).write(dict(zip(('color', 'border_color', 'text_color'), NEW_DEFAULT_COLORS)))

    stamp = env.ref('hudson_sign.sign_item_type_stamp', raise_if_not_found=False)
    if stamp and stamp.placeholder in (False, 'Stamp'):
        stamp.placeholder = STAMP_PLACEHOLDER
        env['hudson.sign.template.item'].search([
            ('type_id', '=', stamp.id), ('placeholder', 'in', [False, 'Stamp']),
        ]).write({'placeholder': STAMP_PLACEHOLDER})
