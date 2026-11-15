# Developer Guide - Hudson Rental Management

Guide for developers who want to understand, modify, or extend the Hudson Rental Management module.

---

## Architecture Overview

### MVC Pattern
The module follows Odoo's Model-View-Controller architecture:
- **Models**: Business logic (`models/`)
- **Views**: UI definitions (`views/`)
- **Controllers**: Web routing (`controllers/`)

### Module Structure
```
hudson_rental/
├── models/          # Business logic layer
├── views/           # Presentation layer
├── controllers/     # Web request handlers
├── wizard/          # Transient models for workflows
├── report/          # Reporting and analytics
├── data/            # Data files and templates
├── security/        # Access control
└── static/          # Frontend assets
```

---

## Core Models

### 1. rental.order
Main rental order model managing the complete rental lifecycle.

**Key Fields:**
```python
name                # Order reference (RNT/00001)
partner_id          # Customer
pickup_date         # When customer gets items
return_date         # Expected return date
actual_return_date  # Actual return (if returned)
state               # Order status
amount_total        # Total amount
amount_late_fee     # Late fees
```

**Key Methods:**
```python
action_confirm()         # Confirm order
action_reserve()         # Reserve stock
action_pickup()          # Process pickup
action_return()          # Process return
action_extend()          # Extend rental
action_create_invoice()  # Generate invoice
```

**States:**
```python
draft → confirmed → reserved → picked_up → returned → done
                                    ↓
                                cancel
```

### 2. rental.order.line
Individual rental items within an order.

**Key Fields:**
```python
product_id       # Rental product
quantity         # Quantity to rent
duration_days    # Rental duration
price_unit       # Price per item
late_fee         # Late return penalty
rental_status    # Line status
```

**Computed Fields:**
```python
_compute_duration()    # Calculate duration
_compute_amount()      # Calculate prices
_compute_late_fee()    # Calculate penalties
```

### 3. rental.pricing
Pricing rules for rental products.

**Key Fields:**
```python
product_tmpl_id  # Product
duration         # Duration value (1, 7, 30)
duration_unit    # hour/day/week/month
price            # Rental price
```

**Methods:**
```python
get_price_per_day()  # Normalize to daily rate
```

### 4. rental.report
Analytics model for reporting (SQL view).

**Purpose:** Aggregates rental data for analysis

---

## Extending the Module

### Add Custom Fields

**Example: Add "Equipment Condition" field**

```python
# models/rental_order.py
from odoo import fields, models

class RentalOrder(models.Model):
    _inherit = 'rental.order'
    
    equipment_condition = fields.Selection([
        ('new', 'New'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
    ], string='Equipment Condition', default='good')
```

```xml
<!-- views/rental_order_views.xml -->
<record id="rental_order_form_custom" model="ir.ui.view">
    <field name="name">rental.order.form.custom</field>
    <field name="model">rental.order</field>
    <field name="inherit_id" ref="hudson_rental.rental_order_view_form"/>
    <field name="arch" type="xml">
        <xpath expr="//field[@name='partner_id']" position="after">
            <field name="equipment_condition"/>
        </xpath>
    </field>
</record>
```

### Override Methods

**Example: Custom pricing logic**

```python
# models/rental_pricing_custom.py
from odoo import models

class RentalPricingCustom(models.Model):
    _inherit = 'rental.pricing'
    
    def get_price_per_day(self):
        """Override to add seasonal pricing"""
        price = super().get_price_per_day()
        
        # Add 20% in peak season (June-August)
        if self.env.context.get('is_peak_season'):
            price *= 1.2
        
        return price
```

### Add New Models

**Example: Equipment maintenance tracking**

```python
# models/rental_maintenance.py
from odoo import fields, models, api

class RentalMaintenance(models.Model):
    _name = 'rental.maintenance'
    _description = 'Rental Equipment Maintenance'
    
    name = fields.Char(string='Reference', required=True)
    product_id = fields.Many2one('product.product', string='Equipment')
    date = fields.Date(string='Maintenance Date', required=True)
    cost = fields.Float(string='Cost')
    notes = fields.Text(string='Notes')
    state = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='scheduled')
```

### Custom Controllers

**Example: API endpoint for external bookings**

