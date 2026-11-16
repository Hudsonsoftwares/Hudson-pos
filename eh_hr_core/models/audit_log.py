# -*- coding: utf-8 -*-
"""eh.hr.audit.log: append-only, hash-chained audit trail.

Every row records who did what, to which record, at which time, with the
before and after payload as JSON. Each row also stores the sha256 of the
previous row's hash plus its own fields, so any edit that does not recompute
the entire downstream chain is caught by verify_chain(). That gives a cheap
integrity check independent of mail.thread.

Retention is configurable via res.config.settings. Archived rows are exported
to CSV ir.attachments and removed from the hot table.
"""
import hashlib
import json
from odoo import api, fields, models


class HrAuditLog(models.Model):
    _name = 'eh.hr.audit.log'
    _description = 'EH HR Platform audit log'
    _order = 'id DESC'
    _log_access = False  # we are the audit log; don't audit ourselves

    # Fixed, app-wide key for the transaction-scoped advisory lock that
    # serializes chain appends. Any stable bigint works.
    _CHAIN_LOCK_KEY = 729107561

    model = fields.Char(required=True, index=True)
    record_id = fields.Integer(index=True)
    action = fields.Char(required=True, index=True)
    actor_id = fields.Many2one('res.users', index=True)
    # Owning company of the audited event, for per-company read isolation via
    # ir.rule. Deliberately NOT part of the hash chain material below: adding
    # this column never alters an existing row's row_hash, so the chain stays
    # valid across the upgrade that introduces it. Null = system-wide event.
    company_id = fields.Many2one('res.company', index=True)
    occurred_at = fields.Datetime(default=fields.Datetime.now, index=True, required=True)
    correlation_id = fields.Char(index=True)
    payload = fields.Json()
    prev_hash = fields.Char(size=64)
    row_hash = fields.Char(size=64, index=True)

    @staticmethod
    def _json_safe(value):
        """Coerce an arbitrary value into something the Json column and
        json.dumps both accept, recursively.

        The audit payload is built from raw field reads (see audited_mixin),
        so relational fields arrive as recordsets and date/datetime fields as
        Python objects. Postgres' jsonb adapter calls json.dumps WITHOUT a
        ``default`` fallback, so an un-coerced recordset raises
        ``TypeError: Object of type res.company is not JSON serializable``.
        Coercing here (used for BOTH the stored column and the hash material)
        keeps the two representations identical, so the chain stays symmetric.
        """
        if isinstance(value, models.BaseModel):
            return value.ids
        if isinstance(value, dict):
            return {str(k): HrAuditLog._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [HrAuditLog._json_safe(v) for v in value]
        if isinstance(value, bytes):
            return value.decode('utf-8', 'replace')
        try:
            json.dumps(value)
            return value
        except TypeError:
            return str(value)

    @staticmethod
    def _chain_material(prev_hash, model, record_id, action, actor_id, payload):
        """Canonical bytes that the row hash is taken over.

        Used by BOTH append and verify so the two can never diverge. A missing
        actor is normalised to 0 on both paths (a previous version hashed it
        as 0 on append but as the string 'False' on verify, which broke the
        chain for every actorless row).
        """
        return '|'.join([
            prev_hash, model or '', str(record_id), action or '',
            str(actor_id or 0),
            json.dumps(payload or {}, sort_keys=True, default=str),
        ])

    @api.model
    def write_event(self, model, record_id, action, actor, payload=None,
                    correlation_id=None, company_id=None):
        """Append a hash-chained row. Always called via sudo() upstream.

        A hash chain is inherently serial: each row's hash depends on the
        current tail. Without serialisation two concurrent transactions can
        read the same tail and fork the chain. We take a transaction-scoped
        Postgres advisory lock so appends are strictly ordered; it releases
        automatically on commit or rollback.
        """
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)',
                            [self._CHAIN_LOCK_KEY])
        last = self.search([], order='id DESC', limit=1)
        prev_hash = last.row_hash if last else ('0' * 64)
        payload = self._json_safe(payload or {})
        actor_id = actor.id if actor else 0
        material = self._chain_material(prev_hash, model, record_id, action,
                                        actor_id, payload)
        row_hash = hashlib.sha256(material.encode('utf-8')).hexdigest()
        if company_id is None and actor:
            company_id = actor.company_id.id
        return self.create({
            'model': model,
            'record_id': record_id,
            'action': action,
            'actor_id': actor.id if actor else False,
            'company_id': company_id or False,
            'correlation_id': correlation_id,
            'payload': payload,
            'prev_hash': prev_hash,
            'row_hash': row_hash,
        })

    def verify_chain(self, limit=None, batch_size=10000):
        """Walk the chain forward, asserting each row's hash matches.

        Returns the id of the first broken row, or False if the chain is
        intact. Uses keyset pagination and clears the cache per batch, so the
        working set stays bounded no matter how large the log grows.
        """
        prev = '0' * 64
        last_id = 0
        checked = 0
        while True:
            rows = self.search([('id', '>', last_id)],
                               order='id ASC', limit=batch_size)
            if not rows:
                return False
            for r in rows:
                material = self._chain_material(
                    prev, r.model, r.record_id, r.action,
                    r.actor_id.id or 0, r.payload,
                )
                expected = hashlib.sha256(material.encode('utf-8')).hexdigest()
                if expected != r.row_hash:
                    return r.id
                prev = r.row_hash
                last_id = r.id
                checked += 1
                if limit and checked >= limit:
                    return False
            self.env.invalidate_all()
