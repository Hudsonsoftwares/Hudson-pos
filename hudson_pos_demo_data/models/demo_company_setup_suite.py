# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - company setup demo data.

  * Company branding: "My Company" -> "Resto Cafe Solutions" (only while still unnamed)
  * GST: company GSTIN/PAN, GSTINs + GST treatment on the CRM B2B customers (intra and inter-state),
    HSN/SAC codes on products, e-invoicing switched on in SANDBOX mode without credentials
    (invoices only get the status "To Send"; nothing is sent to the IRP until a user clicks Send)
  * Barcodes: valid EAN-13 (GS1 India prefix 890) on packaged food, bottled drinks and retail goods
  * Data Recycle: manual-review cleanup rules (never automatic)
  * Payment providers: Wire Transfer + Cash on Delivery published, Demo provider unpublished;
    POS "UPI (QR)" payment method on the bank journal
"""
import logging

from odoo import Command
from .demo_guard import get_param, set_param

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
GSTIN_CHARS = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'


def _ref(env, xid):
    return env.ref(f'{MODULE}.{xid}', raise_if_not_found=False) if xid else None


def _bind(env, xid, record):
    rec = _ref(env, xid)
    if not rec:
        env['ir.model.data'].sudo().create({
            'module': MODULE, 'name': xid, 'model': record._name, 'res_id': record.id, 'noupdate': True,
        })
    return record


def _get_or_create(env, xid, model, vals):
    rec = _ref(env, xid)
    if rec and rec.exists():
        return rec
    return _bind(env, xid, env[model].sudo().create(vals))


def gstin(state_code, pan, entity='1'):
    """Build a GSTIN with the official mod-36 checksum digit."""
    base = f'{state_code}{pan}{entity}Z'
    total = 0
    for i, ch in enumerate(base):
        product = GSTIN_CHARS.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return base + GSTIN_CHARS[(36 - total % 36) % 36]


def ean13(first12):
    digits = [int(d) for d in first12]
    check = (10 - (sum(digits[0::2]) + 3 * sum(digits[1::2])) % 10) % 10
    return first12 + str(check)


# --------------------------------------------------------------------------- 0. multi-company
def _multi_company(env):
    """Ensure 3 default companies exist and all internal users have multi-company access (R2)."""
    Company = env['res.company'].sudo()
    User = env['res.users'].sudo()

    # 1. Company 1 (Main Company: Resto Cafe Solutions)
    c1 = env.ref('base.main_company', raise_if_not_found=False) or env.company
    if not _ref(env, 'rc_company_1'):
        _bind(env, 'rc_company_1', c1)

    india = env.ref('base.in', raise_if_not_found=False)
    country_id = india.id if india else (c1.country_id.id if c1.country_id else False)
    currency_id = c1.currency_id.id

    # 2. Company 2
    c2 = _ref(env, 'rc_company_2')
    if not (c2 and c2.exists()):
        c2 = Company.search([('name', '=', 'Company 2')], limit=1)
        if not c2:
            c2 = Company.create({
                'name': 'Company 2',
                'currency_id': currency_id,
                'country_id': country_id,
                'street': 'MG Road',
                'city': 'Ernakulam',
                'zip': '682016',
                'email': 'company2@restocafe.example',
                'phone': '+91 484 400 5678',
            })
        _bind(env, 'rc_company_2', c2)

    # 3. Company 3
    c3 = _ref(env, 'rc_company_3')
    if not (c3 and c3.exists()):
        c3 = Company.search([('name', '=', 'Company 3')], limit=1)
        if not c3:
            c3 = Company.create({
                'name': 'Company 3',
                'currency_id': currency_id,
                'country_id': country_id,
                'street': 'Airport Road, Nedumbassery',
                'city': 'Kochi',
                'zip': '683111',
                'email': 'company3@restocafe.example',
                'phone': '+91 484 400 9012',
            })
        _bind(env, 'rc_company_3', c3)

    all_companies = c1 | c2 | c3

    # Provision default warehouses for sister companies
    if 'stock.warehouse' in env:
        Warehouse = env['stock.warehouse'].sudo()
        for comp in (c2, c3):
            if not Warehouse.search([('company_id', '=', comp.id)], limit=1):
                try:
                    with env.cr.savepoint():
                        Warehouse.create({
                            'name': comp.name,
                            'code': f'W{comp.id:02d}'[:5],
                            'company_id': comp.id,
                            'partner_id': comp.partner_id.id,
                        })
                except Exception as e:
                    _logger.warning("Hudson POS: could not create warehouse for %s: %s", comp.name, e)

    # Grant multi-company access to all internal users (share=False)
    users = User.search([('share', '=', False)])
    for user in users:
        missing = all_companies - user.company_ids
        vals = {}
        if missing:
            vals['company_ids'] = [Command.link(c.id) for c in missing]
        if not user.company_id:
            vals['company_id'] = c1.id
        if vals:
            try:
                with env.cr.savepoint():
                    user.write(vals)
            except Exception as e:
                _logger.warning("Hudson POS: could not update multi-company access on user %s: %s", user.login, e)

    # Enable base.group_multi_company
    group_mc = env.ref('base.group_multi_company', raise_if_not_found=False)
    if group_mc:
        admin_user = env.ref('base.user_admin', raise_if_not_found=False)
        if admin_user and not admin_user.has_group('base.group_multi_company'):
            try:
                with env.cr.savepoint():
                    admin_user.sudo().write({'group_ids': [Command.link(group_mc.id)]})
            except Exception as e:
                _logger.warning("Hudson POS: could not add admin to multi-company group: %s", e)


# --------------------------------------------------------------------------- 1. branding
def _branding(env):
    company = env.company
    india = env.ref('base.in', raise_if_not_found=False)
    kerala = env['res.country.state'].search([('country_id.code', '=', 'IN'), ('code', '=', 'KL')], limit=1)
    vals = {}
    if company.name in ('My Company', 'Resto Cafe Solutions'):
        if company.name == 'My Company':
            vals.update({'name': 'Resto Cafe Solutions', 'street': 'Marine Drive', 'city': 'Kochi', 'zip': '682031'})
            # never overwrite real contact details (the company e-mail is the sender address of outgoing mail)
            for field, value in (('email', 'hello@restocafe.example'), ('phone', '+91 484 400 1234'),
                                 ('website', 'https://www.restocafe.example')):
                if not company[field]:
                    vals[field] = value
            company.partner_id.write({'name': 'Resto Cafe Solutions'})

        # Heal any dirty leaves/allocations that would block setting company country to India
        if india and company.country_id != india:
            if 'hr.work.entry.type' in env:
                WET = env['hr.work.entry.type'].sudo()
                custom_wets = WET.search([('code', 'in', ['RC_CL', 'RC_SL', 'RC_EL', 'RC_FL', 'RC_UL', 'RC_CO']), ('country_id', '!=', False)])
                if custom_wets:
                    custom_wets.write({'country_id': False})
            if 'hr.leave' in env:
                Leave = env['hr.leave'].sudo()
                conflicts = Leave.search([
                    ('employee_company_id', '=', company.id),
                    ('work_entry_type_id.country_id', '!=', False),
                    ('work_entry_type_id.country_id', '!=', india.id),
                ])
                if conflicts:
                    rc_el = _ref(env, 'rc_hrp_lt_earned') or env['hr.work.entry.type'].sudo().search([('code', '=', 'RC_EL')], limit=1)
                    if rc_el:
                        for cl in conflicts:
                            try:
                                with env.cr.savepoint():
                                    cl.write({'work_entry_type_id': rc_el.id})
                            except Exception:
                                pass
            vals['country_id'] = india.id

        if kerala and company.state_id != kerala:
            vals['state_id'] = kerala.id

    # Header & Footer demo data on company documents
    if 'report_header' in company._fields and not company.report_header:
        vals['report_header'] = 'Kerala flavours, made fresh every day | Authentic Arabian & Multicuisine'
    if 'report_footer' in company._fields and not company.report_footer:
        vals['report_footer'] = 'Resto Cafe Solutions • 26th Mile Bridge, Kanjirappally, Kerala • Phone: +91 484 400 1234 • GSTIN: 32AAKCR7342M1Z5 • Email: hello@restocafe.example'
    if vals:
        company.write(vals)


# --------------------------------------------------------------------------- 2. GST
COMPANY_PAN = 'AAKCR7342M'
# partner xmlid -> (state code, PAN or None, gst treatment, city, state code letters)
B2B = {
    'rc_partner_bluewave': ('32', 'AABCB4821F', 'regular', None),
    'rc_partner_marina_events': ('32', 'AAJFM6610Q', 'regular', None),
    'rc_partner_harbour_park': ('32', 'AADCH2934L', 'regular', None),
    'rc_partner_grand_residency': ('32', 'AACCG5172P', 'regular', None),
    'rc_partner_greenleaf': ('32', 'AAATG8813H', 'regular', None),
    'rc_partner_nest_cowork': ('32', 'AAHCN3305D', 'regular', None),
    'rc_partner_spice_route': ('29', 'AAGFS7719K', 'regular', ('Bengaluru', 'KA', '560001')),  # inter-state -> IGST
    'rc_partner_film_society': (None, None, 'unregistered', None),
    'rc_partner_st_teresa': (None, None, 'unregistered', None),
    'rc_partner_coastal_runners': (None, None, 'unregistered', None),
}
HSN_RULES = [  # (keywords in name/category, HSN/SAC - 6 digits format)
    (('coffee', 'chai', 'tea'), '090100'), (('pepper', 'masala', 'powder', 'spice', 'cardamom'), '091000'),
    (('pickle',), '200190'), (('chips', 'mixture', 'murukku', 'cookie', 'cake', 'halwa'), '190590'),
    (('water', 'cola', 'fanta', 'schweppes', 'minute maid', 'ice tea', 'juice'), '220210'),
    (('chocolate', 'truffle', 'macaron'), '180631'), (('batter', 'mix', 'podi', 'ready'), '210690'),
]


def _gst(env):
    company = env.company
    india = env.ref('base.in')
    states = {s.code: s for s in env['res.country.state'].search([('country_id', '=', india.id)])}
    kerala = states.get('KL')
    if not company.vat:
        company.write({'vat': gstin('32', COMPANY_PAN)})
    if 'l10n_in_gst_registration_type' in company._fields and not company.l10n_in_gst_registration_type:
        sel = dict(company._fields['l10n_in_gst_registration_type']._description_selection(env))
        if 'regular' in sel:
            company.l10n_in_gst_registration_type = 'regular'
    if 'l10n_in_disable_b2c_hsn_reporting' in company._fields:
        company.l10n_in_disable_b2c_hsn_reporting = True
    # e-invoicing in SANDBOX, no credentials: posted B2B invoices only get the status "To Send"
    if 'l10n_in_edi_feature' in company._fields and not company.l10n_in_edi_feature:
        company.write({'l10n_in_edi_feature': True, 'l10n_in_edi_production_env': False})
    if not get_param(env, 'l10n_in.gsp_provider'):
        set_param(env, 'l10n_in.gsp_provider', 'bvm')  # avoids the "Tera GSP deprecated" banner

    for xid, (state_code, pan, treatment, move_to) in B2B.items():
        partner = _ref(env, xid)
        if not partner:
            continue
        vals = {'is_company': True, 'country_id': india.id}
        if 'l10n_in_gst_treatment' in env['res.partner']._fields:
            vals['l10n_in_gst_treatment'] = treatment
        if move_to and not partner.vat:
            city, st, zip_code = move_to
            vals.update({'city': city, 'state_id': states[st].id, 'zip': zip_code})
        elif not partner.state_id and kerala:
            vals['state_id'] = kerala.id
        if pan and not partner.vat:
            vals['vat'] = gstin(state_code, pan)
        partner.write(vals)
        # individual contacts of the company (they inherit the GSTIN as commercial partner)
        partner.child_ids.filtered(lambda c: not c.state_id).write({'state_id': vals.get('state_id', partner.state_id.id)})
    # walk-in / individual customers -> consumer
    for xid in ('rc_sale_partner_priya',):
        p = _ref(env, xid)
        if p:
            p_vals = {'state_id': p.state_id.id or (kerala and kerala.id)}
            if 'l10n_in_gst_treatment' in env['res.partner']._fields:
                p_vals['l10n_in_gst_treatment'] = 'consumer'
            p.write(p_vals)

    # HSN / SAC codes (needed on e-invoices)
    if 'l10n_in_hsn_code' in env['product.template']._fields:
        templates = env['product.template'].with_context(active_test=False).search(
            [('l10n_in_hsn_code', '=', False), ('sale_ok', '=', True)])
        IMD = env['ir.model.data'].sudo()
        retail_ids = set(IMD.search([('module', '=', MODULE), ('model', '=', 'product.template'),
                                     ('name', 'in', RETAIL_XIDS)]).mapped('res_id'))
        retail_ids |= set(IMD.search([('module', '=', MODULE), ('model', '=', 'product.template'),
                                      ('name', '=like', 'rc_pf_%')]).mapped('res_id'))
        for t in templates:
            categ = (t.categ_id.complete_name or '').lower()
            name = f'{t.name} {categ}'.lower()
            if t.id in retail_ids:  # packaged / bottled goods sold as goods -> HSN
                code = next((h for keys, h in HSN_RULES if any(k in name for k in keys)), '210690')
            elif 'rental' in categ or 'rental' in name:
                code = '997319'  # rental of equipment
            elif 'catering' in name or 'event' in name or 'buffet' in name or 'sadya' in name:
                code = '996334'  # outdoor catering
            else:
                code = '996331'  # restaurant / cafe food and beverage service
            t.l10n_in_hsn_code = code

        # Also populate any existing open POS order lines missing HSN so register closing never fails
        if 'pos.order.line' in env and 'l10n_in_hsn_code' in env['pos.order.line']._fields:
            for pol in env['pos.order.line'].search([('l10n_in_hsn_code', '=', False)]):
                pol.l10n_in_hsn_code = pol.product_id.l10n_in_hsn_code or '996331'


# --------------------------------------------------------------------------- 3. barcodes
RETAIL_XIDS = [
    'product_coca_cola', 'product_fanta', 'product_schweppes', 'product_minute_maid', 'product_water', 'product_ice_tea',
    'product_dark_chocolate_bar_70', 'product_white_chocolate_raspberry_bar', 'product_luxury_chocolate_gift_box',
    'product_french_macarons_box_6_pcs', 'product_belgian_milk_chocolate_truffles', 'rc_invf_prod_water', 'rc_invf_prod_coco_water',
]
GS1_COMPANY = '8907712'  # 890 = GS1 India; 7712 = demo company number


def _barcodes(env):
    IMD = env['ir.model.data'].sudo()
    xids = IMD.search([('module', '=', MODULE), ('model', '=', 'product.template'), ('name', '=like', 'rc_pf_%')]).mapped('name')
    xids = sorted(xids) + RETAIL_XIDS
    Product = env['product.product'].with_context(active_test=False)
    used = set(Product.search([('barcode', '!=', False)]).mapped('barcode'))
    item = 10000
    for xid in xids:
        tmpl = _ref(env, xid)
        if not tmpl:
            continue
        for variant in tmpl.with_context(active_test=False).product_variant_ids.sorted('id'):
            item += 1
            if variant.barcode:
                continue
            code = ean13(f'{GS1_COMPANY}{item:05d}')
            if code in used:
                continue
            variant.barcode = code
            used.add(code)


# --------------------------------------------------------------------------- 4. data recycle
def _data_recycle(env):
    if 'data_recycle.model' not in env:
        return
    rules = [
        ('rc_dr_abandoned_carts', 'Abandoned webshop carts (30+ days)', 'sale.order', 'unlink', 'date_order', 30, 'days',
         "[('state', '=', 'draft'), ('website_id', '!=', False)]"),
        ('rc_dr_stale_pos_drafts', 'Unpaid POS draft orders (7+ days)', 'pos.order', 'unlink', 'date_order', 7, 'days',
         "[('state', '=', 'draft')]"),
        ('rc_dr_old_lost_leads', 'Lost catering enquiries (1+ year)', 'crm.lead', 'archive', 'write_date', 1, 'years',
         "[('active', '=', False), ('probability', '=', 0)]"),
        ('rc_dr_old_cancelled_quotes', 'Cancelled quotations (6+ months)', 'sale.order', 'unlink', 'write_date', 6, 'months',
         "[('state', '=', 'cancel')]"),
    ]
    created = env['data_recycle.model']
    for xid, name, model, action, time_field, delta, unit, domain in rules:
        if model not in env:
            continue
        ir_model = env['ir.model']._get(model)
        tfield = env['ir.model.fields']._get(model, time_field)
        vals = {'name': name, 'res_model_id': ir_model.id, 'recycle_mode': 'manual', 'recycle_action': action,
                'time_field_id': tfield.id, 'time_field_delta': delta, 'time_field_delta_unit': unit,
                'notify_user_ids': [Command.clear()]}
        rec = _ref(env, xid)
        if not rec:
            rec = _bind(env, xid, env['data_recycle.model'].sudo().create(vals))
            rec.domain = domain
            if action == 'archive' and 'include_archived' in rec._fields:
                rec.include_archived = True
        created |= rec
    created._recycle_records(batch_commits=False)


# --------------------------------------------------------------------------- 5. payments
def _payments(env):
    company = env.company
    bank_journal = env['account.journal'].search([('type', '=', 'bank'), ('company_id', '=', company.id)], limit=1)
    # company bank account (demo numbers) so Wire Transfer instructions and UPI QR work
    acc = _get_or_create(env, 'rc_pp_company_bank_account', 'res.partner.bank', {
        'account_number': '111102000773420', 'partner_id': company.partner_id.id, 'holder_name': company.name,
        'bank_name': 'The Federal Bank Ltd (Marine Drive, Kochi) - DEMO ACCOUNT', 'bank_bic': 'FDRLINBB',
        'city': 'Kochi', 'company_id': company.id, 'allow_out_payment': True})
    if bank_journal and not bank_journal.bank_account_id:
        bank_journal.bank_account_id = acc

    if 'payment.provider' in env:
        Provider = env['payment.provider'].sudo()
        wire = Provider.search([('code', '=', 'custom'), ('custom_mode', '=', 'wire_transfer')], limit=1)
        if wire:
            wire.write({'is_published': True, 'is_live': True, 'pending_msg': (
                '<p>Please transfer the amount to <b>Resto Cafe Solutions</b>, The Federal Bank Ltd, Marine Drive branch, Kochi '
                '(A/c 1111 0200 0773 42 - demo). Use your order number as the payment reference. '
                'Your catering booking is confirmed once the payment reaches us.</p>')})
        cod = Provider.search([('code', '=', 'custom'), ('custom_mode', '=', 'cash_on_delivery')], limit=1)
        if cod:
            cod.write({'is_published': True, 'is_live': True})
        demo = Provider.search([('code', '=', 'demo')])
        demo.filtered('is_published').write({'is_published': False})

    # POS: UPI (QR) payment method on the bank journal
    PM = env['pos.payment.method'].sudo()
    if bank_journal and 'upi_identifier' in PM._fields and not _ref(env, 'rc_pp_pos_upi'):
        qr_methods = [m[0] for m in env['res.partner.bank'].get_available_qr_methods_in_sequence()]
        if 'upi' in qr_methods:
            upi = _get_or_create(env, 'rc_pp_pos_upi', 'pos.payment.method', {
                'name': 'UPI (QR)', 'type': 'bank', 'journal_id': bank_journal.id, 'payment_method_type': 'bank_qr_code',
                'qr_code_method': 'upi', 'upi_identifier': 'restocafe.demo@federal'})
            for config in env['pos.config'].search([]):
                if upi not in config.payment_method_ids:
                    try:
                        with env.cr.savepoint():
                            config.payment_method_ids = [Command.link(upi.id)]
                    except Exception as e:
                        _logger.info("UPI method not added to %s: %s", config.name, e)


def load_company_setup_suite_demo_data(env):
    for name, step in (('multi-company', _multi_company), ('branding', _branding),
                       ('gst', _gst), ('barcodes', _barcodes),
                       ('data recycle', _data_recycle), ('payments', _payments)):
        try:
            with env.cr.savepoint():
                step(env)
        except Exception as e:
            _logger.exception("Hudson POS: company setup step '%s' failed: %s", name, e)
    _logger.info("Hudson POS: Resto Cafe company setup demo data loaded.")
