# -*- coding: utf-8 -*-
"""eh.hr.rate.limit - fixed-window rate-limit counter for public endpoints.

The public biometric / kiosk / visitor / mobile routes authenticate a
*device*, not a person. A stolen device token would otherwise permit
unbounded calls: bulk PII pulls and PIN brute force. This model gives those
controllers a cheap, worker-shared, restart-durable throttle: one upserted
counter row per (scope, key, fixed-window). The increment is a single atomic
SQL upsert, so it is correct under concurrent gunicorn/gevent workers without
any python-level lock or in-memory dict (which would not survive a restart or
be shared across workers).
"""
import time

from odoo import api, fields, models


class EhHrRateLimit(models.Model):
    _name = 'eh.hr.rate.limit'
    _description = 'EH HR fixed-window rate-limit counter'
    _log_access = False  # high-churn counter table; no create/write metadata

    scope = fields.Char(required=True, index=True,
                        help='Logical bucket, e.g. "mobile.pair".')
    key = fields.Char(required=True, index=True,
                      help='Per-caller discriminator, e.g. client IP or token.')
    window_start = fields.Integer(required=True, index=True,
                                  help='Unix epoch second the window starts at.')
    hits = fields.Integer(default=0)

    # Odoo 19 builds constraints from models.Constraint; 16 to 18 use the
    # _sql_constraints list. Keep both so the unique index (which the hit()
    # upsert's ON CONFLICT targets) exists on every version.
    if hasattr(models, 'Constraint'):
        _unique_window = models.Constraint(
            'unique(scope, key, window_start)',
            'One rate-limit counter row per (scope, key, window).')
    else:
        _sql_constraints = [
            ('unique_window', 'unique(scope, key, window_start)',
             'One rate-limit counter row per (scope, key, window).'),
        ]

    @api.model
    def hit(self, scope, key, limit, window_seconds=60):
        """Register one call. Return True if still within ``limit`` for the
        current window, False if the limit is exceeded (caller should 429).

        A non-positive limit disables throttling. A missing key collapses to a
        single shared bucket so a header-less caller is still bounded.
        """
        if not limit or limit <= 0:
            return True
        key = (key or 'anon')[:128]
        now = int(time.time())
        window = max(1, int(window_seconds))
        window_start = now - (now % window)
        # Atomic upsert: insert at 1, or increment an existing row. RETURNING
        # gives the post-increment count in a single round trip, so two workers
        # racing the same bucket can never both read a stale count.
        self.env.cr.execute(
            """
            INSERT INTO eh_hr_rate_limit (scope, key, window_start, hits)
            VALUES (%s, %s, %s, 1)
            ON CONFLICT (scope, key, window_start)
            DO UPDATE SET hits = eh_hr_rate_limit.hits + 1
            RETURNING hits
            """,
            (scope, key, window_start),
        )
        hits = self.env.cr.fetchone()[0]
        return hits <= limit

    @api.model
    def _gc_windows(self, older_than_seconds=3600):
        """Delete counter rows from windows that closed more than
        ``older_than_seconds`` ago. Wired to a daily cron so the table stays
        small no matter how busy the endpoints are."""
        cutoff = int(time.time()) - max(0, int(older_than_seconds))
        self.env.cr.execute(
            "DELETE FROM eh_hr_rate_limit WHERE window_start < %s", (cutoff,))
