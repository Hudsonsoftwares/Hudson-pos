# -*- coding: utf-8 -*-
"""eh.hr.audited.mixin - automatic audit-log emission on write/create/unlink.

Inheriting models gain:
    * before/after snapshots of audited fields on every write,
    * create + unlink rows in the audit log,
    * a class-level ``_audit_fields`` whitelist (default: all stored fields
      except mail-thread/follower fields) to control what is captured.

The audit log itself is append-only and hash-chained - see
``eh_hr_core/models/audit_log.py``.
"""
from odoo import api, models


_DEFAULT_EXCLUDED = {
    'create_uid', 'create_date', 'write_uid', 'write_date',
    'message_ids', 'message_follower_ids', 'activity_ids',
    '__last_update', 'display_name',
}


class HrAuditedMixin(models.AbstractModel):
    _name = 'eh.hr.audited.mixin'
    _description = 'EH HR Platform - audited record mixin'

    # Override in concrete model: explicit list of field names to capture.
    # Default: capture every stored field that isn't in _DEFAULT_EXCLUDED.
    _audit_fields = None

    def _audit_fields_to_capture(self):
        if self._audit_fields is not None:
            return list(self._audit_fields)
        return [
            name for name, fld in self._fields.items()
            if fld.store and name not in _DEFAULT_EXCLUDED
        ]

    # ------------------------------------------------------------------
    # ORM hooks
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        audit = self.env['eh.hr.audit.log'].sudo()
        for rec in records:
            audit.write_event(
                model=rec._name,
                record_id=rec.id,
                action='create',
                actor=self.env.user,
                payload={k: rec[k] for k in rec._audit_fields_to_capture()
                         if k in rec._fields},
                company_id=rec._audit_company_id(),
            )
        return records

    def write(self, vals):
        # Capture before state for audited fields only - avoid wide reads.
        audit_fields = set(self._audit_fields_to_capture())
        captured = {f for f in vals.keys() if f in audit_fields}
        before = {rec.id: {f: rec[f] for f in captured} for rec in self}
        result = super().write(vals)
        audit = self.env['eh.hr.audit.log'].sudo()
        for rec in self:
            after = {f: rec[f] for f in captured}
            if before.get(rec.id) == after:
                continue
            audit.write_event(
                model=rec._name,
                record_id=rec.id,
                action='write',
                actor=self.env.user,
                payload={'before': before.get(rec.id, {}), 'after': after},
                company_id=rec._audit_company_id(),
            )
        return result

    def unlink(self):
        audit = self.env['eh.hr.audit.log'].sudo()
        snaps = [(rec._name, rec.id, rec.display_name, rec._audit_company_id())
                 for rec in self]
        result = super().unlink()
        for model, rid, name, company_id in snaps:
            audit.write_event(
                model=model, record_id=rid, action='unlink',
                actor=self.env.user, payload={'display_name': name},
                company_id=company_id,
            )
        return result

    def _audit_company_id(self):
        """Owning company id for the audit row, or None if the record is not
        company-scoped. Used so per-company audit-log rules can isolate reads."""
        self.ensure_one()
        if 'company_id' in self._fields and self.company_id:
            return self.company_id.id
        return None
