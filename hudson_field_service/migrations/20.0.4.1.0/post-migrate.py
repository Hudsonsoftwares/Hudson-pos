# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, SUPERUSER_ID

# Former worksheet columns of the jobs -> worksheet field of the template
LEGACY_FIELDS = {
    'ws_manufacturer_id': 'manufacturer_id',
    'ws_model': 'model',
    'ws_serial_number': 'serial_number',
    'ws_intervention_type': 'intervention_type',
    'ws_intervention_description': 'intervention_description',
}


def migrate(cr, version):
    """Worksheet sections (Device, Intervention) become customizable worksheet fields."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    Template = env['fs.worksheet.template'].with_context(active_test=False)

    cr.execute("""SELECT column_name FROM information_schema.columns
                  WHERE table_name = 'fs_worksheet_template' AND column_name IN ('has_device_section', 'has_intervention_section')""")
    if len(cr.fetchall()) == 2:
        cr.execute("SELECT id, has_device_section, has_intervention_section FROM fs_worksheet_template")
        sections = {tid: (device, intervention) for tid, device, intervention in cr.fetchall()}
    else:
        sections = {}
    default = env.ref('hudson_field_service.fs_worksheet_template_device', raise_if_not_found=False)
    for template in Template.search([]).filtered(lambda t: not t.worksheet_definition):
        if template == default:
            template.worksheet_definition = Template._get_default_worksheet_definition()
        else:
            device, intervention = sections.get(template.id, (True, True))
            template.worksheet_definition = Template._get_default_worksheet_definition(
                device=device, intervention=intervention, checks=False, sign_off=False)

    cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'field_service_order' AND column_name = ANY(%s)",
               [list(LEGACY_FIELDS)])
    columns = [row[0] for row in cr.fetchall()]
    if not columns:
        return
    cr.execute("SELECT id, %s FROM field_service_order WHERE worksheet_template_id IS NOT NULL" % ', '.join(columns))
    for row in cr.dictfetchall():
        values = {LEGACY_FIELDS[col]: row[col] for col in columns if row[col]}
        if not values:
            continue
        order = env['field.service.order'].browse(row['id'])
        names = {prop['name'] for prop in order.worksheet_template_id.worksheet_definition or []}
        values = {name: value for name, value in values.items() if name in names}
        if values:
            # A dict only writes the values, the template's definition is kept
            order.with_context(fs_skip_slot_sync=True, tracking_disable=True).worksheet_properties = values
