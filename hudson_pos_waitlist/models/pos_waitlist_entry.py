# -*- coding: utf-8 -*-
"""Waitlist entries created by guests through the QR Self Join page (and later by the POS).

Concurrency model
-----------------
Odoo runs every request in a REPEATABLE READ transaction. Each new entry takes its
queue number with an ``UPDATE`` on one ``pos_waitlist_counter`` row per POS and day.
Two simultaneous joins for the same POS therefore touch the same row: the second one
waits, then fails with a serialization error as soon as the first commits, and Odoo's
HTTP layer replays it with a fresh snapshot. On replay it sees the first entry, so a
double-click or a repeated POST recovers that entry instead of creating another one.
The partial unique index on (config, phone) for active states is the last-resort guard.
"""
import hashlib
import re
import secrets
from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# Only a waiting guest is "on the waitlist". Seated / cancelled / left / no show close the visit:
# the same phone can join again later (each visit is its own entry and W-number).
ACTIVE_STATES = ('waiting',)
DONE_STATES = ('seated', 'cancelled', 'left', 'no_show')

# Host actions allowed from the POS Waitlist screen (current state -> allowed next states).
# Enforced server-side for every non-manager write, not just by the POS buttons.
STATE_TRANSITIONS = {
    'waiting': ('seated', 'cancelled', 'left', 'no_show'),
}

STATE_SELECTION = [
    ('waiting', 'Waiting'),
    ('seated', 'Seated'),
    ('cancelled', 'Cancelled'),
    ('left', 'Left'),
    ('no_show', 'No Show'),
]
# Public join form value for "no floor restriction". Real floors are posted as an opaque
# per-POS key (see ``_floor_public_key``), never as a database id.
ANY_FLOOR = 'any'
SHARE_TABLE_SELECTION = [
    ('private', 'Private table only'),
    ('share', "I'm willing to share a table"),
]
SHARE_TABLE_SHORT = {'private': 'Private table', 'share': 'Can share'}

# Table matching for a waitlist guest (see ``_match_tables``). The host may pick a table
# with a SELECTABLE status; the others are shown for information only.
MATCH_OK = 'match'            # free and big enough, on an allowed floor
MATCH_SHARED = 'shared'       # in use, but enough free seats for a guest willing to share
MATCH_TOO_SMALL = 'too_small'  # free, on an allowed floor, fewer seats than the party
MATCH_BUSY = 'busy'           # open order / just given to another guest
MATCH_OTHER_FLOOR = 'other_floor'  # not on the guest's preferred floor
SELECTABLE_MATCHES = (MATCH_OK, MATCH_SHARED, MATCH_TOO_SMALL)
_MATCH_RANK = {MATCH_OK: 0, MATCH_SHARED: 1, MATCH_TOO_SMALL: 2, MATCH_BUSY: 3, MATCH_OTHER_FLOOR: 4}
SOURCE_SELECTION = [
    ('qr', 'QR Self Join'),
    ('pos', 'POS / Host'),
]

# A guest seated from the waitlist holds their table until the table's POS order reaches the
# server (from then on the standard "draft order on this table" rule applies), and at most this
# long when no order is ever opened (e.g. the guest walked away before ordering).
TABLE_HOLD_MINUTES = 30

TOKEN_PREFIX = 'W-'
MAX_PARTY_SIZE = 50
MAX_GUEST_NAME = 80
MAX_PHONE_CHARS = 32
MIN_PHONE_DIGITS = 6
MAX_PHONE_DIGITS = 15
_PHONE_ALLOWED_RE = re.compile(r'^\+?[0-9\s().\-/]+$')

# Bus events sent on the POS config channel (pos.bus.mixin._notify).
EVENT_CREATED = 'waitlist_created'
EVENT_UPDATED = 'waitlist_updated'
# Bus event for the backend Waitlist menu (sent on the POS User group channel).
EVENT_BACKEND = 'hudson_waitlist_changed'

# Fields the POS / host screens receive. Never includes access_token.
_POS_FIELDS = (
    'token', 'guest_name', 'phone', 'party_size', 'share_table',
    'source', 'state', 'join_time', 'quoted_wait',
)
# Writing any of these refreshes every open POS of the entry's config.
_POS_NOTIFY_FIELDS = set(_POS_FIELDS) | {'tag_ids', 'preferred_floor_id', 'table_id'}


def normalize_phone(phone):
    """Digits only, used to match the same guest on the same POS. Not an identity."""
    digits = re.sub(r'\D', '', phone or '')
    if digits.startswith('00'):
        digits = digits[2:]
    return digits


