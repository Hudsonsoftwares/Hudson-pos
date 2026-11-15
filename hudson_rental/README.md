# Hudson Rental Management

Complete rental management solution for Odoo 19.

## Features

- **Online Rental Booking** - Customers can rent products directly from website
- **Flexible Pricing** - Define pricing by hour, day, week, or month
- **Order Management** - Complete rental lifecycle management
- **Stock Integration** - Real-time availability tracking
- **Invoicing** - Automatic invoice generation with late fees
- **Customer Portal** - Self-service rental management
- **Reports** - Comprehensive analytics and reporting

## Installation

1. Copy the module folder to your Odoo addons directory
2. Update the app list: `Settings → Apps → Update Apps List`
3. Search for "Hudson Rental Management"
4. Click Install

## Configuration

### 1. General Settings

Go to `Settings → Rental` and configure:
- Rental Location: Where rental products are stored
- Rental Picking Type: For delivery operations
- Auto Invoice: Automatically create invoices on return
- Security Deposit: Require deposits for rentals

### 2. Rental Products

1. Go to `Rental → Configuration → Rental Products`
2. Create or select a product
3. Check "Can be Rented"
4. Add pricing rules in the Rental tab:
   - Duration (e.g., 1, 7, 30)
   - Unit (Hour, Day, Week, Month)
   - Price

Example pricing:
- 1 Day: $50
- 7 Days: $300 ($42.86/day)
- 30 Days: $1000 ($33.33/day)

### 3. Security Settings

Configure security deposit and late fees per product:
- Security Deposit: Refundable amount
- Late Fee Per Day: Penalty for late returns

## Usage

### Creating a Rental Order

1. Go to `Rental → Orders → Create`
2. Select customer
3. Add rental products
4. Set pickup and return dates
5. Prices calculate automatically based on duration
6. Confirm the order

### Order Workflow

1. **Draft** → Create quotation
2. **Confirmed** → Customer confirms
3. **Reserved** → Stock reserved
4. **Picked Up** → Customer receives items
5. **Returned** → Items returned
6. **Done** → Order completed and invoiced

### Processing Operations

**Pickup:**
- Click "Pickup" button
- Confirm picked quantities
- Stock moves created automatically

**Return:**
- Click "Return" button
- Enter actual return date
- Mark item conditions
- Late fees calculated if applicable
- Invoice created automatically

**Extend Rental:**
- Click "Extend" button while rental is active
- Select new return date
- Price updated automatically

### Website Integration

Rental products appear on website automatically:
- Visit `/rental/products` to see all rentals
- Customers select dates and add to cart
- Checkout process creates rental order

### Customer Portal

Customers can access `/my/rentals` to:
- View all their rentals
- Check current rental status
- Download rental documents
- Request extensions

## Reports

Access rental analytics:
- `Rental → Reporting → Rental Analysis`
- Pivot and graph views available
- Group by product, customer, date, etc.
- Track revenue and utilization

## API / Technical

### Models

- `rental.order` - Main rental order
- `rental.order.line` - Rental order lines
- `rental.pricing` - Pricing rules per product
- `rental.report` - Analysis/reporting

### Controllers

- `/rental/products` - List all rental products
- `/rental/product/<id>` - Product detail with configurator
- `/rental/configure` - Calculate price (JSON-RPC)
- `/rental/add_to_cart` - Add rental to cart (JSON-RPC)
- `/my/rentals` - Customer portal

## Troubleshooting

**Products not showing on website:**
- Ensure "Can be Rented" is checked
- Add at least one pricing rule
- Publish the product on website

**Price not calculating:**
- Check pricing rules exist for the product
- Verify dates are correctly set
- Ensure rental duration falls within min/max limits

**Stock issues:**
- Configure rental location in settings
- Check stock levels in rental location
- Verify picking type is set correctly

## Credits

**Author:** Hudson Community
**License:** LGPL-3
**Version:** 19.0.1.0.0

## Support

For issues, questions, or contributions:
- GitHub: https://github.com/nandusaji2001/hudson-community
- Create an issue or pull request

## Changelog

### Version 1.0.0
- Initial release
- Complete rental order management
- Website integration
- Customer portal
- Pricing configuration
- Stock integration
- Invoicing with late fees
- Reports and analytics
