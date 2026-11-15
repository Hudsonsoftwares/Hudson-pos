# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Existing fields (preserved) ──────────────────────────────────────────

    field_service_default_hourly_rate = fields.Float(
        string='Default Hourly Rate',
        config_parameter='hudson_field_service.default_hourly_rate',
        default=50.0,
        help='Default hourly rate used when creating invoices for field service time.',
    )

    # ── Scheduling ────────────────────────────────────────────────────────────

    fs_project_planning = fields.Boolean(
        string='Project Planning',
        config_parameter='hudson_field_service.fs_project_planning',
        default=True,
        help=(
            'Allow field service orders to be linked to project tasks. '
            'Materials added to the order will be invoiced against the '
            'project\'s originating sale order when available.'
        ),
    )
    fs_planning_enabled = fields.Boolean(
        string='Field Service Jobs',
        config_parameter='hudson_field_service.fs_planning_enabled',
        default=True,
        help='Shifts with a customer are field service jobs (timer, photos, products, worksheet, invoicing).',
    )
    fs_planning_auto_plan = fields.Boolean(
        string='Auto Plan',
        config_parameter='hudson_field_service.fs_planning_auto_plan',
        default=True,
        help='Enable automatic scheduling of field service orders based on role and availability.',
    )

    # ── Field Service features ────────────────────────────────────────────────

    fs_timesheets = fields.Boolean(
        string='Timesheets',
        config_parameter='hudson_field_service.fs_timesheets',
        default=True,
        help='Enable time tracking on field service orders via the built-in timer.',
    )
    fs_billing = fields.Boolean(
        string='Billing',
        config_parameter='hudson_field_service.fs_billing',
        default=True,
        help=(
            'Invoice time and materials to customers. '
            'When enabled, products added to a field service order are '
            'automatically synced to the linked (or auto-created) sale order.'
        ),
    )
    fs_worksheets = fields.Boolean(
        string='Worksheets',
        config_parameter='hudson_field_service.fs_worksheets',
        default=True,
        help='Allow technicians to document the work performed using the Worksheet tab.',
    )
    fs_products = fields.Boolean(
        string='Products',
        config_parameter='hudson_field_service.fs_products',
        default=True,
        help='Track materials and parts used during field service visits.',
    )
    fs_hide_prices = fields.Boolean(
        string='Hide Prices on Customer Report',
        config_parameter='hudson_field_service.fs_hide_prices',
        default=False,
        help='Remove unit prices and subtotals from the PDF report sent to customers.',
    )
    fs_customer_signature = fields.Boolean(
        string='Customer Report & Signature',
        config_parameter='hudson_field_service.fs_customer_signature',
        default=True,
        help=(
            'Enable the customer report (PDF) and allow customers to provide '
            'a digital signature via the customer portal.'
        ),
    )
    fs_geolocation = fields.Boolean(
        string='Geolocation',
        config_parameter='hudson_field_service.fs_geolocation',
        default=True,
        help=(
            'Track technicians\' GPS location when they start/resume a timer. '
            'Managers can view all active technicians on the Live Map.'
        ),
    )
    fs_location_radius = fields.Float(
        string='Location Radius (meters)',
        config_parameter='hudson_field_service.fs_location_radius',
        default=500.0,
        help='Radius around the customer address. Used for validation or live map alerts.',
    )
    fs_radius_validation = fields.Boolean(
        string='Radius Sign In',
        config_parameter='hudson_field_service.fs_radius_validation',
        default=False,
        help='Strictly allow sign in/out only within the specified radius of the customer location.',
    )

    # ── Sale Order & Invoicing ─────────────────────────────────────────────────

    fs_auto_sale_order = fields.Boolean(
        string='Auto-create Sale Order for Products',
        config_parameter='hudson_field_service.fs_auto_sale_order',
        default=True,
        help=(
            'Automatically create a sale order when products are added to a '
            'standalone field service order (i.e., not linked to a project sale order). '
            'Products will be added as sale order lines and invoiced via that SO.'
        ),
    )

    # ── Customer Satisfaction ─────────────────────────────────────────────────

    fs_customer_ratings = fields.Boolean(
        string='Customer Ratings',
        config_parameter='hudson_field_service.fs_customer_ratings',
        default=False,
        help=(
            'Automatically send a satisfaction survey to the customer when a '
            'field service order is marked as Done.'
        ),
    )
    fs_rating_survey_id = fields.Many2one(
        'survey.survey',
        string='Rating Survey Template',
        config_parameter='hudson_field_service.fs_rating_survey_id',
        help='The survey sent to customers after a completed intervention.',
    )

    # ── Inventory & Stock ─────────────────────────────────────────────────────

    fs_stock_deduction = fields.Boolean(
        string='Automatic Stock Deduction',
        config_parameter='hudson_field_service.fs_stock_deduction',
        default=False,
        help='Automatically deduct stock (create and validate a delivery order) when a field service order is marked Done.',
    )
    fs_default_picking_type_id = fields.Many2one(
        'stock.picking.type',
        string='Default Picking Type',
        config_parameter='hudson_field_service.fs_default_picking_type_id',
        domain="[('code', '=', 'outgoing')]",
        help='The operation type used to deduct stock for field service products.',
    )


    # ── Operations ─────────────────────────────────────────────────────────────

    fs_mapbox_token = fields.Char(
        string='Mapbox Token',
        config_parameter='hudson_field_service.fs_mapbox_token',
        help='Mapbox access token: real driving routes and travel times on the maps and for travel fees.',
    )
    fs_equipment = fields.Boolean(
        string='Equipment',
        config_parameter='hudson_field_service.fs_equipment',
        default=True,
        help='Track customer equipment and its intervention history.',
    )
    fs_maintenance_contracts = fields.Boolean(
        string='Maintenance Contracts',
        config_parameter='hudson_field_service.fs_maintenance_contracts',
        default=False,
        help='Track whether customer equipment is covered by a maintenance contract. '
             'Jobs on covered equipment are under warranty and are not invoiced.',
    )
    fs_confirmation_email = fields.Boolean(
        string='Confirmation Email',
        config_parameter='hudson_field_service.fs_confirmation_email',
        default=True,
        help='Send a confirmation email to the customer when a shift is published.',
    )
    fs_confirmation_template_id = fields.Many2one(
        'mail.template',
        string='Email Template',
        config_parameter='hudson_field_service.fs_confirmation_template_id',
        domain="[('model', '=', 'field.service.order')]",
    )

    # ── Sales & Billing ──────────────────────────────────────────────────────────

    fs_travel_fees = fields.Boolean(
        string='Travel Fees',
        config_parameter='hudson_field_service.fs_travel_fees',
        default=False,
        help="Invoice the travel time to the customer's location.",
    )
    fs_travel_product_id = fields.Many2one(
        'product.product',
        string='Travel Product',
        config_parameter='hudson_field_service.fs_travel_product_id',
        domain="[('type', '=', 'service')]",
        help='Service invoiced per hour of travel (round trip).',
    )
    fs_website_form = fields.Boolean(
        string='Website Form',
        config_parameter='hudson_field_service.fs_website_form',
        default=True,
        help='Collect intervention requests via an online form.',
    )
    fs_website_form_url = fields.Char(string='Form URL', compute='_compute_fs_website_form_url')

    def _compute_fs_website_form_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_str('web.base.url')
        for settings in self:
            settings.fs_website_form_url = f'{base_url}/field-service/request'

    def set_values(self):
        Order = self.env['field.service.order']
        planning_was_enabled = Order._is_planning_sync_enabled()
        super().set_values()
        if Order._is_planning_sync_enabled() != planning_was_enabled:
            Order._resync_all_planning_slots()
