from odoo import SUPERUSER_ID, api

# xmlid: (sequence, old default name, new name, placeholder, tip)
DEFAULTS = {
    'sign_item_type_signature': (1, 'Signature', 'Signature', 'Signature', 'Sign it'),
    'sign_item_type_initial': (2, 'Initial', 'Initials', 'Initials', 'Fill in your initials'),
    'sign_item_type_name': (3, 'Name', 'Name', 'Name', 'Fill in'),
    'sign_item_type_email': (4, 'Email', 'Email', 'Email', 'Fill in'),
    'sign_item_type_phone': (5, 'Phone', 'Phone', 'Phone', 'Fill in'),
    'sign_item_type_company': (6, 'Company', 'Company', 'Company', 'Fill in'),
    'sign_item_type_text': (7, 'Text', 'Text', 'Text', 'Fill in'),
    'sign_item_type_multiline': (8, 'Multiline Text', 'Multiline', 'Multiline Text', 'Fill in'),
    'sign_item_type_checkbox': (9, 'Checkbox', 'Checkbox', False, 'Check'),
    'sign_item_type_date': (12, 'Date', 'Date', 'Date', 'Fill in'),
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, (sequence, old_name, new_name, placeholder, tip) in DEFAULTS.items():
        record = env.ref(f'hudson_sign.{xmlid}', raise_if_not_found=False)
        if not record:
            continue
        vals = {'sequence': sequence}
        if record.name == old_name:
            vals['name'] = new_name
        if placeholder and not record.placeholder:
            vals['placeholder'] = placeholder
        if not record.tip:
            vals['tip'] = tip
        record.write(vals)

    # Recompute the stored status now that Cancelled / Expired exist
    requests = env['hudson.sign.request'].search([])
    env.add_to_compute(requests._fields['state'], requests)
    requests.flush_recordset(['state'])