class PosWaitlistTag(models.Model):
    _name = 'pos.waitlist.tag'
    _description = 'Waitlist Tag'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        copy=False,
        help="Stable value posted by the public join form. Internal IDs are never exposed. "
             "Generated from the name when left empty; renaming a tag keeps its code.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint('unique (code)', 'Tag code must be unique.')

    @api.model
    def _unique_code(self, name):
        base = re.sub(r'[^a-z0-9]+', '_', (name or '').lower()).strip('_')[:40] or 'tag'
        code, n = base, 1
        Tag = self.with_context(active_test=False).sudo()
        while Tag.search_count([('code', '=', code)], limit=1):
            n += 1
            code = f'{base}_{n}'
        return code

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('code'):
                vals['code'] = self._unique_code(vals.get('name'))
        return super().create(vals_list)

    def write(self, vals):
        if 'code' in vals and not vals['code']:
            del vals['code']  # never blank out the value the public form posts
        return super().write(vals)


class PosWaitlistLookupAttempt(models.Model):
    """One row per Find My Place lookup, used only for per-IP rate limiting.

    Stores an HMAC of the client IP (never the IP or the phone number). Rows older than
    a day are removed by the autovacuum.
    """
    _name = 'pos.waitlist.lookup.attempt'
    _description = 'Waitlist Find My Place Attempt'
    _log_access = False

    key = fields.Char(required=True, index=True)
    attempt_time = fields.Datetime(required=True, index=True, default=fields.Datetime.now)

    @api.model
    def _register_attempt(self, key, limit, window_seconds):
        """Record one attempt for ``key``; ``False`` (and nothing recorded) when over ``limit``."""
        since = fields.Datetime.now() - timedelta(seconds=window_seconds)
        Attempt = self.sudo()
        if Attempt.search_count([('key', '=', key), ('attempt_time', '>=', since)], limit=limit) >= limit:
            return False
        Attempt.create({'key': key})
        return True

    @api.autovacuum
    def _gc_lookup_attempts(self):
        self.sudo().search([('attempt_time', '<', fields.Datetime.now() - timedelta(days=1))]).unlink()


class PosWaitlistCounter(models.Model):
    """One row per POS and business day; holds the last W-number handed out.

    Rows are only ever touched with SQL in ``PosWaitlistEntry._next_queue_number``.
    """
    _name = 'pos.waitlist.counter'
    _description = 'Waitlist Queue Counter'
    _log_access = False

    config_id = fields.Many2one('pos.config', required=True, ondelete='cascade', index=True)
    day = fields.Date(required=True)
    last_number = fields.Integer(required=True, default=0)

    _config_day_unique = models.Constraint('unique (config_id, day)', 'One counter per POS and day.')


