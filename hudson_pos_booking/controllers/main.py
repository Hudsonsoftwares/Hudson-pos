# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import http, fields, SUPERUSER_ID
from odoo.http import request
from odoo.addons.point_of_sale.controllers.main import PosController

class PosControllerBooking(PosController):

    def _get_pos_service_worker(self):
        body = super()._get_pos_service_worker()
        # 1. Update cache version to force stale cache bust in Chrome
        body = body.replace('const cacheName = "odoo-pos-cache";', 'const cacheName = "odoo-pos-cache-v12";')

        # 2. Never intercept navigation or POS UI / booking routes in service worker
        if 'event.request.method !== "GET"' in body:
            body = body.replace(
                'event.request.method !== "GET"',
                'event.request.method !== "GET" || event.request.mode === "navigate" || url.includes("/pos/ui") || url.includes("/booking")'
            )

        # 3. Add activate listener to immediately purge all old cached bundles
        cache_purge_logic = """
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== cacheName) {
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});
"""
        body += cache_purge_logic

        # 4. Safe fallback instead of undefined or Response.error()
        target = "return await cache.match(event.request);"
        safe_fallback = """const cached = await cache.match(event.request);
        if (cached) return cached;
        return new Response("", { status: 404 });"""
        if target in body:
            body = body.replace(target, safe_fallback)
        return body

    @http.route(["/pos/ui/<config_id>", "/pos/ui/<config_id>/<path:subpath>"], auth="user", type='http')
    def pos_web(self, config_id=False, from_backend=False, subpath=None, **k):
        """
        Gracefully handle pos routes, redirect action/manage-booking to booking,
        and disable caching on the main HTML entry point.
        """
        if config_id:
            try:
                cfg_id = int(config_id)
                config = request.env['pos.config'].sudo().browse(cfg_id)
                if not config.exists():
                    valid_config = request.env['pos.config'].sudo().search([
                        ('use_booking', '=', True), ('active', '=', True)
                    ], limit=1) or request.env['pos.config'].sudo().search([('active', '=', True)], limit=1)
                    if valid_config:
                        target_path = f"/pos/ui/{valid_config.id}"
                        if subpath:
                            target_path += f"/{subpath}"
                        params = request.httprequest.query_string.decode('utf-8')
                        if params:
                            target_path += f"?{params}"
                        return request.redirect(target_path)
            except (ValueError, TypeError):
                pass

        if subpath and "action/manage-booking" in subpath:
            params = request.httprequest.query_string.decode('utf-8')
            target_path = f"/pos/ui/{config_id}/booking"
            if params:
                target_path += f"?{params}"
            return request.redirect(target_path)

        res = super().pos_web(config_id=config_id, from_backend=from_backend, subpath=subpath, **k)
        if hasattr(res, 'headers'):
            res.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            res.headers['Pragma'] = 'no-cache'
        return res


import json
import logging
_logger = logging.getLogger(__name__)

from odoo.addons.appointment.controllers.main import AppointmentController

