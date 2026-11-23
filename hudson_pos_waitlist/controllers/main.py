# -*- coding: utf-8 -*-
import hashlib
import ipaddress
import logging
import re
from werkzeug.exceptions import NotFound

from odoo import http, _
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools.misc import hmac
try:
    from odoo.http.stream import content_disposition
except ImportError:
    from odoo.http import content_disposition

from ..models.pos_waitlist_entry import ANY_FLOOR, SHARE_TABLE_SELECTION, MAX_GUEST_NAME, MAX_GUEST_NOTE

_logger = logging.getLogger(__name__)

# Shape of tokens made by pos.config._generate_waitlist_token (secrets.token_urlsafe).
# Anything else is rejected before touching the database.
_TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{16,64}$')
# Shape of pos.waitlist.entry access tokens (secrets.token_urlsafe(32) -> 43 chars).
_ACCESS_TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{32,64}$')

# The URL itself is the secret: never cache it, index it, or leak it to third-party hosts.
_PUBLIC_PAGE_HEADERS = [
    ('Cache-Control', 'no-store, max-age=0'),
    ('X-Robots-Tag', 'noindex, nofollow'),
    ('Referrer-Policy', 'same-origin'),
]

# Queue numbers restart daily; a day is plenty for the "Track My Waitlist" cookie.
_TRACKING_COOKIE_MAX_AGE = 24 * 60 * 60

# Find My Place: lookups allowed per client IP within the window (not shown to guests).
_LOOKUP_RATE_LIMIT = 10
_LOOKUP_RATE_WINDOW = 10 * 60  # seconds

# Form fields read from the POST body. Everything else is ignored.
# No table field: guests pick a floor / area only, the host picks the table.
_JOIN_FORM_FIELDS = ('guest_name', 'phone', 'phone_country', 'party_size', 'preferred_floor', 'share_table',
                     'guest_note')