```python
# controllers/api.py
from odoo import http
from odoo.http import request
import json

class RentalAPI(http.Controller):
    
    @http.route('/api/rental/availability', type='json', auth='public')
    def check_availability(self, product_id, start_date, end_date):
        """Check if product is available for dates"""
        product = request.env['product.product'].sudo().browse(product_id)
        
        # Your availability logic here
        available = product.rental_stock_available > 0
        
        return {
            'available': available,
            'quantity': product.rental_stock_available,
            'product_name': product.name
        }
```

### Custom Wizards

**Example: Bulk extend wizard**

```python
# wizard/rental_bulk_extend_wizard.py
from odoo import fields, models

class RentalBulkExtendWizard(models.TransientModel):
    _name = 'rental.bulk.extend.wizard'
    _description = 'Bulk Extend Rentals'
    
    order_ids = fields.Many2many('rental.order', string='Orders')
    extension_days = fields.Integer(string='Extend by Days', required=True)
    
    def action_extend_all(self):
        for order in self.order_ids:
            new_date = order.return_date + timedelta(days=self.extension_days)
            order.write({'return_date': new_date})
```

---

## JavaScript Customization

### Custom Widget Example

```javascript
/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

export class RentalCalendarWidget extends Component {
    setup() {
        this.state = {
            selectedDate: null
        };
    }
    
    selectDate(date) {
        this.state.selectedDate = date;
        this.props.onChange(date);
    }
}

RentalCalendarWidget.template = "rental.CalendarWidget";

registry.category("fields").add("rental_calendar", RentalCalendarWidget);
```

### Frontend Validation

```javascript
// static/src/js/rental_validation.js
odoo.define('hudson_rental.validation', function (require) {
    'use strict';

    var FormController = require('web.FormController');

    FormController.include({
        _onSave: function () {
            if (this.modelName === 'rental.order') {
                var pickupDate = this.model.get('pickup_date');
                var returnDate = this.model.get('return_date');
                
                if (returnDate <= pickupDate) {
                    this.displayNotification({
                        message: 'Return date must be after pickup date',
                        type: 'danger'
                    });
                    return Promise.reject();
                }
            }
            return this._super.apply(this, arguments);
        }
    });
});
```

---

## Database Schema

### rental_order
```sql
CREATE TABLE rental_order (
    id SERIAL PRIMARY KEY,
    name VARCHAR,
    partner_id INTEGER REFERENCES res_partner,
    date_order TIMESTAMP,
    pickup_date TIMESTAMP,
    return_date TIMESTAMP,
    actual_return_date TIMESTAMP,
    state VARCHAR,
    amount_untaxed NUMERIC,
    amount_tax NUMERIC,
    amount_total NUMERIC,
    amount_deposit NUMERIC,
    amount_late_fee NUMERIC,
    currency_id INTEGER REFERENCES res_currency,
    company_id INTEGER REFERENCES res_company,
    user_id INTEGER REFERENCES res_users,
    sale_order_id INTEGER REFERENCES sale_order,
    note TEXT,
    create_date TIMESTAMP,
    write_date TIMESTAMP,
    create_uid INTEGER REFERENCES res_users,
    write_uid INTEGER REFERENCES res_users
);
```

### Indexes
```sql
CREATE INDEX idx_rental_order_partner ON rental_order(partner_id);
CREATE INDEX idx_rental_order_state ON rental_order(state);
CREATE INDEX idx_rental_order_pickup ON rental_order(pickup_date);
CREATE INDEX idx_rental_order_return ON rental_order(return_date);
```

---

## Testing

### Unit Tests Example

```python
# tests/test_rental_order.py
from odoo.tests.common import TransactionCase
from datetime import datetime, timedelta

class TestRentalOrder(TransactionCase):
    
    def setUp(self):
        super().setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Test Customer'
        })
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'is_rental': True,
        })
    
    def test_order_creation(self):
        """Test rental order creation"""
        order = self.env['rental.order'].create({
            'partner_id': self.partner.id,
            'pickup_date': datetime.now(),
            'return_date': datetime.now() + timedelta(days=7),
        })
        self.assertEqual(order.state, 'draft')
    
    def test_price_calculation(self):
        """Test automatic price calculation"""
        # Add test logic
        pass
    
    def test_late_fee(self):
        """Test late fee calculation"""
        # Add test logic
        pass
```

### Running Tests
```bash
odoo-bin -d test_db -i hudson_rental --test-enable --stop-after-init
```

---

## API Reference

### Rental Order API

**Create Order:**
```python
order = env['rental.order'].create({
    'partner_id': partner_id,
    'pickup_date': '2026-08-10 10:00:00',
    'return_date': '2026-08-15 10:00:00',
    'order_line_ids': [(0, 0, {
        'product_id': product_id,
        'quantity': 1,
    })]
})
```