class PosAppointmentController(AppointmentController):

    @http.route(['/appointment/<model("appointment.type"):appointment_type>/info'], type='http', auth='public', website=True, methods=['GET', 'POST'])
    def appointment_info(self, appointment_type, **kwargs):
        res = super().appointment_info(appointment_type, **kwargs)
        if hasattr(res, 'qcontext'):
            company = appointment_type.sudo().company_id or request.env.company
            currency = company.currency_id
            tip_product_ids = request.env['pos.config'].sudo().search([('tip_product_id', '!=', False)]).mapped('tip_product_id').ids
            exclude_ids = list(tip_product_ids)

            food_domain = [
                ('available_in_pos', '=', True),
                ('sale_ok', '=', True),
                ('type', '!=', 'service'),
                ('name', 'not ilike', 'gift card'),
                ('name', 'not ilike', 'event registration'),
                ('name', 'not ilike', 'voucher'),
                ('name', '!=', 'Tip'),
                '|', ('company_id', '=', False), ('company_id', '=', company.id)
            ]
            if exclude_ids:
                food_domain.append(('id', 'not in', exclude_ids))

            food_products = request.env['product.product'].sudo().search(food_domain, order='sequence, name asc', limit=500)

            categories_map = {}
            combos_dict = {}
            product_prices = {}
            for p in food_products:
                for cat in p.pos_categ_ids:
                    if cat.id not in categories_map:
                        categories_map[cat.id] = {
                            'id': cat.id,
                            'name': cat.name,
                            'count': 1,
                        }
                    else:
                        categories_map[cat.id]['count'] += 1

                # Calculate final tax-inclusive price for product
                taxes = p.taxes_id.filtered(lambda t: not t.company_id or t.company_id == company)
                if taxes:
                    tax_res = taxes.compute_all(p.lst_price, currency=currency, quantity=1, product=p)
                    incl_price = round(tax_res['total_included'], 2)
                else:
                    incl_price = round(p.lst_price, 2)
                product_prices[p.id] = incl_price

                # Extract combo options for combo products
                if p.type == 'combo' and p.combo_ids:
                    c_groups = []
                    for combo in p.combo_ids:
                        c_items = []
                        for ci in combo.combo_item_ids:
                            if ci.product_id.exists():
                                extra = float(ci.extra_price or 0.0)
                                if extra > 0 and taxes:
                                    extra_tax = taxes.compute_all(extra, currency=currency, quantity=1)['total_included']
                                    extra_incl = round(extra_tax, 2)
                                else:
                                    extra_incl = round(extra, 2)
                                c_items.append({
                                    'id': ci.id,
                                    'product_id': ci.product_id.id,
                                    'name': ci.product_id.name,
                                    'extra_price': extra_incl,
                                    'image_url': f'/web/image/product.product/{ci.product_id.id}/image_128',
                                })
                        if c_items:
                            c_groups.append({
                                'id': combo.id,
                                'name': combo.name,
                                'items': c_items,
                            })
                    if c_groups:
                        combos_dict[str(p.id)] = {
                            'id': p.id,
                            'name': p.name,
                            'price': incl_price,
                            'groups': c_groups,
                        }

            food_categories = sorted(categories_map.values(), key=lambda c: c['name'])
            res.qcontext['food_products'] = food_products
            res.qcontext['food_categories'] = food_categories
            res.qcontext['product_prices'] = product_prices
            res.qcontext['currency_symbol'] = currency.symbol or '$'
            res.qcontext['combos_data_json'] = json.dumps(combos_dict)
        return res

    @http.route(['/appointment/<model("appointment.type"):appointment_type>/submit'], type='http', auth='public', website=True, methods=['POST'])
    def appointment_submit(self, appointment_type, **kwargs):
        import re
        response = super().appointment_submit(appointment_type, **kwargs)
        booking = None
        if hasattr(response, 'qcontext') and 'booking' in response.qcontext:
            booking = response.qcontext['booking']
        elif hasattr(response, 'location') and '/appointment/' in (response.location or ''):
            m = re.search(r'/appointment/(\d+)', response.location)
            if m:
                booking = request.env['appointment.booking'].sudo().browse(int(m.group(1)))

        if booking and booking.exists():
            # 1. Customer Notes / Special Requests (append without clobbering appointment answers)
            customer_notes = kwargs.get('customer_notes') or kwargs.get('special_requests') or kwargs.get('notes')
            if customer_notes and isinstance(customer_notes, str) and customer_notes.strip():
                clean_notes = customer_notes.strip()
                try:
                    existing_details = booking.guest_details or ""
                    merged_details = f"{existing_details}\nSpecial Requests: {clean_notes}".strip() if existing_details else clean_notes
                    booking.sudo().write({
                        'guest_details': merged_details,
                        'notes': clean_notes,
                    })
                except Exception:
                    pass

            # 2. Pre-order Food items
            import math
            preorder_items = []
            for key, val in kwargs.items():
                if key.startswith('food_qty_') and val:
                    qty = 0
                    try:
                        f_val = float(val)
                        if not math.isinf(f_val) and not math.isnan(f_val):
                            i_val = int(f_val)
                            if 1 <= i_val <= 50:
                                qty = i_val
                    except (ValueError, TypeError, OverflowError):
                        qty = 0

                    if qty > 0:
                        try:
                            prod_id = int(key.replace('food_qty_', ''))
                        except (ValueError, TypeError):
                            continue
                        product = request.env['product.product'].sudo().browse(prod_id)
                        if product.exists() and product.sale_ok:
                            combo_raw = kwargs.get(f'food_combo_data_{prod_id}')
                            combo_choices = []
                            combo_details_str = ""
                            extra_price_total = 0.0

                            if combo_raw and isinstance(combo_raw, str):
                                try:
                                    raw_choices = json.loads(combo_raw)
                                    if isinstance(raw_choices, list):
                                        valid_item_ids = set(product.combo_ids.combo_item_ids.ids)
                                        for c in raw_choices:
                                            ci_id = c.get('combo_item_id') or c.get('id')
                                            if ci_id:
                                                try:
                                                    ci_int = int(ci_id)
                                                except (ValueError, TypeError):
                                                    continue
                                                if ci_int in valid_item_ids:
                                                    ci = request.env['product.combo.item'].sudo().browse(ci_int)
                                                    if ci.exists():
                                                        extra_price = max(0.0, float(ci.extra_price or 0.0))
                                                        extra_price_total += extra_price
                                                        disp_name = ci.product_id.name or c.get('name') or ''
                                                        if extra_price > 0:
                                                            disp_name += f" (+{extra_price:.2f})"
                                                        combo_choices.append({
                                                            'combo_item_id': ci.id,
                                                            'product_id': ci.product_id.id,
                                                            'name': disp_name,
                                                            'extra_price': extra_price,
                                                        })
                                        if combo_choices:
                                            combo_details_str = " + ".join(c['name'] for c in combo_choices)
                                except Exception as err:
                                    _logger.warning("Error verifying combo choices for product %s: %s", prod_id, err)

                            company = booking.company_id or appointment_type.sudo().company_id or (request.env.website and request.env.website.company_id) or request.env.company
                            currency = company.currency_id
                            taxes = product.taxes_id.filtered(lambda t: not t.company_id or t.company_id == company)
                            base_unit_price = float(product.lst_price) + extra_price_total
                            if taxes:
                                tax_calc = taxes.compute_all(base_unit_price, currency=currency, quantity=1, product=product)
                                unit_price_incl = round(tax_calc['total_included'], 2)
                            else:
                                unit_price_incl = round(base_unit_price, 2)

                            preorder_items.append({
                                'booking_id': booking.id,
                                'product_id': product.id,
                                'qty': qty,
                                'price_unit_base': base_unit_price,
                                'price_unit': unit_price_incl,
                                'subtotal': round(qty * unit_price_incl, 2),
                                'combo_details': combo_details_str,
                                'combo_choices': combo_choices,
                                'note': f"Combo Choices: {combo_details_str}" if combo_details_str else "",
                            })

            preorder_lines = request.env['appointment.booking.preorder.line']
            if preorder_items:
                line_create_vals = []
                for it in preorder_items:
                    line_create_vals.append({
                        'booking_id': it['booking_id'],
                        'product_id': it['product_id'],
                        'qty': it['qty'],
                        'price_unit': it['price_unit'],
                        'combo_details': it.get('combo_details') or '',
                        'note': it.get('note') or '',
                    })
                preorder_lines = request.env['appointment.booking.preorder.line'].sudo().create(line_create_vals)
                booking._compute_food_order_info()

            if customer_notes or preorder_items:
                booking._notify_pos_floor()

            # 3. Online Payment: If food items were pre-ordered, route directly to Online Payment!
            if preorder_items and sum(it['subtotal'] for it in preorder_items) > 0:
                request.update_env(su=True)
                company = booking.company_id or appointment_type.sudo().company_id or (request.env.website and request.env.website.company_id) or request.env.company
                if booking.sale_order_id:
                    # Append pre-ordered dishes to existing sale order
                    for it in preorder_items:
                        prod = request.env['product.product'].sudo().browse(it['product_id'])
                        line_desc = prod.display_name
                        if it.get('combo_details'):
                            line_desc += f" ({it['combo_details']})"
                        request.env['sale.order.line'].sudo().create({
                            'order_id': booking.sale_order_id.id,
                            'product_id': prod.id,
                            'name': line_desc,
                            'product_uom_qty': it['qty'],
                            'price_unit': it['price_unit_base'],
                        })
                    return request.redirect(f'/appointment/{booking.id}/payment?token={booking.access_token}')
                else:
                    # Create new sale order for pre-ordered food and redirect to payment
                    so_lines = []
                    for it in preorder_items:
                        prod = request.env['product.product'].sudo().browse(it['product_id'])
                        line_desc = prod.display_name
                        if it.get('combo_details'):
                            line_desc += f" ({it['combo_details']})"
                        so_lines.append((0, 0, {
                            'product_id': prod.id,
                            'name': line_desc,
                            'product_uom_qty': it['qty'],
                            'price_unit': it['price_unit_base'],
                        }))
                    try:
                        partner_id = booking.partner_id.id if booking.partner_id else (request.env.user.partner_id.id if request.env.user else False)
                        if not partner_id:
                            partner_id = request.env.ref('base.public_partner').id
                        SaleOrder = request.env['sale.order'].sudo().with_company(company)
                        warehouse = request.env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
                        pricelist = request.env['product.pricelist'].sudo().search([
                            ('company_id', 'in', (company.id, False)),
                        ], limit=1)
                        so_vals = {
                            'company_id': company.id,
                            'partner_id': partner_id,
                            'state': 'draft',
                            'require_signature': False,
                            'prepayment_percent': 1.0,
                            'order_line': so_lines,
                        }
                        if warehouse:
                            so_vals['warehouse_id'] = warehouse.id
                        if pricelist:
                            so_vals['pricelist_id'] = pricelist.id
                        so = SaleOrder.create(so_vals)
                        booking.sudo().write({
                            'company_id': company.id,
                            'sale_order_id': so.id,
                            'state': 'pending_payment',
                        })
                        return request.redirect(f'/appointment/{booking.id}/payment?token={booking.access_token}')
                    except Exception as e:
                        _logger.error("Could not create sale order for food pre-order payment: %s", e)
                        if preorder_lines:
                            preorder_lines.unlink()
                            booking._compute_food_order_info()

        return response

    @http.route([
        '/appointment/<model("appointment.booking"):booking>/invoice',
        '/appointment/<int:booking_id>/invoice',
        '/appointment/<string:booking_ref>/invoice',
    ], type='http', auth='public', website=True)
    def appointment_booking_invoice(self, booking=None, booking_id=None, booking_ref=None, **kwargs):
        request.update_env(user=SUPERUSER_ID)
        if not booking and booking_id:
            booking = request.env['appointment.booking'].browse(booking_id)
        if not booking and booking_ref:
            try:
                b_id = int(booking_ref.split('-')[-1])
                booking = request.env['appointment.booking'].browse(b_id)
            except (ValueError, IndexError):
                booking = request.env['appointment.booking'].search([
                    ('access_token', '=', kwargs.get('token'))
                ], limit=1)

        if not booking or not booking.exists():
            return request.not_found()

        token = kwargs.get('token')
        if not token or booking.access_token != token:
            return request.not_found()

        so = booking.sale_order_id
        if not so:
            return request.redirect(f'/appointment/manage/{booking.id}?token={booking.access_token}')

        # 1. Read-only lookup for existing posted invoice
        invoice = so.invoice_ids.filtered(lambda inv: inv.state == 'posted')[:1]

        # 2. If a posted invoice exists, render default Odoo invoice PDF slip
        if invoice:
            try:
                pdf_content, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
                    'account.account_invoices', [invoice.id]
                )
                safe_name = (invoice.name or f"INV_{booking.id}").replace('/', '_').replace(' ', '_')
                filename = f"Invoice_{safe_name}.pdf"
                headers = [
                    ('Content-Type', 'application/pdf'),
                    ('Content-Length', len(pdf_content)),
                    ('Content-Disposition', f'inline; filename="{filename}"'),
                ]
                return request.make_response(pdf_content, headers=headers)
            except Exception as e:
                _logger.warning("Could not render account.account_invoices PDF: %s", e)

        # 3. If SO is confirmed/paid, render sale order receipt PDF
        if so.state in ('sale', 'done'):
            try:
                pdf_content, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
                    'sale.action_report_saleorder', [so.id]
                )
                safe_name = (so.name or f"SO_{booking.id}").replace('/', '_').replace(' ', '_')
                filename = f"Order_Receipt_{safe_name}.pdf"
                headers = [
                    ('Content-Type', 'application/pdf'),
                    ('Content-Length', len(pdf_content)),
                    ('Content-Disposition', f'inline; filename="{filename}"'),
                ]
                return request.make_response(pdf_content, headers=headers)
            except Exception as e:
                _logger.warning("Could not render sale.action_report_saleorder PDF: %s", e)

        # 4. If unpaid / draft quotation, redirect to manage page to pay
        return request.redirect(f'/appointment/manage/{booking.id}?token={booking.access_token}')


