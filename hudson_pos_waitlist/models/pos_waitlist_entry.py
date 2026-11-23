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
import unicodedata
import uuid
from collections import deque
from datetime import datetime, timedelta
from math import ceil
from statistics import median

import phonenumbers
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

# Table matching for a waitlist guest (see ``_match_tables``). A table with a SELECTABLE
# status seats the whole party on its own; a COMBINABLE one may be joined with other free
# tables of its floor (merged like the POS floor plan); the others are shown for information.
MATCH_OK = 'match'            # free and big enough, on an allowed floor
MATCH_SHARED = 'shared'       # in use, but enough free seats for a guest willing to share
MATCH_TOO_SMALL = 'too_small'  # free, on an allowed floor, fewer seats than the party
MATCH_BUSY = 'busy'           # open order / just given to another guest
MATCH_OTHER_FLOOR = 'other_floor'  # not on the guest's preferred floor
SELECTABLE_MATCHES = (MATCH_OK, MATCH_SHARED)
COMBINABLE_MATCHES = (MATCH_OK, MATCH_TOO_SMALL)
_MATCH_RANK = {MATCH_OK: 0, MATCH_SHARED: 0, MATCH_TOO_SMALL: 2, MATCH_BUSY: 3, MATCH_OTHER_FLOOR: 4}
# Seating arrangements suggested to the host (see ``_seating_arrangements``): at most this many,
# and the search for multi-table combinations visits at most this many candidate tables per
# floor (the queue wait estimate replays many guests, it searches less).
MAX_ARRANGEMENTS = 8
COMBO_SEARCH_NODES = 4000
ESTIMATE_COMBO_SEARCH_NODES = 400
# Spare seats of a table without a seat count (treated as big enough, but never a close fit).
_UNKNOWN_FIT = 10 ** 6
SOURCE_SELECTION = [
    ('qr', 'QR Self Join'),
    ('pos', 'POS / Host'),
]

# A guest seated from the waitlist holds their table until the table's POS order reaches the
# server (from then on the standard "draft order on this table" rule applies), and at most this
# long when no order is ever opened (e.g. the guest walked away before ordering).
TABLE_HOLD_MINUTES = 30

# Recent seating pace (see ``_seating_interval``): the latest SEATING_RATE_SAMPLES gaps between
# Waiting -> Seated events of the last SEATING_RATE_WINDOW_MINUTES; fewer than
# SEATING_RATE_MIN_INTERVALS gaps = not enough data, the configured Average Waiting Time is used.
SEATING_RATE_WINDOW_MINUTES = 120
SEATING_RATE_SAMPLES = 10
SEATING_RATE_MIN_INTERVALS = 3
# Actual-wait calibration (see ``_wait_calibration``): only guests quoted at least this many
# minutes count, and estimates are stretched at most by this factor.
WAIT_CALIBRATION_MIN_QUOTE = 5
WAIT_CALIBRATION_MAX = 1.5
# Displayed ranges stop here: anything longer (or a party the tables cannot seat yet) is "30+ min".
WAIT_RANGE_CAP = 30

TOKEN_PREFIX = 'W-'
MAX_GUEST_NAME = 80
MAX_GUEST_NOTE = 300
MAX_PHONE_CHARS = 32
# Technical ceiling of an integer column, not a business rule: the real party-size limit is
# per POS (pos.config._waitlist_party_size_limit).
_INT4_MAX = 2147483647

# What a guest may type: digits, spaces, hyphens, dots, parentheses and one leading "+".
_PHONE_ALLOWED_RE = re.compile(r'^\+?[0-9\s().\-]+$')
# Country used for numbers typed without "+<country code>" when the guest's choice is
# missing: the restaurant company's country, else this one.
DEFAULT_PHONE_REGION = 'IN'
# Extra rule kept from the review for India: a 10-digit mobile starting with 7, 8 or 9
# (the phone library alone also accepts Indian landline formats).
_INDIAN_MOBILE_RE = re.compile(r'^[789][0-9]{9}$')

# Bus events sent on the POS config channel (pos.bus.mixin._notify).
EVENT_CREATED = 'waitlist_created'
EVENT_UPDATED = 'waitlist_updated'
# Bus event for the backend Waitlist menu (sent on the POS User group channel).
EVENT_BACKEND = 'hudson_waitlist_changed'

# Fields the POS / host screens receive. Never includes access_token.
_POS_FIELDS = (
    'token', 'guest_name', 'phone', 'party_size', 'share_table',
    'source', 'state', 'join_time', 'quoted_wait', 'guest_note',
)
# Writing any of these refreshes every open POS of the entry's config.
_POS_NOTIFY_FIELDS = set(_POS_FIELDS) | {'tag_ids', 'preferred_floor_id', 'table_id', 'table_ids',
                                         'partner_id'}

# Sides used when the extra tables of one party are merged under the main table
# (restaurant.table.parent_side, the standard POS "merge tables").
_MERGE_SIDES = ('right', 'bottom', 'left', 'top')


def phone_region(region):
    """``region`` as an ISO country code the phone library knows, else ``None``."""
    region = (region or '').strip().upper() if isinstance(region, str) else ''
    return region if region in phonenumbers.SUPPORTED_REGIONS else None


def parse_phone(phone, region=None):
    """``phonenumbers.PhoneNumber`` for ``phone`` (``region`` for numbers without +code), or None."""
    try:
        return phonenumbers.parse(phone or '', phone_region(region) or DEFAULT_PHONE_REGION)
    except phonenumbers.NumberParseException:
        return None


def normalize_phone(phone, region=None):
    """Digits used to match the same guest on the same POS. Not an identity.

    The international number (country code + national number, E.164 without "+"), so every
    way of typing one number matches: "+91 98765 43210", "098765 43210" (India selected),
    "0091 9876543210" all give ``919876543210``. Falls back to the plain digits.
    """
    number = parse_phone(phone, region)
    if number and phonenumbers.is_possible_number(number):
        return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)[1:]
    digits = re.sub(r'\D', '', phone or '')
    return digits[2:] if digits.startswith('00') else digits


def is_valid_guest_name(name):
    """Letters of any script (with their accents / vowel signs) and single spaces only.

    Same rule as the join form's Unicode letter / mark regex: no digits, no punctuation or
    symbols, no leading / trailing / double spaces.
    """
    if not name or name != name.strip() or '  ' in name:
        return False
    words = name.split(' ')
    return all(word and unicodedata.category(word[0]).startswith('L')
               and all(unicodedata.category(c)[0] in 'LM' for c in word)
               for word in words)


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
    floor_ids = fields.Many2many(
        'restaurant.floor', string="Suggested Floors",
        help="When a guest picks this tag, suitable free tables on these floors are suggested "
             "first to the host. Only a hint: party size, availability and the guest's own floor "
             "choice always come first.")

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