class PosWaitlistEntry(models.Model):
    _name = 'pos.waitlist.entry'
    _description = 'Waitlist Entry'
    _order = 'join_time, id'
    _rec_name = 'token'
    # An entry always belongs to its POS's company: never accept a POS of another company.
    _check_company_auto = True

    token = fields.Char(
        string="Queue Token", readonly=True, copy=False, index=True,
        help="Human-readable number shown to the guest and the host, e.g. W-014. "
             "Restarts at W-001 every business day for each POS.")
    sequence_number = fields.Integer(readonly=True, copy=False)
    queue_date = fields.Date(readonly=True, copy=False, index=True)

    guest_name = fields.Char(required=True)
    phone = fields.Char(required=True)
    phone_normalized = fields.Char(readonly=True, index=True)
    party_size = fields.Integer(required=True, default=2)
    preferred_floor_id = fields.Many2one(
        'restaurant.floor', string="Preferred Floor / Area", ondelete='set null', index='btree_not_null',
        help="Floor of this POS the guest asked for. Empty = Any Floor (every active floor of the POS).")
    share_table = fields.Selection(SHARE_TABLE_SELECTION, string="Table Sharing",
                                   required=True, default='private')
    tag_ids = fields.Many2many('pos.waitlist.tag', string="Tags")

    config_id = fields.Many2one('pos.config', string="Point of Sale", required=True,
                                ondelete='cascade', index=True, check_company=True)
    company_id = fields.Many2one('res.company', required=True, index=True,
                                 default=lambda self: self.env.company)
    source = fields.Selection(SOURCE_SELECTION, required=True, default='pos')
    state = fields.Selection(STATE_SELECTION, required=True, default='waiting', index=True)
    join_time = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now)
    end_time = fields.Datetime(readonly=True, help="When the entry left the active queue.")
    quoted_wait = fields.Integer(
        string="Quoted Wait (min)",
        help="Estimated wait quoted to the guest when they joined, in minutes.")

    table_id = fields.Many2one(
        'restaurant.table', string="Table", readonly=True, copy=False, index='btree_not_null',
        ondelete='set null', help="Existing POS table the guest was seated at.")

    access_token = fields.Char(
        readonly=True, copy=False, groups='point_of_sale.group_pos_manager',
        help="Random secret in the guest's Track My Waitlist link (/waitlist/s/<token>).")

    position = fields.Integer(compute='_compute_position',
                              help="Place among waiting guests of this POS (1 = next). 0 when not waiting.")

    _access_token_unique = models.Constraint('unique (access_token)', 'Access token must be unique.')
    _token_per_day_unique = models.UniqueIndex(
        '(config_id, queue_date, sequence_number)',
        'This queue number was already used today for this Point of Sale.')
    _one_active_per_phone = models.UniqueIndex(
        "(config_id, phone_normalized) WHERE state = 'waiting'",
        'This phone number already has an active waitlist entry for this Point of Sale.')
    _party_size_positive = models.Constraint('CHECK (party_size > 0)', 'Party size must be positive.')

    @api.constrains('preferred_floor_id', 'config_id')
    def _check_preferred_floor_belongs_to_config(self):
        for entry in self.sudo():
            if entry.preferred_floor_id and entry.preferred_floor_id not in entry.config_id.floor_ids:
                raise ValidationError(_(
                    "Floor %(floor)s is not a floor of %(pos)s.",
                    floor=entry.preferred_floor_id.name, pos=entry.config_id.name))

    @api.constrains('table_id', 'config_id')
    def _check_table_belongs_to_config(self):
        """The table must be on one of the entry's own POS floors.

        restaurant.table has no company_id, so check_company cannot cover it; without this a
        direct write of table_id could hold another POS's (or company's) table.
        """
        for entry in self.sudo():
            if entry.table_id and entry.table_id.floor_id not in entry.config_id.floor_ids:
                raise ValidationError(_(
                    "Table %(table)s is not on a floor of %(pos)s.",
                    table=entry.table_id.table_number, pos=entry.config_id.name))

    # ------------------------------------------------------------------
    # Queue position (never stored)
    # ------------------------------------------------------------------
    def _compute_position(self):
        waiting = self.filtered(lambda e: e.state == 'waiting' and e.id)
        (self - waiting).position = 0
        for entry in waiting:
            entry.position = self._waiting_ahead_count(entry.config_id, entry.join_time, entry.id) + 1

    @api.model
    def _waiting_ahead_count(self, config, join_time=None, entry_id=None):
        """Waiting entries of ``config`` queued before (join_time, entry_id); all of them without join_time."""
        domain = [('config_id', '=', config.id), ('state', '=', 'waiting')]
        if join_time:
            domain += ['|', ('join_time', '<', join_time),
                       '&', ('join_time', '=', join_time), ('id', '<', entry_id or 0)]
        return self.sudo().search_count(domain)

    # ------------------------------------------------------------------
    # Estimated wait (deliberately simple; override to improve)
    # ------------------------------------------------------------------
    @api.model
    def _estimate_wait_minutes(self, config):
        """The one place the customer-facing estimate comes from: the POS's Average Waiting Time.

        Deliberately the configured value as is, the same for every waiting guest. It is
        never multiplied by the queue position, so the guest cannot infer their place in line.
        """
        return max(config.sudo().waitlist_minutes_per_party or 0, 1)

    def _get_estimated_wait(self):
        """Estimated average wait for this entry: the POS setting while waiting, else 0."""
        self.ensure_one()
        if self.state != 'waiting':
            return 0
        return self._estimate_wait_minutes(self.config_id)

    # ------------------------------------------------------------------
    # Numbering
    # ------------------------------------------------------------------
    @api.model
    def _business_tz_name(self, config):
        """Timezone of the restaurant, identical for every caller.

        Never the current user's: a guest (public user) and a host (POS user) joining at the
        same moment must land on the same business day, or both would get W-001.
        Company address tz, else the main administrator's tz, else UTC.
        """
        admin = self.env.ref('base.user_admin', raise_if_not_found=False)
        return (config.sudo().company_id.partner_id.tz
                or (admin and admin.sudo().tz)
                or 'UTC')

    @api.model
    def _business_day(self, config):
        tz_name = self._business_tz_name(config)
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            tz = pytz.utc
        return pytz.utc.localize(datetime.utcnow()).astimezone(tz).date()

    @api.model
    def _next_queue_number(self, config, day):
        """Atomically take the next number for ``config`` on ``day``.

        The UPDATE is also the per-POS lock described in the module docstring.
        """
        cr = self.env.cr
        self.env['pos.waitlist.counter'].flush_model()
        cr.execute("""
            INSERT INTO pos_waitlist_counter (config_id, day, last_number)
            VALUES (%s, %s, 0)
            ON CONFLICT (config_id, day) DO NOTHING
        """, (config.id, day))
        cr.execute("""
            UPDATE pos_waitlist_counter
               SET last_number = last_number + 1
             WHERE config_id = %s AND day = %s
         RETURNING last_number
        """, (config.id, day))
        number = cr.fetchone()[0]
        self.env['pos.waitlist.counter'].invalidate_model()
        return number

    @api.model
    def _format_token(self, number):
        return f"{TOKEN_PREFIX}{number:03d}"

    @api.model
    def _generate_access_token(self):
        return secrets.token_urlsafe(32)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        Config = self.env['pos.config'].sudo()
        for vals in vals_list:
            config = Config.browse(vals['config_id'])
            # Always the POS's company: a caller-supplied company_id cannot move the entry
            # out of the company whose record rules protect it.
            vals['company_id'] = config.company_id.id
            if vals.get('phone'):
                vals['phone_normalized'] = normalize_phone(vals['phone'])
            if not vals.get('access_token'):
                vals['access_token'] = self._generate_access_token()
            if not vals.get('token'):
                day = self._business_day(config)
                number = self._next_queue_number(config, day)
                vals.update(queue_date=day, sequence_number=number, token=self._format_token(number))
        entries = super().create(vals_list)
        entries._notify_pos(EVENT_CREATED)
        return entries

    def write(self, vals):
        if 'state' in vals:
            self._check_state_transition(vals['state'])
        if 'phone' in vals:
            vals['phone_normalized'] = normalize_phone(vals['phone'])
        if vals.get('state') in DONE_STATES and 'end_time' not in vals:
            vals['end_time'] = fields.Datetime.now()
        elif vals.get('state') in ACTIVE_STATES:
            vals['end_time'] = False
        res = super().write(vals)
        if set(vals) & _POS_NOTIFY_FIELDS:
            # Positions of the other waiting guests change too: the POS reloads the queue.
            self._notify_pos(EVENT_UPDATED)
        return res

    # ------------------------------------------------------------------
    # QR Self Join
    # ------------------------------------------------------------------
    @api.model
    def _waitlist_floors(self, config):
        """Floors a guest of ``config`` may prefer: the POS's active floors with a seatable table."""
        tables = self._seatable_tables(config)
        return tables.floor_id.sorted(lambda f: (f.sequence, f.id))

    @api.model
    def _floor_public_key(self, config, floor):
        """Opaque value the public join form posts for ``floor``.

        Derived from the secret POS token, so it reveals no database id and is only valid
        for this POS: a key copied from another restaurant's form matches nothing here.
        """
        raw = f"{config.sudo().waitlist_token or ''}:{floor.id}".encode()
        return 'f' + hashlib.sha256(raw).hexdigest()[:16]

    @api.model
    def _public_floor_options(self, config):
        """``[(key, label)]`` for the join form: Any Floor first, then the POS floors."""
        floors = self._waitlist_floors(config)
        return [(ANY_FLOOR, _("Any Floor"))] + [(self._floor_public_key(config, f), f.name) for f in floors]

    @api.model
    def _floor_from_public_key(self, config, key):
        """``(floor, ok)``: the floor of ``config`` behind ``key``; empty floor for Any Floor."""
        Floor = self.env['restaurant.floor']
        if not key or key == ANY_FLOOR:
            return Floor, True
        for floor in self._waitlist_floors(config):
            if self._floor_public_key(config, floor) == key:
                return floor, True
        return Floor, False

    @api.model
    def _validate_join_values(self, values, config=None):
        """Clean and validate raw form values. Returns a dict ready for ``create``.

        Raises ValidationError with a guest-facing message. Nothing from the browser is
        trusted: selection values and tags are checked against server-side lists, and the
        preferred floor must be one of ``config``'s own floors (posted as an opaque key).
        """
        errors = []
        guest_name = ' '.join((values.get('guest_name') or '').split())
        if not guest_name:
            errors.append(_("Please enter your name."))
        elif len(guest_name) > MAX_GUEST_NAME:
            errors.append(_("Name is too long."))

        phone, phone_error = self._clean_phone(values.get('phone'))
        if phone_error:
            errors.append(phone_error)

        raw_size = values.get('party_size')
        raw_size = str(raw_size).strip() if raw_size is not None else ''
        party_size = int(raw_size) if raw_size.isdigit() else 0
        if not 1 <= party_size <= MAX_PARTY_SIZE:
            errors.append(_("Party size must be a whole number between 1 and %s.", MAX_PARTY_SIZE))

        floor_key = values.get('preferred_floor') or ANY_FLOOR
        floor = self.env['restaurant.floor']
        if not isinstance(floor_key, str):
            errors.append(_("Please choose a valid floor."))
        elif floor_key != ANY_FLOOR:
            floor, ok = self._floor_from_public_key(config, floor_key) if config else (floor, False)
            if not ok:
                errors.append(_("Please choose a valid floor."))

        share_table = values.get('share_table') or 'private'
        if share_table not in dict(SHARE_TABLE_SELECTION):
            errors.append(_("Please choose a valid table sharing option."))

        tag_codes = values.get('tags') or []
        if isinstance(tag_codes, str):
            tag_codes = [tag_codes]
        tag_codes = {c for c in tag_codes if isinstance(c, str) and c}
        tags = self.env['pos.waitlist.tag'].sudo().search([('code', 'in', list(tag_codes))]) if tag_codes else \
            self.env['pos.waitlist.tag']
        if len(tags) != len(tag_codes):
            errors.append(_("Please choose valid options."))

        if errors:
            raise ValidationError('\n'.join(errors))
        return {
            'guest_name': guest_name,
            'phone': phone,
            'party_size': party_size,
            'preferred_floor_id': floor.id or False,
            'share_table': share_table,
            'tag_ids': [fields.Command.set(tags.ids)],
        }

    @api.model
    def _clean_phone(self, raw_phone):
        """``(phone, error)``: whitespace-collapsed phone and a guest-facing error or ``None``.

        Shared by the join form and Find My Place so both accept exactly the same numbers.
        """
        phone = ' '.join(str(raw_phone or '').split())
        if not phone:
            return phone, _("Please enter your phone number.")
        digits = normalize_phone(phone)
        if (len(phone) > MAX_PHONE_CHARS or not _PHONE_ALLOWED_RE.match(phone)
                or not MIN_PHONE_DIGITS <= len(digits) <= MAX_PHONE_DIGITS):
            return phone, _("Please enter a valid phone number.")
        return phone, None

    @api.model
    def _find_my_place(self, config, raw_phone):
        """Find My Place: the active (waiting) entry of ``config`` for this phone.

        ``config`` comes from the QR token, never from the browser. Never creates anything.
        Raises ValidationError for an invalid phone; returns an empty recordset when not found.
        """
        config.ensure_one()
        phone, error = self._clean_phone(raw_phone)
        if error:
            raise ValidationError(error)
        return self._find_active_entry(config, normalize_phone(phone))

    @api.model
    def _find_active_entry(self, config, phone_normalized):
        return self.sudo().search([
            ('config_id', '=', config.id),
            ('phone_normalized', '=', phone_normalized),
            ('state', 'in', ACTIVE_STATES),
        ], limit=1)

    @api.model
    def _join_from_qr(self, config, values):
        """Create (or recover) the guest's active entry for ``config``.

        ``config`` comes from the QR token, never from the browser.
        Returns ``(entry, created)``.
        """
        config.ensure_one()
        clean = self._validate_join_values(values, config)
        existing = self._find_active_entry(config, normalize_phone(clean['phone']))
        if existing:
            return existing, False
        clean.update({
            'config_id': config.id,
            'company_id': config.company_id.id,
            'source': 'qr',
            'state': 'waiting',
            'join_time': fields.Datetime.now(),
            'quoted_wait': self._estimate_wait_minutes(config),
        })
        entry = self.sudo().with_company(config.company_id).create(clean)
        return entry, True

    @api.model
    def _get_by_access_token(self, access_token):
        if not access_token:
            return self.sudo().browse()
        return self.sudo().search([('access_token', '=', access_token)], limit=1)

    @api.model
    def _get_active_tracking_entry(self, config, access_token):
        """The active (waiting) entry of ``config`` owning ``access_token``, else empty.

        Used by the join form to show "Track My Waitlist": a token remembered from another
        POS, or one whose entry is seated/cancelled/left/no_show, yields nothing.
        """
        entry = self._get_by_access_token(access_token)
        if entry and entry.config_id == config and entry.state in ACTIVE_STATES:
            return entry
        return self.sudo().browse()

    def _floor_label(self):
        self.ensure_one()
        return self.sudo().preferred_floor_id.name or _("Any Floor")

    def _public_status(self):
        """Everything the guest's status page may show. Only this entry, no IDs, no phone."""
        self.ensure_one()
        return {
            'restaurant_name': self.config_id.name,
            'token': self.token,
            'party_size': self.party_size,
            'table': self.table_id.table_number if self.state == 'seated' and self.table_id else False,
            'floor_pref': self._floor_label(),
            'share_table': dict(SHARE_TABLE_SELECTION)[self.share_table],
            'tags': self.tag_ids.mapped('name'),
            'state': self.state,
            'state_label': dict(STATE_SELECTION)[self.state],
            # No queue position here: nothing on the guest's page or JSON reveals their place
            # in line or how many parties are ahead. Only the POS's Average Waiting Time.
            'estimated_wait': self._get_estimated_wait(),
            'active': self.state in ACTIVE_STATES,
        }

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------
    def _check_state_transition(self, new_state):
        """Reject state changes outside STATE_TRANSITIONS.

        POS managers (and superuser code such as data fixes) may still correct a state
        from the back office; POS users can only follow the host flow.
        """
        if self.env.su or self.env.user.has_group('point_of_sale.group_pos_manager'):
            return
        for entry in self:
            if entry.state != new_state and new_state not in STATE_TRANSITIONS.get(entry.state, ()):
                raise ValidationError(_(
                    "Waitlist %(token)s cannot go from %(old)s to %(new)s.",
                    token=entry.token,
                    old=dict(STATE_SELECTION)[entry.state],
                    new=dict(STATE_SELECTION).get(new_state, new_state)))

    @api.model
    def pos_change_state(self, config_id, entry_id, expected_state, new_state):
        """Host action from the POS Waitlist screen. Safe against concurrent terminals.

        ``expected_state`` is the state the terminal displayed when the host clicked. The
        row is locked with ``SELECT ... FOR UPDATE``: when another terminal changed the
        entry first, PostgreSQL raises a serialization error and Odoo replays this call on
        a fresh snapshot, where the state no longer matches ``expected_state``. Only the
        first valid transition succeeds; the others get the latest state and queue back.

        Returns ``{'ok', 'message', 'state', 'queue'}``.
        """
        config = self.env['pos.config'].browse(int(config_id)).exists()
        if not config:
            raise ValidationError(_("This Point of Sale no longer exists."))
        config.check_access('read')

        entry = self.browse(int(entry_id)).exists()
        if not entry or entry.config_id != config:
            return {
                'ok': False,
                'message': _("This waitlist entry no longer exists."),
                'state': False,
                'queue': self.get_pos_queue(config.id),
            }
        entry.check_access('write')

        self.flush_model(['state'])
        self.env.cr.execute(
            "SELECT state FROM pos_waitlist_entry WHERE id = %s FOR UPDATE", (entry.id,))
        current = self.env.cr.fetchone()[0]
        entry.invalidate_recordset(['state'])

        labels = dict(STATE_SELECTION)
        if new_state == 'seated' and current == expected_state and self._seatable_tables(config):
            return {
                'ok': False,
                'message': _("Choose a table to seat %(token)s.", token=entry.token),
                'state': current,
                'queue': self.get_pos_queue(config.id),
            }
        if current != expected_state:
            return {
                'ok': False,
                'message': _("%(token)s was already updated on another terminal: it is now %(state)s.",
                             token=entry.token, state=labels[current]),
                'state': current,
                'queue': self.get_pos_queue(config.id),
            }
        if new_state not in STATE_TRANSITIONS.get(current, ()):
            return {
                'ok': False,
                'message': _("%(token)s cannot go from %(old)s to %(new)s.", token=entry.token,
                             old=labels[current], new=labels.get(new_state, new_state)),
                'state': current,
                'queue': self.get_pos_queue(config.id),
            }

        entry.write({'state': new_state})  # also notifies every POS of this config
        return {
            'ok': True,
            'message': _("%(token)s is now %(state)s.", token=entry.token, state=labels[new_state]),
            'state': new_state,
            'queue': self.get_pos_queue(config.id),
        }

    # ------------------------------------------------------------------
    # Seating at an existing POS table
    # ------------------------------------------------------------------
    @api.model
    def _seatable_tables(self, config):
        """Tables a guest of ``config`` can be seated at: the POS's own floor plan.

        Inactive tables and merged child tables (whose orders live on the parent) are left out.
        """
        tables = config.sudo().floor_ids.filtered('active').table_ids
        return tables.filtered(lambda t: t.active and not t.parent_id)

    @api.model
    def _table_occupancy(self, tables):
        """``{table_id: {'reason': str, 'guests': int}}`` for the tables that are NOT free.

        Reuses Odoo's own occupancy rule (a draft pos.order on the table, as in
        ``restaurant.table.are_orders_still_in_draft``) and adds the short hold of a guest
        seated from the waitlist whose order has not reached the server yet
        (TABLE_HOLD_MINUTES). ``guests`` counts the people already there: the draft
        orders' guest count plus the parties of guests still holding the table.
        """
        if not tables:
            return {}
        Order = self.env['pos.order'].sudo()
        busy = {}
        for order in Order.search([('table_id', 'in', tables.ids), ('state', '=', 'draft')]):
            info = busy.setdefault(order.table_id.id, {
                'reason': _("Table %s has an open order.", order.table_id.table_number), 'guests': 0})
            info['guests'] += order.customer_count or 0

        since = fields.Datetime.now() - timedelta(minutes=TABLE_HOLD_MINUTES)
        holds = self.sudo().search([
            ('table_id', 'in', tables.ids), ('state', '=', 'seated'), ('end_time', '>=', since),
        ])
        for hold in holds:
            ordered = Order.search_count([
                ('table_id', '=', hold.table_id.id), ('create_date', '>=', hold.end_time),
            ], limit=1)
            if ordered:
                continue  # the guest's own order is there now: counted with the draft orders
            info = busy.setdefault(hold.table_id.id, {
                'reason': _("Table %(table)s was just given to %(token)s.",
                            table=hold.table_id.table_number, token=hold.token),
                'guests': 0})
            info['guests'] += hold.party_size
        return busy

    @api.model
    def _table_busy_reasons(self, tables):
        """``{table_id: reason}`` for the tables in ``tables`` that are NOT free right now."""
        return {table_id: info['reason'] for table_id, info in self._table_occupancy(tables).items()}

    @api.model
    def _match_tables(self, config, party_size=1, share_table='private', preferred_floor=None):
        """Rate every seatable table of ``config`` for one guest. Never assigns anything.

        Inputs, in order: preferred floor (empty = Any Floor: every active POS floor),
        current availability (open orders + waitlist holds), table-sharing preference and
        party size against the table's seats. Returns a list of dicts sorted best first:
        ``{'id', 'table_number', 'floor_id', 'floor_name', 'seats', 'free_seats',
        'status', 'reason', 'selectable'}``.

        * free table on an allowed floor     -> ``match`` (or ``too_small`` below party size)
        * busy table, guest willing to share,
          enough free seats left              -> ``shared``
        * any other busy table                -> ``busy``
        * table on another floor than the one
          the guest asked for                 -> ``other_floor``

        A table without a seat count (0) is treated as big enough.
        """
        tables = self._seatable_tables(config)
        occupancy = self._table_occupancy(tables)
        party_size = max(int(party_size or 1), 1)
        rows = []
        for table in tables:
            seats = table.seats or 0
            busy = occupancy.get(table.id)
            guests = busy['guests'] if busy else 0
            free_seats = max(seats - guests, 0) if seats else 0
            if preferred_floor and table.floor_id != preferred_floor:
                status = MATCH_OTHER_FLOOR
                reason = _("Guest asked for %s.", preferred_floor.name)
            elif not busy:
                status = MATCH_TOO_SMALL if seats and seats < party_size else MATCH_OK
                reason = _("%(seats)s seats for a party of %(party)s.", seats=seats, party=party_size) \
                    if status == MATCH_TOO_SMALL else ''
            elif share_table == 'share' and seats and guests and free_seats >= party_size:
                status = MATCH_SHARED
                reason = _("Shared: %(free)s of %(seats)s seats free.", free=free_seats, seats=seats)
            else:
                status = MATCH_BUSY
                reason = busy['reason']
            rows.append({
                'id': table.id,
                'table_number': table.table_number,
                'floor_id': table.floor_id.id,
                'floor_name': table.floor_id.name,
                'seats': seats,
                'free_seats': free_seats if busy else seats,
                'status': status,
                'reason': reason,
                'selectable': status in SELECTABLE_MATCHES,
            })
        # Best first: status, then the snuggest fit (fewest spare seats), then table number.
        rows.sort(key=lambda r: (_MATCH_RANK[r['status']],
                                 (r['free_seats'] or 999) - party_size if r['status'] in (MATCH_OK, MATCH_SHARED) else 0,
                                 r['table_number'] or 0, r['id']))
        return rows

    def _match_my_tables(self):
        self.ensure_one()
        entry = self.sudo()
        return self._match_tables(entry.config_id, entry.party_size, entry.share_table,
                                  entry.preferred_floor_id)

    @api.model
    def get_seatable_tables(self, config_id, entry_id=False):
        """Server view of table availability for the POS table picker (RPC).

        With ``entry_id`` the tables are matched against that guest (floor, party size,
        sharing); ``tables`` then lists every table with its status, best first, and
        ``available_ids`` the ones the host may pick. The POS also treats tables with an
        unsynced open order on that terminal as taken.
        """
        config = self.env['pos.config'].browse(int(config_id))
        config.check_access('read')
        entry = self.browse(int(entry_id)).exists() if entry_id else self.browse()
        if entry and entry.config_id == config:
            entry.check_access('read')
            rows = entry._match_my_tables()
        else:
            rows = self._match_tables(config)
        return {
            'available_ids': [r['id'] for r in rows if r['selectable']],
            'busy': {str(r['id']): r['reason'] for r in rows if r['status'] in (MATCH_BUSY, MATCH_SHARED)},
            'tables': rows,
            'preferred_floor_id': entry.preferred_floor_id.id if entry else False,
        }

    @api.model
    def pos_seat_guest(self, config_id, entry_id, expected_state, table_id):
        """Seat a waiting guest at an existing POS table (Waiting -> Seated). Safe against concurrent terminals.

        Locks the entry, then the table row (always in that order, so no deadlock). The table
        row is touched with a no-op UPDATE: two terminals seating anyone at the same table
        conflict on it, the second one fails with a serialization error and Odoo replays it
        on a fresh snapshot, where the table is now held and the seat is refused.

        The chosen table is re-matched against the guest on the server (never trusted from
        the browser): it must still exist, be on one of this POS's floors, be on the guest's
        preferred floor (when they chose one) and be free, or have enough free seats for a
        guest who accepted to share. A too-small free table stays the host's call.

        Returns ``{'ok', 'message', 'state', 'table_id', 'shared', 'tables', 'queue'}``;
        ``tables`` is the fresh matching so the host can pick another table.
        """
        config = self.env['pos.config'].browse(int(config_id)).exists()
        if not config:
            raise ValidationError(_("This Point of Sale no longer exists."))
        config.check_access('read')
        entry = self.browse(int(entry_id)).exists()

        def result(ok, message, state, table=False, shared=False):
            return {
                'ok': ok, 'message': message, 'state': state, 'table_id': table, 'shared': shared,
                'tables': self.get_seatable_tables(
                    config.id, entry.id if entry and entry.config_id == config else False),
                'queue': self.get_pos_queue(config.id),
            }

        if not entry or entry.config_id != config:
            return result(False, _("This waitlist entry no longer exists."), False)
        entry.check_access('write')

        self.flush_model(['state'])
        self.env.cr.execute(
            "SELECT state FROM pos_waitlist_entry WHERE id = %s FOR UPDATE", (entry.id,))
        current = self.env.cr.fetchone()[0]
        entry.invalidate_recordset(['state'])
        labels = dict(STATE_SELECTION)
        if current != expected_state or current != 'waiting':
            if current != expected_state:
                message = _("%(token)s was already updated on another terminal: it is now %(state)s.",
                            token=entry.token, state=labels[current])
            else:
                message = _("Only waiting guests can be seated (%(token)s is %(state)s).",
                            token=entry.token, state=labels[current])
            return result(False, message, current)

        seatable = self._seatable_tables(config)
        table = self.env['restaurant.table'].sudo().browse(int(table_id)) if table_id else \
            self.env['restaurant.table']
        if not table:
            if seatable:
                return result(False, _("Choose a table to seat %(token)s.", token=entry.token), current)
        else:
            if not table.exists() or table not in seatable:
                return result(False, _("This table is no longer available on this Point of Sale."), current)
            self.env.cr.execute(
                "UPDATE restaurant_table SET write_date = write_date WHERE id = %s", (table.id,))
            match = next((r for r in entry._match_my_tables() if r['id'] == table.id), None)
            if not match:
                return result(False, _("This table is no longer available on this Point of Sale."), current)
            if not match['selectable']:
                return result(False, _("%s Choose another table.", match['reason']), current)

        shared = bool(table) and match['status'] == MATCH_SHARED
        entry.write({'state': 'seated', 'table_id': table.id or False})  # notifies every POS
        if shared:
            message = _("%(token)s seated at shared table %(table)s.", token=entry.token, table=table.table_number)
        elif table:
            message = _("%(token)s seated at table %(table)s.", token=entry.token, table=table.table_number)
        else:
            message = _("%(token)s is now %(state)s.", token=entry.token, state=labels['seated'])
        return result(True, message, 'seated', table.id or False, shared)

    # ------------------------------------------------------------------
    # POS integration (data + events)
    # ------------------------------------------------------------------
    def _pos_payload(self):
        share_labels = dict(SHARE_TABLE_SELECTION)
        result = []
        for entry in self:
            data = {f: entry[f] for f in _POS_FIELDS}
            data['join_time'] = fields.Datetime.to_string(entry.join_time)
            data['id'] = entry.id
            data['tags'] = entry.tag_ids.mapped('name')
            data['position'] = entry.position
            data['estimated_wait'] = entry._get_estimated_wait()
            data['preferred_floor_id'] = entry.sudo().preferred_floor_id.id or False
            data['floor_pref_label'] = entry._floor_label()
            data['share_table_label'] = share_labels.get(entry.share_table, '')
            data['share_table_short'] = _(SHARE_TABLE_SHORT.get(entry.share_table, ''))  # noqa: INT001
            data['allowed_states'] = list(STATE_TRANSITIONS.get(entry.state, ()))
            result.append(data)
        return result

    @api.model
    def get_pos_queue(self, config_id):
        """Active queue + server clock for the POS Waitlist screen (RPC).

        ``server_time`` lets the POS compute "waited" times without trusting the
        terminal's own clock.
        """
        entries = self.get_active_entries(config_id)
        return {
            'entries': entries,
            'enabled': self.env['pos.config'].sudo().browse(config_id).enable_qr_self_join,
            'server_time': fields.Datetime.to_string(fields.Datetime.now()),
        }

    def _notify_pos(self, event, payload=True):
        """Tell every screen showing these entries that they changed (best effort).

        The server-side record stays the single source of truth; this only says "reload":
        * POS Waitlist screens of the entry's config: bus event on the POS config channel
          (they reload the queue with get_pos_queue).
        * Backend Waitlist menu (list / form): bus event on the POS User group channel,
          which every POS user's backend tab is subscribed to (they reload the view).
        * Customer Track My Waitlist: polls /waitlist/s/<token>/json, nothing to push.
        """
        for config in self.sudo().config_id:
            entries = self.filtered(lambda e: e.config_id == config)
            try:
                config._notify(event, {'entries': entries._pos_payload() if payload else []})
            except Exception:  # noqa: BLE001 - the bus must never block a guest from joining
                pass
        self._notify_backend()

    def _notify_backend(self):
        """Ping open backend Waitlist views. Ids only: views re-read with the user's rights."""
        group = self.env.ref('point_of_sale.group_pos_user', raise_if_not_found=False)
        if not group or not self:
            return
        try:
            self.env['bus.bus'].sudo()._sendone(group, EVENT_BACKEND, {
                'entry_ids': self.ids,
                'company_ids': self.sudo().company_id.ids,
            })
        except Exception:  # noqa: BLE001 - never block a status change on the bus
            pass

    def unlink(self):
        # Deleted from the back office: every POS / backend view drops it right away.
        self.sudo().exists()._notify_pos(EVENT_UPDATED, payload=False)
        return super().unlink()

    @api.model
    def get_active_entries(self, config_id):
        """Active queue of one POS, for the POS / host screens (RPC)."""
        config = self.env['pos.config'].browse(config_id)
        config.check_access('read')
        entries = self.search([('config_id', '=', config.id), ('state', 'in', ACTIVE_STATES)])
        return entries._pos_payload()
