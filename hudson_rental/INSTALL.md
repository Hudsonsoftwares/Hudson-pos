# Installation Guide - Hudson Rental Management

## Prerequisites

- Odoo 19.0 or later
- Python 3.10 or later
- Required Odoo modules:
  - sale_management
  - stock
  - account
  - portal
  - website_sale

## Installation Steps

### 1. Copy Module to Addons Directory

```bash
# Copy the hudson_rental folder to your Odoo addons directory
cp -r hudson_rental /path/to/odoo/addons/
```

Or if you have a custom addons path:

```bash
cp -r hudson_rental /path/to/custom-addons/
```

### 2. Update Odoo Configuration

Make sure your custom addons path is in `odoo.conf`:

```ini
[options]
addons_path = /path/to/odoo/addons,/path/to/custom-addons
```

### 3. Restart Odoo Service

```bash
# Restart Odoo to load new modules
sudo systemctl restart odoo
# or
sudo service odoo restart
```

### 4. Update Apps List

1. Log in to Odoo as Administrator
2. Go to **Apps** menu
3. Click **Update Apps List** button (enable Developer Mode if not visible)
4. Confirm the update

### 5. Install the Module

1. In Apps menu, search for "Hudson Rental"
2. Click **Install** button
3. Wait for installation to complete

## Post-Installation Configuration

### Step 1: Configure Rental Settings

1. Go to **Settings → General Settings**
2. Scroll to **Rental** section
3. Configure:
   - **Rental Location**: Select or create a location for rental stock
   - **Rental Picking Type**: Choose the delivery operation type
   - **Auto Create Invoice**: Enable to auto-generate invoices on return
   - **Require Security Deposit**: Enable if deposits are required

### Step 2: Create Rental Location (if needed)

1. Go to **Inventory → Configuration → Locations**
2. Create a new location: "Rental Stock"
3. Set usage type: "Internal Location"

### Step 3: Configure Rental Picking Type (if needed)

1. Go to **Inventory → Configuration → Operation Types**
2. Find or create "Rentals" operation type
3. Set type: "Delivery Orders"
4. Set source location: Your rental location

### Step 4: Setup Your First Rental Product

1. Go to **Rental → Configuration → Rental Products**
2. Create or select a product
3. Enable **Can be Rented** checkbox
4. In **Rental** tab, configure:
   - Minimum/Maximum rental duration
   - Security deposit amount
   - Late fee per day

5. Add **Rental Pricing** rules:
   - Click **Add a line**
   - Set duration (e.g., 1)
   - Select unit (Day, Week, Month)
   - Enter price
   - Add multiple pricing tiers

Example:
```
Duration  | Unit  | Price
----------|-------|-------
1         | Day   | 50.00
7         | Day   | 300.00
30        | Day   | 1000.00
```

### Step 5: Website Configuration (Optional)

To enable rental products on website:

1. Go to **Website → Configuration → Settings**
2. Enable **eCommerce** if not already enabled
3. Go to your rental product
4. Click **Go to Website** button
5. Click **Unpublished** to publish it

## Testing the Installation

### Test 1: Create a Rental Order

1. Go to **Rental → Orders → Create**
2. Select a customer
3. Add a rental product line
4. Set pickup and return dates
5. Verify price calculates correctly
6. Save the order

### Test 2: Check Website Integration

1. Visit your website: `http://your-domain.com/rental/products`
2. You should see your rental products
3. Click on a product
4. Configure dates and add to cart
5. Verify checkout process works

### Test 3: Process Complete Workflow

1. Create and confirm a rental order
2. Click **Reserve Stock**
3. Click **Pickup** and confirm
4. Click **Return** and confirm
5. Click **Create Invoice**
6. Verify invoice is generated

## Troubleshooting

### Issue: Module Not Appearing in Apps List

**Solution:**
- Make sure the module folder is in the correct addons path
- Restart Odoo service
- Update apps list with Technical features enabled
- Check Odoo logs for errors: `tail -f /var/log/odoo/odoo.log`

### Issue: Import Errors

**Solution:**
```bash
# Check Python dependencies
pip3 install -r /path/to/odoo/requirements.txt

# Restart Odoo
sudo systemctl restart odoo
```

### Issue: Permission Errors

**Solution:**
```bash
# Set correct ownership
sudo chown -R odoo:odoo /path/to/custom-addons/hudson_rental

# Set correct permissions
sudo chmod -R 755 /path/to/custom-addons/hudson_rental
```

### Issue: Database Errors During Installation

**Solution:**
1. Check PostgreSQL is running
2. Check Odoo has correct database permissions
3. Try manual upgrade:
```bash
odoo-bin -c /etc/odoo/odoo.conf -d your_database -u hudson_rental --stop-after-init
```

### Issue: Rental Products Not Showing on Website

**Solution:**
1. Ensure product is published on website
2. Check "Can be Rented" is enabled
3. Verify at least one pricing rule exists
4. Clear browser cache
5. Check website_sale module is installed

### Issue: Stock Issues

**Solution:**
1. Go to **Inventory → Configuration → Locations**
2. Ensure rental location exists
3. Add stock to rental location:
   - Go to product
   - Click **Update Quantity**
   - Select rental location
   - Set quantity

### Issue: Invoice Not Creating

**Solution:**
1. Check accounting module is installed
2. Verify customer has proper invoicing address
3. Check fiscal position is configured
4. Ensure taxes are set on products

## Upgrading

To upgrade the module:

```bash
# Stop Odoo
sudo systemctl stop odoo

# Update module files
cp -r hudson_rental /path/to/addons/

# Upgrade module
odoo-bin -c /etc/odoo/odoo.conf -d your_database -u hudson_rental --stop-after-init

# Start Odoo
sudo systemctl start odoo
```

Or from UI:
1. Go to Apps
2. Search "Hudson Rental"
3. Click Upgrade

## Uninstallation

To uninstall the module:

1. Go to **Apps**
2. Search "Hudson Rental"
3. Click **Uninstall**
4. Confirm the action

**Warning:** This will delete all rental data!

## Support

For issues or questions:
- GitHub Issues: https://github.com/nandusaji2001/hudson-community/issues
- Email: support@hudsoncommunity.org (if applicable)

## Additional Resources

- [README.md](README.md) - Module features and usage
- [User Guide](static/description/index.html) - Detailed user documentation
- Odoo Documentation: https://www.odoo.com/documentation/19.0/

## License

This module is licensed under LGPL-3. See [LICENSE](LICENSE) file for details.