class PosWaitlistController(http.Controller):

    def _get_pos_config_by_token(self, token):
        """Active pos.config owning ``token``, or an empty recordset.

        The token is the only input trusted from the browser; no record IDs are accepted.
        """
        PosConfig = request.env['pos.config'].sudo()
        if not token or not _TOKEN_RE.match(token):
            return PosConfig
        return PosConfig.search([('waitlist_token', '=', token)], limit=1)

    def _unavailable(self):
        """Same page and status for every unknown / disabled / invalid token: reveals nothing."""
        return request.render('hudson_pos_waitlist.waitlist_unavailable', {
            'page_title': _("Waitlist Unavailable"),
        }, status=404, headers=_PUBLIC_PAGE_HEADERS)

    # ------------------------------------------------------------------
    # "Track My Waitlist" on the join form
    # The browser keeps the entry's existing access_token in an HttpOnly cookie, one per POS,
    # set when the guest joins / is recovered / opens their status page. The form only shows
    # the link when the server confirms that entry is still active for this very POS.
    # ------------------------------------------------------------------
    @staticmethod
    def _tracking_cookie_name(pos_config):
        digest = hashlib.sha256((pos_config.waitlist_token or '').encode()).hexdigest()[:16]
        return f'hudson_wl_{digest}'

    def _remember_entry(self, response, entry):
        """Store ``entry``'s access token on the guest's browser for its POS."""
        secure = (request.httprequest.scheme == 'https'
                  or request.httprequest.headers.get('X-Forwarded-Proto', '').startswith('https'))
        response.set_cookie(
            self._tracking_cookie_name(entry.config_id), entry.access_token,
            max_age=_TRACKING_COOKIE_MAX_AGE, path='/waitlist/',
            httponly=True, samesite='Lax', secure=secure)
        return response

    def _forget_entry(self, response, pos_config):
        """Drop this browser's tracking cookie for ``pos_config`` (the visit is over)."""
        response.delete_cookie(self._tracking_cookie_name(pos_config), path='/waitlist/')
        return response

    def _get_tracking_entry(self, pos_config):
        access_token = request.httprequest.cookies.get(self._tracking_cookie_name(pos_config))
        Entry = request.env['pos.waitlist.entry'].sudo()
        if not access_token or not _ACCESS_TOKEN_RE.match(access_token):
            return Entry.browse()
        return Entry._get_active_tracking_entry(pos_config, access_token)

    def _get_seated_entry(self, pos_config):
        """This browser's remembered visit for ``pos_config`` if the guest is seated and still
        at their table, else empty."""
        access_token = request.httprequest.cookies.get(self._tracking_cookie_name(pos_config))
        Entry = request.env['pos.waitlist.entry'].sudo()
        if not access_token or not _ACCESS_TOKEN_RE.match(access_token):
            return Entry.browse()
        return Entry._get_seated_tracking_entry(pos_config, access_token)

    def _render_join_form(self, pos_config, restaurant_token, values=None, errors=None, status=200,
                          find=None):
        tags = request.env['pos.waitlist.tag'].sudo().search([])
        Entry = request.env['pos.waitlist.entry'].sudo()
        # Read on every request from the POS's current active floors: new / renamed floors show
        # up without regenerating the QR code.
        floor_options = Entry._public_floor_options(pos_config)
        tracking_entry = self._get_tracking_entry(pos_config)
        response = request.render('hudson_pos_waitlist.waitlist_join_page', {
            # Find My Place panel: {'open': bool, 'phone': str, 'error': str}
            'find': find or {},
            'find_action': f'/waitlist/join/{restaurant_token}/find',
            'tracking': tracking_entry and {
                'url': f'/waitlist/s/{tracking_entry.access_token}',
                'token': tracking_entry.token,
                'state_label': tracking_entry._public_status()['state_label'],
            },
            'page_title': _("Join Waitlist"),
            'restaurant_name': pos_config.name,
            'company': pos_config.company_id,
            'form_action': f'/waitlist/join/{restaurant_token}',
            'values': values or {'preferred_floor': ANY_FLOOR, 'share_table': 'private', 'tags': []},
            # Country picker for the phone number (ISO codes only); the restaurant's country first.
            'phone_countries': Entry._public_phone_countries(),
            'default_phone_country': Entry._phone_region(pos_config),
            'errors': errors or [],
            # Any Floor + this POS's own floors. Hidden when the POS has no floor plan.
            'floor_options': floor_options if len(floor_options) > 1 else [],
            'share_table_options': SHARE_TABLE_SELECTION,
            'tags': [(t.code, t.name) for t in tags],
            # 0 = no limit. The server applies the same limit on submit.
            'max_party_size': pos_config._waitlist_party_size_limit(),
            'max_guest_name': MAX_GUEST_NAME,
            'max_guest_note': MAX_GUEST_NOTE,
        }, status=status, headers=_PUBLIC_PAGE_HEADERS)
        if not tracking_entry and request.httprequest.cookies.get(self._tracking_cookie_name(pos_config)):
            # The remembered visit is closed (left, cancelled, no show, completed) or unknown:
            # it is never offered again. A new visit starts from this form as a new entry.
            self._forget_entry(response, pos_config)
        return response

    @http.route('/waitlist/join/<string:restaurant_token>', type='http', auth='public',
                methods=['GET'], website=False, sitemap=False)
    def waitlist_join(self, restaurant_token, **kwargs):
        """Public Join Waitlist form opened by scanning a restaurant's QR Self Join code."""
        pos_config = self._get_pos_config_by_token(restaurant_token)
        if not pos_config or not pos_config.enable_qr_self_join:
            _logger.info("QR Self Join unavailable (%s token)", 'disabled' if pos_config else 'unknown')
            return self._unavailable()
        if not kwargs.get('new'):
            # Seated and still at the table: Back from the status page (or scanning the QR again)
            # shows the guest's own status, not an empty join form. "Join the waitlist again"
            # on the status page passes ?new=1 to start a new visit on purpose.
            seated = self._get_seated_entry(pos_config)
            if seated:
                return request.redirect(f'/waitlist/s/{seated.access_token}', code=303, local=True)
        return self._render_join_form(pos_config, restaurant_token)

    # csrf=False: guests are anonymous and their session may be reset between GET and POST by
    # the multi-database resolver (hudson_kitchen_display), which would reject every submit.
    # The POST only ever creates a waitlist entry for the POS named in the URL token, with
    # fully server-validated values; a forged cross-site POST gains nothing a direct one does not.
    @http.route('/waitlist/join/<string:restaurant_token>', type='http', auth='public',
                methods=['POST'], website=False, sitemap=False, csrf=False)
    def waitlist_join_submit(self, restaurant_token, **post):
        pos_config = self._get_pos_config_by_token(restaurant_token)
        if not pos_config or not pos_config.enable_qr_self_join:
            return self._unavailable()

        values = {key: post.get(key, '') for key in _JOIN_FORM_FIELDS}
        values['tags'] = request.httprequest.form.getlist('tags')
        if post.get('website'):
            # Honeypot field hidden from humans: silently show the form again for bots.
            return self._render_join_form(pos_config, restaurant_token, values)

        Entry = request.env['pos.waitlist.entry'].sudo()
        try:
            entry, created = Entry._join_from_qr(pos_config, values)
        except ValidationError as e:
            errors = [line for line in str(e.args[0]).split('\n') if line]
            return self._render_join_form(pos_config, restaurant_token, values, errors, status=400)

        _logger.info("Waitlist %s %s via QR for POS %s", entry.token,
                     'created' if created else 'recovered', pos_config.id)
        # Post/Redirect/Get: refreshing the status page never re-submits the form.
        url = f'/waitlist/s/{entry.access_token}'
        if not created:
            url += '?existing=1'
        return self._remember_entry(request.redirect(url, code=303, local=True), entry)

    # ------------------------------------------------------------------
    # Find My Place: recover an active entry on a new phone / browser
    # ------------------------------------------------------------------
    @staticmethod
    def _client_ip():
        """Best-effort client IP for rate limiting.

        With proxy_mode on, ProxyFix already put the client in remote_addr. Without it (e.g. the
        dev tunnel / a local reverse proxy) every guest arrives from loopback, which would make
        the limit global; then the right-most X-Forwarded-For hop is used: it is the one added by
        that local proxy itself, so a client cannot forge it by sending its own header.
        """
        httpreq = request.httprequest
        ip = httpreq.remote_addr or ''
        try:
            local = ipaddress.ip_address(ip).is_loopback or ipaddress.ip_address(ip).is_private
        except ValueError:
            local = False
        forwarded = httpreq.headers.get('X-Forwarded-For', '')
        if local and forwarded:
            ip = forwarded.split(',')[-1].strip()[:64] or ip
        return ip or 'unknown'

    def _lookup_rate_key(self):
        """HMAC of the client IP: neither the IP nor the phone number is ever stored."""
        return hmac(request.env(su=True), 'hudson-waitlist-find-my-place', self._client_ip())

    # csrf=False for the same reason as the join POST. The lookup creates nothing and only
    # ever searches the POS named in the URL token.
    @http.route('/waitlist/join/<string:restaurant_token>/find', type='http', auth='public',
                methods=['POST'], website=False, sitemap=False, csrf=False)
    def waitlist_find_my_place(self, restaurant_token, **post):
        pos_config = self._get_pos_config_by_token(restaurant_token)
        if not pos_config or not pos_config.enable_qr_self_join:
            return self._unavailable()

        phone = (post.get('phone') or '')[:64]
        country = (post.get('phone_country') or '')[:8]
        find = {'open': True, 'phone': phone, 'phone_country': country}
        if post.get('website'):
            # Honeypot: bots get the panel back with nothing revealed.
            return self._render_join_form(pos_config, restaurant_token, find=find)

        Attempt = request.env['pos.waitlist.lookup.attempt'].sudo()
        if not Attempt._register_attempt(self._lookup_rate_key(), _LOOKUP_RATE_LIMIT, _LOOKUP_RATE_WINDOW):
            _logger.info("Waitlist Find My Place rate limit hit for POS %s", pos_config.id)
            find['error'] = _("Too many attempts. Please try again in a few minutes.")
            return self._render_join_form(pos_config, restaurant_token, find=find, status=429)

        Entry = request.env['pos.waitlist.entry'].sudo()
        try:
            entry = Entry._find_my_place(pos_config, phone, country or None)
        except ValidationError as e:
            find['error'] = str(e.args[0])
            return self._render_join_form(pos_config, restaurant_token, find=find, status=400)
        if not entry:
            find['error'] = _("No active waitlist entry found for this number.")
            return self._render_join_form(pos_config, restaurant_token, find=find)

        _logger.info("Waitlist %s recovered via Find My Place for POS %s", entry.token, pos_config.id)
        return self._remember_entry(
            request.redirect(f'/waitlist/s/{entry.access_token}?existing=1', code=303, local=True), entry)

    def _get_entry_by_access_token(self, access_token):
        Entry = request.env['pos.waitlist.entry'].sudo()
        if not access_token or not _ACCESS_TOKEN_RE.match(access_token):
            return Entry.browse()
        return Entry._get_by_access_token(access_token)

    @http.route('/waitlist/s/<string:access_token>', type='http', auth='public',
                methods=['GET'], website=False, sitemap=False)
    def waitlist_status(self, access_token, existing=None, **kwargs):
        """Track My Waitlist: the guest's own entry, reachable only through its random token."""
        entry = self._get_entry_by_access_token(access_token)
        if not entry:
            return self._unavailable()
        status = entry._public_status()
        config = entry.config_id
        response = request.render('hudson_pos_waitlist.waitlist_status_page', {
            'page_title': _("Track My Waitlist"),
            'restaurant_name': status['restaurant_name'],
            'company': entry.config_id.company_id,
            'status': status,
            'existing': bool(existing),
            # Live updates only while waiting: a closed page (Seated included) never polls.
            'status_url': f'/waitlist/s/{access_token}' if status['active'] else False,
            # A closed visit (Seated, Left, Cancelled, No Show) is never reopened: the guest
            # goes back to the restaurant's normal QR join form, which creates a new visit.
            'join_url': (f'/waitlist/join/{config.waitlist_token}?new=1'
                         if config.enable_qr_self_join and config.waitlist_token else False),
        }, headers=_PUBLIC_PAGE_HEADERS)
        if status['active'] or (entry.state == 'seated' and entry._seating_active()):
            # Waiting, or seated and still at the table: the join form sends this browser back
            # here (see waitlist_join).
            # Opening the link on another device makes that device's form show it too.
            self._remember_entry(response, entry)
        elif request.httprequest.cookies.get(self._tracking_cookie_name(config)) == access_token:
            # This closed visit is no longer this browser's current one.
            self._forget_entry(response, config)
        return response

    @http.route('/waitlist/s/<string:access_token>/json', type='http', auth='public',
                methods=['GET'], website=False, sitemap=False)
    def waitlist_status_json(self, access_token, **kwargs):
        """Polled by the status page to refresh state / estimated wait without reloading.

        Only a waiting entry is tracked. Once it is closed (Seated, Cancelled, Left, No Show) the
        answer is ``410 Gone`` carrying the final state once more (so the page that was polling
        shows "Seated - Table 4"), and the page stops: tracking for that visit has ended.
        """
        entry = self._get_entry_by_access_token(access_token)
        if not entry:
            raise NotFound()
        status = entry._public_status()
        return request.make_json_response(status, headers=_PUBLIC_PAGE_HEADERS,
                                          status=200 if status['active'] else 410)

    def _qr_png(self, restaurant_token):
        """Stored QR PNG of an enabled POS, or 404."""
        pos_config = self._get_pos_config_by_token(restaurant_token)
        if not pos_config or not pos_config.enable_qr_self_join or not pos_config.qr_code_image:
            raise NotFound()
        return pos_config, pos_config.qr_code_image.content

    @http.route('/waitlist/qr/<string:restaurant_token>/download', type='http', auth='public', sitemap=False)
    def waitlist_qr_download(self, restaurant_token, **kwargs):
        pos_config, png = self._qr_png(restaurant_token)
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', pos_config.name or 'Restaurant')
        return request.make_response(png, headers=[
            ('Content-Type', 'image/png'),
            ('Content-Disposition', content_disposition(f"QR_Self_Join_{safe_name}.png")),
            ('Cache-Control', 'no-cache'),
        ])

    @http.route('/waitlist/qr/<string:restaurant_token>/image', type='http', auth='public', sitemap=False)
    def waitlist_qr_image(self, restaurant_token, **kwargs):
        _pos_config, png = self._qr_png(restaurant_token)
        return request.make_response(png, headers=[
            ('Content-Type', 'image/png'),
            ('Cache-Control', 'no-cache'),
        ])
