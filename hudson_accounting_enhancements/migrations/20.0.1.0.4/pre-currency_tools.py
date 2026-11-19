import logging

_logger = logging.getLogger(__name__)


def _column_exists(cr, table, column):
    cr.execute("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s", (table, column))
    return bool(cr.fetchone())


def migrate(cr, version):
    """ One exchange rate updater and one currency revaluation engine.

    1. The "Fetch ECB Currency Rates" scheduled action of this module is deleted (post-currency_tools.py):
       when it was active, the root companies still updated by hand switch to the daily update of
       om_currency_rate_update, from the same sources (ECB, backup open.er-api.com through ExchangeRate-API without
       key), so that the rates keep being updated.
    2. The adjustment entries of the "Make Adjustment Entry" wizard are marked as currency revaluations, so that
       the revaluation engine of om_currency_revaluation, which now posts them, counts those never reversed instead
       of booking the same gain or loss again.
    """
    if not version:
        return
    cr.execute("""
        SELECT cron.id, cron.active
          FROM ir_cron cron
          JOIN ir_model_data imd ON imd.model = 'ir.cron' AND imd.res_id = cron.id
         WHERE imd.module = 'hudson_accounting_enhancements' AND imd.name = 'ir_cron_fetch_ecb_currency_rates'
    """)
    row = cr.fetchone()
    if row and row[1]:
        cr.execute("UPDATE ir_cron SET active = FALSE WHERE id = %s", (row[0],))
        if _column_exists(cr, 'res_company', 'rate_interval'):
            cr.execute("""
                UPDATE res_company
                   SET rate_interval = 'daily', rate_provider = 'ecb', rate_fallback_provider = 'exchangerate_api',
                       rate_next_date = NULL
                 WHERE parent_id IS NULL AND rate_interval = 'manual'
             RETURNING name
            """)
            names = [name for name, in cr.fetchall()]
            if names:
                _logger.info("The automatic ECB rates of %s are now updated daily by om_currency_rate_update",
                             ', '.join(str(name) for name in names))
        # the scheduled action of om_currency_rate_update runs every day and follows the interval of each company
        cr.execute("""
            UPDATE ir_cron SET active = TRUE
             WHERE id IN (SELECT res_id FROM ir_model_data
                           WHERE module = 'om_currency_rate_update' AND name = 'ir_cron_update_currency_rates'
                             AND model = 'ir.cron')
        """)

    if _column_exists(cr, 'account_move', 'currency_reval_date'):
        cr.execute("""
            UPDATE account_move
               SET currency_reval_date = date
             WHERE move_type = 'entry'
               AND currency_reval_date IS NULL
               AND reversed_entry_id IS NULL
               AND ref LIKE 'Foreign currencies adjustment entry as of %%'
        """)
        if cr.rowcount:
            _logger.info("%s adjustment entries of the Unrealized Currencies report marked as currency revaluations",
                         cr.rowcount)
