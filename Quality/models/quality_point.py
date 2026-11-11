# -*- coding: utf-8 -*-
import random

from dateutil.relativedelta import relativedelta

# pyrefly: ignore [missing-import]
from odoo import api, fields, models
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError


class QualityPoint(models.Model):
    """Quality Control Point (QCP).

    This is the *rule*: "when this operation happens, generate this kind
    of inspection". It never represents an inspection itself - that is the
    job of quality.check, which is generated from a quality.point.
    """
    _name = 'quality.point'
    _description = 'Quality Control Point'
    _inherit = ['mail.thread']
    _order = 'sequence, id'
    _rec_name = 'name'

    TEST_TYPES = [
        ('instructions', 'Instructions'),
        ('picture', 'Take a Picture'),
        ('passfail', 'Pass - Fail'),
        ('measure', 'Measure'),
        ('spreadsheet', 'Spreadsheet'),
    ]

    name = fields.Char(string='Reference', default='New', copy=False, readonly=True)
    title = fields.Char(string='Title')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company)
    color = fields.Integer(default=0)

    # ---- WHAT: products / categories -------------------------------------
    apply_to = fields.Selection([
        ('products', 'Products'),
        ('categories', 'Categories')
    ], string='Apply to', default='products')
    product_ids = fields.Many2many('product.product', string='Products')
    product_category_id = fields.Many2one('product.category', string='Product Category')

    # ---- WHERE: operations --------------------------------------------
    picking_type_ids = fields.Many2many(
        'stock.picking.type', string='Operations',
        help='Receipts, Deliveries, Internal Transfers... this QCP applies to.')
    applies_to_manufacturing = fields.Boolean(
        string='Applies to Manufacturing',
        help='Check this to generate quality checks on Manufacturing Orders / Work Orders.')
    workorder_operation_id = fields.Many2one(
        'mrp.routing.workcenter', string='Work Order Operation',
        help='Restrict this QCP to one specific operation/step of the routing '
             '(e.g. Assembly, Painting). Leave empty to apply to the whole '
             'manufacturing order.')

    # ---- WHO -------------------------------------------------------------
    team_id = fields.Many2one('quality.team', string='Quality Team')
    user_id = fields.Many2one('res.users', string='Responsible')

    # ---- HOW MUCH: control per --------------------------------------------
    control_per = fields.Selection([
        ('operation', 'Operation'),
        ('product', 'Product'),
        ('quantity', 'Quantity'),
    ], default='operation', required=True, string='Control Per',
        help='Operation: one check for the whole transfer/MO.\n'
             'Product: one check per distinct product on the transfer/MO.\n'
             'Quantity: partial-quantity sampling, supports Failure Locations.')

    # ---- HOW OFTEN: frequency ----------------------------------------------
    control_frequency = fields.Selection([
        ('all', 'All'),
        ('random', 'Randomly'),
        ('periodical', 'Periodically'),
        ('on_demand', 'On-Demand'),
    ], default='all', required=True, string='Control Frequency')
    random_percentage = fields.Float(string='Random % ', default=100.0)
    periodic_qty = fields.Integer(string='Every', default=1)
    periodic_uom = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
    ], default='day', string='Period Unit')
    testing_percentage_within_lot = fields.Float(
        string='Testing Percentage Within Lot', 
        default=100.0,
        help="Defines the percentage within a lot that should be tested"
    )
    last_check_date = fields.Datetime(string='Last Generated On')

    # ---- WHAT KIND: check type -------------------------------------------
    test_type = fields.Selection(TEST_TYPES, default='passfail', required=True, string='Type')

    # Measure-specific
    norm = fields.Float(string='Norm')
    norm_unit = fields.Char(string='Unit')
    tolerance_min = fields.Float(string='Tolerance Min')
    tolerance_max = fields.Float(string='Tolerance Max')

    # Devices
    device_id = fields.Many2one('quality.device', string='Device')
    obox_device_id = fields.Many2one('quality.obox.device', string='Obox Device')



    # Spreadsheet
    spreadsheet_template_id = fields.Many2one(
        'quality.spreadsheet.template',
        string='Spreadsheet Template',
        help='Spreadsheet template to duplicate onto every generated check.')
    spreadsheet_success_cell = fields.Char(
        string='Success Cell',
        help='Reference identifying which cell/field determines pass/fail.')

    # ---- TEXT AREAS --------------------------------------------------------
    instructions = fields.Html(string='Instructions', help='Shown to the employee performing the check.')
    failure_message = fields.Html(string='Message If Failure', help='What to do if the check fails.')
    notes = fields.Html(string='Notes', help='Internal notes, NOT shown to the employee performing the check.')

    failure_location_ids = fields.Many2many(
        'stock.location', string='Failure Locations',
        help="If quality check fails, a destination location is chosen from this list for\n"
             "- each failed specific product quantity if control is per quantity\n"
             "- all quantities of a product if control is per product\n"
             "- all quantities of products in the operation if control is per operation"
    )

    check_ids = fields.One2many('quality.check', 'point_id', string='Generated Checks')
    check_count = fields.Integer(compute='_compute_check_count')

    @api.depends('check_ids')
    def _compute_check_count(self):
        for point in self:
            point.check_count = self.env['quality.check'].search_count([('point_id', '=', point.id)]) if point.id else 0

    @api.onchange('spreadsheet_template_id')
    def _onchange_spreadsheet_template_id(self):
        if self.spreadsheet_template_id and self.spreadsheet_template_id.success_cell:
            self.spreadsheet_success_cell = self.spreadsheet_template_id.success_cell

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('quality.point') or 'New'
        return super().create(vals_list)

    @api.constrains('picking_type_ids', 'applies_to_manufacturing')
    def _check_has_operation(self):
        for point in self:
            if not point.picking_type_ids and not point.applies_to_manufacturing:
                raise ValidationError(
                    'A Quality Control Point needs at least one Inventory '
                    'Operation selected, or "Applies to Manufacturing" enabled.')

    @api.constrains('control_per', 'testing_percentage_within_lot')
    def _check_testing_percentage(self):
        for point in self:
            if point.control_per == 'quantity' and point.testing_percentage_within_lot <= 0.0:
                raise ValidationError('The Testing Percentage must be strictly greater than 0% when controlling by Quantity.')



    def action_view_checks(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'Quality.action_quality_check')
        action['domain'] = [('point_id', '=', self.id)]
        action['context'] = {'default_point_id': self.id}
        return action

    # -------------------------------------------------------------------
    # Rule engine
    # -------------------------------------------------------------------
    def _should_trigger(self):
        """Decide, according to control_frequency, whether this QCP should
        generate a new check right now."""
        self.ensure_one()
        if self.control_frequency == 'all':
            return True
        if self.control_frequency == 'on_demand':
            return False
        if self.control_frequency == 'random':
            return (random.random() * 100.0) <= (self.random_percentage or 0.0)
        if self.control_frequency == 'periodical':
            if not self.last_check_date:
                return True
            unit = self.periodic_uom or 'day'
            qty = self.periodic_qty or 1
            delta = relativedelta(**{f'{unit}s': qty})
            return fields.Datetime.now() >= (self.last_check_date + delta)
        return True

    @api.model
    def _get_matching_points(self, company, products=None, picking_type=None,
                              is_manufacturing=False, workorder_operation=None):
        """Return quality.point recordset applicable to the given context."""
        domain = [
            ('active', '=', True),
            '|', ('company_id', '=', company.id), ('company_id', '=', False),
        ]
        if is_manufacturing:
            domain += [('applies_to_manufacturing', '=', True)]
            if workorder_operation:
                domain += ['|',
                           ('workorder_operation_id', '=', False),
                           ('workorder_operation_id', '=', workorder_operation.id)]
        else:
            if picking_type:
                domain += [('picking_type_ids', 'in', picking_type.ids)]

        points = self.search(domain)

        def matches_product(point):
            if not products:
                return True
            if point.product_ids:
                return bool(point.product_ids & products)
            if point.product_category_id:
                cat_id_str = str(point.product_category_id.id)
                return any(
                    p.categ_id == point.product_category_id or
                    cat_id_str in (p.categ_id.parent_path or '').split('/')
                    for p in products
                )
            return True  # no product/category restriction -> applies to everything

        return points.filtered(matches_product)

    def _mark_triggered(self):
        self.write({'last_check_date': fields.Datetime.now()})
