# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import logging
from datetime import datetime, date, timedelta
from odoo import Command

_logger = logging.getLogger(__name__)


def load_hr_suite_demo_data(env):
    """
    Creates complete, interconnected HR Suite demo data:
    1. Employees & Departments (Kitchen, Cafe, Service, Logistics, Management)
    2. Attendances (Check-ins & check-outs for past 3 days and today)
    3. Time Off / Leaves (Leave allocations and approved/pending leaves)
    4. Fleet (Delivery bikes and catering van with odometers and service logs)
    5. Lunch (Staff canteen meals, wallet credits, and sample lunch orders)
    6. Expenses (Chef tasting, bike fuel, barista tools, first-aid supplies)
    """
    _logger.info("Hudson HR Suite: Loading interconnected demo data...")

    # -------------------------------------------------------------------------
    # 1. Departments & Jobs
    # -------------------------------------------------------------------------
    Dept = env['hr.department'].sudo()
    Job = env['hr.job'].sudo()

    def get_or_create_dept(name):
        d = Dept.search([('name', '=', name)], limit=1)
        if not d:
            d = Dept.create({'name': name})
        return d

    dept_kitchen = get_or_create_dept('Kitchen & Culinary')
    dept_cafe = get_or_create_dept('Bar & Cafe')
    dept_service = get_or_create_dept('Service & Hospitality')
    dept_logistics = get_or_create_dept('Logistics & Delivery')
    dept_admin = get_or_create_dept('Administration & Management')

    def get_or_create_job(name, dept):
        j = Job.search([('name', '=', name)], limit=1)
        if not j:
            j = Job.create({'name': name, 'department_id': dept.id})
        return j

    job_head_chef = get_or_create_job('Head Chef', dept_kitchen)
    job_sous_chef = get_or_create_job('Sous Chef', dept_kitchen)
    job_line_cook = get_or_create_job('Line Cook & Prep Specialist', dept_kitchen)
    job_barista = get_or_create_job('Head Barista & Cafe Specialist', dept_cafe)
    job_waiter = get_or_create_job('Senior Service Captain & Waiter', dept_service)
    job_cashier = get_or_create_job('POS Cashier & Receptionist', dept_service)
    job_rider_1 = get_or_create_job('Senior Delivery Rider', dept_logistics)
    job_rider_2 = get_or_create_job('Fleet Logistics Driver', dept_logistics)
    job_manager = get_or_create_job('Restaurant General Manager', dept_admin)

    # -------------------------------------------------------------------------
    # 2. Employees & User linking
    # -------------------------------------------------------------------------
    Employee = env['hr.employee'].sudo()
    User = env['res.users'].sudo()
    admin_user = env.ref('base.user_admin', raise_if_not_found=False)

    staff_specs = [
        {
            'name': 'Rahul Nair',
            'job_id': job_head_chef.id,
            'job_title': 'Head Chef',
            'department_id': dept_kitchen.id,
            'work_email': 'rahul.nair@hudsonresto.com',
            'work_phone': '+91 98470 11001',
        },
        {
            'name': 'Ananya Sharma',
            'job_id': job_sous_chef.id,
            'job_title': 'Sous Chef',
            'department_id': dept_kitchen.id,
            'work_email': 'ananya.sharma@hudsonresto.com',
            'work_phone': '+91 98470 11002',
        },
        {
            'name': 'Vishnu Kumar',
            'job_id': job_line_cook.id,
            'job_title': 'Line Cook & Prep Specialist',
            'department_id': dept_kitchen.id,
            'work_email': 'vishnu.kumar@hudsonresto.com',
            'work_phone': '+91 98470 11003',
        },
        {
            'name': 'Priya Menon',
            'job_id': job_barista.id,
            'job_title': 'Head Barista & Cafe Specialist',
            'department_id': dept_cafe.id,
            'work_email': 'priya.menon@hudsonresto.com',
            'work_phone': '+91 98470 11004',
        },
        {
            'name': 'Mohammed Bilal',
            'job_id': job_waiter.id,
            'job_title': 'Senior Service Captain & Waiter',
            'department_id': dept_service.id,
            'work_email': 'mohammed.bilal@hudsonresto.com',
            'work_phone': '+91 98470 11005',
        },
        {
            'name': 'Sneha Pillai',
            'job_id': job_cashier.id,
            'job_title': 'POS Cashier & Receptionist',
            'department_id': dept_service.id,
            'work_email': 'sneha.pillai@hudsonresto.com',
            'work_phone': '+91 98470 11006',
        },
        {
            'name': 'Arun Varma',
            'job_id': job_rider_1.id,
            'job_title': 'Senior Delivery Rider',
            'department_id': dept_logistics.id,
            'work_email': 'arun.varma@hudsonresto.com',
            'work_phone': '+91 98470 11007',
        },
        {
            'name': 'Kevin Joseph',
            'job_id': job_rider_2.id,
            'job_title': 'Fleet Logistics Driver',
            'department_id': dept_logistics.id,
            'work_email': 'kevin.joseph@hudsonresto.com',
            'work_phone': '+91 98470 11008',
        },
        {
            'name': 'Suresh Kumar',
            'job_id': job_manager.id,
            'job_title': 'Restaurant General Manager',
            'department_id': dept_admin.id,
            'work_email': 'suresh.kumar@hudsonresto.com',
            'work_phone': '+91 98470 11009',
        },
    ]

    employees = {}
    admin_emp = env['hr.employee'].search([('user_id', '=', admin_user.id)], limit=1) if admin_user else False
    if admin_emp:
        employees['Administrator'] = admin_emp

    for spec in staff_specs:
        emp_name = spec['name']
        emp = Employee.search([('name', '=', emp_name)], limit=1)
        if not emp:
            emp = Employee.create(dict(spec))
        else:
            emp.write(dict(spec))
        employees[emp_name] = emp

    # Set manager hierarchy: Suresh Kumar manages everyone
    manager = employees.get('Suresh Kumar')
    if manager:
        for name, emp in employees.items():
            if name != 'Suresh Kumar':
                emp.parent_id = manager.id

    # -------------------------------------------------------------------------
    # 3. Attendances (Past 3 days + Today)
    # -------------------------------------------------------------------------
    Attendance = env['hr.attendance'].sudo()
    now = datetime.now()
    today_date = now.date()

    # Clear previous attendance for demo employees to keep clean
    all_emp_ids = [e.id for e in employees.values()]
    existing_att = Attendance.search([('employee_id', 'in', all_emp_ids)])
    existing_att.unlink()

    for emp in employees.values():
        # Day -3: 09:00 to 17:00 (8 hrs)
        d3 = today_date - timedelta(days=3)
        Attendance.create({
            'employee_id': emp.id,
            'check_in': datetime(d3.year, d3.month, d3.day, 9, 0, 0),
            'check_out': datetime(d3.year, d3.month, d3.day, 17, 0, 0),
        })

        # Day -2: 09:00 to 17:30 (8.5 hrs)
        d2 = today_date - timedelta(days=2)
        Attendance.create({
            'employee_id': emp.id,
            'check_in': datetime(d2.year, d2.month, d2.day, 9, 0, 0),
            'check_out': datetime(d2.year, d2.month, d2.day, 17, 30, 0),
        })

        # Day -1 (Yesterday): 09:00 to 17:00 (8 hrs)
        d1 = today_date - timedelta(days=1)
        Attendance.create({
            'employee_id': emp.id,
            'check_in': datetime(d1.year, d1.month, d1.day, 9, 0, 0),
            'check_out': datetime(d1.year, d1.month, d1.day, 17, 0, 0),
        })

        # Today: Checked in at 09:00 AM (still active on shift)
        Attendance.create({
            'employee_id': emp.id,
            'check_in': datetime(today_date.year, today_date.month, today_date.day, 9, 0, 0),
            'check_out': False,
        })

    # -------------------------------------------------------------------------
    # 4. Time Off / Leaves & Allocation
    # -------------------------------------------------------------------------
    Allocation = env['hr.leave.allocation'].sudo()
    Leave = env['hr.leave'].sudo()
    WorkEntryType = env['hr.work.entry.type'].sudo()

    comp_country_id = env.company.country_id.id if env.company.country_id else False
    country_domain = [('country_id', 'in', [comp_country_id, False])]

    wet_annual = WorkEntryType.search([('name', 'ilike', 'Annual')] + country_domain, limit=1)
    if not wet_annual:
        wet_annual = WorkEntryType.search([('name', 'ilike', 'Legal leave')] + country_domain, limit=1)
    if not wet_annual:
        wet_annual = WorkEntryType.search([('name', 'ilike', 'Generic Time Off')] + country_domain, limit=1)
    if not wet_annual:
        wet_annual = WorkEntryType.search(country_domain, limit=1)
    if not wet_annual:
        wet_annual = WorkEntryType.create({'name': 'Annual Paid Leave', 'code': 'ANNUAL_LEAVE', 'country_id': False})

    # Allocate 15 days of annual leave to each employee
    for emp in employees.values():
        existing_alloc = Allocation.search([
            ('employee_id', '=', emp.id),
            ('work_entry_type_id', '=', wet_annual.id)
        ], limit=1)
        if not existing_alloc:
            try:
                Allocation.create({
                    'name': 'Annual Paid Leave 2026',
                    'employee_id': emp.id,
                    'work_entry_type_id': wet_annual.id,
                    'number_of_days': 15,
                    'state': 'validate',
                })
            except Exception:
                pass

    # Sample Leaves:
    # 1. Ananya Sharma: Approved vacation for next week (2 days)
    ananya = employees.get('Ananya Sharma')
    if ananya:
        existing_leave = Leave.search([('employee_id', '=', ananya.id)], limit=1)
        if not existing_leave:
            next_mon = today_date + timedelta(days=(7 - today_date.weekday()))
            next_tue = next_mon + timedelta(days=1)
            try:
                l1 = Leave.create({
                    'name': 'Culinary Workshop & Family Vacation',
                    'employee_id': ananya.id,
                    'work_entry_type_id': wet_annual.id,
                    'request_date_from': next_mon,
                    'request_date_to': next_tue,
                })
                l1.action_validate()
            except Exception:
                pass

    # 2. Mohammed Bilal: Pending leave request for next Friday (1 day)
    bilal = employees.get('Mohammed Bilal')
    if bilal:
        existing_leave = Leave.search([('employee_id', '=', bilal.id)], limit=1)
        if not existing_leave:
            next_fri = today_date + timedelta(days=(4 - today_date.weekday() + 7) % 7 or 7)
            try:
                Leave.create({
                    'name': 'Personal Event & Family Gathering',
                    'employee_id': bilal.id,
                    'work_entry_type_id': wet_annual.id,
                    'request_date_from': next_fri,
                    'request_date_to': next_fri,
                })
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # 5. Fleet Vehicles, Odometers & Service Logs
    # -------------------------------------------------------------------------
    Brand = env['fleet.vehicle.model.brand'].sudo()
    Model = env['fleet.vehicle.model'].sudo()
    Vehicle = env['fleet.vehicle'].sudo()
    Odometer = env['fleet.vehicle.odometer'].sudo()
    Service = env['fleet.vehicle.log.services'].sudo()

    def get_or_create_brand(name):
        b = Brand.search([('name', '=', name)], limit=1)
        if not b:
            b = Brand.create({'name': name})
        return b

    brand_honda = get_or_create_brand('Honda')
    brand_yamaha = get_or_create_brand('Yamaha')
    brand_tata = get_or_create_brand('Tata Motors')

    def get_or_create_model(name, brand, vtype='bike'):
        m = Model.search([('name', '=', name), ('brand_id', '=', brand.id)], limit=1)
        if not m:
            m = Model.create({
                'name': name,
                'brand_id': brand.id,
                'vehicle_type': vtype,
            })
        return m

    model_activa = get_or_create_model('Activa 6G Scooter', brand_honda, 'bike')
    model_rayzr = get_or_create_model('RayZR 125 Fi Hybrid', brand_yamaha, 'bike')
    model_van = get_or_create_model('Ace Delivery Mini Van', brand_tata, 'car')

    arun = employees.get('Arun Varma')
    kevin = employees.get('Kevin Joseph')

    vehicles_spec = [
        {
            'license_plate': 'KL-07-CD-4521',
            'model_id': model_activa.id,
            'driver_employee_id': arun.id if arun else False,
            'odometer': 14250,
            'service_desc': 'Scheduled 10,000 km Engine Oil & Brake Shoe Replacement',
            'service_cost': 1200,
        },
        {
            'license_plate': 'KL-07-EF-8910',
            'model_id': model_rayzr.id,
            'driver_employee_id': kevin.id if kevin else False,
            'odometer': 8740,
            'service_desc': 'Periodic General Service, Air Filter & Chain Lubrication',
            'service_cost': 850,
        },
        {
            'license_plate': 'KL-07-GH-1234',
            'model_id': model_van.id,
            'driver_employee_id': manager.id if manager else False,
            'odometer': 32400,
            'service_desc': 'Logistics Van Tyre Alignment, Brake Fluid & Oil Service',
            'service_cost': 4500,
        },
    ]

    for vspec in vehicles_spec:
        v = Vehicle.search([('license_plate', '=', vspec['license_plate'])], limit=1)
        if not v:
            v = Vehicle.create({
                'license_plate': vspec['license_plate'],
                'model_id': vspec['model_id'],
                'driver_employee_id': vspec['driver_employee_id'],
                'odometer': vspec['odometer'],
            })
        else:
            v.write({
                'driver_employee_id': vspec['driver_employee_id'],
                'odometer': vspec['odometer'],
            })

        # Add Odometer reading record
        existing_odo = Odometer.search([('vehicle_id', '=', v.id)], limit=1)
        if not existing_odo:
            Odometer.create({
                'vehicle_id': v.id,
                'value': vspec['odometer'],
                'date': today_date,
            })

        # Add Service Log
        existing_srv = Service.search([('vehicle_id', '=', v.id)], limit=1)
        if not existing_srv:
            try:
                Service.create({
                    'vehicle_id': v.id,
                    'description': vspec['service_desc'],
                    'amount': vspec['service_cost'],
                    'date': today_date - timedelta(days=5),
                })
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # 6. Lunch Service (Catering Vendor, Staff Meals, Wallet Credits & Orders)
    # -------------------------------------------------------------------------
    Partner = env['res.partner'].sudo()
    Location = env['lunch.location'].sudo()
    Supplier = env['lunch.supplier'].sudo()
    LunchCategory = env['lunch.product.category'].sudo()
    LunchProduct = env['lunch.product'].sudo()
    Cashmove = env['lunch.cashmove'].sudo()
    LunchOrder = env['lunch.order'].sudo()

    # Vendor partner
    vendor_partner = Partner.search([('name', '=', 'Hudson Staff Catering Vendor')], limit=1)
    if not vendor_partner:
        vendor_partner = Partner.create({
            'name': 'Hudson Staff Catering Vendor',
            'email': 'catering@hudsonresto.com',
            'phone': '+91 98470 99887',
            'is_company': True,
        })

    # Location
    location = Location.search([('name', '=', 'Restaurant Staff Room & Kitchen')], limit=1)
    if not location:
        location = Location.create({
            'name': 'Restaurant Staff Room & Kitchen',
            'address': 'Main Restaurant Dining Complex, Staff Floor',
        })

    # Supplier
    supplier = Supplier.search([('partner_id', '=', vendor_partner.id)], limit=1)
    if not supplier:
        supplier = Supplier.create({
            'partner_id': vendor_partner.id,
            'send_by': 'mail',
            'available_location_ids': [Command.set([location.id])],
        })

    # Categories
    def get_or_create_lunch_cat(name):
        c = LunchCategory.search([('name', '=', name)], limit=1)
        if not c:
            c = LunchCategory.create({'name': name})
        return c

    cat_meals = get_or_create_lunch_cat('Chef Special Meals')
    cat_bites = get_or_create_lunch_cat('Cafe Bites & Beverages')

    # Lunch Products
    lunch_products_specs = [
        {
            'name': 'Kerala Traditional Meals with Fish Curry',
            'category_id': cat_meals.id,
            'supplier_id': supplier.id,
            'price': 150.0,
            'description': 'Fresh matta rice, sambar, avial, thoran, pickle and authentic seer fish curry.',
        },
        {
            'name': 'Hyderabadi Chicken Dum Biryani Bento',
            'category_id': cat_meals.id,
            'supplier_id': supplier.id,
            'price': 180.0,
            'description': 'Fragrant basmati rice dum biryani with raita, salan and sweet dessert.',
        },
        {
            'name': 'Healthy Mediterranean Salad & Protein Bowl',
            'category_id': cat_meals.id,
            'supplier_id': supplier.id,
            'price': 120.0,
            'description': 'Organic greens, cherry tomatoes, grilled paneer/tofu, olives and lemon dressing.',
        },
        {
            'name': 'Artisan Filter Coffee & Steamed Snack Platter',
            'category_id': cat_bites.id,
            'supplier_id': supplier.id,
            'price': 60.0,
            'description': 'Freshly brewed Arabica filter coffee paired with Kerala banana roast / pazhampori.',
        },
    ]

    lunch_prods = {}
    for lspec in lunch_products_specs:
        lp = LunchProduct.search([('name', '=', lspec['name'])], limit=1)
        if not lp:
            lp = LunchProduct.create(lspec)
        lunch_prods[lspec['name']] = lp

    # Credit Lunch Wallet for Admin user
    if admin_user:
        existing_cm = Cashmove.search([('user_id', '=', admin_user.id)], limit=1)
        if not existing_cm:
            Cashmove.create({
                'user_id': admin_user.id,
                'amount': 2500.0,
                'description': 'Monthly Staff Meal Allowance',
                'date': today_date,
            })

        # Create Today's sample lunch order
        p_biryani = lunch_prods.get('Hyderabadi Chicken Dum Biryani Bento')
        if p_biryani:
            existing_lo = LunchOrder.search([
                ('user_id', '=', admin_user.id),
                ('date', '=', today_date)
            ], limit=1)
            if not existing_lo:
                try:
                    LunchOrder.create({
                        'user_id': admin_user.id,
                        'product_id': p_biryani.id,
                        'supplier_id': supplier.id,
                        'lunch_location_id': location.id,
                        'date': today_date,
                        'price': p_biryani.price,
                        'state': 'confirmed',
                        'note': 'Extra raita please, deliver to Staff Room by 1:00 PM.',
                    })
                except Exception:
                    pass

    # -------------------------------------------------------------------------
    # 7. Expenses
    # -------------------------------------------------------------------------
    Expense = env['hr.expense'].sudo()
    Product = env['product.product'].sudo()

    prod_meal = Product.search([('can_be_expensed', '=', True), ('name', 'ilike', 'Meal')], limit=1)
    prod_travel = Product.search([('can_be_expensed', '=', True), ('name', 'ilike', 'Travel')], limit=1)
    if not prod_travel:
        prod_travel = Product.search([('can_be_expensed', '=', True), ('name', 'ilike', 'Mileage')], limit=1)
    prod_gen = Product.search([('can_be_expensed', '=', True), ('name', 'ilike', 'Expense')], limit=1)
    if not prod_gen:
        prod_gen = prod_meal or prod_travel

    rahul = employees.get('Rahul Nair')
    priya = employees.get('Priya Menon')

    expenses_spec = [
        {
            'name': 'Specialty Organic Spices & Herbs for Kitchen Tasting',
            'employee_id': rahul.id if rahul else False,
            'product_id': prod_meal.id if prod_meal else prod_gen.id,
            'total_amount_currency': 1250.0,
            'date': today_date - timedelta(days=2),
        },
        {
            'name': 'Delivery Fleet Petrol & Fuel Refill (KL-07-CD-4521)',
            'employee_id': arun.id if arun else False,
            'product_id': prod_travel.id if prod_travel else prod_gen.id,
            'total_amount_currency': 450.0,
            'date': today_date - timedelta(days=1),
        },
        {
            'name': 'Barista Specialty Milk Frothing Pitcher & Latte Art Tool',
            'employee_id': priya.id if priya else False,
            'product_id': prod_gen.id,
            'total_amount_currency': 850.0,
            'date': today_date,
        },
        {
            'name': 'Restaurant First Aid Safety Kit & Kitchen Sanitation Refill',
            'employee_id': manager.id if manager else False,
            'product_id': prod_gen.id,
            'total_amount_currency': 1400.0,
            'date': today_date - timedelta(days=3),
        },
    ]

    for espec in expenses_spec:
        if not espec['employee_id']:
            continue
        exp = Expense.search([
            ('name', '=', espec['name']),
            ('employee_id', '=', espec['employee_id'])
        ], limit=1)
        if not exp:
            try:
                Expense.create({
                    'name': espec['name'],
                    'employee_id': espec['employee_id'],
                    'product_id': espec['product_id'],
                    'total_amount_currency': espec['total_amount_currency'],
                    'date': espec['date'],
                })
            except Exception as e:
                _logger.warning("Could not create demo expense %s: %s", espec['name'], e)

    # -------------------------------------------------------------------------
    # 8. Payroll (Monthly Payruns, Payslips & Breakdown Lines)
    # -------------------------------------------------------------------------
    if 'hr.payslip' in env and 'hr.payslip.run' in env:
        _logger.info("Hudson HR Suite: Loading Payroll demo data...")
        PayslipRun = env['hr.payslip.run'].sudo()
        Payslip = env['hr.payslip'].sudo()
        PayslipLine = env['hr.payslip.line'].sudo()
        Structure = env['hr.payroll.structure'].sudo()
        Category = env['hr.salary.rule.category'].sudo()
        Rule = env['hr.salary.rule'].sudo()

        struct = Structure.search([], limit=1)
        rule_basic = Rule.search([('code', '=', 'BASIC')], limit=1)
        rule_gross = Rule.search([('code', '=', 'GROSS')], limit=1)
        rule_net = Rule.search([('code', '=', 'NET')], limit=1)
        rule_alw = Rule.search([('category_id.code', '=', 'ALW')], limit=1) or rule_basic
        rule_ded = Rule.search([('category_id.code', '=', 'DED')], limit=1) or rule_net

        cat_basic = Category.search([('code', '=', 'BASIC')], limit=1)
        cat_alw = Category.search([('code', '=', 'ALW')], limit=1)
        cat_gross = Category.search([('code', '=', 'GROSS')], limit=1)
        cat_ded = Category.search([('code', '=', 'DED')], limit=1)
        cat_net = Category.search([('code', '=', 'NET')], limit=1)

        # 1. November 2026 Payrun (Current - Ready in Review / Verify)
        nov_run = PayslipRun.search([('name', '=', 'November 2026 — Restaurant & Cafe Staff Payrun')], limit=1)
        if not nov_run:
            nov_run = PayslipRun.create({
                'name': 'November 2026 — Restaurant & Cafe Staff Payrun',
                'date_start': date(2026, 11, 1),
                'date_end': date(2026, 11, 30),
            })

        # 2. October 2026 Payrun (Previous Month - Validated & Paid)
        oct_run = PayslipRun.search([('name', '=', 'October 2026 — Restaurant & Cafe Staff Payrun')], limit=1)
        if not oct_run:
            oct_run = PayslipRun.create({
                'name': 'October 2026 — Restaurant & Cafe Staff Payrun',
                'date_start': date(2026, 10, 1),
                'date_end': date(2026, 10, 31),
                'state': 'close',
            })

        # Staff salary specifications: (Name, Basic, HRA, Allowance, PF)
        salaries = [
            ('Rahul Nair', 40000, 15000, 10000, 1800),
            ('Ananya Sharma', 25000, 10000, 7000, 1800),
            ('Vishnu Kumar', 18000, 6000, 3000, 1800),
            ('Priya Menon', 22000, 8000, 5000, 1800),
            ('Mohammed Bilal', 16000, 5000, 4000, 1800),
            ('Sneha Pillai', 17000, 5500, 2500, 1800),
            ('Arun Varma', 15000, 5000, 5000, 1800),
            ('Kevin Joseph', 16000, 5000, 3000, 1800),
            ('Suresh Kumar', 55000, 20000, 15000, 1800),
        ]

        for emp_name, basic, hra, alw, pf in salaries:
            emp = employees.get(emp_name)
            if not emp:
                continue

            gross = basic + hra + alw
            net = gross - pf

            version = emp.version_id or env['hr.version'].sudo().search([('employee_id', '=', emp.id)], limit=1)
            if version:
                version_vals = {'wage': basic}
                if struct:
                    version_vals['struct_id'] = struct.id
                    if hasattr(version, 'structure_type_id') and getattr(struct, 'type_id', False):
                        version_vals['structure_type_id'] = struct.type_id.id
                version.write(version_vals)
            else:
                version = env['hr.version'].sudo().create({
                    'name': f"{emp_name} - Regular Employment",
                    'employee_id': emp.id,
                    'wage': basic,
                    'struct_id': struct.id if struct else False,
                    'date_start': date(2026, 1, 1),
                })

            # Create November Payslip (Current)
            nov_slip = Payslip.search([
                ('employee_id', '=', emp.id),
                ('payslip_run_id', '=', nov_run.id)
            ], limit=1)
            if not nov_slip:
                try:
                    nov_slip = Payslip.create({
                        'name': f'Salary Slip - {emp_name} - November 2026',
                        'employee_id': emp.id,
                        'contract_id': version.id,
                        'struct_id': struct.id if struct else False,
                        'date_from': date(2026, 11, 1),
                        'date_to': date(2026, 11, 30),
                        'payslip_run_id': nov_run.id,
                        'basic_wage': basic,
                        'gross_wage': gross,
                        'net_wage': net,
                        'state': 'verify',
                    })
                    # Add Breakdown Lines
                    lines = [
                        ('Basic Salary', 'BASIC', rule_basic, cat_basic, basic, basic),
                        ('House Rent Allowance (HRA)', 'HRA', rule_alw, cat_alw, hra, hra),
                        ('Special Position Allowance', 'ALW', rule_alw, cat_alw, alw, alw),
                        ('Gross Taxable Salary', 'GROSS', rule_gross, cat_gross, gross, gross),
                        ('Provident Fund (PF) Employee', 'PF', rule_ded, cat_ded, -pf, -pf),
                        ('Net Salary Payable', 'NET', rule_net, cat_net, net, net),
                    ]
                    for lname, lcode, lrule, lcat, lamnt, ltot in lines:
                        PayslipLine.create({
                            'slip_id': nov_slip.id,
                            'name': lname,
                            'code': lcode,
                            'salary_rule_id': lrule.id if lrule else False,
                            'category_id': lrule.category_id.id if (lrule and lrule.category_id) else (lcat.id if lcat else False),
                            'employee_id': emp.id,
                            'contract_id': version.id,
                            'amount': lamnt,
                            'total': ltot,
                            'appears_on_payslip': True,
                        })
                except Exception as e:
                    _logger.warning("Could not create Nov payslip for %s: %s", emp_name, e)

            # Create October Paid Payslip (Previous)
            oct_slip = Payslip.search([
                ('employee_id', '=', emp.id),
                ('payslip_run_id', '=', oct_run.id)
            ], limit=1)
            if not oct_slip:
                try:
                    oct_slip = Payslip.create({
                        'name': f'Salary Slip - {emp_name} - October 2026',
                        'employee_id': emp.id,
                        'contract_id': version.id,
                        'struct_id': struct.id if struct else False,
                        'date_from': date(2026, 10, 1),
                        'date_to': date(2026, 10, 31),
                        'payslip_run_id': oct_run.id,
                        'basic_wage': basic,
                        'gross_wage': gross,
                        'net_wage': net,
                        'state': 'done',
                    })
                    lines = [
                        ('Basic Salary', 'BASIC', rule_basic, cat_basic, basic, basic),
                        ('House Rent Allowance (HRA)', 'HRA', rule_alw, cat_alw, hra, hra),
                        ('Special Position Allowance', 'ALW', rule_alw, cat_alw, alw, alw),
                        ('Gross Taxable Salary', 'GROSS', rule_gross, cat_gross, gross, gross),
                        ('Provident Fund (PF) Employee', 'PF', rule_ded, cat_ded, -pf, -pf),
                        ('Net Salary Payable', 'NET', rule_net, cat_net, net, net),
                    ]
                    for lname, lcode, lrule, lcat, lamnt, ltot in lines:
                        PayslipLine.create({
                            'slip_id': oct_slip.id,
                            'name': lname,
                            'code': lcode,
                            'salary_rule_id': lrule.id if lrule else False,
                            'category_id': lrule.category_id.id if (lrule and lrule.category_id) else (lcat.id if lcat else False),
                            'employee_id': emp.id,
                            'contract_id': version.id,
                            'amount': lamnt,
                            'total': ltot,
                            'appears_on_payslip': True,
                        })
                except Exception as e:
                    _logger.warning("Could not create Oct payslip for %s: %s", emp_name, e)

    _logger.info("Hudson HR Suite: Interconnected demo data successfully loaded!")


