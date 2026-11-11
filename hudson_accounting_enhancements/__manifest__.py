{
    'name': 'Hudson Accounting Enhancements',
    'version': '20.0.1.0.2',
    'category': 'Accounting',
    'summary': (
        'Dynamic Interactive Financial Reports (OWL), Cash Flow Statement, Annual Report, '
        'Executive Summary, Unrealized Currency, Restructured P&L, Balance Sheet, '
        'Auto ECB Currency Rates, Extended Tax Report, Bank Reconciliation & Accruals'
    ),
    'description': """
        Comprehensive enhancements to the om_account_accountant community accounting module:

        1. Interactive Dynamic Financial Reports (OWL) for Profit and Loss, Balance Sheet,
           Cash Flow, Trial Balance, General Ledger, Partner Ledger, Aged Balances, and Tax Reports with drill-downs and XLSX/JSON export.
        2. Restructured Profit & Loss with Cost of Revenue, Gross Profit, Operating Expenses,
           Operating Profit, Other Income, and Net Profit breakdown.
        3. Balance Sheet with proper separate Equity section (Share Capital, Retained Earnings,
           Current Year Earnings) split from Liabilities.
        4. Cash Flow Statement (Indirect Method) — Operating, Investing & Financing activities.
        5. Annual Report — Combined year-end financial summary (BS + P&L in one document).
        6. Executive Summary — One-page KPI dashboard with ratios and period comparisons.
        7. Unrealized Currency Gains/Losses wizard and report for open foreign-currency items.
        8. Automatic Currency Rate Updates via the European Central Bank (ECB) XML feed.
        9. Extended Tax Report with tax group breakdown, base vs. tax amount columns.
        10. Budget Items menu correctly linked under Accounting > Management.
        11. Reconciliation improvements: manual journal entry access, auto-reconciliation wizard.
    """,
    'author': 'Hudson Software',
    'website': 'https://www.hudsonsoftwares.com',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'account_payment',
        'account_edi_proxy_client',
        'product_margin',
        'sale_timesheet',
        'fleet',
        'purchase',
        'sale_management',
        'stock_account',
        'om_account_accountant',
        'om_account_budget',
        'accounting_pdf_reports',
    ],
    'data': [
        'security/ir.access.csv',
        'security/hudson_loan_security.xml',
        'security/account_annual_report_security.xml',
        'security/hudson_multi_company_rules.xml',
        'data/account_financial_report_bs_pl.xml',
        'views/dynamic_report_action.xml',
        'wizard/hudson_set_partner_wizard_views.xml',
        'wizard/hudson_set_account_wizard_views.xml',
        'wizard/hudson_bank_match_wizard_views.xml',
        'views/account_account_views.xml',
        'views/account_move_views.xml',
        'data/currency_rate_cron.xml',
        'views/res_currency_views.xml',
        'views/account_budget_views.xml',
        'views/account_aged_report_views.xml',
        'views/report_template.xml',
        'wizard/account_cash_flow_views.xml',
        'wizard/account_annual_report_views.xml',
        'wizard/account_executive_summary_views.xml',
        'wizard/account_unrealized_currency_views.xml',
        'wizard/account_tax_extended_views.xml',
        'wizard/account_accrued_orders_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/accrual_views.xml',
        'report/report.xml',
        'report/report_aged.xml',
        'report/report_cash_flow.xml',
        'report/report_annual.xml',
        'report/report_executive_summary.xml',
        'report/report_unrealized_currency.xml',
        'report/report_tax_extended.xml',
        'report/report_dynamic_snapshot.xml',
        'wizard/account_auto_reconcile_wizard_views.xml',
        'views/account_reconcile_views.xml',
        'views/account_bank_statement_line_views.xml',
        'views/account_journal_dashboard_override.xml',
        'views/analytic_reporting_views.xml',
        'wizard/hudson_loan_compute_wizard_views.xml',
        'views/hudson_loan_views.xml',
        'wizard/hudson_inventory_valuation_wizard_views.xml',
        'views/account_multi_ledger_views.xml',
        'views/account_review_config_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hudson_accounting_enhancements/static/src/js/grid_session_init.js',
            'hudson_accounting_enhancements/static/src/scss/dynamic_report.scss',
            'hudson_accounting_enhancements/static/src/js/dynamic_report.js',
            'hudson_accounting_enhancements/static/src/xml/dynamic_report.xml',
            'hudson_accounting_enhancements/static/src/scss/reconcile_view.scss',
            'hudson_accounting_enhancements/static/src/js/bank_rec_dropdown_widget.js',
            'hudson_accounting_enhancements/static/src/xml/bank_rec_dropdown_widget.xml',
            'hudson_accounting_enhancements/static/src/scss/bank_matching.scss',
            'hudson_accounting_enhancements/static/src/js/bank_matching_list_renderer.js',
            'hudson_accounting_enhancements/static/src/xml/bank_matching_list_renderer.xml',
            'hudson_accounting_enhancements/static/src/scss/annual_report.scss',
            'hudson_accounting_enhancements/static/src/scss/inventory_valuation.scss',
            'hudson_accounting_enhancements/static/src/views/grid/grid_view.scss',
            'hudson_accounting_enhancements/static/src/views/grid/grid_controller.js',
            'hudson_accounting_enhancements/static/src/views/grid/grid_view.js',
            'hudson_accounting_enhancements/static/src/views/grid/grid_controller.xml',
        ],
        'web.assets_backend_lazy': [
            'hudson_accounting_enhancements/static/src/js/pivot_model_fix.js',
        ],
        'web.report_assets_common': [
            'hudson_accounting_enhancements/static/src/css/report_fixes.css',
        ],
    },
    'application': False,
    'installable': True,
    'auto_install': False,
    'images': [],
}