class PosWaitlistPartnerLock(models.Model):
    """One row per company and phone number (international digits), used only as a lock.

    Rows are only ever touched with SQL in ``PosWaitlistEntry._lock_customer_phone`` so that
    two simultaneous QR joins with the same number never create two customers.
    """
    _name = 'pos.waitlist.partner.lock'
    _description = 'Waitlist Customer Lock'
    _log_access = False

    company_id = fields.Many2one('res.company', required=True, ondelete='cascade')
    phone_key = fields.Char(required=True)
    hits = fields.Integer(required=True, default=0)

    _company_phone_unique = models.Constraint('unique (company_id, phone_key)',
                                              'One lock row per company and phone number.')


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
    guest_note = fields.Text(
        string="Anything We Should Know",
        help="Free text the guest typed on the join form. Shown to the host as context when "
             "choosing a table; it never overrides party size or table availability.")
    partner_id = fields.Many2one(
        'res.partner', string="Customer", ondelete='set null', index='btree_not_null',
        help="Customer created or reused (same mobile number) when the guest joined by QR.")

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
        ondelete='set null', help="Existing POS table the guest was seated at (the main table "
                                  "when several tables were combined).")
    table_ids = fields.Many2many(
        'restaurant.table', 'pos_waitlist_entry_table_rel', 'entry_id', 'table_id',
        string="Tables", readonly=True, copy=False,
        help="Every table of this guest's seating. Several tables when the party was larger "
             "than one table: they are merged under the main table like a POS table merge.")
    pos_order_id = fields.Many2one(
        'pos.order', string="POS Order", readonly=True, copy=False, ondelete='set null',
        index='btree_not_null',
        help="This guest's own POS order, opened from the waitlist. Guests sharing one table each "
             "keep their own order and pay their own bill.")
    pos_order_uuid = fields.Char(
        readonly=True, copy=False, index='btree_not_null',
        help="Technical: uuid the POS gives this guest's own order. Issued by the server when the "
             "guest is seated, so the order is never merged into another party's order on the "
             "same table (see pos.order._get_open_order).")
    shared_seating = fields.Boolean(
        string="Shared Table", readonly=True, copy=False,
        help="Seated at a table another party was already using (guest accepted to share).")

    access_token = fields.Char(
        readonly=True, copy=False, groups='point_of_sale.group_pos_manager',
        help="Random secret in the guest's Track My Waitlist link (/waitlist/s/<token>).")

    position = fields.Integer(compute='_compute_position',
                              help="Place among waiting guests of this POS (1 = next). 0 when not waiting.")
    estimated_wait_label = fields.Char(
        string="Estimated Wait", compute='_compute_estimated_wait_label',
        help="Live estimate of a waiting guest, the same range the guest and the POS see "
             "(current POS tables, party size, guests ahead, recent seating pace).")

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

    @api.constrains('table_id', 'table_ids', 'config_id')
    def _check_table_belongs_to_config(self):
        """The table must be on one of the entry's own POS floors.

        restaurant.table has no company_id, so check_company cannot cover it; without this a
        direct write of table_id could hold another POS's (or company's) table.
        """
        for entry in self.sudo():
            for table in entry.table_id | entry.table_ids:
                if table.floor_id not in entry.config_id.floor_ids:
                    raise ValidationError(_(
                        "Table %(table)s is not on a floor of %(pos)s.",
                        table=table.table_number, pos=entry.config_id.name))

    # ------------------------------------------------------------------
    # Queue position (never stored)
    # ------------------------------------------------------------------
    def _compute_position(self):
        waiting = self.filtered(lambda e: e.state == 'waiting' and e.id)
        (self - waiting).position = 0
        for entry in waiting:
            entry.position = self._waiting_ahead_count(entry.config_id, entry.join_time, entry.id) + 1

    def _compute_estimated_wait_label(self):
        """Backend list / form: the shared server-side estimate, one queue replay per POS."""
        waiting = self.filtered(lambda e: e.state == 'waiting' and e.id)
        (self - waiting).estimated_wait_label = False
        estimates = {config: self._queue_wait_estimates(config) for config in waiting.config_id}
        for entry in waiting:
            entry.estimated_wait_label = entry._get_wait_info(estimates[entry.config_id])['estimated_wait_label']

    @api.model
    def _waiting_ahead_count(self, config, join_time=None, entry_id=None):
        """Waiting entries of ``config`` queued before (join_time, entry_id); all of them without join_time."""
        domain = [('config_id', '=', config.id), ('state', '=', 'waiting')]
        if join_time:
            domain += ['|', ('join_time', '<', join_time),
                       '&', ('join_time', '=', join_time), ('id', '<', entry_id or 0)]
        return self.sudo().search_count(domain)

    # ------------------------------------------------------------------
    # Estimated wait: capacity-aware queue simulation (never position x average)
    # ------------------------------------------------------------------
    @api.model
    def _seating_interval(self, config, now=None):
        """``(minutes, observed)``: how often this restaurant currently seats a waiting party.

        Measured from the latest Waiting -> Seated events of this POS (``end_time`` of seated
        entries) inside a rolling window, as the MEDIAN gap between consecutive seatings, so
        one unusually fast (a burst into free tables) or slow seating cannot distort it. When
        the restaurant has been idle longer than that, the still-open gap counts as one more
        sample. The measure is blended with the configured Average Waiting Time in proportion
        to the number of gaps, so a few seatings never fully replace the baseline. Without
        enough recent seatings the configured Average Waiting Time is the pace (fallback /
        baseline). How long guests actually waited is used by ``_wait_calibration``.
        """
        baseline = float(max(config.sudo().waitlist_minutes_per_party or 0, 1))
        now = now or fields.Datetime.now()
        seated = self.sudo().search_read([
            ('config_id', '=', config.id), ('state', '=', 'seated'),
            ('end_time', '>=', now - timedelta(minutes=SEATING_RATE_WINDOW_MINUTES)),
        ], ['end_time'], order='end_time desc, id desc', limit=SEATING_RATE_SAMPLES + 1)
        times = sorted(r['end_time'] for r in seated)
        gaps = [(b - a).total_seconds() / 60 for a, b in zip(times, times[1:])]
        if len(gaps) < SEATING_RATE_MIN_INTERVALS:
            return baseline, False
        interval = median(gaps)
        open_gap = (now - times[-1]).total_seconds() / 60
        if open_gap > interval:
            interval = median(gaps + [open_gap])
        weight = min(len(gaps) / SEATING_RATE_SAMPLES, 1.0)
        return max(weight * interval + (1 - weight) * baseline, 1.0), True

    @api.model
    def _wait_calibration(self, config, now=None):
        """Factor >= 1 applied to non-zero estimates, from how long guests ACTUALLY waited.

        Recent seated guests of the rolling window that were quoted a real wait
        (``quoted_wait`` >= WAIT_CALIBRATION_MIN_QUOTE): their actual wait is
        ``end_time - join_time`` (Waiting -> Seated). When the median actual / quoted ratio
        shows the restaurant runs slower than estimated, later estimates are stretched by it
        (capped at WAIT_CALIBRATION_MAX). Never below 1: a faster-than-quoted evening never
        shortens a guest's estimate (conservative). 1.0 without enough data.
        """
        now = now or fields.Datetime.now()
        seated = self.sudo().search_read([
            ('config_id', '=', config.id), ('state', '=', 'seated'),
            ('end_time', '>=', now - timedelta(minutes=SEATING_RATE_WINDOW_MINUTES)),
            ('quoted_wait', '>=', WAIT_CALIBRATION_MIN_QUOTE),
        ], ['join_time', 'end_time', 'quoted_wait'], order='end_time desc, id desc',
            limit=SEATING_RATE_SAMPLES)
        ratios = [max((r['end_time'] - r['join_time']).total_seconds() / 60, 0) / r['quoted_wait']
                  for r in seated if r['join_time'] and r['end_time']]
        if len(ratios) < SEATING_RATE_MIN_INTERVALS:
            return 1.0
        return min(max(median(ratios), 1.0), WAIT_CALIBRATION_MAX)

    @api.model
    def _queue_wait_estimates(self, config, extra_party=None):
        """``{entry_id: minutes or None}`` for every waiting guest of ``config``, in one pass.

        ``extra_party`` (``{'size', 'share', 'floor_id'}``) is a guest about to join, returned
        under the key ``'new'`` (used for the quote at join time).

        The queue is replayed against the POS's own table state; nothing is stored:

        * tables and their availability come from ``_seatable_tables`` / ``_table_occupancy``,
          i.e. the standard POS rule (a draft order on the table) plus the waitlist hold. A
          table released by the normal POS payment flow is simply free here;
        * guests are served in queue order. Each takes, as soon as possible, the snuggest free
          table big enough for the party, else (if they accept) a busy table with enough free
          seats, else a group of free tables of one floor (combined seating, as the host
          would merge them). A guest who cannot be seated yet does not block the next guests,
          as a host seats a smaller party at a table too small for a big one;
        * the preferred floor is honoured only when that floor can hold the party at all;
        * busy tables free up one at a time, the longest-occupied first, every
          ``_seating_interval`` minutes (measured pace, else the Average Waiting Time). A
          table taken during the replay is released again later;
        * when recent guests actually waited longer than quoted, real waits are stretched by
          ``_wait_calibration`` (never shortened).

        So free and suitable tables, party size, the guests still ahead, and the current
        seating pace all shape each guest's estimate, and every change (join, cancel, seat,
        a POS order opened or paid) changes it on the next read. ``None`` = this POS's tables
        can never seat the party (the host decides). A POS without a floor plan has no table
        state to read: the measured pace per guest ahead, else the flat Average Waiting Time.
        """
        config = config.sudo()
        now = fields.Datetime.now()
        waiting = self.sudo().search([('config_id', '=', config.id), ('state', '=', 'waiting')])
        parties = [{'key': e.id, 'size': max(e.party_size, 1), 'share': e.share_table == 'share',
                    'floor_id': e.preferred_floor_id.id} for e in waiting]
        if extra_party:
            parties.append(dict(extra_party, key='new', size=max(int(extra_party.get('size') or 1), 1)))
        if not parties:
            return {}
        interval, observed = self._seating_interval(config, now)
        factor = self._wait_calibration(config, now)
        tables = self._seatable_tables(config)
        if not tables:
            return {p['key']: (interval * (index + 1) if observed else interval) * factor
                    for index, p in enumerate(parties)}

        occupancy = self._table_occupancy(tables)
        rows, pool = {}, {}
        for table in tables:
            seats = table.seats or 0
            busy = occupancy.get(table.id)
            guests = busy['guests'] if busy else 0
            row = {
                'id': table.id, 'table_number': table.table_number, 'seats': seats,
                'floor_id': table.floor_id.id, 'floor_name': table.floor_id.name,
                'floor_sequence': table.floor_id.sequence, 'status': MATCH_OK,
                # Seats a guest willing to share can still take at this busy table.
                'share_seats': (max(seats - guests, 0)
                                if busy and seats and guests and not busy.get('exclusive') else 0),
            }
            rows[table.id] = row
            if not busy:
                pool[table.id] = row
        releases = deque(sorted(occupancy, key=lambda tid: (occupancy[tid]['since'] or now, tid)))

        floor_capacity = {}
        for row in rows.values():
            cap = floor_capacity.setdefault(row['floor_id'], {'total': 0, 'unlimited': False})
            cap['total'] += row['seats']
            cap['unlimited'] |= not row['seats']
        estimates, pending = {}, []
        for party in parties:
            floors = {f for f, cap in floor_capacity.items() if cap['unlimited'] or cap['total'] >= party['size']}
            if party['floor_id'] in floors:
                floors = {party['floor_id']}
            party['floors'] = floors
            if floors:
                pending.append(party)
            else:
                estimates[party['key']] = None

        def pick(party):
            """``(table_ids, shared)`` the party can have right now, else ``None``."""
            size, floors = party['size'], party['floors']
            singles = [r for r in pool.values()
                       if r['floor_id'] in floors and (not r['seats'] or r['seats'] >= size)]
            if singles:
                best = min(singles, key=lambda r: (r['seats'] or _INT4_MAX, r['table_number'] or 0, r['id']))
                return [best['id']], False
            if party['share']:
                shared = [r for r in rows.values()
                          if r['id'] not in pool and r['floor_id'] in floors and r['share_seats'] >= size]
                if shared:
                    best = min(shared, key=lambda r: (r['share_seats'], r['table_number'] or 0, r['id']))
                    return [best['id']], True
            combos = self._table_combinations([r for r in pool.values() if r['floor_id'] in floors], size,
                                              max_nodes=ESTIMATE_COMBO_SEARCH_NODES)
            if combos:
                best = min(combos, key=lambda c: (c['seats'], len(c['table_ids']), c['floor_sequence']))
                return best['table_ids'], False
            return None

        def seat_everyone_possible(minute):
            for party in list(pending):
                choice = pick(party)
                if not choice:
                    continue
                table_ids, shared = choice
                estimates[party['key']] = minute
                pending.remove(party)
                for table_id in table_ids:
                    row = rows[table_id]
                    if shared:
                        row['share_seats'] -= party['size']
                        continue
                    del pool[table_id]
                    releases.append(table_id)  # this party will leave too, after the others
                    row['share_seats'] = (max(row['seats'] - party['size'], 0)
                                          if party['share'] and len(table_ids) == 1 else 0)

        seat_everyone_possible(0.0)
        step, max_steps = 0, (len(rows) + 1) * (len(parties) + 1)
        while pending and releases and step < max_steps:
            step += 1
            released = rows[releases.popleft()]
            released['share_seats'] = 0
            pool[released['id']] = released
            seat_everyone_possible(step * interval)
        for party in pending:
            estimates[party['key']] = None
        # Recent guests waited longer than they were quoted: stretch every real wait (never shorten).
        return {key: (minutes * factor if minutes else minutes) for key, minutes in estimates.items()}

    @api.model
    def _wait_range(self, minutes):
        """``(low, high)`` minutes shown to people instead of a falsely exact value.

        Coarse, conservative bands: 0-5, 5-10, 10-15, 15-20, 20-30, then ``(30, None)`` =
        "30+ min". ``None`` (no table / combination of this POS can seat the party in the
        replay) is "30+ min" too: never a falsely short or falsely exact number.
        """
        if minutes is None or minutes >= WAIT_RANGE_CAP:
            return WAIT_RANGE_CAP, None
        if minutes >= 20:
            return 20, WAIT_RANGE_CAP
        low = int(minutes // 5) * 5
        return low, low + 5

    @api.model
    def _wait_label(self, minutes):
        low, high = self._wait_range(minutes)
        if high is None:
            return _("%s+ min", low)
        return _("~%(low)s–%(high)s min", low=low, high=high)

    @api.model
    def _wait_info(self, minutes):
        """Estimate fields shared by the POS payload, the guest status page and the backend."""
        low, high = self._wait_range(minutes)
        return {
            # Internal value (quoted_wait, sorting); people only ever see the range label.
            'estimated_wait': ceil(minutes) if minutes is not None else WAIT_RANGE_CAP,
            'estimated_wait_min': low,
            'estimated_wait_max': high or False,
            'estimated_wait_label': self._wait_label(minutes),
        }

    def _get_estimated_wait(self):
        """This waiting guest's estimate in minutes (0 when not waiting / unknown)."""
        return self._get_wait_info()['estimated_wait']

    def _get_wait_info(self, estimates=None):
        """``_wait_info`` of this entry; ``estimates`` = a precomputed ``_queue_wait_estimates``."""
        self.ensure_one()
        if self.state != 'waiting':
            return {'estimated_wait': 0, 'estimated_wait_min': False,
                    'estimated_wait_max': False, 'estimated_wait_label': ''}
        if estimates is None:
            estimates = self._queue_wait_estimates(self.config_id)
        return self._wait_info(estimates.get(self.id))

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
                vals['phone_normalized'] = normalize_phone(vals['phone'], self._phone_region(config))
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
            vals['phone_normalized'] = normalize_phone(vals['phone'], self._phone_region(self.config_id[:1]))
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
    def _phone_region(self, config):
        """Default country for numbers typed without +code: the restaurant's company country."""
        code = config.sudo().company_id.country_id.code if config else False
        return phone_region(code) or DEFAULT_PHONE_REGION

    @api.model
    def _public_phone_countries(self):
        """``[(iso_code, label)]`` for the join form's country picker: every country with a
        calling code the phone library knows. Codes only, never database ids."""
        countries = self.env['res.country'].sudo().search([('phone_code', '!=', 0)])
        options = []
        for country in countries.sorted(lambda c: c.name or ''):
            code = phone_region(country.code)
            if code:
                flag = ''.join(chr(0x1F1E6 + ord(ch) - ord('A')) for ch in code)
                options.append((code, f'{flag} +{country.phone_code} {country.name}'))
        return options

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
        guest_name, name_error = self._clean_guest_name(values.get('guest_name'))
        if name_error:
            errors.append(name_error)

        phone, phone_error = self._clean_phone(values.get('phone'), values.get('phone_country'), config)
        if phone_error:
            errors.append(phone_error)

        raw_size = values.get('party_size')
        raw_size = str(raw_size).strip() if raw_size is not None else ''
        party_size = int(raw_size) if raw_size.isdigit() and len(raw_size) <= 10 else 0
        limit = config.sudo()._waitlist_party_size_limit() if config else 0
        if not 1 <= party_size <= (limit or _INT4_MAX):
            if limit:
                errors.append(_("Party size must be a whole number between 1 and %s. "
                                "For a larger group, please speak with the host.", limit))
            else:
                errors.append(_("Party size must be a whole number of at least 1."))

        raw_note = values.get('guest_note')
        guest_note = raw_note if isinstance(raw_note, str) else ''
        # Printable text only, one line break at most between lines.
        guest_note = '\n'.join(
            ' '.join(''.join(c for c in line if c.isprintable() or c.isspace()).split())
            for line in guest_note.splitlines())
        guest_note = re.sub(r'\n{2,}', '\n', guest_note).strip()
        if len(guest_note) > MAX_GUEST_NOTE:
            errors.append(_("Please keep your note under %s characters.", MAX_GUEST_NOTE))

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
            'guest_note': guest_note or False,
        }

    @api.model
    def _clean_guest_name(self, raw_name):
        """``(name, error)``: letters and single spaces only, or a guest-facing error."""
        name = ' '.join(str(raw_name or '').split())
        if not name:
            return name, _("Please enter your name.")
        if len(name) > MAX_GUEST_NAME:
            return name, _("Name is too long.")
        if not is_valid_guest_name(name):
            return name, _("Please enter a name using letters and spaces only.")
        return name, None

    @api.model
    def _clean_phone(self, raw_phone, country_code=None, config=None):
        """``(phone, error)``: the number in international format ("+91 98765 43210") and a
        guest-facing error or ``None``.

        Shared by the join form and Find My Place so both accept exactly the same numbers.
        Any country: ``country_code`` (ISO code from the form's country picker, else the
        restaurant's country) is used for numbers typed without "+<code>", and the number
        must be valid for its country (phone library rules). Indian numbers must also be a
        10-digit mobile starting with 7, 8 or 9.
        """
        phone = ' '.join(str(raw_phone or '').split())
        if country_code and not phone_region(country_code):
            return phone, _("Please choose a valid country.")
        if not phone:
            return phone, _("Please enter your phone number.")
        region = phone_region(country_code) or self._phone_region(config)
        number = parse_phone(phone, region) if _PHONE_ALLOWED_RE.match(phone) else None
        if len(phone) > MAX_PHONE_CHARS or not number or not phonenumbers.is_valid_number(number):
            return phone, _("Please enter a valid phone number for the selected country.")
        if (phonenumbers.region_code_for_number(number) == 'IN'
                and not _INDIAN_MOBILE_RE.match(str(number.national_number))):
            return phone, _("Please enter a valid 10-digit Indian mobile number starting with 7, 8 or 9.")
        return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.INTERNATIONAL), None

    @api.model
    def _find_my_place(self, config, raw_phone, country_code=None):
        """Find My Place: this phone's waiting entry at ``config``.

        Only a waiting guest is tracked: tracking ends at Seated, so seated (and cancelled /
        left / no show) visits are never returned. ``config`` comes from the QR token, never
        from the browser. Never creates anything. Raises ValidationError for an invalid phone;
        returns an empty recordset when not found.
        """
        config.ensure_one()
        phone, error = self._clean_phone(raw_phone, country_code, config)
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
            if not existing.partner_id:
                existing.partner_id = self._qr_customer(config, existing.guest_name, existing.phone)
            return existing, False
        clean.update({
            'config_id': config.id,
            'company_id': config.company_id.id,
            'source': 'qr',
            'state': 'waiting',
            'join_time': fields.Datetime.now(),
            # What this guest is told when joining: their own place in the current queue.
            'quoted_wait': self._wait_info(self._queue_wait_estimates(config, extra_party={
                'size': clean['party_size'], 'share': clean['share_table'] == 'share',
                'floor_id': clean['preferred_floor_id']}).get('new'))['estimated_wait'],
            'partner_id': self._qr_customer(config, clean['guest_name'], clean['phone']).id,
        })
        entry = self.sudo().with_company(config.company_id).create(clean)
        return entry, True

    @api.model
    def _qr_customer(self, config, guest_name, phone):
        """The ``res.partner`` of this QR guest: an existing customer with the same phone
        number, else a new one.

        A customer's phone matches whether it was recorded with its country code
        ("+91 98765 43210", "0091...") or nationally ("98765 43210", "098765 43210").
        Only customers visible to the POS's company are reused. An existing customer is never
        renamed. Runs as superuser: the guest is anonymous and never sees the partner.
        """
        Partner = self.env['res.partner'].sudo().with_company(config.company_id)
        number = parse_phone(phone, self._phone_region(config))
        if not number or not phonenumbers.is_valid_number(number):
            return Partner.browse()
        international = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)[1:]
        # Before looking: a concurrent join of this number waits here, then sees our customer.
        self._lock_customer_phone(config.company_id, international)
        # A phone saved without country code is read as the restaurant's own country.
        same_country = phonenumbers.region_code_for_number(number) == self._phone_region(config)
        national = str(number.national_number) if same_country else international
        Partner.flush_model(['phone', 'active', 'company_id'])
        self.env.cr.execute(r"""
            SELECT id FROM res_partner
             WHERE active
               AND phone IS NOT NULL
               AND (company_id IS NULL OR company_id = %s)
               AND regexp_replace(phone, '\D', '', 'g') IN (%s, '00' || %s, %s, '0' || %s)
             ORDER BY id
             LIMIT 1
        """, (config.company_id.id, international, international, national, national))
        row = self.env.cr.fetchone()
        if row:
            return Partner.browse(row[0])
        return Partner.create({'name': guest_name, 'phone': phone})

    @api.model
    def _lock_customer_phone(self, company, phone_key):
        """Serialize customer lookup / creation for one phone number of one company.

        Same technique as ``_next_queue_number``: an UPDATE on one shared row. Two joins of the
        same number at the same moment (even at two POS of the company) touch the same row:
        the second waits, then fails with a serialization error once the first commits, and
        Odoo replays it on a fresh snapshot where the first one's customer is visible. So a
        phone number never gets two customers, whatever the POS.
        """
        self.env['pos.waitlist.partner.lock'].flush_model()
        self.env.cr.execute("""
            INSERT INTO pos_waitlist_partner_lock (company_id, phone_key, hits)
            VALUES (%s, %s, 1)
            ON CONFLICT (company_id, phone_key)
            DO UPDATE SET hits = pos_waitlist_partner_lock.hits + 1
        """, (company.id, phone_key))
        self.env['pos.waitlist.partner.lock'].invalidate_model()

    @api.model
    def _get_by_access_token(self, access_token):
        if not access_token:
            return self.sudo().browse()
        return self.sudo().search([('access_token', '=', access_token)], limit=1)

    @api.model
    def _get_active_tracking_entry(self, config, access_token):
        """The waiting entry of ``config`` owning ``access_token``, else empty.

        Used by the join form to show "Track My Waitlist". Tracking ends at Seated: a seated,
        cancelled, left or no show visit, or a token remembered from another POS, yields nothing.
        """
        entry = self._get_by_access_token(access_token)
        if entry and entry.config_id == config and entry.state in ACTIVE_STATES:
            return entry
        return self.sudo().browse()

    def _get_seated_tracking_entry(self, config, access_token):
        """The seated entry of ``config`` owning ``access_token`` while the guest is still at
        their table (``_seating_active``), else empty.

        Used by the join form: Back / a new scan during the visit returns to the status page
        instead of an empty join form. Once the visit is completed the normal form shows again.
        """
        entry = self._get_by_access_token(access_token)
        if entry and entry.config_id == config and entry.state == 'seated' and entry._seating_active():
            return entry
        return self.sudo().browse()

    # ------------------------------------------------------------------
    # Seated visit: is the guest still at their table?
    # ------------------------------------------------------------------
    def _seated_tables(self):
        """Every table of this seating (main table first). Older entries only have ``table_id``."""
        self.ensure_one()
        entry = self.sudo()
        return entry.table_id | entry.table_ids

    def _seating_order(self):
        """The POS order of this seating, or an empty recordset when none reached the server yet.

        The guest's own order (opened from the waitlist with the uuid issued at seating, linked
        when it reaches the server). A guest at a shared table only ever has that order: never
        the other party's. Otherwise (e.g. "Seat Only", the host opened the table later) the
        first order opened on the guest's main table since they were seated that is not another
        waitlist guest's own order (the same rule the table hold uses).
        """
        self.ensure_one()
        entry = self.sudo()
        Order = self.env['pos.order'].sudo()
        if entry.pos_order_id:
            return entry.pos_order_id
        if entry.pos_order_uuid:
            order = Order.search([('uuid', '=', entry.pos_order_uuid)], limit=1)
            if order or entry.shared_seating:
                return order
        if entry.state != 'seated' or not entry.table_id or not entry.end_time:
            return Order
        others = self.sudo().search([
            ('id', '!=', entry.id), ('pos_order_id.table_id', '=', entry.table_id.id),
            ('pos_order_id.create_date', '>=', entry.end_time),
        ]).pos_order_id
        return Order.search([
            ('table_id', '=', entry.table_id.id), ('create_date', '>=', entry.end_time),
            ('id', 'not in', others.ids),
        ], order='create_date, id', limit=1)

    def _seating_active(self):
        """True while a guest seated at a table is still on their visit.

        Server-side rule, the same for Find My Place, the tracking link and the status page:
        * the seating's order is still open (draft) -> active; paid / cancelled -> completed;
        * no order yet -> active while the table hold lasts (TABLE_HOLD_MINUTES).
        Entries seated without a table have nothing to recover.
        """
        self.ensure_one()
        entry = self.sudo()
        if entry.state != 'seated' or not entry.table_id or not entry.end_time:
            return False
        order = entry._seating_order()
        if order:
            return order.state == 'draft'
        return entry.end_time >= fields.Datetime.now() - timedelta(minutes=TABLE_HOLD_MINUTES)

    def _tables_label(self):
        """Table number(s) shown to the guest: ``3``, or ``"4 + 5"`` for combined tables."""
        self.ensure_one()
        tables = self._seated_tables()
        if len(tables) == 1:
            return tables.table_number
        return ' + '.join(str(n) for n in tables.mapped('table_number'))

    def _floor_label(self):
        self.ensure_one()
        return self.sudo().preferred_floor_id.name or _("Any Floor")

    def _public_status(self):
        """Everything the guest's status page may show. Only this entry, no IDs, no phone."""
        self.ensure_one()
        seating_active = self._seating_active()
        return dict(self._get_wait_info(), **{
            'restaurant_name': self.config_id.name,
            'token': self.token,
            'party_size': self.party_size,
            # Final Seated page: the assigned table, while the guest's order / seating is in
            # progress (shown once; tracking itself has ended).
            'table': self._tables_label() if seating_active else False,
            'floor_pref': self._floor_label(),
            'share_table': dict(SHARE_TABLE_SELECTION)[self.share_table],
            'tags': self.tag_ids.mapped('name'),
            'note': self.guest_note or '',
            'state': self.state,
            'state_label': dict(STATE_SELECTION)[self.state],
            # No queue position here: the guest sees only their own estimated wait range
            # (estimated_wait*, from _queue_wait_estimates), never their place in line.
            'active': self.state in ACTIVE_STATES,
            # Only a waiting guest is tracked (live updates); Seated is the final state.
            'tracking_ended': self.state not in ACTIVE_STATES,
            'seating_active': seating_active,
            # Seated at a table and the order / seating is over: the visit is complete.
            'completed': self.state == 'seated' and bool(self.table_id) and not seating_active,
        })

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
        """``{table_id: {'reason': str, 'guests': int, 'since': datetime}}`` for the tables that
        are NOT free (``since``: when the table was taken: its oldest open order or the hold).

        Reuses Odoo's own occupancy rule (a draft pos.order on the table, as in
        ``restaurant.table.are_orders_still_in_draft``) and adds the short hold of a guest
        seated from the waitlist whose order has not reached the server yet
        (TABLE_HOLD_MINUTES). ``guests`` counts the people already there: the draft
        orders' guest count plus the parties of guests still holding the table. Several parties
        may share one table, each with its own order: their guests add up.

        ``exclusive``: a waitlist guest who asked for a private table is seated there (order
        open or table hold). Nobody else is put on that table, even a guest willing to share.
        """
        if not tables:
            return {}
        Order = self.env['pos.order'].sudo()
        Entry = self.sudo()
        busy = {}
        orders = Order.search([('table_id', 'in', tables.ids), ('state', '=', 'draft')])
        for order in orders:
            info = busy.setdefault(order.table_id.id, {
                'reason': _("Table %s has an open order.", order.table_id.table_number), 'guests': 0,
                'since': order.create_date})
            info['guests'] += order.customer_count or 0
            info['since'] = min(info['since'] or order.create_date, order.create_date)

        # Open orders of private waitlist seatings: the guest's own (linked) order, or the order
        # the host opened on their table from the floor plan (the seating's _seating_order).
        exclusive = set()
        linked = Entry.search([('pos_order_id', 'in', orders.ids)])
        exclusive.update(linked.filtered(lambda e: e.share_table == 'private').pos_order_id.table_id.ids)
        unlinked = orders - linked.pos_order_id
        for table in unlinked.table_id:
            first = unlinked.filtered(lambda o: o.table_id == table).sorted(lambda o: (o.create_date, o.id))[:1]
            seating = Entry.search([
                ('state', '=', 'seated'), ('table_id', '=', table.id), ('end_time', '<=', first.create_date),
            ], order='end_time desc, id desc', limit=1)
            if seating.share_table == 'private' and seating._seating_order() == first:
                exclusive.add(table.id)

        since = fields.Datetime.now() - timedelta(minutes=TABLE_HOLD_MINUTES)
        holds = Entry.search([
            ('state', '=', 'seated'), ('end_time', '>=', since),
            '|', ('table_id', 'in', tables.ids), ('table_ids', 'in', tables.ids),
        ])
        for hold in holds:
            if hold.table_id and hold._seating_order():
                # The guest's own order is there now: counted with the draft orders. Extra
                # tables of a combined seating are merged under the main one (left out of
                # _seatable_tables) until that order is paid.
                continue
            for table in hold._seated_tables() & tables:
                info = busy.setdefault(table.id, {
                    'reason': _("Table %(table)s was just given to %(token)s.",
                                table=table.table_number, token=hold.token),
                    'guests': 0, 'since': hold.end_time})
                # A combined party fills every one of its tables.
                info['guests'] += hold.party_size if len(hold._seated_tables()) == 1 else (table.seats or 0)
                if hold.share_table == 'private':
                    exclusive.add(table.id)
        for table_id in exclusive & set(busy):
            busy[table_id]['exclusive'] = True
        return busy

    @api.model
    def _table_busy_reasons(self, tables):
        """``{table_id: reason}`` for the tables in ``tables`` that are NOT free right now."""
        return {table_id: info['reason'] for table_id, info in self._table_occupancy(tables).items()}

    @api.model
    def _match_tables(self, config, party_size=1, share_table='private', preferred_floor=None,
                      hint_floors=None):
        """Rows of ``_match_tables_full`` (every seatable table rated, best first)."""
        return self._match_tables_full(config, party_size, share_table, preferred_floor,
                                       hint_floors)['tables']

    @api.model
    def _match_tables_full(self, config, party_size=1, share_table='private', preferred_floor=None,
                           hint_floors=None):
        """Rate every seatable table of ``config`` for one guest and rank the seating
        arrangements that can hold the whole party right now. Never assigns anything.

        Always computed from the POS's current active floors and tables and their live
        occupancy (``_table_occupancy``: draft POS orders + waitlist holds), never cached.

        Each table is rated against the party's size on its **available** seats
        (``seats - occupied``):

        * free table, enough seats            -> ``match``
        * free table, fewer seats than party  -> ``too_small`` (only usable combined)
        * busy table, guest willing to share,
          enough seats still free             -> ``shared``
        * any other busy table                -> ``busy`` (a private guest never gets
                                                 seats at another customer's table)
        * table on another floor than the one
          the guest asked for (honoured)      -> ``other_floor``

        Arrangements (``_seating_arrangements``): one ``match`` / ``shared`` table, or a group
        of free tables of one floor whose seats add up to the party (merged like the POS floor
        plan). Never an arrangement short of seats. Ranked by, in order: capacity fit (fewest
        spare seats), fewer tables, own table before a shared one, hints, nearest (tables
        closest together on the floor plan), then floor / table order.

        The guest's preferred floor is honoured only when it has at least one arrangement;
        otherwise every floor is offered and ``preference_relaxed`` is set: a preference never
        forces an unsuitable table.

        Returns ``{'tables': rows, 'arrangements': [...], 'combinations': [...],
        'preference_relaxed': bool}``; ``combinations`` are the multi-table arrangements.
        Rows are ``{'id', 'table_number', 'floor_id', 'floor_name', 'floor_sequence', 'seats',
        'occupied', 'free_seats', 'status', 'reason', 'selectable', 'combinable', 'hint',
        'position'}``; ``free_seats`` = seats available to this guest now.

        A table without a seat count (0) is treated as big enough (but never as a close fit).
        """
        tables = self._seatable_tables(config)
        occupancy = self._table_occupancy(tables)
        party_size = max(int(party_size or 1), 1)
        hint_floors = hint_floors or self.env['restaurant.floor']
        rows = []
        for table in tables:
            seats = table.seats or 0
            busy = occupancy.get(table.id)
            guests = busy['guests'] if busy else 0
            # A private party's table has no seats left for anyone else.
            free_seats = (0 if busy.get('exclusive') else max(seats - guests, 0)) if busy else seats
            if not busy:
                status = MATCH_TOO_SMALL if seats and seats < party_size else MATCH_OK
                reason = _("%(seats)s seats for a party of %(party)s: combine it with another free table.",
                           seats=seats, party=party_size) if status == MATCH_TOO_SMALL else ''
            elif share_table == 'share' and seats and guests and free_seats >= party_size:
                status = MATCH_SHARED
                reason = _("Shared: %(occupied)s / %(seats)s occupied, %(free)s seats available.",
                           occupied=guests, seats=seats, free=free_seats)
            else:
                status = MATCH_BUSY
                reason = busy['reason']
                if share_table == 'share' and busy.get('exclusive'):
                    reason = _("%(reason)s Private seating: not shared.", reason=reason)
                elif share_table == 'share' and seats and guests and free_seats:
                    reason = _("%(reason)s Only %(free)s seats available for a party of %(party)s.",
                               reason=reason, free=free_seats, party=party_size)
            rows.append({
                'id': table.id,
                'table_number': table.table_number,
                'floor_id': table.floor_id.id,
                'floor_name': table.floor_id.name,
                'floor_sequence': table.floor_id.sequence,
                'seats': seats,
                'occupied': guests,
                'free_seats': free_seats,
                'status': status,
                'reason': reason,
                'hint': table.floor_id in hint_floors,
                'position': self._table_position(table),
            })

        arrangements = self._seating_arrangements(rows, party_size)

        # The preferred floor, only when it can seat the party.
        preference_relaxed = False
        if preferred_floor:
            # Existing rule: a suitable table there, or (no single table fits anywhere) a
            # combination of its tables.
            singles_fit = [a for a in arrangements if len(a['table_ids']) == 1]
            if any(a['floor_id'] == preferred_floor.id for a in (singles_fit or arrangements)):
                for row in rows:
                    if row['floor_id'] != preferred_floor.id:
                        row['status'] = MATCH_OTHER_FLOOR
                        row['reason'] = _("Guest asked for %s.", preferred_floor.name)
                arrangements = [a for a in arrangements if a['floor_id'] == preferred_floor.id]
            else:
                preference_relaxed = True

        for row in rows:
            row['selectable'] = row['status'] in SELECTABLE_MATCHES
            row['combinable'] = row['status'] in COMBINABLE_MATCHES
        # Best first: tables that seat the party (closest fit, own table, hints, floor / table
        # order), then tables only usable combined, then the ones that cannot be picked.
        rows.sort(key=lambda r: (_MATCH_RANK[r['status']],
                                 self._spare_seats(r['free_seats'], party_size) if r['selectable'] else 0,
                                 r['status'] == MATCH_SHARED,
                                 not r['hint'],
                                 r['floor_sequence'] or 0, r['floor_id'] or 0,
                                 r['table_number'] or 0, r['id']))
        arrangements = arrangements[:MAX_ARRANGEMENTS]
        for rank, arrangement in enumerate(arrangements):
            arrangement['rank'] = rank
        return {
            'tables': rows,
            'arrangements': arrangements,
            'combinations': [a for a in arrangements if len(a['table_ids']) > 1],
            'preference_relaxed': preference_relaxed,
        }

    @api.model
    def _table_position(self, table):
        """Centre ``[x, y]`` of the table on its POS floor plan (``floor_plan_layout``, the
        layout the POS floor screen draws), or ``None`` when the table was never placed."""
        layout = table.floor_plan_layout or {}
        try:
            return [float(layout['left']) + float(layout.get('width') or 0) / 2,
                    float(layout['top']) + float(layout.get('height') or 0) / 2]
        except (KeyError, TypeError, ValueError):
            return None

    @api.model
    def _spare_seats(self, available, party_size):
        """Seats left over when ``party_size`` guests take ``available`` seats (capacity fit)."""
        return available - party_size if available else _UNKNOWN_FIT

    @api.model
    def _arrangement_spread(self, rows):
        """How far apart the tables of an arrangement are: ``(0, distance)`` from their
        floor-plan positions, ``(1, table-number gap)`` when a table was never placed (POS table
        order as the fallback), ``(0, 0)`` for one table."""
        if len(rows) < 2:
            return (0, 0)
        positions = [r['position'] for r in rows]
        if all(positions):
            distance = sum(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
                           for i, a in enumerate(positions) for b in positions[i + 1:])
            return (0, round(distance, 2))
        numbers = [r['table_number'] or 0 for r in rows]
        return (1, max(numbers) - min(numbers))

    @api.model
    def _seating_arrangements(self, rows, party_size):
        """Every way to seat the whole party right now, best first.

        * one ``match`` table (free, enough seats) or ``shared`` table (enough seats still
          free at another party's table, only for a guest willing to share);
        * several free tables of one floor (``_table_combinations``), every one of them needed
          (a group with a spare table is never offered: the smaller group is).

        Ranking (``key``): capacity fit (fewest spare seats: party 4 -> a 4-seat table, then
        2 + 2, before a 6-seat table), fewer tables, own table before a shared one, hint
        floors, nearest (tables closest together on the floor plan), floor order, table
        numbers. Each arrangement: ``{'key', 'table_ids', 'table_numbers', 'floor_id',
        'floor_name', 'floor_sequence', 'available' (per table), 'seats' (total available),
        'occupied' (per table), 'capacity' (per table), 'spare', 'shared', 'hint'}``; the first
        table is the main one.
        """
        party_size = max(int(party_size or 1), 1)
        singles = [[r] for r in rows if r['status'] in SELECTABLE_MATCHES]
        groups = singles + [
            [r for r in rows if r['id'] in combo['table_ids']]
            for combo in self._table_combinations(rows, party_size)
        ]
        arrangements = []
        for group in groups:
            group.sort(key=lambda r: (r['table_number'] or 0, r['id']))
            unknown = any(not r['seats'] for r in group)
            total = sum(r['free_seats'] for r in group)
            spare = _UNKNOWN_FIT if unknown else total - party_size
            shared = any(r['status'] == MATCH_SHARED for r in group)
            hint = all(r['hint'] for r in group)
            arrangements.append({
                'key': '-'.join(str(r['id']) for r in group),
                'table_ids': [r['id'] for r in group],
                'table_numbers': [r['table_number'] for r in group],
                'floor_id': group[0]['floor_id'],
                'floor_name': group[0]['floor_name'],
                'floor_sequence': group[0]['floor_sequence'],
                'available': [r['free_seats'] for r in group],
                'occupied': [r['occupied'] for r in group],
                'capacity': [r['seats'] for r in group],
                'seats': 0 if unknown else total,
                'spare': 0 if unknown else spare,
                'shared': shared,
                'hint': hint,
                '_key': (spare, len(group), shared, not hint, self._arrangement_spread(group),
                         group[0]['floor_sequence'] or 0, group[0]['floor_id'] or 0,
                         [r['table_number'] or 0 for r in group], [r['id'] for r in group]),
            })
        arrangements.sort(key=lambda a: a['_key'])
        for arrangement in arrangements:
            del arrangement['_key']
        return arrangements

    @api.model
    def _table_combinations(self, rows, party_size, max_nodes=COMBO_SEARCH_NODES):
        """Groups of 2+ free tables of one floor whose seats add up to ``party_size``.

        Only free tables with a seat count (``match`` / ``too_small``), never busy, held or
        shared ones (another customer's table is never merged into this party), never across
        floors (they are merged under one main POS table). Every table of a group is needed:
        dropping any one leaves the party short (minimal groups), so 4 + 2 is never offered
        for a party of 4 when the 4-seat table alone fits.

        Depth-first over the floor's free tables, largest first, pruned when the remaining
        tables cannot reach the party; at most ``max_nodes`` tables visited per floor.
        Returns ``[{'floor_id', 'floor_name', 'floor_sequence', 'table_ids', 'table_numbers',
        'seats'}]`` (unordered; ``_seating_arrangements`` ranks them).
        """
        party_size = max(int(party_size or 1), 1)
        by_floor = {}
        for row in rows:
            if row['status'] in COMBINABLE_MATCHES and row['seats']:
                by_floor.setdefault(row['floor_id'], []).append(row)
        combinations = []
        for free in by_floor.values():
            free.sort(key=lambda r: (-r['seats'], r['table_number'] or 0, r['id']))
            remaining = [0] * (len(free) + 1)  # seats of free[i:]
            for index in reversed(range(len(free))):
                remaining[index] = remaining[index + 1] + free[index]['seats']
            if remaining[0] < party_size:
                continue
            found, budget = [], [max_nodes]

            def walk(start, chosen, total):
                for index in range(start, len(free)):
                    if budget[0] <= 0 or total + remaining[index] < party_size:
                        return
                    budget[0] -= 1
                    row = free[index]
                    if total + row['seats'] >= party_size:
                        if chosen:  # a single table is not a combination
                            found.append(chosen + [row])
                        continue  # minimal: never add a table once the party fits
                    walk(index + 1, chosen + [row], total + row['seats'])

            walk(0, [], 0)
            for group in found:
                group = sorted(group, key=lambda r: (r['table_number'] or 0, r['id']))
                combinations.append({
                    'floor_id': group[0]['floor_id'],
                    'floor_name': group[0]['floor_name'],
                    'floor_sequence': group[0]['floor_sequence'],
                    'table_ids': [r['id'] for r in group],
                    'table_numbers': [r['table_number'] for r in group],
                    'seats': sum(r['seats'] for r in group),
                })
        return combinations

    # Words too generic to point at one floor when they appear in a guest's note.
    _HINT_STOP_WORDS = frozenset({
        'floor', 'area', 'zone', 'section', 'room', 'hall', 'level', 'side', 'table', 'tables',
        'seating', 'space', 'the', 'and',
    })

    def _hint_floors(self):
        """Floors suggested by this guest's context, used only to rank suitable tables:

        * the "Suggested Floors" of the guest's tags (configured per tag);
        * POS floors whose name the guest mentions in "Anything we should know"
          (e.g. "terrace please" -> floor "Terrace"), matched on the current floor names.
        """
        self.ensure_one()
        entry = self.sudo()
        floors = entry.tag_ids.floor_ids & entry.config_id.floor_ids
        words = set(re.findall(r'\w+', (entry.guest_note or '').lower()))
        if words:
            for floor in entry.config_id.floor_ids.filtered('active'):
                name_words = {w for w in re.findall(r'\w+', (floor.name or '').lower())
                              if len(w) >= 3 and not w.isdigit() and w not in self._HINT_STOP_WORDS}
                if name_words & words:
                    floors |= floor
        return floors

    def _match_my_tables_full(self):
        self.ensure_one()
        entry = self.sudo()
        return self._match_tables_full(entry.config_id, entry.party_size, entry.share_table,
                                       entry.preferred_floor_id, entry._hint_floors())

    def _match_my_tables(self):
        return self._match_my_tables_full()['tables']

    @api.model
    def get_seatable_tables(self, config_id, entry_id=False):
        """Server view of table availability for the POS table picker (RPC).

        With ``entry_id`` the tables are matched against that guest (party size, availability,
        floor, sharing, hints); ``tables`` then lists every table with its status, best first,
        and ``available_ids`` the ones the host may pick. ``floors`` are the POS's current
        active floors with a seatable table, read now from the server (a floor created or
        renamed after the POS session opened is included). ``arrangements`` are the ranked
        ways to seat the whole party right now (one table, a shared table, or free tables of
        one floor combined), closest capacity fit first; ``combinations`` the multi-table ones.
        The POS also treats tables with an unsynced open order on that terminal as taken.
        """
        config = self.env['pos.config'].browse(int(config_id))
        config.check_access('read')
        entry = self.browse(int(entry_id)).exists() if entry_id else self.browse()
        if entry and entry.config_id == config:
            entry.check_access('read')
            data = entry._match_my_tables_full()
        else:
            entry = self.browse()
            data = self._match_tables_full(config)
        rows = data['tables']
        floors = sorted({(r['floor_sequence'], r['floor_name'] or '', r['floor_id']) for r in rows})
        return {
            'available_ids': [r['id'] for r in rows if r['selectable']],
            'busy': {str(r['id']): r['reason'] for r in rows if r['status'] in (MATCH_BUSY, MATCH_SHARED)},
            'tables': rows,
            'floors': [{'id': floor_id, 'name': name, 'sequence': seq} for seq, name, floor_id in floors],
            'arrangements': data['arrangements'],
            'combinations': data['combinations'],
            'preferred_floor_id': entry.preferred_floor_id.id if entry else False,
            'preference_relaxed': data['preference_relaxed'],
            'party_size': entry.party_size if entry else 0,
        }

    @api.model
    def pos_seat_guest(self, config_id, entry_id, expected_state, table_id):
        """Seat a waiting guest at one or several existing POS tables (Waiting -> Seated).

        ``table_id`` is one table id, or a list of ids when the host combines tables for a
        party larger than one table (the first id is the main table).

        Safe against concurrent terminals: locks the entry, then every chosen table row in id
        order (always the same order, so no deadlock). The table rows are touched with a no-op
        UPDATE: two terminals seating anyone at the same table conflict on it, the second one
        fails with a serialization error and Odoo replays it on a fresh snapshot, where the
        table is now held and the seat is refused.

        The chosen tables are re-matched against the guest on the server (never trusted from
        the browser): each must still exist, be on one of this POS's floors, respect the
        guest's preferred floor when it is honoured, and be free, or (single table only) have
        enough free seats for a guest who accepted to share. A table short of seats is refused
        alone. Combined tables must all be free, on the same floor and add up to the party
        (each table re-rated now, under the locks: a stale picker is refused); the extra tables
        are merged under the main one exactly like the POS floor plan's table merge
        (``restaurant.table.set_parent_id``), so one order serves the whole party and the
        tables are released together when it is paid.

        Returns ``{'ok', 'message', 'state', 'table_id', 'table_ids', 'shared', 'tables',
        'queue', 'merged_tables'}``; ``tables`` is the fresh matching so the host can pick
        again, ``merged_tables`` the merges the POS replays on its floor plan.
        """
        config = self.env['pos.config'].browse(int(config_id)).exists()
        if not config:
            raise ValidationError(_("This Point of Sale no longer exists."))
        config.check_access('read')
        entry = self.browse(int(entry_id)).exists()

        def result(ok, message, state, table=False, shared=False, tables=None, merged=None):
            return {
                'ok': ok, 'message': message, 'state': state, 'table_id': table, 'shared': shared,
                'table_ids': tables or ([table] if table else []),
                'merged_tables': merged or [],
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
        Table = self.env['restaurant.table'].sudo()
        raw_ids = table_id if isinstance(table_id, (list, tuple)) else [table_id]
        try:
            table_ids = list(dict.fromkeys(int(t) for t in raw_ids if t))  # unique, host's order
        except (TypeError, ValueError):
            return result(False, _("This table is no longer available on this Point of Sale."), current)
        tables = Table.browse(table_ids)
        if not tables:
            if seatable:
                return result(False, _("Choose a table to seat %(token)s.", token=entry.token), current)
            entry.write({'state': 'seated', 'table_id': False})  # POS without floor plan
            return result(True, _("%(token)s is now %(state)s.", token=entry.token, state=labels['seated']),
                          'seated')

        if len(tables.exists()) != len(tables) or tables - seatable:
            return result(False, _("This table is no longer available on this Point of Sale."), current)
        # Lock every chosen table, always in id order (no deadlock between terminals).
        for locked_id in sorted(tables.ids):
            self.env.cr.execute(
                "UPDATE restaurant_table SET write_date = write_date WHERE id = %s", (locked_id,))
        # Re-rate the chosen tables now, under the locks: the picker's view may be stale.
        matches = {r['id']: r for r in entry._match_my_tables()}
        if any(t.id not in matches for t in tables):
            return result(False, _("This table is no longer available on this Point of Sale."), current)
        party = max(entry.party_size, 1)

        main = tables[0]
        shared = False
        if len(tables) > 1:
            if len(tables.floor_id) > 1:
                return result(False, _("Tables combined for one party must be on the same floor."), current)
            for table in tables:
                match = matches[table.id]
                if not match['combinable']:
                    if match['status'] in (MATCH_BUSY, MATCH_SHARED):
                        message = _("%(reason)s Only free tables can be combined. Choose another table.",
                                    reason=match['reason'] if match['status'] == MATCH_BUSY
                                    else _("Table %s is in use.", table.table_number))
                    else:
                        message = _("%s Choose another table.", match['reason'])
                    return result(False, message, current)
            seats = [matches[t.id]['seats'] for t in tables]
            if all(seats) and sum(seats) < party:
                return result(False, _(
                    "Tables %(tables)s have %(seats)s seats for a party of %(party)s. Add another "
                    "free table or choose another arrangement.",
                    tables=' + '.join(str(n) for n in tables.mapped('table_number')),
                    seats=sum(seats), party=party), current)
        else:
            match = matches[main.id]
            if not match['selectable']:
                if match['status'] == MATCH_TOO_SMALL:
                    message = _("Table %(table)s has %(seats)s seats for a party of %(party)s: "
                                "combine it with another free table or choose another table.",
                                table=main.table_number, seats=match['seats'], party=party)
                else:
                    message = _("%s Choose another table.", match['reason'])
                return result(False, message, current)
            shared = match['status'] == MATCH_SHARED

        # The guest's own order: the POS opens a new order on the table with this uuid, so a
        # shared table keeps one order (and one bill) per party, never a combined one.
        entry.write({'state': 'seated', 'table_id': main.id, 'table_ids': [fields.Command.set(tables.ids)],
                     'shared_seating': shared, 'pos_order_uuid': str(uuid.uuid4()),
                     'pos_order_id': False})  # notifies every POS

        merged = []
        extras = tables - main
        if extras:
            # Standard POS table merge: the extra tables become children of the main table.
            for index, extra in enumerate(extras):
                side = _MERGE_SIDES[index % len(_MERGE_SIDES)]
                extra.set_parent_id(main.id, side, config.id)
                merged.append({'id': extra.id, 'parent_id': main.id, 'parent_side': side})
            numbers = ' + '.join(str(n) for n in tables.mapped('table_number'))
            message = _("%(token)s seated at tables %(tables)s.", token=entry.token, tables=numbers)
        elif shared:
            message = _("%(token)s seated at shared table %(table)s.", token=entry.token, table=main.table_number)
        else:
            message = _("%(token)s seated at table %(table)s.", token=entry.token, table=main.table_number)
        res = result(True, message, 'seated', main.id, shared, tables.ids, merged)
        res['order_uuid'] = entry.sudo().pos_order_uuid
        return res

    # ------------------------------------------------------------------
    # POS integration (data + events)
    # ------------------------------------------------------------------
    def _pos_payload(self):
        share_labels = dict(SHARE_TABLE_SELECTION)
        # One queue replay per POS for all its entries (not one per entry).
        estimates = {config: self._queue_wait_estimates(config)
                     for config in self.filtered(lambda e: e.state == 'waiting').config_id}
        result = []
        for entry in self:
            data = {f: entry[f] for f in _POS_FIELDS}
            data['join_time'] = fields.Datetime.to_string(entry.join_time)
            data['id'] = entry.id
            data['tags'] = entry.tag_ids.mapped('name')
            data['position'] = entry.position
            data.update(entry._get_wait_info(estimates.get(entry.config_id, {})))
            data['preferred_floor_id'] = entry.sudo().preferred_floor_id.id or False
            data['partner_id'] = entry.sudo().partner_id.id or False
            data['guest_note'] = entry.guest_note or ''
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