def clear_hr_suite_demo_data(env):
    """
    Cleans up HR Suite demo data.
    """
    _logger.info("Hudson HR Suite: Cleaning up demo data...")
    emp_names = [
        'Rahul Nair', 'Ananya Sharma', 'Vishnu Kumar',
        'Priya Menon', 'Mohammed Bilal', 'Sneha Pillai',
        'Arun Varma', 'Kevin Joseph', 'Suresh Kumar'
    ]
    employees = env['hr.employee'].sudo().search([('name', 'in', emp_names)])

    if employees:
        # 0. Unlink payroll
        if 'hr.payslip' in env:
            try:
                with env.cr.savepoint():
                    slips = env['hr.payslip'].sudo().search([('employee_id', 'in', employees.ids)])
                    if slips:
                        try:
                            slips.write({'state': 'draft'})
                        except Exception:
                            pass
                        if 'hr.payslip.line' in env:
                            env['hr.payslip.line'].sudo().search([('slip_id', 'in', slips.ids)]).unlink()
                        slips.unlink()
            except Exception as e:
                _logger.warning("Could not unlink payslips: %s", e)

        if 'hr.payslip.run' in env:
            try:
                with env.cr.savepoint():
                    runs = env['hr.payslip.run'].sudo().search([
                        ('name', 'in', [
                            'November 2026 — Restaurant & Cafe Staff Payrun',
                            'October 2026 — Restaurant & Cafe Staff Payrun',
                            'Test Payrun Nov 2026'
                        ])
                    ])
                    if runs:
                        try:
                            runs.write({'state': 'draft'})
                        except Exception:
                            pass
                        runs.unlink()
            except Exception as e:
                _logger.warning("Could not unlink payruns: %s", e)

        # 1. Unlink attendances
        try:
            with env.cr.savepoint():
                env['hr.attendance'].sudo().search([('employee_id', 'in', employees.ids)]).unlink()
        except Exception as e:
            _logger.warning("Could not unlink attendances: %s", e)

        # 2. Unlink leaves & allocations
        try:
            with env.cr.savepoint():
                env['hr.leave'].sudo().search([('employee_id', 'in', employees.ids)]).unlink()
                env['hr.leave.allocation'].sudo().search([('employee_id', 'in', employees.ids)]).unlink()
        except Exception as e:
            _logger.warning("Could not unlink leaves: %s", e)

        # 3. Unlink fleet
        try:
            with env.cr.savepoint():
                vehicles = env['fleet.vehicle'].sudo().search([('driver_employee_id', 'in', employees.ids)])
                if vehicles:
                    if 'fleet.vehicle.assignation.log' in env:
                        env['fleet.vehicle.assignation.log'].sudo().search([('vehicle_id', 'in', vehicles.ids)]).unlink()
                    env['fleet.vehicle.odometer'].sudo().search([('vehicle_id', 'in', vehicles.ids)]).unlink()
                    env['fleet.vehicle.log.services'].sudo().search([('vehicle_id', 'in', vehicles.ids)]).unlink()
                    vehicles.unlink()
        except Exception as e:
            _logger.warning("Could not unlink fleet: %s", e)

        # 4. Unlink expenses
        try:
            with env.cr.savepoint():
                env['hr.expense'].sudo().search([('employee_id', 'in', employees.ids)]).unlink()
        except Exception as e:
            _logger.warning("Could not unlink expenses: %s", e)

        # 5. Unlink lunch orders & cashmoves
        try:
            with env.cr.savepoint():
                admin_user = env.ref('base.user_admin', raise_if_not_found=False)
                if admin_user:
                    env['lunch.order'].sudo().search([('user_id', '=', admin_user.id)]).unlink()
        except Exception as e:
            _logger.warning("Could not unlink lunch orders: %s", e)

        # Finally unlink employees
        try:
            with env.cr.savepoint():
                employees.unlink()
        except Exception as e:
            _logger.warning("Could not unlink employees: %s", e)

    _logger.info("Hudson HR Suite: Demo data cleared.")
