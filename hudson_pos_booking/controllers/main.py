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


import hmac
import json
import logging
import random
from datetime import datetime, timedelta
from urllib.parse import quote

from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

from odoo.addons.appointment.controllers.main import AppointmentController, _linked_resources_state


def _get_resource_conflict_ids(resource, env):
    """Return all appointment.resource IDs that conflict with this resource,
    including linked resources and merged POS restaurant tables."""
    res_ids = {resource.id}
    if 'linked_resource_ids' in resource._fields:
        res_ids |= set(resource.linked_resource_ids.ids)
    tables = env['restaurant.table'].sudo().search([
        ('appointment_resource_id', 'in', list(res_ids))
    ])
    if tables:
        merged = tables.get_merged_and_linked_tables()
        res_ids |= set(merged.mapped('appointment_resource_id').ids)
    return res_ids


class PosAppointmentController(AppointmentController):
    """Website booking flow of the POS Table Booking Bridge.

    Everything that used to be customised inside the ``appointment`` module
    (phone-first guest details, Date questions, celebration fields, yearly
    wish links, Email + SMS confirmation, merged-table conflicts) is handled
    here so the stock ``appointment`` module stays untouched.
    """

    _WISH_SESSION_KEY = 'hudson_pos_booking_wish'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_tz(self, appointment_type=None):
        import pytz
        tz_name = None
        if appointment_type and appointment_type.appointment_tz:
            tz_name = appointment_type.appointment_tz
        if not tz_name and appointment_type and appointment_type.company_id.partner_id.tz:
            tz_name = appointment_type.company_id.partner_id.tz
        if not tz_name:
            tz_name = request.env.company.partner_id.tz or request.env.user.tz
        try:
            return pytz.timezone(tz_name or 'Asia/Calcutta')
        except Exception:
            return pytz.timezone('Asia/Calcutta')

    def _get_wish_prefill_context(self, appointment_type, kwargs):
        """Guest details of a previous celebration booking, when the page is
        opened from a yearly wish link (``wish_ref`` + ``wish_token``).
        The link is remembered in the session so calendar navigation keeps it."""
        wish_ref = kwargs.get('wish_ref')
        wish_token = kwargs.get('wish_token')
        stored = request.session.get(self._WISH_SESSION_KEY) or {}
        if not (wish_ref and wish_token) and appointment_type:
            remembered = stored.get(str(appointment_type.id)) or {}
            wish_ref, wish_token = remembered.get('wish_ref'), remembered.get('wish_token')
        if not wish_ref or not wish_token:
            return {}
        try:
            ref_id = int(wish_ref)
        except (ValueError, TypeError):
            return {}
        booking = request.env['appointment.booking'].sudo().browse(ref_id).exists()
        if not booking or not booking.access_token:
            return {}
        if not hmac.compare_digest(str(booking.access_token), str(wish_token)):
            return {}
        if appointment_type:
            stored = dict(stored)
            stored[str(appointment_type.id)] = {'wish_ref': str(booking.id), 'wish_token': str(wish_token)}
            request.session[self._WISH_SESSION_KEY] = stored
        return {
            'wish_ref': str(booking.id),
            'wish_token': str(wish_token),
            'name': booking._get_guest_display_name() or '',
            'email': booking._get_recipient_email() or '',
            'phone': booking._get_recipient_phone() or '',
            'celebrant_name': booking.celebrant_name or '',
            'celebration_type': booking.celebration_event_name if booking.celebration_type else '',
            'occasion_title': booking.occasion_title or '',
            'occasion_date': fields.Date.to_string(booking.occasion_date) if booking.occasion_date else '',
            'party_size': booking.party_size or 1,
        }

    def _should_send_immediate_confirmation(self, appointment_type, booking, kwargs):
        """Food pre-orders are confirmed (Email + SMS) only once paid."""
        import math
        for key, val in kwargs.items():
            if key.startswith('food_qty_') and val:
                try:
                    f_val = float(val)
                    if not math.isinf(f_val) and not math.isnan(f_val) and 1 <= int(f_val) <= 50:
                        return False
                except (ValueError, TypeError, OverflowError):
                    continue
        return booking.state in ('confirmed', 'checked_in')

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @http.route()
    def appointment_preview(self, appointment_type=None, appointment_type_id=None, **kwargs):
        if not appointment_type and appointment_type_id:
            appointment_type = request.env['appointment.type'].sudo().browse(appointment_type_id).exists()
        wish_prefill = self._get_wish_prefill_context(appointment_type, kwargs) if appointment_type else {}
        if wish_prefill and not kwargs.get('party_size') and wish_prefill.get('party_size'):
            kwargs['party_size'] = str(wish_prefill['party_size'])
        res = super().appointment_preview(appointment_type=appointment_type, appointment_type_id=appointment_type_id, **kwargs)
        if hasattr(res, 'qcontext'):
            res.qcontext.update({
                'wish_ref': wish_prefill.get('wish_ref', ''),
                'wish_token': wish_prefill.get('wish_token', ''),
                'wish_prefill': wish_prefill,
            })
            appt = res.qcontext.get('appointment_type') or appointment_type
            if appt and appt.sudo()._hudson_is_resource_event_type():
                # Tables are assigned by the restaurant: customers never get a resource picker.
                res.qcontext['assign_method'] = 'random'
        return res

    @http.route(['/appointment/<model("appointment.type"):appointment_type>/info'], type='http', auth='public', website=True, methods=['GET', 'POST'])
    def appointment_info(self, appointment_type, **kwargs):
        res = super().appointment_info(appointment_type, **kwargs)
        if hasattr(res, 'qcontext'):
            wish_prefill = self._get_wish_prefill_context(appointment_type, kwargs)
            question_prefills = {}
            if wish_prefill:
                for q in appointment_type.sudo().question_ids:
                    role = q.question_role or 'none'
                    if q.is_occasion_date or role == 'occasion_date':
                        question_prefills[q.id] = wish_prefill.get('occasion_date', '')
                    elif role == 'celebrant_name':
                        question_prefills[q.id] = wish_prefill.get('celebrant_name', '')
                    elif role == 'celebration_type':
                        question_prefills[q.id] = wish_prefill.get('celebration_type', '')
                    elif role == 'occasion_title':
                        question_prefills[q.id] = wish_prefill.get('occasion_title', '')
            res.qcontext.update({
                'staff_user_id': kwargs.get('staff_user_id') or '',
                'wish_ref': wish_prefill.get('wish_ref', ''),
                'wish_token': wish_prefill.get('wish_token', ''),
                'wish_prefill': wish_prefill,
                'question_prefills': question_prefills,
            })
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
                pos_cats = getattr(p, 'pos_categ_ids', None) or (getattr(p, 'pos_categ_id', None) and [p.pos_categ_id]) or []
                for cat in pos_cats:
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
                if getattr(p, 'type', '') == 'combo' and hasattr(p, 'combo_ids') and p.combo_ids:
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

    def _hudson_book_appointment(self, appointment_type, **kwargs):
        """Create the website booking (phone mandatory, email optional).

        Replaces the stock submit logic, which requires an email and matches
        guests by email only; it is otherwise the same booking algorithm, plus
        Date questions, celebration fields and merged POS table conflicts.
        """
        date_str = kwargs.get('date')
        time_str = kwargs.get('time')
        name = (kwargs.get('name') or '').strip()
        email = (kwargs.get('email') or '').strip() or False
        phone = (kwargs.get('phone') or '').strip()
        party_size = kwargs.get('party_size', 1)
        error_url = f'/appointment/{appointment_type.id}?error='

        # the phone may also come from a "Phone Number" question, if any
        if not phone:
            for phone_question in appointment_type.sudo().question_ids.filtered(lambda q: q.question_type == 'phone'):
                answer = (kwargs.get(f'question_{phone_question.id}') or '').strip()
                if answer:
                    phone = answer
                    break

        if not date_str or not time_str or not name or not phone:
            return request.redirect(error_url + 'missing_fields')
        try:
            party_size = max(1, int(party_size))
        except (ValueError, TypeError):
            party_size = 1

        try:
            import pytz
            start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            tz = self._get_tz(appointment_type)
            start_dt_utc = tz.localize(start_dt).astimezone(pytz.UTC).replace(tzinfo=None)
            end_dt_utc = start_dt_utc + timedelta(hours=appointment_type.appointment_duration)
        except ValueError:
            return request.redirect(error_url + 'invalid_datetime')

        booking_duration = appointment_type.appointment_duration
        if appointment_type.schedule_type == 'flexible':
            slot_period = next((period for period in appointment_type.sudo()._get_flexible_periods()
                                if period[0] == start_dt_utc), None)
            if not slot_period:
                return request.redirect(error_url + 'invalid_datetime')
            end_dt_utc = slot_period[1]
            booking_duration = (end_dt_utc - start_dt_utc).total_seconds() / 3600

        type_periods, periods_by_user, periods_by_resource = appointment_type.sudo()._get_closing_periods()
        if appointment_type.sudo()._period_overlaps(start_dt_utc, end_dt_utc, type_periods):
            return request.redirect(error_url + 'closed_day')

        # Custom questions (validated before any record is created)
        answers_dict = {}
        for key, val in kwargs.items():
            if key.startswith('question_') and val:
                try:
                    q_id = int(key.replace('question_', '').split('_')[0])
                except ValueError:
                    continue
                answers_dict.setdefault(q_id, []).append(str(val).strip())

        Answer = request.env['appointment.answer'].sudo()
        for req_q in appointment_type.sudo().question_ids.filtered('is_required'):
            if not any(v for v in answers_dict.get(req_q.id, []) if v):
                return request.redirect(error_url + 'missing_fields')

        answer_vals_list = []
        for q_id, vals in answers_dict.items():
            q = request.env['appointment.question'].sudo().browse(q_id)
            if not q.exists():
                continue
            clean_vals = [v for v in vals if v]
            if not clean_vals:
                continue
            answer_vals = {
                'question_id': q.id,
                'value_text': ', '.join(clean_vals),
            }
            if q.question_type == 'date':
                parsed_date = Answer._parse_date_value(clean_vals[0])
                if not parsed_date:
                    return request.redirect(error_url + 'missing_fields')
                answer_vals['value_date'] = parsed_date
                answer_vals['value_text'] = fields.Date.to_string(parsed_date)
            elif q.question_type in ('select', 'radio', 'checkbox'):
                chosen = q.answer_ids.filtered(lambda a: a.name in clean_vals)
                if chosen:
                    answer_vals['value_answer_ids'] = [(6, 0, chosen.ids)]
            answer_vals_list.append((0, 0, answer_vals))

        # Get or create the guest partner (email optional, phone mandatory,
        # never the company / admin partner)
        company = appointment_type.sudo().company_id or request.env.website.company_id or request.env.company
        Partner = request.env['res.partner'].sudo()
        BookingModel = request.env['appointment.booking'].sudo()
        excluded_ids = [1]
        if company and company.partner_id:
            excluded_ids.append(company.partner_id.id)
        comp_scope = [('id', 'not in', excluded_ids), ('company_id', 'in', [False, company.id])]

        partner = Partner.browse()
        if email:
            partner = Partner.search(comp_scope + [('email', '=ilike', email)], limit=1)
        if not partner:
            phone_domain = [('phone', '=', phone)]
            if 'mobile' in Partner._fields:
                phone_domain = ['|', ('phone', '=', phone), ('mobile', '=', phone)]
            partner = Partner.search(comp_scope + phone_domain, limit=1)
            if not partner:
                target_digits = BookingModel._normalize_phone_digits(phone)
                if len(target_digits) >= 7:
                    candidates = Partner.search(comp_scope + [('phone', '!=', False)], order='id desc', limit=200)
                    for cand in candidates:
                        c_digits = BookingModel._normalize_phone_digits(cand.phone)
                        if c_digits and (c_digits == target_digits or c_digits.endswith(target_digits[-10:])
                                         or target_digits.endswith(c_digits[-10:])):
                            partner = cand
                            break
        if not partner:
            partner = Partner.create({'name': name, 'email': email or False, 'phone': phone})
        else:
            p_vals = {}
            if phone and not partner.phone:
                p_vals['phone'] = phone
            if email and not partner.email:
                p_vals['email'] = email
            if p_vals:
                partner.write(p_vals)

        booking_vals = {
            'appointment_type_id': appointment_type.id,
            'start_datetime': start_dt_utc,
            'end_datetime': end_dt_utc,
            'duration': booking_duration,
            'state': 'confirmed',
            'partner_id': partner.id,
            'customer_name': name,
            'customer_phone': phone,
            'customer_email': email or False,
            'party_size': party_size,
            'answer_ids': answer_vals_list,
            'name': f"{appointment_type.name} - {start_dt.strftime('%b %d, %Y %H:%M')}"
        }

        time_limit = (datetime.utcnow() - timedelta(minutes=15)).strftime('%Y-%m-%d %H:%M:%S')
        active_booking_domain = [
            '|',
                ('state', 'in', ['confirmed', 'checked_in']),
                '&', ('state', '=', 'pending_payment'), ('create_date', '>=', time_limit),
        ]

        if appointment_type.booking_target == 'resources' and appointment_type.resource_ids:
            requested_target_id = kwargs.get('staff_user_id')
            if requested_target_id:
                try:
                    requested_target_id = int(requested_target_id)
                except ValueError:
                    requested_target_id = False

            resources_to_check = appointment_type.resource_ids
            if requested_target_id:
                requested_resource = resources_to_check.filtered(lambda r: r.id == requested_target_id)
                if requested_resource:
                    resources_to_check = requested_resource

            conflicts_by_resource = {r.id: _get_resource_conflict_ids(r, request.env) for r in resources_to_check}
            all_r_ids = set(resources_to_check.ids)
            for r_ids in conflicts_by_resource.values():
                all_r_ids |= r_ids
            all_bookings = BookingModel.search([
                ('resource_ids', 'in', list(all_r_ids)),
                ('start_datetime', '<', end_dt_utc),
                ('end_datetime', '>', start_dt_utc),
            ] + active_booking_domain)
            bookings_by_resource = {}
            for r_id, conflict_ids in conflicts_by_resource.items():
                bookings_by_resource[r_id] = all_bookings.filtered(
                    lambda b, ids=conflict_ids: bool(set(b.resource_ids.ids) & ids))

            # Best fit: the free resource leaving the fewest empty seats; a
            # resource combined with its linked resources only when no single
            # one fits. A resource chosen by the customer is kept as is.
            single_candidates = []
            linked_candidates = []
            for position, resource in enumerate(resources_to_check):
                resource_bookings = bookings_by_resource.get(resource.id, BookingModel)
                r_avail = not appointment_type.sudo()._period_overlaps(
                    start_dt_utc, end_dt_utc, periods_by_resource.get(resource.id, []))
                overlapping_party_size = sum(resource_bookings.mapped('party_size'))

                avail_cap = 0
                if overlapping_party_size > 0 and not (resource.shareable or appointment_type.group_booking):
                    r_avail = False
                else:
                    avail_cap = resource.capacity - overlapping_party_size
                own_cap = avail_cap

                linked_free = resource.browse()
                if r_avail:
                    linked_ok, linked_cap, linked_free = _linked_resources_state(
                        appointment_type, resource, start_dt_utc, end_dt_utc, periods_by_resource,
                        lambda linked: sum(all_bookings.filtered(
                            lambda b: linked.id in b.resource_ids.ids).mapped('party_size')))
                    if linked_ok:
                        avail_cap += linked_cap
                    else:
                        r_avail = False

                if not r_avail or party_size > avail_cap:
                    continue
                if requested_target_id:
                    single_candidates.append((0, position, resource | linked_free))
                elif own_cap >= party_size:
                    single_candidates.append((own_cap - party_size, position, resource))
                else:
                    linked_candidates.append((avail_cap - party_size, position, resource | linked_free))

            candidates = single_candidates or linked_candidates
            if not candidates:
                return request.redirect(error_url + 'no_resource_available')
            booking_vals['resource_ids'] = [(6, 0, min(candidates, key=lambda c: c[:2])[2].ids)]

        elif appointment_type.booking_target == 'users' and appointment_type.sudo().user_ids:
            requested_staff_id = kwargs.get('staff_user_id')
            if requested_staff_id:
                try:
                    requested_staff_id = int(requested_staff_id)
                except ValueError:
                    requested_staff_id = False

            existing_user_bookings = BookingModel.search([
                ('appointment_type_id.booking_target', '=', 'users'),
                ('start_datetime', '<', end_dt_utc),
                ('end_datetime', '>', start_dt_utc),
            ] + active_booking_domain)
            users_to_check = appointment_type.sudo().user_ids
            employee_windows = {}
            if appointment_type.employee_schedule:
                employee_windows = appointment_type.sudo()._get_employee_available_windows(
                    users_to_check, start_dt_utc, end_dt_utc)
            busy_by_user = appointment_type.sudo()._get_busy_intervals_by_user(users_to_check, start_dt_utc, end_dt_utc)

            available_users = []
            for u in users_to_check:
                if busy_by_user.get(u.id) or appointment_type.sudo()._period_overlaps(
                        start_dt_utc, end_dt_utc, periods_by_user.get(u.id, [])):
                    continue
                if appointment_type.employee_schedule and not any(
                        window_start <= start_dt_utc and end_dt_utc <= window_end
                        for window_start, window_end in employee_windows.get(u.id, [])):
                    continue
                overlapping_party_size = sum(existing_user_bookings.filtered(
                    lambda b: b.staff_user_id.id == u.id).mapped('party_size'))
                user_cap = u.capacity if 'capacity' in u._fields else appointment_type.capacity
                if overlapping_party_size + party_size > user_cap:
                    continue
                available_users.append(u.id)

            if not available_users:
                return request.redirect(error_url + 'no_user_available')
            if requested_staff_id and appointment_type.assign_method == 'customer':
                if requested_staff_id not in available_users:
                    return request.redirect(error_url + 'user_unavailable')
                booking_vals['staff_user_id'] = requested_staff_id
            else:
                booking_vals['staff_user_id'] = random.choice(available_users)

        if appointment_type.has_payment_step and appointment_type.product_id:
            booking_vals['state'] = 'pending_payment'

        try:
            with request.env.cr.savepoint():
                booking = BookingModel.create(booking_vals)
        except (ValidationError, UserError) as err:
            err_msg = str(err.args[0] if err.args else err)
            return request.redirect(error_url + f'conflict&msg={quote(err_msg)}')

        # Upfront payment (booking fees): stock appointment payment page
        if appointment_type.has_payment_step and appointment_type.product_id:
            so = request.env['sale.order'].sudo().with_company(company).create({
                'company_id': company.id,
                'partner_id': partner.id,
                'state': 'draft',
                'require_signature': False,
                'prepayment_percent': 1.0,
                'order_line': [(0, 0, {
                    'product_id': appointment_type.product_id.id,
                    'name': f"Booking Fees: {appointment_type.name} - {booking.start_datetime.strftime('%b %d, %Y %H:%M')}",
                    'product_uom_qty': 1,
                    'price_unit': appointment_type.product_id.lst_price,
                })]
            })
            booking.sale_order_id = so.id
            return request.redirect(f'/appointment/{booking.id}/payment?token={booking.access_token}')

        if appointment_type.create_opportunity:
            try:
                with request.env.cr.savepoint():
                    request.env['crm.lead'].sudo().with_company(company).create({
                        'company_id': company.id,
                        'name': f"{appointment_type.name} - {partner.name}",
                        'partner_id': partner.id,
                        'email_from': partner.email,
                        'phone': partner.phone,
                        'type': 'opportunity',
                        'description': f"Created from Appointment Booking: {appointment_type.name}\nStart Date: {booking.start_datetime}",
                        'user_id': (booking.staff_user_id or appointment_type.sudo().user_id).id or False,
                    })
            except Exception:
                _logger.warning("Could not create opportunity for booking %s", booking.id, exc_info=True)

        invite_token = kwargs.get('invite_token')
        if invite_token:
            invite = request.env['appointment.invite'].sudo().search([('access_token', '=', invite_token)], limit=1)
            if invite:
                invite.appointment_count += 1

        if booking.state != 'pending_payment' and self._should_send_immediate_confirmation(appointment_type, booking, kwargs):
            booking._send_booking_confirmation_notifications()

        return request.render('appointment.appointment_confirmation', {
            'appointment_type': appointment_type,
            'booking': booking,
            'start_dt': start_dt,
            'user': request.env.user if request.env.user.id != request.env.ref('base.public_user').id else None,
            'partner_name': booking._get_guest_display_name() or name or partner.name,
            'partner_email': booking._get_recipient_email() or '',
            'partner_phone': booking._get_recipient_phone() or '',
            'party_size': booking.party_size,
            'guest_details': booking.calendar_contact_details,
        })

    @http.route()
    def appointment_payment(self, booking_id=None, booking=None, **kwargs):
        """The stock page passes ``assign_token_route='/payment/assign_token'``,
        a route that does not exist in Odoo 20: with a saved card selected the
        payment form then only tries to *assign* the token (404) and never pays.
        Dropping it makes saved cards use the normal token payment flow."""
        res = super().appointment_payment(booking_id=booking_id, booking=booking, **kwargs)
        if hasattr(res, 'qcontext'):
            res.qcontext.pop('assign_token_route', None)
        return res

    @http.route()
    def appointment_cancel(self, booking_id=None, booking=None, **kwargs):
        target = booking or (request.env['appointment.booking'].sudo().browse(booking_id).exists() if booking_id else None)
        was_cancelled = bool(target) and target.sudo().state == 'cancelled'
        res = super().appointment_cancel(booking_id=booking_id, booking=booking, **kwargs)
        if target and not was_cancelled and target.sudo().state == 'cancelled':
            target.sudo()._send_booking_cancellation_sms()
        return res

    @http.route(['/appointment/<model("appointment.type"):appointment_type>/submit'], type='http', auth='public', website=True, methods=['POST'])
    def appointment_submit(self, appointment_type, **kwargs):
        import re
        response = self._hudson_book_appointment(appointment_type, **kwargs)
        booking = None
        if hasattr(response, 'qcontext') and 'booking' in response.qcontext:
            booking = response.qcontext['booking']
        elif hasattr(response, 'location') and '/payment' in (response.location or ''):
            m = re.search(r'/appointment/(\d+)/payment', response.location)
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
                        warehouse = (
                            request.env['stock.warehouse'].sudo().search([('company_id', '=', company.id)], limit=1)
                            if 'stock.warehouse' in request.env
                            else False
                        )
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
                        if warehouse and 'warehouse_id' in SaleOrder._fields:
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
                        if booking.state in ('confirmed', 'checked_in') and not booking.confirmation_sent:
                            booking.sudo()._send_booking_confirmation_notifications()
            elif booking.state in ('confirmed', 'checked_in') and not booking.confirmation_sent:
                booking.sudo()._send_booking_confirmation_notifications()

        return response

    @http.route([
        '/appointment/<int:booking_id>/invoice',
        '/appointment/<string:booking_ref>/invoice',
    ], type='http', auth='public', website=True)
    def appointment_booking_invoice(self, booking_id=None, booking_ref=None, **kwargs):
        request.update_env(user=SUPERUSER_ID)
        booking = None
        if booking_id:
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


