# Quick Start Guide - Hudson Rental Management

Get up and running with Hudson Rental Management in 5 minutes!

## Step 1: Install the Module (2 minutes)

1. Place the `hudson_rental` folder in your Odoo addons directory
2. Restart Odoo: `sudo systemctl restart odoo`
3. Go to **Apps** → Click **Update Apps List**
4. Search for "Hudson Rental"
5. Click **Install**

## Step 2: Basic Configuration (2 minutes)

### Configure Settings

1. Go to **Settings → General Settings**
2. Find the **Rental** section
3. Set:
   - ✅ **Auto Create Invoice**: ON
   - ✅ **Require Security Deposit**: ON
4. Click **Save**

### Create Rental Location (Optional)

Skip this if you already have a warehouse location.

1. Go to **Inventory → Configuration → Locations**
2. Click **Create**
3. Name: "Rental Stock"
4. Location Type: "Internal Location"
5. Click **Save**

## Step 3: Add Your First Rental Product (1 minute)

1. Go to **Rental → Configuration → Rental Products**
2. Click **Create**
3. Fill in:
   - **Product Name**: e.g., "Professional Camera"
   - **Product Type**: Storable Product
   - ✅ Check **Can be Rented**
   
4. Go to **Rental** tab:
   - **Security Deposit**: 200
   - **Late Fee Per Day**: 25

5. Add **Rental Pricing**:
   ```
   Duration: 1    Unit: Day     Price: 100
   Duration: 7    Unit: Day     Price: 600
   Duration: 30   Unit: Day     Price: 2000
   ```
   
6. Click **Save**

## Step 4: Create Your First Rental Order (30 seconds)

1. Go to **Rental → Orders**
2. Click **Create**
3. Select a **Customer**
4. Click **Add a product** in Order Lines
5. Select your rental product
6. Set **Pickup Date**: Tomorrow
7. Set **Return Date**: 3 days from tomorrow
8. Price auto-calculates! 💰
9. Click **Save**

## Step 5: Test the Complete Workflow (30 seconds)

1. Click **Confirm** → Order confirmed ✅
2. Click **Reserve Stock** → Stock reserved ✅
3. Click **Pickup** → Confirm pickup ✅
4. Click **Return** → Process return ✅
5. Invoice auto-created! 🎉

## 🎯 You're Done!

Your rental system is now operational!

---

## What's Next?

### Enable Website Rentals

1. Go to your product
2. Click **Go to Website**
3. Click **Unpublished** to publish
4. Visit: `your-domain.com/rental/products`
5. Customers can now rent online! 🌐

### Add More Products

1. Create products as usual
2. Just check ✅ **Can be Rented**
3. Add pricing rules
4. Done!

### Customize Pricing

Create different pricing tiers:

- **Hourly**: For short rentals
  - Duration: 1, Unit: Hour, Price: 25
  
- **Daily**: Most common
  - Duration: 1, Unit: Day, Price: 100
  
- **Weekly**: Save 15%
  - Duration: 7, Unit: Day, Price: 595
  
- **Monthly**: Save 30%
  - Duration: 30, Unit: Day, Price: 2100

### Setup Email Notifications

Templates are pre-configured for:
- ✉️ Rental confirmation
- ✉️ Pickup reminder
- ✉️ Return reminder

Go to **Settings → Technical → Email Templates** to customize.

---

## Common Tasks

### Check Product Availability

1. Go to product
2. **Rental Stock Available** field shows current availability
3. Accounts for currently rented items

### Extend a Rental

1. Open the rental order
2. Click **Extend** button
3. Select new return date
4. Price recalculates automatically
5. Customer is notified

### Handle Late Returns

System automatically:
- Calculates days late
- Applies late fees (if configured)
- Adds fees to invoice

### View Reports

**Rental → Reporting → Rental Analysis**

- 📊 Revenue by product
- 📈 Rental trends
- ⏱️ Duration analysis
- 💰 Late fees tracking

---

## Tips & Tricks

### 💡 Pricing Strategy

**Linear Pricing:**
```
1 day = $50
7 days = $350 ($50/day)
30 days = $1500 ($50/day)
```

**Volume Discount:**
```
1 day = $50
7 days = $300 ($42.86/day - Save 15%)
30 days = $1000 ($33.33/day - Save 33%)
```

### 💡 Security Deposits

Set deposits to:
- Cover product value
- Encourage on-time returns
- Protect against damage

Rule of thumb: 20-50% of product value

### 💡 Late Fees

Set late fees high enough to:
- Encourage timely returns
- Cover opportunity cost
- Discourage abuse

Example: Daily rental $50 → Late fee $25/day

### 💡 Minimum Durations

Prevent unprofitable short rentals:
- High-value items: Min 3-7 days
- Low-value items: Min 1 day
- Event equipment: Min 1 day

---

## Need Help?

### Documentation
- 📖 [Full README](README.md)
- 🔧 [Installation Guide](INSTALL.md)
- 📝 [Changelog](CHANGELOG.md)

### Support
- 🐛 Report bugs: [GitHub Issues](https://github.com/nandusaji2001/hudson-community/issues)
- 💬 Ask questions: Community Forum
- 📧 Email: support@hudsoncommunity.org

### Demo Data

Want to test with sample products?

Install with demo data enabled:
```bash
odoo-bin -d your_db -i hudson_rental --load-language=en_US
```

Includes:
- 3 sample rental products
- Pre-configured pricing
- Ready-to-test orders

---

## Keyboard Shortcuts

- `Alt + C`: Create new order
- `Alt + S`: Save
- `Alt + D`: Discard
- `Alt + E`: Edit

Enable: **Settings → Developer Mode**

---

## Video Tutorials (Coming Soon)

- [ ] Basic Setup
- [ ] Creating Rental Products
- [ ] Processing Orders
- [ ] Website Configuration
- [ ] Reports & Analytics

---

**Congratulations! Your rental business is now digital! 🚀**

Happy Renting! 🎉
