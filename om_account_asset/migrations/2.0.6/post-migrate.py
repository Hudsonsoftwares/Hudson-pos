import logging

from odoo import api, fields, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """ 2.0.6:

    * draft assets whose manual first depreciation date was defaulted to the purchase date get the end of
      the purchase period instead (the first period ended on the purchase date: a one-day entry with prorata
      temporis, a period depreciated before the purchase without it)
    * the remaining (draft) depreciation entries of the running degressive assets depreciated by period are
      computed again: the yearly degressive factor was applied to every period
    * the disposal entries left in draft by the sale or disposal of an asset are posted
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Asset = env['account.asset.asset'].with_context(active_test=False)

    draft_assets = Asset.search([
        ('state', '=', 'draft'),
        ('date_first_depreciation', '=', 'manual'),
        ('first_depreciation_manual_date', '!=', False),
    ]).filtered(lambda a: a.first_depreciation_manual_date == a.date)
    for asset in draft_assets:
        asset.first_depreciation_manual_date = asset._get_default_first_depreciation_date()
    if draft_assets:
        _logger.info("First depreciation date moved to the end of the purchase period on %s draft assets",
                     len(draft_assets))

    degressive_assets = Asset.search([
        ('state', '=', 'open'),
        ('method', 'in', ('degressive', 'degressive_then_linear')),
        ('method_time', '!=', 'rate'),
        ('method_period', '<', 12),
    ])
    for asset in degressive_assets:
        try:
            with cr.savepoint():
                asset._recompute_board()
        except Exception:
            _logger.exception("Could not recompute the depreciation board of the asset %s (id %s)",
                              asset.name, asset.id)

    today = fields.Date.context_today(Asset)
    disposals = Asset.search([('state', '=', 'close'), ('disposal_move_id.state', '=', 'draft')]).disposal_move_id
    for move in disposals:
        try:
            with cr.savepoint():
                # an entry dated in the future is posted on its date by the auto-post job
                move._post(soft=True)
        except Exception:
            _logger.exception("Could not post the disposal entry %s (id %s) dated %s, post it manually",
                              move.display_name, move.id, move.date)
    if disposals:
        _logger.info("Posted the draft disposal entries of %s closed assets (%s dated after %s stay scheduled)",
                     len(disposals), len(disposals.filtered(lambda m: m.date > today)), today)