**Process Workflow:**
```python
order.action_confirm()    # Confirm
order.action_reserve()    # Reserve stock
order.action_pickup()     # Open pickup wizard
order.action_return()     # Open return wizard
```

**Search Orders:**
```python
# Active rentals
orders = env['rental.order'].search([
    ('state', 'in', ['reserved', 'picked_up'])
])

# Late returns
orders = env['rental.order'].search([
    ('state', '=', 'picked_up'),
    ('return_date', '<', fields.Datetime.now())
])
```

---

## Performance Optimization

### Database Optimization

**Use store=True for computed fields that are frequently accessed:**
```python
amount_total = fields.Monetary(
    compute='_compute_amount',
    store=True  # Stored in database
)
```

**Add indexes for frequently searched fields:**
```python
_sql_constraints = [
    ('name_uniq', 'unique(name)', 'Order reference must be unique')
]
```

### Query Optimization

**Bad:**
```python
for order in orders:
    print(order.partner_id.name)  # N+1 queries
```

**Good:**
```python
orders = orders.with_context(prefetch_fields=['partner_id'])
for order in orders:
    print(order.partner_id.name)  # Prefetched
```

### Caching

```python
from odoo import tools

@tools.ormcache('product_id', 'duration')
def get_rental_price(self, product_id, duration):
    # Expensive calculation
    return price
```

---

## Security Best Practices

### Record Rules
```xml
<!-- Only show customer's own rentals -->
<record id="rental_order_portal_rule" model="ir.rule">
    <field name="name">Portal: Own Rentals</field>
    <field name="model_id" ref="model_rental_order"/>
    <field name="domain_force">
        [('partner_id', '=', user.partner_id.id)]
    </field>
    <field name="groups" eval="[(4, ref('base.group_portal'))]"/>
</record>
```

### Field-Level Security
```python
sensitive_data = fields.Char(
    string='Sensitive',
    groups='base.group_system'  # Admin only
)
```

### Input Validation
```python
@api.constrains('pickup_date', 'return_date')
def _check_dates(self):
    for order in self:
        if order.return_date <= order.pickup_date:
            raise ValidationError('Invalid dates')
```

---

## Debugging Tips

### Enable Developer Mode
Settings → Activate Developer Mode

### Debug Logging
```python
import logging
_logger = logging.getLogger(__name__)

_logger.debug('Debug message')
_logger.info('Info message')
_logger.warning('Warning message')
_logger.error('Error message')
```

### Debug in Code
```python
import pdb; pdb.set_trace()  # Breakpoint
```

### SQL Debugging
```python
self.env.cr.execute("SELECT * FROM rental_order WHERE state = 'draft'")
results = self.env.cr.dictfetchall()
```

---

## Deployment Checklist

- [ ] Update version in `__manifest__.py`
- [ ] Update `CHANGELOG.md`
- [ ] Run tests: `--test-enable`
- [ ] Check translations
- [ ] Optimize database indexes
- [ ] Review security rules
- [ ] Test on staging environment
- [ ] Backup production database
- [ ] Deploy to production
- [ ] Monitor logs for errors
- [ ] Verify data integrity

---

## Contributing

### Code Style
Follow PEP 8 for Python:
- 4 spaces indentation
- Max line length: 79 characters
- Use meaningful variable names

### Git Workflow
```bash
git checkout -b feature/my-new-feature
# Make changes
git commit -m "Add: New feature description"
git push origin feature/my-new-feature
# Create pull request
```

### Commit Messages
- `Add:` New feature
- `Fix:` Bug fix
- `Update:` Modification
- `Remove:` Deletion
- `Refactor:` Code restructuring

---

## Resources

### Odoo Documentation
- [Odoo 19 Developer Documentation](https://www.odoo.com/documentation/19.0/developer.html)
- [ORM API Reference](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html)
- [QWeb Templates](https://www.odoo.com/documentation/19.0/developer/reference/frontend/qweb.html)

### Community
- [Odoo Community Forum](https://www.odoo.com/forum/help-1)
- [GitHub Odoo](https://github.com/odoo/odoo)

---

## Support

For development questions:
- GitHub Issues: Technical problems
- Developer Forum: General questions
- Email: dev@hudsoncommunity.org

---

**Happy Coding! 🚀**

*Hudson Community Developer Team*
