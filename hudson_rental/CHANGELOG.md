# Changelog

All notable changes to the Hudson Rental Management module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-04

### Added
- Initial release of Hudson Rental Management for Odoo 19
- Complete rental order lifecycle management (Draft → Confirmed → Reserved → Picked Up → Returned → Done)
- Flexible rental pricing configuration (hourly, daily, weekly, monthly)
- Online rental booking through website integration
- Customer portal for rental history and management
- Real-time rental stock availability tracking
- Automatic price calculation based on rental duration
- Security deposit management
- Late fee calculation for overdue returns
- Rental extension functionality while orders are in progress
- Pickup and return wizards for easy processing
- Stock integration with automatic delivery order creation
- Invoice generation with rental charges and late fees
- Comprehensive rental analytics and reporting (pivot, graph, tree views)
- Multi-company support
- Portal access rules for customers
- Email templates for rental confirmation and reminders
- Product rental configuration with min/max duration limits
- Integration with Odoo Sales, Inventory, and Accounting modules

### Features by Module

#### Core Models
- `rental.order` - Main rental order with full lifecycle
- `rental.order.line` - Rental line items with duration tracking
- `rental.pricing` - Flexible pricing rules per product
- `rental.report` - Analytics and reporting model

#### Product Configuration
- Rental flag on products
- Multiple pricing tiers per product
- Security deposit settings
- Late fee configuration
- Min/max rental duration limits

#### Order Management
- Quotation creation
- Order confirmation
- Stock reservation
- Pickup processing
- Return handling
- Rental extension
- Late fee calculation
- Invoice generation

#### Website Integration
- Rental product catalog page
- Product detail with date configurator
- Real-time price calculation
- Availability checking
- Add to cart integration
- Checkout process

#### Customer Portal
- Rental order list
- Order detail view
- Rental history
- Status tracking
- Extension requests

#### Reporting
- Rental analysis with pivot tables
- Revenue tracking by product/customer/period
- Duration analysis
- Late fee tracking
- Utilization metrics

#### Stock Management
- Dedicated rental locations
- Automated stock movements
- Pickup delivery orders
- Return receiving
- Availability tracking

#### Invoicing
- Automatic invoice creation
- Rental charges
- Late fees
- Security deposits
- Tax calculation

### Technical Details
- Compatible with Odoo 19.0
- Python 3.10+ required
- Depends on: sale_management, stock, account, portal, website_sale
- LGPL-3 License
- Multi-language support ready
- Multi-currency support
- Responsive design for mobile

### Security
- User and Manager access groups
- Multi-company rules
- Portal access restrictions
- Customer data isolation

### Documentation
- README with feature overview
- INSTALL guide with troubleshooting
- Inline help text
- HTML documentation page

### Demo Data
- 3 sample rental products
- Pricing examples
- Ready-to-test configuration

## [Unreleased]

### Planned Features
- Rental calendar view
- Availability calendar
- Recurring rental subscriptions
- Rental packages/bundles
- Damage tracking and charges
- Equipment maintenance scheduling
- QR code scanning for pickup/return
- SMS notifications
- Mobile app integration
- Advanced pricing rules (seasonal, volume discounts)
- Rental contracts with terms
- Equipment location tracking
- Customer ratings and reviews
- Automated reminder emails
- Integration with booking platforms
- Multi-location rental management

### Known Issues
- Icon file is SVG, needs PNG conversion for better Odoo compatibility
- Calendar view not yet implemented
- Some translations may be missing

### Future Improvements
- Performance optimization for large rental catalogs
- Enhanced reporting with more KPIs
- Barcode scanning support
- Equipment maintenance module integration
- Advanced search filters
- Batch operations for bulk processing
- API endpoints for third-party integrations

---

## Version History

### Version Numbering
- Major version: Incompatible API changes
- Minor version: Backward-compatible functionality additions
- Patch version: Backward-compatible bug fixes

### Support Policy
- Latest version: Full support
- Previous minor version: Security fixes only
- Older versions: Community support only

---

## Contributors

- Hudson Community Team
- GitHub Contributors: https://github.com/nandusaji2001/hudson-community/graphs/contributors

## License

LGPL-3 - See LICENSE file for details

## Links

- GitHub Repository: https://github.com/nandusaji2001/hudson-community
- Issue Tracker: https://github.com/nandusaji2001/hudson-community/issues
- Documentation: See README.md and INSTALL.md
