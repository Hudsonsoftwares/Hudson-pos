# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import base64
import hashlib
import logging
import os
from .demo_xml import load_demo_xml as convert_file  # tolerant of apps not installed
from .demo_guard import preexisting
from odoo import Command

_logger = logging.getLogger(__name__)

DEMO_XML_FILES = [
    'demo/pos_categories.xml',
    'demo/product_tags.xml',
    'demo/courses.xml',
    'demo/note_models.xml',
    'demo/floors_and_tables.xml',
    'demo/pricelists.xml',
    'demo/loyalty_programs.xml',
    'demo/products_resto.xml',
]

RECRUITMENT_XML_FILE = 'demo/recruitment_demo.xml'

IMAGE_SEARCH_PATHS = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static', 'src', 'img')),
    r'C:\Program Files\Odoo 20.0.20260928\server\odoo\addons\pos_restaurant\static\img',
    r'C:\Program Files\Odoo 20.0.20260928\server\odoo\addons\point_of_sale\static\img',
]

PRODUCT_IMAGE_MAP = {
    'Bacon Burger': 'th-burger.png',
    'Cheese Burger': 'th-cheeseburger.png',
    'Burger Menu Combo': 'combo-hamb.png',
    'Club Sandwich': 'th-club.png',
    'Mozzarella Sandwich': 'th-mozza.png',
    'Chicken Curry Sandwich': 'th-sandwich.png',
    'Spicy Tuna Sandwich': 'th-tuna.png',
    'Pizza Margherita': 'th-pizza-ma.png',
    'Pizza Vegetarian': 'th-pizza-ve.png',
    'Funghi': 'th-pizza-fu.png',
    'Pasta 4 Formaggi': 'th-pasta-4f.png',
    'Pasta Bolognese': 'th-pasta.png',
    'Pasta Lunch Combo': 'th-pasta.png',
    'Lunch Maki 18pc': 'th-maki.png',
    'Lunch Salmon 20pc': 'th-salmon.png',
    'Lunch Temaki mix 3pc': 'th-temaki.png',
    'Salmon and Avocado': 'th-salmon-avocado.png',
    'Sushi Lunch Combo': 'sushi-combo.png',
    'Coca-Cola': 'th-coke.png',
    'Fanta': 'th-fanta.png',
    'Water': 'th-water.png',
    'Schweppes': 'th-schweppes.png',
    'Minute Maid': 'th-minute_maid.png',
    'Milkshake Banana': 'th-milkshake_banana.png',
    'Espresso': 'th-espresso.png',
    'Green Tea': 'th-green_tea.png',
    'Ice Tea': 'th-ice_tea.png',
    'Signature Hot Chocolate': 'product_hot_chocolate.png',
    'Warm Apple Pie': 'product_apple_pie.png',
    'Artisan Chocolate Croissant': 'product_pain_au_chocolat.png',
    'Double Chocolate Chip Cookie': 'product_chocolate_chip_cookie.png',
    'New York Cheesecake': 'product_new_york_cheesecake.png',
    'Chocolate Lava Cake': 'product_chocolate_lava_cake.png',
    'Crème Brûlée': 'product_creme_brulee.png',
    'Tiramisu': 'product_tiramisu.png',
    'Fresh Strawberry Tart': 'product_cherry_pie.png',
    'Vanilla Bean Ice Cream Sundae': 'product_ice_cream_sundae.png',
    'French Macarons Box (6 pcs)': 'product_french_macarons.png',
    'Belgian Milk Chocolate Truffles': 'product_belgian_truffles.png',
    'Dark Chocolate Bar 70%': 'product_dark_chocolate_bar.png',
    'White Chocolate Raspberry Bar': 'product_white_chocolate_bar.png',
    'Luxury Chocolate Gift Box': 'product_luxury_chocolate_box.png',
    'Dessert & Hot Drink Combo': 'product_dessert_combo.png',
    'Fudge Brownie & Ice Cream': 'product_fudge_brownie.png',
}

LEGACY_PLACEHOLDER_IMAGES = (
    'pastries-icon.png',
    'soft-drink-icon.png',
)

LEGACY_REUSED_IMAGES = {
    'Double Chocolate Chip Cookie': 'product_blueberry_muffin.png',
    'Vanilla Bean Ice Cream Sundae': 'th-milkshake_banana.png',
    'New York Cheesecake': 'product_pecan_pie.png',
}


def load_pos_demo_data(env, pos_config_ids=None):
    """
    Load ALL demo data available for the apps installed right now: the POS core data (when
    Point of Sale, Restaurant, Loyalty and Inventory are installed) and every suite whose apps
    are installed. Suites of apps installed later are loaded automatically at that time by
    ``hudson.pos.demo.autoloader`` (see demo_autoloader.py).
    """
    from .demo_autoloader import run_autoload
    return run_autoload(env, force=True, pos_config_ids=pos_config_ids)


def load_pos_core_demo_data(env, pos_config_ids=None):
    """
    Complete Restaurant & Cafe POS Demo Data Loader (requires point_of_sale, pos_restaurant,
    pos_loyalty and stock):
    - Purges duplicate/orphan floor plans.
    - Loads categories, tags, courses, prep notes, floors, pricelists, loyalty, and products.
    - Creates real POS Combo Choices and configures combo products with type='combo'.
    - Configures 2 distinct food & beverage POS configs: Restaurant (Dine-in) & Cafe (Register).
    - Sets beautiful graphical floor plan table positions.
    - Attaches high-res product images, initial warehouse stock and sample POS orders.
    """
    _logger.info("Hudson POS: Starting Restaurant & Cafe Demo Data loader...")

    # 1. Clean up duplicate / orphan floors created previously
    with env.cr.savepoint():
        _cleanup_duplicate_floors(env)

    # 2. Pre-bind existing records to ir.model.data
    with env.cr.savepoint():
        _pre_bind_existing_records(env)

    # 3. Execute all standard XML demo files safely inside savepoints
    for xml_file in DEMO_XML_FILES:
        try:
            with env.cr.savepoint():
                _logger.info("Loading demo XML: %s", xml_file)
                convert_file(
                    env,
                    'hudson_pos_demo_data',
                    xml_file,
                    idref={},
                    mode='init',
                    noupdate=True,
                )
        except Exception as e:
            _logger.error("Failed to load demo file %s: %s", xml_file, e)

    # 4. Clean up any 'My Company' duplicate floor created by Odoo during POS init
    with env.cr.savepoint():
        _cleanup_duplicate_floors(env)

    # 5. Configure graphical floor layouts and table positions
    try:
        with env.cr.savepoint():
            _configure_floors_and_tables(env)
    except Exception as e:
        _logger.warning("Could not configure floors and tables: %s", e)

    # 6. Ensure Restaurant and Cafe POS configurations exist
    try:
        with env.cr.savepoint():
            _ensure_default_shops(env)
    except Exception as e:
        _logger.warning("Could not ensure default POS shops: %s", e)

    # 6b. Configure product variants (sizes and flavours)
    try:
        with env.cr.savepoint():
            _configure_product_variants(env)
    except Exception as e:
        _logger.warning("Could not configure product variants: %s", e)

    # 7. Configure true POS Combos (product.combo & type='combo')
    try:
        with env.cr.savepoint():
            _configure_combos(env)
    except Exception as e:
        _logger.warning("Could not configure POS combos: %s", e)

    # 8. Attach images to products
    try:
        with env.cr.savepoint():
            _load_product_images(env)
    except Exception as e:
        _logger.warning("Could not load product images: %s", e)

    # 8b. Configure advanced loyalty programs, product rules/rewards, and sample cards
    try:
        with env.cr.savepoint():
            _configure_loyalty_demo_data(env)
    except Exception as e:
        _logger.warning("Could not configure loyalty demo data: %s", e)

    # 9. Link floors, screens, pricelists, and loyalty programs to POS configs
    try:
        with env.cr.savepoint():
            _post_process_pos_configs(env, pos_config_ids)
    except Exception as e:
        _logger.warning("Could not post-process POS configs: %s", e)

    # Remove any dummy company floor auto-created by pos_restaurant during shop creation
    with env.cr.savepoint():
        _cleanup_duplicate_floors(env)

    # 10. Initialize stock inventory
    try:
        with env.cr.savepoint():
            _load_stock_inventory(env)
    except Exception as e:
        _logger.warning("Could not load stock inventory: %s", e)

    # 11. Create sample POS orders for demonstration
    try:
        with env.cr.savepoint():
            _load_sample_pos_orders(env)
    except Exception as e:
        _logger.warning("Could not load sample POS orders: %s", e)

    _logger.info("Hudson POS: Restaurant & Cafe POS core demo data loaded successfully.")
    return True


def load_recruitment_jobs_demo_data(env):
    """Restaurant & Cafe job openings published on the website (requires website_hr_recruitment)."""
    if 'hr.job' not in env or 'is_published' not in env['hr.job']._fields:
        _logger.info("Skipping %s because website_hr_recruitment is not installed.", RECRUITMENT_XML_FILE)
        return
    try:
        with env.cr.savepoint():
            convert_file(env, 'hudson_pos_demo_data', RECRUITMENT_XML_FILE,
                         idref={}, mode='init', noupdate=True)
    except Exception as e:
        _logger.error("Failed to load demo file %s: %s", RECRUITMENT_XML_FILE, e)
    _load_recruitment_demo_data(env)


def _cleanup_duplicate_floors(env):
    """
    Removes auto-generated dummy floors named after the company ('My Company') when orphaned without POS configs.
    """
    if 'restaurant.floor' not in env:  # POS Restaurant not installed (yet)
        return
    RestaurantFloor = env['restaurant.floor'].sudo()
    dummy_names = list({n for n in ['My Company', env.company.name] if n})
    dummy_floors = RestaurantFloor.search([
        ('name', 'in', dummy_names),
        ('pos_config_ids', '=', False),
    ])
    for flr in dummy_floors:
        try:
            with env.cr.savepoint():
                flr.table_ids.unlink()
                flr.unlink()
        except Exception as e:
            _logger.warning("Could not unlink dummy floor %s: %s", flr.id, e)


def _configure_floors_and_tables(env):
    """
    Decorated floor plans: walls, entrance, reception, bar, open kitchen, booths, chairs around
    every table, patio with fountain, parasols and fire-pit lounge (see demo_floor_plan.py).
    """
    from .demo_floor_plan import apply_floor_plans
    apply_floor_plans(env)


def _ensure_default_shops(env):
    """
    Ensures 2 distinct food & beverage POS shops exist:
    1. Restaurant (Dine-in with Tables, Floors, Courses, Prep notes)
    2. Cafe (Counter-service Register with Drinks, Coffee, Desserts, Combos)
    """
    PosConfig = env['pos.config'].sudo()
    # floors exist only with POS Restaurant; the shops are created anyway and get their floors
    # when POS Restaurant is installed (the auto-loader runs this again then)
    floors = env['restaurant.floor'].sudo().search([('name', 'in', ['Main Floor', 'Patio'])])         if 'restaurant.floor' in env else []

    # 1. Restaurant POS
    resto = PosConfig.search([('name', '=', 'Restaurant')], limit=1)
    if not resto:
        resto = PosConfig.search([('module_pos_restaurant', '=', True)], limit=1)
    if not resto:
        resto = PosConfig.create({
            'name': 'Restaurant',
            'module_pos_restaurant': True,
        })
    else:
        resto.write({
            'name': 'Restaurant',
            'module_pos_restaurant': True,
        })

    if not resto.current_session_id:
        resto_vals = {}
        if hasattr(resto, 'default_screen'):
            resto_vals['default_screen'] = 'tables'
        if hasattr(resto, 'use_course_allocation'):
            resto_vals['use_course_allocation'] = True
        if floors:
            resto_vals['floor_ids'] = [Command.set(floors.ids)]
        resto.write(resto_vals)

    # 2. Cafe POS (Counter service / Quick register)
    cafe = PosConfig.search([('name', '=', 'Cafe')], limit=1)
    if not cafe:
        cafe = PosConfig.create({
            'name': 'Cafe',
            'module_pos_restaurant': False,
        })
    else:
        cafe.write({
            'module_pos_restaurant': False,
        })

    if not cafe.current_session_id and hasattr(cafe, 'default_screen'):
        cafe.write({'default_screen': 'register'})


def _configure_product_variants(env):
    """
    Configures multi-attribute product variants (Sizes and Flavours) on existing POS demo products.
    Sets realistic price extras (e.g. Medium, Large, Double Scoop, Double Patty) and internal codes.
    """
    if 'product.attribute' not in env or 'product.template' not in env:
        return

    _logger.info("Hudson POS: Configuring product variants (sizes and flavours)...")

    ProductAttribute = env['product.attribute'].sudo()
    AttributeValue = env['product.attribute.value'].sudo()
    ProductTemplate = env['product.template'].sudo()
    PTAL = env['product.template.attribute.line'].sudo()

    def get_or_create_attr(name, display_type='pills'):
        attr = ProductAttribute.search([('name', '=', name)], limit=1)
        if not attr:
            attr = ProductAttribute.create({'name': name, 'display_type': display_type})
        return attr

    def get_or_create_val(attr, val_name, seq=10):
        val = AttributeValue.search([('attribute_id', '=', attr.id), ('name', '=', val_name)], limit=1)
        if not val:
            val = AttributeValue.create({'attribute_id': attr.id, 'name': val_name, 'sequence': seq})
        return val

    # Base attributes
    attr_size = get_or_create_attr('Size', 'pills')
    attr_pack_size = get_or_create_attr('Pack Size', 'pills')
    attr_portion = get_or_create_attr('Portion Size', 'pills')
    attr_patty = get_or_create_attr('Patty Size', 'pills')
    attr_flavour = get_or_create_attr('Flavour', 'pills')
    attr_flavour_style = get_or_create_attr('Flavour Style', 'pills')
    attr_bacon_flavour = get_or_create_attr('Bacon Flavour', 'pills')
    attr_macaron_flavour = get_or_create_attr('Flavour Assortment', 'pills')
    attr_tea_size = get_or_create_attr('Serving Size', 'pills')
    attr_bread = get_or_create_attr('Bread Type', 'pills')
    attr_pasta = get_or_create_attr('Pasta Type', 'pills')
    attr_spice = get_or_create_attr('Spice Level', 'pills')
    attr_water_type = get_or_create_attr('Water Type', 'pills')
    attr_dressing = get_or_create_attr('Dressing', 'pills')
    attr_serving = get_or_create_attr('Serving Style', 'pills')
    attr_card_value = get_or_create_attr('Card Value', 'pills')

    VARIANT_CONFIGS = [
        # 1. Existing Core Dishes & Drinks
        ('Pizza Margherita', 'PIZ-MARG', [
            (attr_size, [('Regular (10")', 1, 0.0, 'REG'), ('Medium (12")', 2, 3.5, 'MED'), ('Large (14")', 3, 6.0, 'LRG')])
        ]),
        ('Pizza Vegetarian', 'PIZ-VEG', [
            (attr_size, [('Regular (10")', 1, 0.0, 'REG'), ('Medium (12")', 2, 4.0, 'MED'), ('Large (14")', 3, 7.0, 'LRG')])
        ]),
        ('Cheese Burger', 'BUR-CHS', [
            (attr_patty, [('Single Patty (150g)', 1, 0.0, '150G'), ('Double Patty (300g)', 2, 3.5, '300G')]),
            (attr_flavour_style, [('Classic American Cheddar', 1, 0.0, 'CLSC'), ('Spicy Jalapeno Melt', 2, 0.75, 'SPCY'), ('Smoky BBQ & Onion', 3, 1.0, 'BBQ')])
        ]),
        ('Bacon Burger', 'BUR-BCN', [
            (attr_patty, [('Single Patty', 1, 0.0, 'SGL'), ('Double Patty', 2, 3.5, 'DBL')]),
            (attr_bacon_flavour, [('Crispy Smoked Maple Bacon', 1, 0.0, 'MAPLE'), ('Black Pepper Glazed Bacon', 2, 0.5, 'PEPR')])
        ]),
        ('Milkshake Banana', 'MS-SHAKE', [
            (attr_flavour, [('Banana Cream', 1, 0.0, 'BAN'), ('Belgian Chocolate', 2, 0.0, 'CHOC'), ('Wild Strawberry', 3, 0.0, 'STRW'), ('Salted Caramel', 4, 0.0, 'CARM')]),
            (attr_size, [('Regular (350ml)', 10, 0.0, '350ML'), ('Large (500ml)', 11, 1.5, '500ML')])
        ]),
        ('Fanta', 'DRK-FNT', [
            (attr_flavour, [('Orange Splash', 10, 0.0, 'ORN'), ('Grape Burst', 11, 0.0, 'GRP'), ('Pineapple Passion', 12, 0.0, 'PIN')])
        ]),
        ('Espresso', 'COF-ESP', [
            (attr_size, [('Single Shot', 20, 0.0, 'SGL'), ('Double Shot (Doppio)', 21, 1.0, 'DBL')])
        ]),
        ('Green Tea', 'TEA-GRN', [
            (attr_flavour, [('Jasmine Blossom', 20, 0.0, 'JAS'), ('Moroccan Mint', 21, 0.0, 'MNT'), ('Lemon & Ginger', 22, 0.0, 'LEM')]),
            (attr_tea_size, [('Cup (250ml)', 1, 0.0, 'CUP'), ('Teapot (600ml)', 2, 2.5, 'POT')])
        ]),
        ('Vanilla Bean Ice Cream Sundae', 'DS-ICR', [
            (attr_flavour, [('Madagascar Vanilla', 30, 0.0, 'VAN'), ('Belgian Chocolate', 31, 0.0, 'CHOC'), ('Wild Berry Swirl', 32, 0.0, 'BRY'), ('Salted Caramel Crunch', 33, 0.0, 'CARM')]),
            (attr_portion, [('Single Scoop', 1, 0.0, '1SCP'), ('Double Scoop', 2, 2.5, '2SCP')])
        ]),
        ('French Macarons Box (6 pcs)', 'DS-MAC', [
            (attr_macaron_flavour, [('Classic Parisian (Vanilla, Pistachio, Raspberry)', 1, 0.0, 'CLSC'), ('Chocolatier Collection (Dark, Milk, White)', 2, 1.0, 'CHOC'), ('Exotic Citrus & Berry (Passionfruit, Lemon, Cassis)', 3, 1.5, 'EXOT')])
        ]),
        ('Artisan Chocolate Croissant', 'BKG-CRS', [
            (attr_flavour, [('Classic Dark Chocolate (70%)', 40, 0.0, 'DRK'), ('Hazelnut Praline Gianduja', 41, 0.75, 'PRAL'), ('Almond Frangipane & Chocolate', 42, 1.0, 'ALMD')])
        ]),

        # 2. Sandwiches, Pizzas & Savory Mains
        ('Funghi', 'PIZ-FNG', [
            (attr_size, [('Personal (8")', 1, 0.0, '8IN'), ('Medium (12")', 2, 3.5, '12IN'), ('Large (16")', 3, 6.5, '16IN')])
        ]),
        ('Chicken Curry Sandwich', 'SND-CHK', [
            (attr_size, [('Half (6")', 1, 0.0, '6IN'), ('Full (12")', 2, 2.5, '12IN')]),
            (attr_bread, [('Artisan Sourdough', 1, 0.0, 'SRD'), ('Brioche Roll', 2, 0.5, 'BRC')])
        ]),
        ('Club Sandwich', 'SND-CLB', [
            (attr_portion, [('Single Deck', 1, 0.0, 'SGL'), ('Double Stack', 2, 2.0, 'DBL')]),
            (attr_flavour_style, [('Classic Turkey & Bacon', 1, 0.0, 'TRK'), ('Smoked Ham & Cheddar', 2, 0.5, 'HAM')])
        ]),
        ('Mozzarella Sandwich', 'SND-MOZ', [
            (attr_bread, [('Rosemary Focaccia', 1, 0.0, 'FOC'), ('Ciabatta Rustica', 2, 0.0, 'CIA'), ('Gluten-Free Bread', 3, 1.0, 'GF')]),
            (attr_flavour, [('Pesto Genovese & Tomato', 1, 0.0, 'PST'), ('Sun-Dried Tomato & Olive Tapenade', 2, 0.5, 'SDT')])
        ]),
        ('Spicy Tuna Sandwich', 'SND-TNA', [
            (attr_size, [('Half (6")', 1, 0.0, '6IN'), ('Full (12")', 2, 2.5, '12IN')]),
            (attr_spice, [('Mild Kick', 1, 0.0, 'MLD'), ('Medium Zest', 2, 0.0, 'MED'), ('Extra Spicy Sriracha', 3, 0.5, 'XSP')])
        ]),
        ('Pasta 4 Formaggi', 'PST-4F', [
            (attr_portion, [('Standard (300g)', 1, 0.0, 'STD'), ('Grande (450g)', 2, 3.5, 'GRD')]),
            (attr_pasta, [('Penne Rigate', 1, 0.0, 'PEN'), ('Tagliatelle Egg Pasta', 2, 0.5, 'TAG')])
        ]),
        ('Pasta Bolognese', 'PST-BOL', [
            (attr_portion, [('Standard (300g)', 1, 0.0, 'STD'), ('Grande (450g)', 2, 3.0, 'GRD')]),
            (attr_pasta, [('Spaghetti No. 5', 1, 0.0, 'SPG'), ('Rigatoni', 2, 0.0, 'RIG')])
        ]),
        ('Lunch Maki 18pc', 'SUS-MAK', [
            (attr_macaron_flavour, [('Chef Selection Classic', 1, 0.0, 'CLSC'), ('Salmon & Tuna Deluxe', 2, 2.5, 'DLX'), ('Spicy Tempura Crunch', 3, 2.0, 'SPCY')])
        ]),
        ('Lunch Salmon 20pc', 'SUS-SAL', [
            (attr_serving, [('Fresh Nigiri & Sashimi', 1, 0.0, 'RAW'), ('Seared Aburi Torched with Ponzu', 2, 2.0, 'ABU')])
        ]),
        ('Lunch Temaki mix 3pc', 'SUS-TMK', [
            (attr_macaron_flavour, [('Traditional Nori Wrap', 1, 0.0, 'NORI'), ('Soy Crepe Wrap', 2, 1.0, 'SOY')])
        ]),
        ('Salmon and Avocado', 'BWL-SAL', [
            (attr_portion, [('Regular Bowl', 1, 0.0, 'REG'), ('Large Bowl', 2, 3.5, 'LRG')]),
            (attr_dressing, [('Toasted Sesame Ginger', 1, 0.0, 'SES'), ('Citrus Ponzu Vinaigrette', 2, 0.0, 'PNZ'), ('Spicy Kewpie Mayo', 3, 0.5, 'KWP')])
        ]),

        # 3. Desserts, Pastries & Chocolates
        ('Belgian Milk Chocolate Truffles', 'CHOC-TRF', [
            (attr_portion, [('Box of 4 pcs', 1, 0.0, '4PC'), ('Box of 8 pcs', 2, 5.0, '8PC'), ('Box of 16 pcs', 3, 11.0, '16PC')]),
            (attr_flavour, [('Velvety Milk Truffle', 1, 0.0, 'MLK'), ('Dark Cocoa Dust 72%', 2, 0.5, 'DRK'), ('Hazelnut Praline Feuilletine', 3, 1.0, 'PRL')])
        ]),
        ('Chocolate Lava Cake', 'DS-LAV', [
            (attr_flavour, [('Belgian Dark Cocoa Core', 1, 0.0, 'DRK'), ('Gooey Salted Caramel Center', 2, 1.0, 'CARM'), ('Ruby Raspberry Ganache', 3, 1.0, 'RASP')]),
            (attr_serving, [('Warm Cake Only', 1, 0.0, 'CAKE'), ('A La Mode + Madagascar Vanilla Scoop', 2, 2.0, 'ICR')])
        ]),
        ('Crème Brûlée', 'DS-CRB', [
            (attr_flavour, [('Bourbon Vanilla Bean', 1, 0.0, 'VAN'), ('Earl Grey & Lavender Tea', 2, 0.75, 'EGY'), ('Double Ristretto Espresso', 3, 0.75, 'ESP')])
        ]),
        ('Fresh Strawberry Tart', 'DS-STR', [
            (attr_portion, [('Individual Tartlet (4")', 1, 0.0, 'IND'), ('Sharing Tart (8")', 2, 7.5, 'SHR')]),
            (attr_flavour, [('Vanilla Custard & Fresh Strawberries', 1, 0.0, 'CST'), ('Pistachio Cream & Glazed Berries', 2, 1.0, 'PST')])
        ]),
        ('Fudge Brownie & Ice Cream', 'DS-BRW', [
            (attr_flavour, [('Double Fudge Walnut Brownie', 1, 0.0, 'WLN'), ('Triple Chocolate Brownie (Nut-Free)', 2, 0.0, 'TRP')]),
            (attr_portion, [('Single Scoop Vanilla', 1, 0.0, '1SCP'), ('Double Scoop Vanilla & Choc', 2, 2.5, '2SCP')])
        ]),
        ('New York Cheesecake', 'DS-NYK', [
            (attr_portion, [('Individual Generous Slice', 1, 0.0, 'SLC'), ('Whole Sharing Cheesecake (8")', 2, 18.0, 'WHL')]),
            (attr_flavour, [('Classic Cream Cheese', 1, 0.0, 'CLS'), ('Wild Maine Blueberry Compote', 2, 1.0, 'BLU'), ('Wild Strawberry Coulis', 3, 1.0, 'STR')])
        ]),
        ('Tiramisu', 'DS-TIR', [
            (attr_portion, [('Individual Glass Cup', 1, 0.0, 'CUP'), ('Sharing Dessert Bowl', 2, 5.5, 'BWL')]),
            (attr_flavour, [('Traditional Espresso & Marsala', 1, 0.0, 'ESP'), ('Amaretto Almond Crunch', 2, 1.0, 'AMR'), ('Uji Matcha Green Tea', 3, 1.0, 'MTC')])
        ]),
        ('Warm Apple Pie', 'DS-APP', [
            (attr_serving, [('Warm Oven-Baked Slice', 1, 0.0, 'SLC'), ('A La Mode with Vanilla Ice Cream', 2, 2.0, 'MOD')]),
            (attr_flavour, [('Spiced Dutch Cinnamon Apple', 1, 0.0, 'CIN'), ('Salted Caramel & Roasted Pecan', 2, 1.0, 'CARM')])
        ]),
        ('Dark Chocolate Bar 70%', 'CHOC-BAR', [
            (attr_flavour, [('Pure Single Origin Dark 70%', 1, 0.0, 'PURE'), ('Himalayan Pink Salt & Roasted Almonds', 2, 0.5, 'SALT'), ('Candied Orange Peel & Cocoa Nibs', 3, 0.75, 'ORN')])
        ]),
        ('Luxury Chocolate Gift Box', 'CHOC-GFT', [
            (attr_portion, [('Collection of 9 pcs', 1, 0.0, '9PC'), ('Grand Collection of 16 pcs', 2, 8.0, '16PC'), ('Imperial Wooden Box 25 pcs', 3, 16.0, '25PC')])
        ]),
        ('White Chocolate Raspberry Bar', 'CHOC-WHT', [
            (attr_flavour, [('Crispy Freeze-Dried Raspberry', 1, 0.0, 'RASP'), ('Sicilian Pistachio & White Chocolate', 2, 0.5, 'PST'), ('Toasted Coconut & Vanilla Bean', 3, 0.5, 'COC')])
        ]),
        ('Double Chocolate Chip Cookie', 'BKG-CKI', [
            (attr_portion, [('Single Jumbo Cookie', 1, 0.0, '1PC'), ('Trio Pack (3 Cookies)', 2, 4.0, '3PC'), ('Baker Box (6 Cookies)', 3, 8.5, '6PC')]),
            (attr_flavour, [('Belgian Double Chocolate Chunk', 1, 0.0, 'DBL'), ('White Chocolate & Macadamia Nut', 2, 0.5, 'MAC')])
        ]),
        ('Signature Hot Chocolate', 'BEV-HOTC', [
            (attr_size, [('Regular (8oz)', 1, 0.0, '8OZ'), ('Grande (12oz)', 2, 1.2, '12OZ')]),
            (attr_flavour, [('Rich Belgian Dark 65%', 1, 0.0, 'DRK'), ('Silky Swiss Milk Chocolate', 2, 0.0, 'MLK'), ('Spiced Mexican Chilli Cinnamon', 3, 0.5, 'MEX')])
        ]),

        # 4. Soft Drinks, Teas, Water
        ('Coca-Cola', 'DRK-COK', [
            (attr_size, [('Can 330ml', 1, 0.0, 'CAN'), ('Glass Bottle 330ml', 2, 0.5, 'BTL'), ('PET 500ml', 3, 0.8, '500ML')]),
            (attr_flavour, [('Classic Original', 1, 0.0, 'CLS'), ('Zero Sugar', 2, 0.0, 'ZERO'), ('Cherry Vanilla Twist', 3, 0.3, 'CHR')])
        ]),
        ('Ice Tea', 'DRK-ICT', [
            (attr_size, [('Glass (350ml)', 1, 0.0, '350ML'), ('Carafe (1 Litre)', 2, 3.5, '1L')]),
            (attr_flavour, [('Sun Peach Nectar', 1, 0.0, 'PCH'), ('Fresh Lemon Citrus', 2, 0.0, 'LEM'), ('Tropical Passionfruit', 3, 0.3, 'PAS')])
        ]),
        ('Minute Maid', 'DRK-MMD', [
            (attr_size, [('Bottle 250ml', 1, 0.0, '250ML'), ('Bottle 400ml', 2, 1.0, '400ML')]),
            (attr_flavour, [('Pulpy Orange Delight', 1, 0.0, 'ORN'), ('Crisp Crisp Apple', 2, 0.0, 'APP'), ('Tropical Guava & Mango', 3, 0.0, 'TRP')])
        ]),
        ('Schweppes', 'DRK-SCH', [
            (attr_size, [('Can 330ml', 1, 0.0, 'CAN'), ('Glass Bottle 300ml', 2, 0.5, 'BTL')]),
            (attr_flavour, [('Indian Tonic Water', 1, 0.0, 'TNC'), ('Sparkling Ginger Ale', 2, 0.0, 'GNG'), ('Club Soda Water', 3, 0.0, 'SDA'), ('Bitter Lemon Refresher', 4, 0.0, 'BLM')])
        ]),
        ('Water', 'DRK-WTR', [
            (attr_size, [('Eco Bottle 500ml', 1, 0.0, '500ML'), ('Glass Bottle 750ml', 2, 1.2, '750ML'), ('Family Bottle 1.5L', 3, 1.8, '1.5L')]),
            (attr_water_type, [('Natural Mountain Spring (Still)', 1, 0.0, 'STL'), ('Effervescent Mineral (Sparkling)', 2, 0.5, 'SPK')])
        ]),

        # 5. Packaged Heritage Foods, Snacks & Pickles
        ('Cardamom Butter Cookies', 'RT-CKI', [
            (attr_pack_size, [('Tin 200g', 1, 0.0, '200G'), ('Family Tin 400g', 2, 120.0, '400G')])
        ]),
        ('Christmas Plum Cake (Rich Fruit)', 'RT-PLM', [
            (attr_pack_size, [('Gift Loaf 500g', 1, 0.0, '500G'), ('Celebration Round 1 kg', 2, 380.0, '1KG')])
        ]),
        ('Dry Coconut Chutney Powder', 'RT-CPD', [
            (attr_pack_size, [('Pouch 100g', 1, 0.0, '100G'), ('Pouch 250g', 2, 70.0, '250G')]),
            (attr_spice, [('Medium Spiced', 1, 0.0, 'MED'), ('Extra Spicy Guntur', 2, 0.0, 'HOT')])
        ]),
        ('Gift Card', 'SYS-GFT', [
            (attr_card_value, [('$25 Dining Credit', 1, -25.0, '25USD'), ('$50 Dining Credit', 2, 0.0, '50USD'), ('$100 Dining Credit', 3, 50.0, '100USD')])
        ]),
        ('Idli & Dosa Batter Mix', 'RT-BTR', [
            (attr_pack_size, [('Fresh Pouch 1 kg', 1, 0.0, '1KG'), ('Catering Tub 2 kg', 2, 90.0, '2KG')])
        ]),
        ('Instant Appam Mix', 'RT-APM', [
            (attr_pack_size, [('Pouch 500g', 1, 0.0, '500G'), ('Family Pouch 1 kg', 2, 100.0, '1KG')])
        ]),
        ('Jackfruit Chips', 'RT-JCK', [
            (attr_pack_size, [('Pouch 200g', 1, 0.0, '200G'), ('Bulk Jar 500g', 2, 180.0, '500G')]),
            (attr_flavour, [('Crispy Sea Salt', 1, 0.0, 'SALT'), ('Spicy Malabar Pepper', 2, 10.0, 'PEPR')])
        ]),
        ('Kerala Banana Chips (Coconut Oil)', 'RT-BNP', [
            (attr_pack_size, [('Pouch 200g', 1, 0.0, '200G'), ('Bulk Jar 500g', 2, 150.0, '500G')]),
            (attr_flavour, [('Golden Salted Crisp', 1, 0.0, 'SALT'), ('Spicy Masala Tossed', 2, 10.0, 'MAS'), ('Sweet Jaggery Sharkara Upperi', 3, 20.0, 'JAG')])
        ]),
        ('Kerala Cut Mango Pickle', 'RT-MNG', [
            (attr_pack_size, [('Jar 250g', 1, 0.0, '250G'), ('Pouch 500g', 2, 110.0, '500G')]),
            (attr_flavour, [('Traditional Tender Mango (Kadumango)', 1, 0.0, 'KADU'), ('Garlic Spiced Mango Pickle', 2, 10.0, 'GRLC')])
        ]),
        ('Kerala Treats Gift Box', 'RT-GFT', [
            (attr_portion, [('Heritage Standard Box', 1, 0.0, 'STD'), ('Grand Malabar Wooden Box', 2, 450.0, 'ROYAL')])
        ]),
        ('Kozhikode Black Halwa', 'RT-HLW', [
            (attr_pack_size, [('Pack 250g', 1, 0.0, '250G'), ('Block 500g', 2, 180.0, '500G'), ('Grand Box 1 kg', 3, 390.0, '1KG')])
        ]),
        ('Malabar Chicken Biryani (Ready-to-Eat)', 'RT-BRY', [
            (attr_portion, [('Single Portion (350g)', 1, 0.0, '350G'), ('Family Feast (800g)', 2, 220.0, '800G')])
        ]),
        ('Avial (Ready-to-Eat)', 'RT-AVL', [
            (attr_pack_size, [('Meal Pouch 300g', 1, 0.0, '300G'), ('Double Pouch 600g', 2, 130.0, '600G')])
        ]),
        ('Dal Makhani (Ready-to-Eat)', 'RT-DAL', [
            (attr_pack_size, [('Meal Pouch 300g', 1, 0.0, '300G'), ('Double Pouch 600g', 2, 140.0, '600G')])
        ]),
        ('Vegetable Stew (Ready-to-Eat)', 'RT-STW', [
            (attr_pack_size, [('Meal Pouch 300g', 1, 0.0, '300G'), ('Double Pouch 600g', 2, 135.0, '600G')])
        ]),
        ('Prawn Pickle', 'RT-PRW', [
            (attr_pack_size, [('Glass Jar 250g', 1, 0.0, '250G'), ('Family Jar 500g', 2, 280.0, '500G')])
        ]),
        ('Sweet & Sour Lime Pickle', 'RT-LME', [
            (attr_pack_size, [('Glass Jar 250g', 1, 0.0, '250G'), ('Family Jar 500g', 2, 100.0, '500G')])
        ]),
        ('Red Rice Puttu Podi', 'RT-PUT', [
            (attr_pack_size, [('Pouch 500g', 1, 0.0, '500G'), ('Pouch 1 kg', 2, 70.0, '1KG')])
        ]),
        ('Rice Murukku', 'RT-MRK', [
            (attr_pack_size, [('Pack 200g', 1, 0.0, '200G'), ('Family Box 500g', 2, 120.0, '500G')]),
            (attr_flavour, [('Traditional Crunchy Sesame', 1, 0.0, 'SES'), ('Spicy Garlic Butter', 2, 10.0, 'GRLC')])
        ]),
        ('Spicy Kerala Mixture', 'RT-MIX', [
            (attr_pack_size, [('Pouch 200g', 1, 0.0, '200G'), ('Family Jar 500g', 2, 130.0, '500G')]),
            (attr_spice, [('Classic Spicy Crunch', 1, 0.0, 'CLS'), ('Extra Hot Devil Fire', 2, 10.0, 'HOT')])
        ]),
    ]

    for tmpl_name, prefix, attr_defs in VARIANT_CONFIGS:
        tmpl = ProductTemplate.search([('name', '=', tmpl_name)], limit=1)
        if not tmpl:
            continue

        existing_attr_ids = set(tmpl.attribute_line_ids.mapped('attribute_id.id'))
        target_attr_ids = set(a.id for a, _ in attr_defs)

        if existing_attr_ids != target_attr_ids:
            if tmpl.attribute_line_ids:
                tmpl.attribute_line_ids.unlink()

            for attr, val_tuples in attr_defs:
                val_ids = [get_or_create_val(attr, vname, seq).id for vname, seq, _, _ in val_tuples]
                PTAL.create({
                    'product_tmpl_id': tmpl.id,
                    'attribute_id': attr.id,
                    'value_ids': [Command.set(val_ids)],
                })

        # Configure price extras and internal codes
        price_map = {}
        code_map = {}
        for attr, val_tuples in attr_defs:
            for vname, _, extra, code_suffix in val_tuples:
                price_map[(attr.id, vname)] = extra
                val_rec = AttributeValue.search([('attribute_id', '=', attr.id), ('name', '=', vname)], limit=1)
                if val_rec:
                    code_map[(attr.id, val_rec.id)] = code_suffix

        for line in tmpl.attribute_line_ids:
            for ptav in line.product_template_value_ids:
                extra = price_map.get((line.attribute_id.id, ptav.name), 0.0)
                if ptav.price_extra != extra:
                    ptav.price_extra = extra

        for idx, v in enumerate(tmpl.product_variant_ids, 1):
            if not v.default_code or v.default_code.startswith(prefix):
                suffixes = [code_map.get((ptav.attribute_id.id, ptav.product_attribute_value_id.id), '')
                            for ptav in v.product_template_attribute_value_ids]
                suffix_str = '-'.join(filter(None, suffixes))
                v.default_code = f'{prefix}-{suffix_str}' if suffix_str else f'{prefix}-{idx:02d}'


def _configure_combos(env):
    """
    Creates Odoo 20 product.combo records and configures combo products with type='combo'.
    """
    if 'product.combo' not in env:
        return

    ProductCombo = env['product.combo'].sudo()
    ProductProduct = env['product.product'].sudo()
    ProductTemplate = env['product.template'].sudo()

    def get_or_create_combo(combo_name, product_names):
        combo = ProductCombo.search([('name', '=', combo_name)], limit=1)
        items = []
        for pname in product_names:
            prod = ProductProduct.search([('name', '=', pname)], limit=1)
            if prod:
                items.append(Command.create({'product_id': prod.id, 'extra_price': 0}))
        if combo:
            combo.combo_item_ids.unlink()
            combo.write({'combo_item_ids': items})
        else:
            combo = ProductCombo.create({
                'name': combo_name,
                'combo_item_ids': items
            })
        return combo

    c_burgers = get_or_create_combo('Burgers', ['Cheese Burger', 'Bacon Burger'])
    c_drinks = get_or_create_combo('Drinks', ['Coca-Cola', 'Fanta', 'Minute Maid', 'Water', 'Milkshake Banana'])
    c_sushi = get_or_create_combo('Sushi Choices', ['Lunch Maki 18pc', 'Lunch Salmon 20pc', 'Lunch Temaki mix 3pc'])
    c_pasta = get_or_create_combo('Pasta Choices', ['Pasta 4 Formaggi', 'Pasta Bolognese'])
    c_desserts = get_or_create_combo('Dessert Choices', [
        'Tiramisu', 'New York Cheesecake', 'Chocolate Lava Cake', 'Double Chocolate Chip Cookie', 'Warm Apple Pie'
    ])

    combos_map = {
        'Burger Menu Combo': [c_burgers, c_drinks],
        'Sushi Lunch Combo': [c_sushi, c_drinks],
        'Pasta Lunch Combo': [c_pasta, c_drinks],
        'Dessert & Hot Drink Combo': [c_desserts, c_drinks],
    }

    for prod_name, combo_list in combos_map.items():
        template = ProductTemplate.search([('name', '=', prod_name)], limit=1)
        if template:
            try:
                template.write({
                    'type': 'combo',
                    'combo_ids': [Command.set([c.id for c in combo_list])],
                    'available_in_pos': True,
                })
            except Exception as e:
                _logger.warning("Could not configure combo product %s: %s", prod_name, e)


def _load_product_images(env, replace_placeholders=False):
    """
    Attaches high-resolution product images to food, drink, and dessert products.
    Replaces missing images and outline placeholder icons, and optionally upgrades
    legacy reused product photos during migrations without overwriting custom images.
    """
    ProductTemplate = env['product.template'].sudo()
    IrAttachment = env['ir.attachment'].sudo()

    def get_image_bytes(filename):
        for base_dir in IMAGE_SEARCH_PATHS:
            full_path = os.path.join(base_dir, filename)
            if os.path.exists(full_path):
                try:
                    with open(full_path, 'rb') as f:
                        return f.read()
                except Exception:
                    pass
        return None

    def get_file_sha1(filename):
        data = get_image_bytes(filename)
        return hashlib.sha1(data).hexdigest() if data else None

    placeholder_hashes = {
        h for fname in LEGACY_PLACEHOLDER_IMAGES
        if (h := get_file_sha1(fname))
    }
    placeholder_hashes.update({
        'ed345d90cf7a5246fec80d9656351666e6a3f6a4',  # pastries-icon.png
        'c2232be8ab8840c29a0a144ab7fdd459abe4320f',  # soft-drink-icon.png
    })

    legacy_reused_known_hashes = {
        'Double Chocolate Chip Cookie': '82100d0a73780e6ba3e45712763108b48a61b658',  # product_blueberry_muffin.png
        'Vanilla Bean Ice Cream Sundae': '3bbd34cf004ebeeeacbb9da67c4d9b444d300183',  # th-milkshake_banana.png
        'New York Cheesecake': 'f66573e2f158a333c2871a5b8f18e7940e140a0f',  # product_pecan_pie.png
    }

    for prod_name, img_filename in PRODUCT_IMAGE_MAP.items():
        tmpl = ProductTemplate.search([('name', '=', prod_name)], limit=1)
        if not tmpl:
            continue

        img_bytes = get_image_bytes(img_filename)
        if not img_bytes:
            continue

        target_sha1 = hashlib.sha1(img_bytes).hexdigest()
        should_write = False

        att = IrAttachment.search([
            ('res_model', '=', 'product.template'),
            ('res_id', '=', tmpl.id),
            ('res_field', '=', 'image_1920'),
        ], limit=1)

        current_sha1 = att.checksum if (att and att.checksum) else None
        if not current_sha1 and tmpl.image_1920:
            try:
                current_sha1 = hashlib.sha1(base64.b64decode(tmpl.image_1920)).hexdigest()
            except Exception:
                current_sha1 = None

        if not current_sha1:
            should_write = True
        elif current_sha1 != target_sha1:
            if current_sha1 in placeholder_hashes:
                should_write = True
            elif replace_placeholders and prod_name in LEGACY_REUSED_IMAGES:
                legacy_hashes = {legacy_reused_known_hashes.get(prod_name)}
                legacy_sha1 = get_file_sha1(LEGACY_REUSED_IMAGES[prod_name])
                if legacy_sha1:
                    legacy_hashes.add(legacy_sha1)
                if current_sha1 in legacy_hashes:
                    should_write = True

        if should_write:
            try:
                tmpl.write({'image_1920': base64.b64encode(img_bytes).decode('utf-8')})
            except Exception as e:
                _logger.warning("Could not set image on %s: %s", prod_name, e)


def _pre_bind_existing_records(env):
    """
    Maps existing records to their XML IDs in ir.model.data to ensure
    convert_file performs updates instead of duplicate inserts.
    """
    def bind_xml(model, xml_name, domain):
        if model not in env:
            return
        rec = env[model].sudo().search(domain, limit=1)
        if rec:
            xdata = env['ir.model.data'].sudo().search([
                ('module', '=', 'hudson_pos_demo_data'),
                ('name', '=', xml_name),
            ], limit=1)
            if not xdata:
                env['ir.model.data'].sudo().create({
                    'module': 'hudson_pos_demo_data',
                    'name': xml_name,
                    'model': model,
                    'res_id': rec.id,
                    'noupdate': True,
                })

    categories = [
        ('pos_category_food', 'Food'),
        ('pos_category_drinks', 'Drinks'),
        ('pos_category_desserts', 'Desserts'),
        ('pos_category_chocolates', 'Chocolates & Sweets'),
    ]
    for xname, cname in categories:
        bind_xml('pos.category', xname, [('name', '=', cname)])

    tags = [
        ('tag_chef_special', 'Chef Special'),
        ('tag_best_seller', 'Best Seller'),
        ('tag_vegetarian', 'Vegetarian'),
        ('tag_gluten_free', 'Gluten Free'),
        ('tag_organic', 'Organic'),
        ('tag_new', 'New'),
    ]
    for xname, tname in tags:
        bind_xml('product.tag', xname, [('name', '=', tname)])

    courses = [
        ('course_starter', 'Starter'),
        ('course_main', 'Main Course'),
        ('course_dessert', 'Dessert'),
        ('course_drinks', 'Drinks'),
    ]
    for xname, cname in courses:
        bind_xml('pos.course', xname, [('name', '=', cname)])

    notes = [
        ('note_extra_spicy', 'Extra Spicy 🌶️'),
        ('note_less_sugar', 'Less Sugar 🍯'),
        ('note_no_ice', 'No Ice 🧊'),
        ('note_gluten_free', 'Gluten Free 🌾'),
        ('note_nut_allergy', 'Nut Allergy Warning 🥜'),
        ('note_takeaway', 'Pack for Takeaway 🥡'),
    ]
    for xname, nname in notes:
        bind_xml('pos.note', xname, [('name', '=', nname)])

    floors = [
        ('floor_main', 'Main Floor'),
        ('floor_patio', 'Patio'),
    ]
    for xname, fname in floors:
        bind_xml('restaurant.floor', xname, [('name', '=', fname)])

    programs = [
        ('loyalty_program_gift_card', 'Gift Cards'),
        ('loyalty_program_ewallet', 'eWallet'),
        ('loyalty_program_happy_hour', 'Happy Hour — 15% Off All Orders'),
        ('loyalty_program_welcome_discount', 'Welcome Discount — 10% Off First Order'),
        ('loyalty_program_weekend_special', 'Weekend Special — 20% Off Beverages'),
        ('loyalty_program_points', 'RestoCafe Loyalty Points'),
        ('loyalty_program_family_combo', 'Family Combo — 20% Off Orders Above ₹500'),
        ('loyalty_program_coupons', 'Seasonal Discount Coupons — 15% Off'),
        ('loyalty_program_promo_discount10', 'Discount Code: DISCOUNT10 — 10% Off Order'),
        ('loyalty_program_promo_burger20', 'Discount Code: BURGER20 — 20% Off Burgers'),
        ('loyalty_program_buy_x_get_y_burger', 'Buy 2 Burgers, Get 1 Soft Drink Free'),
        ('loyalty_program_buy_x_get_y_coffee', 'Buy 2 Hot Drinks, Get 1 Cookie Free'),
        ('loyalty_program_next_order_coupons', 'Spend ₹500, Get 15% Off Next Order'),
    ]
    for xname, pname in programs:
        bind_xml('loyalty.program', xname, [('name', '=', pname)])


def _post_process_pos_configs(env, pos_config_ids=None):
    """
    Links loaded demo floors, pricelists, presets, booking, kiosk, tips,
    and category restrictions to POS configs.
    """
    PosConfig = env['pos.config'].sudo()
    configs = PosConfig.browse(pos_config_ids) if pos_config_ids else PosConfig.search([])

    floors = env['restaurant.floor'].sudo().search([('name', 'in', ['Main Floor', 'Patio'])])         if 'restaurant.floor' in env else []
    pricelists = env['product.pricelist'].sudo().search([('name', 'in', ['Happy Hour (20% Off)', 'VIP Member (15% Off)'])])
    loyalty_progs = env['loyalty.program'].sudo().search([]) if 'loyalty.program' in env else []
    demo_cats = env['pos.category'].sudo().search([('name', 'in', ['Food', 'Drinks', 'Desserts', 'Chocolates & Sweets'])])

    # Presets (Dine In, Takeout, Delivery)
    presets = env['pos.preset'].sudo().search([]) if 'pos.preset' in env else False

    # Table Booking appointment type
    app_type = env['appointment.type'].sudo().search([('name', '=', 'Table Booking')], limit=1) if 'appointment.type' in env else False

    # Tip Product (reuse core Odoo POS Tips product first to avoid duplicates)
    tip_prod = env.ref('point_of_sale.product_product_tip', raise_if_not_found=False)
    if tip_prod:
        if not tip_prod.active:
            tip_prod.sudo().write({'active': True})
    else:
        tip_prod = env['product.product'].sudo().with_context(active_test=False).search([('name', '=', 'Tips')], limit=1)
        if tip_prod and not tip_prod.active:
            tip_prod.sudo().write({'active': True})
    if not tip_prod and 'product.product' in env:
        try:
            tip_prod = env['product.product'].sudo().create({
                'name': 'Tips',
                'type': 'service',
                'available_in_pos': True,
                'list_price': 0.0,
            })
        except Exception:
            pass

    for config in configs:
        is_restaurant = any(kw in config.name.lower() for kw in ['resto', 'restau', 'bar', 'ousu'])

        vals = {}
        if not config.current_session_id:
            if is_restaurant:
                vals['module_pos_restaurant'] = True
                if hasattr(config, 'default_screen'):
                    vals['default_screen'] = 'tables'
                if floors:
                    vals['floor_ids'] = [Command.set(floors.ids)]
            else:
                vals['module_pos_restaurant'] = False
                if hasattr(config, 'default_screen'):
                    vals['default_screen'] = 'register'

        # Pricelists
        if pricelists:
            valid_pricelists = pricelists.filtered(lambda p: not p.currency_id or p.currency_id == config.currency_id)
            if valid_pricelists:
                group_pricelist = env.ref('product.group_product_pricelist', raise_if_not_found=False)
                group_user = env.ref('base.group_user', raise_if_not_found=False)
                if group_pricelist and group_user and group_pricelist not in group_user.sudo().all_implied_ids:
                    group_user.sudo()._apply_group(group_pricelist)
                env['res.company'].sudo()._activate_or_create_pricelists()

                vals['use_pricelist'] = True
                vals['available_pricelist_ids'] = [Command.link(p.id) for p in valid_pricelists]
                default_pl = env['product.pricelist'].sudo().search([
                    ('company_id', 'in', [config.company_id.id, False]),
                    ('currency_id', '=', config.currency_id.id),
                    ('item_ids', '=', False),
                ], order='sequence asc, id asc', limit=1) or env['product.pricelist'].sudo().search([
                    ('name', '=', 'Default'),
                    ('company_id', 'in', [config.company_id.id, False]),
                    ('currency_id', '=', config.currency_id.id),
                ], limit=1) or valid_pricelists[:1]
                if default_pl:
                    vals['available_pricelist_ids'].append(Command.link(default_pl.id))
                    if not config.pricelist_id:
                        vals['pricelist_id'] = default_pl.id

        # 1. Take out / Delivery / Presets
        if hasattr(config, 'use_presets') and presets:
            vals['use_presets'] = True
            vals['available_preset_ids'] = [Command.set(presets.ids)]
            if is_restaurant:
                vals['default_preset_id'] = presets[0].id
            elif len(presets) > 1:
                vals['default_preset_id'] = presets[1].id

        # 2. Table Booking (Reservations)
        if is_restaurant and hasattr(config, 'use_booking') and app_type:
            vals['module_pos_appointment'] = True
            vals['use_booking'] = True
            vals['booking_appointment_type_id'] = app_type.id
            if hasattr(config, 'booking_no_show_grace_minutes'):
                vals['booking_no_show_grace_minutes'] = 15

        # 3. Mobile self-order & Kiosk
        if hasattr(config, 'self_ordering_mode'):
            if is_restaurant:
                vals['self_ordering_mode'] = 'mobile'
                vals['self_ordering_service_mode'] = 'table'
            else:
                vals['self_ordering_mode'] = 'kiosk'
                vals['self_ordering_service_mode'] = 'counter'
            if hasattr(config, 'self_ordering_pay_after'):
                vals['self_ordering_pay_after'] = 'meal'

        # 4. Tips configuration
        if hasattr(config, 'iface_tipproduct') and tip_prod:
            vals['iface_tipproduct'] = True
            vals['tip_product_id'] = tip_prod.id
            if hasattr(config, 'set_tip_after_payment'):
                vals['set_tip_after_payment'] = True
            if hasattr(config, 'tip_percentage_1'):
                vals['tip_percentage_1'] = 5
                vals['tip_percentage_2'] = 10
                vals['tip_percentage_3'] = 15

        # 5. Restrict categories
        if hasattr(config, 'limit_categories') and demo_cats:
            vals['limit_categories'] = True
            vals['iface_available_categ_ids'] = [Command.set(demo_cats.ids)]
            if hasattr(config, 'show_category_images'):
                vals['show_category_images'] = True

        try:
            config.write(vals)
            _logger.info("Hudson POS: Successfully configured all advanced options on POS '%s'", config.name)
        except Exception as e:
            _logger.warning("Could not update POS config %s: %s", config.name, e)

    # Link only valid loyalty programs (that have valid rewards) to active POS configs
    # Unlink any program without rewards to avoid JS ControlButtons crash
    if loyalty_progs:
        for prog in loyalty_progs:
            try:
                if prog.reward_ids:
                    prog.write({'pos_config_ids': [Command.set(configs.ids)]})
                else:
                    prog.write({'pos_config_ids': [Command.clear()]})
            except Exception:
                pass


def _configure_loyalty_demo_data(env):
    """
    Sets up complete, rich demo data for all 6 loyalty program types (+ Gift Card & eWallet):
    1. Coupons (coupons): Seasonal coupons with pre-generated codes COUPON15, BURGER50, FESTIVE20
    2. Loyalty Cards (loyalty): RestoCafe VIP Club with 3 reward tiers (5%, 10%, Free Lava Cake) and demo card VIP-CLUB-1001 with 150 points
    3. Promotions (promotion): Happy Hour, Welcome, Weekend, Family Combo
    4. Discount Code (promo_code): DISCOUNT10 (10% off order) and BURGER20 (20% off burgers)
    5. Buy X Get Y (buy_x_get_y): Buy 2 Burgers Get 1 Soft Drink Free, Buy 2 Hot Drinks Get 1 Cookie Free
    6. Next Order Coupons (next_order_coupons): Spend ₹500 Get 15% Off Next Order with demo card NEXTVISIT15
    7. Gift Cards (gift_card): Demo card GIFTCARD-100 (₹100 balance)
    8. eWallet (ewallet): Demo card EWALLET-500 (₹500 balance)
    """
    if 'loyalty.program' not in env:
        return

    LoyaltyProgram = env['loyalty.program'].sudo()
    LoyaltyCard = env['loyalty.card'].sudo()
    LoyaltyHistory = env['loyalty.history'].sudo() if 'loyalty.history' in env else False
    Product = env['product.product'].sudo()

    # Find products for rules and rewards
    bacon_burger = Product.search([('name', '=', 'Bacon Burger')], limit=1)
    cheese_burger = Product.search([('name', '=', 'Cheese Burger')], limit=1)
    coke = Product.search([('name', '=', 'Coca-Cola')], limit=1)
    espresso = Product.search([('name', '=', 'Espresso')], limit=1)
    green_tea = Product.search([('name', '=', 'Green Tea')], limit=1)
    ice_tea = Product.search([('name', '=', 'Ice Tea')], limit=1)
    cookie = Product.search([('name', '=', 'Double Chocolate Chip Cookie')], limit=1)
    cake = Product.search([('name', '=', 'Chocolate Lava Cake')], limit=1)

    burger_ids = [p.id for p in [bacon_burger, cheese_burger] if p]
    hot_drink_ids = [p.id for p in [espresso, green_tea, ice_tea] if p]

    def ensure_card(program, code, points, description='Demo Card', partner=False):
        if not program or not code:
            return
        card = False
        if partner and program.program_type == 'loyalty':
            card = LoyaltyCard.search([('program_id', '=', program.id), ('partner_id', '=', partner.id)], limit=1)
        if not card:
            card = LoyaltyCard.search([('code', '=', code)], limit=1)
        if not card:
            card = LoyaltyCard.create({
                'program_id': program.id,
                'code': code,
                'partner_id': partner.id if partner else False,
            })
        if card and points > card.points and 'loyalty.history' in env:
            diff = points - card.points
            env['loyalty.history'].sudo().create({
                'card_id': card.id,
                'description': description,
                'issued': diff,
            })
        return card

    # 1. Buy X Get Y: Burgers -> Soft Drink Free
    p_bxy_burger = LoyaltyProgram.search([('name', '=', 'Buy 2 Burgers, Get 1 Soft Drink Free')], limit=1)
    if not p_bxy_burger:
        p_bxy_burger = LoyaltyProgram.create({
            'name': 'Buy 2 Burgers, Get 1 Soft Drink Free',
            'program_type': 'buy_x_get_y',
            'trigger': 'auto',
            'applies_on': 'current',
            'portal_point_name': 'Credit(s)',
        })
    if p_bxy_burger:
        if not p_bxy_burger.rule_ids and burger_ids:
            p_bxy_burger.write({
                'rule_ids': [Command.create({
                    'reward_point_mode': 'unit',
                    'reward_point_amount': 1,
                    'minimum_qty': 2,
                    'product_ids': [Command.set(burger_ids)],
                })]
            })
        elif p_bxy_burger.rule_ids and burger_ids:
            p_bxy_burger.rule_ids[0].write({
                'reward_point_mode': 'unit',
                'reward_point_amount': 1,
                'minimum_qty': 2,
                'product_ids': [Command.set(burger_ids)],
            })
        if not p_bxy_burger.reward_ids and coke:
            p_bxy_burger.write({
                'reward_ids': [Command.create({
                    'reward_type': 'product',
                    'reward_product_id': coke.id,
                    'reward_product_qty': 1,
                    'required_points': 2,
                    'description': 'Free Coca-Cola with 2 Burgers',
                })]
            })
        elif p_bxy_burger.reward_ids and coke:
            p_bxy_burger.reward_ids[0].write({
                'reward_type': 'product',
                'reward_product_id': coke.id,
                'reward_product_qty': 1,
                'required_points': 2,
                'description': 'Free Coca-Cola with 2 Burgers',
            })

    # 2. Buy X Get Y: Hot Drinks -> Cookie Free
    p_bxy_coffee = LoyaltyProgram.search([('name', '=', 'Buy 2 Hot Drinks, Get 1 Cookie Free')], limit=1)
    if not p_bxy_coffee:
        p_bxy_coffee = LoyaltyProgram.create({
            'name': 'Buy 2 Hot Drinks, Get 1 Cookie Free',
            'program_type': 'buy_x_get_y',
            'trigger': 'auto',
            'applies_on': 'current',
            'portal_point_name': 'Credit(s)',
        })
    if p_bxy_coffee:
        if not p_bxy_coffee.rule_ids and hot_drink_ids:
            p_bxy_coffee.write({
                'rule_ids': [Command.create({
                    'reward_point_mode': 'unit',
                    'reward_point_amount': 1,
                    'minimum_qty': 2,
                    'product_ids': [Command.set(hot_drink_ids)],
                })]
            })
        elif p_bxy_coffee.rule_ids and hot_drink_ids:
            p_bxy_coffee.rule_ids[0].write({
                'reward_point_mode': 'unit',
                'reward_point_amount': 1,
                'minimum_qty': 2,
                'product_ids': [Command.set(hot_drink_ids)],
            })
        if not p_bxy_coffee.reward_ids and cookie:
            p_bxy_coffee.write({
                'reward_ids': [Command.create({
                    'reward_type': 'product',
                    'reward_product_id': cookie.id,
                    'reward_product_qty': 1,
                    'required_points': 2,
                    'description': 'Free Cookie with 2 Hot Drinks',
                })]
            })
        elif p_bxy_coffee.reward_ids and cookie:
            p_bxy_coffee.reward_ids[0].write({
                'reward_type': 'product',
                'reward_product_id': cookie.id,
                'reward_product_qty': 1,
                'required_points': 2,
                'description': 'Free Cookie with 2 Hot Drinks',
            })

    # 3. Discount Code: BURGER20 - link to burger products
    p_burger20 = LoyaltyProgram.search([('name', '=', 'Discount Code: BURGER20 — 20% Off Burgers')], limit=1)
    if p_burger20 and burger_ids:
        if p_burger20.rule_ids:
            p_burger20.rule_ids[0].write({'product_ids': [Command.set(burger_ids)]})
        if p_burger20.reward_ids:
            p_burger20.reward_ids[0].write({
                'discount_applicability': 'specific',
                'discount_product_ids': [Command.set(burger_ids)],
            })

    # 4. Loyalty Points: Add Tier 3 free dessert reward
    p_loyalty = LoyaltyProgram.search([('program_type', '=', 'loyalty')], limit=1)
    if p_loyalty and cake:
        free_cake_reward = p_loyalty.reward_ids.filtered(lambda r: r.reward_type == 'product')
        if not free_cake_reward:
            p_loyalty.write({
                'reward_ids': [Command.create({
                    'reward_type': 'product',
                    'reward_product_id': cake.id,
                    'reward_product_qty': 1,
                    'required_points': 150,
                    'description': 'Free Chocolate Lava Cake for 150 Points',
                })]
            })

    # 5. Pre-generate active demo cards for all programs
    p_coupon = LoyaltyProgram.search([('name', '=', 'Seasonal Discount Coupons — 15% Off')], limit=1)
    if p_coupon:
        ensure_card(p_coupon, 'COUPON15', 1, 'Seasonal 15% Off Coupon')
        ensure_card(p_coupon, 'BURGER50', 1, 'Burger Season Coupon')
        ensure_card(p_coupon, 'FESTIVE20', 1, 'Festive Celebration Coupon')

    p_next = LoyaltyProgram.search([('name', '=', 'Spend ₹500, Get 15% Off Next Order')], limit=1)
    if p_next:
        ensure_card(p_next, 'NEXTVISIT15', 1, 'Next Visit 15% Off Coupon')

    # Dedicated demo VIP partner for loyalty card testing
    vip_partner = env['res.partner'].sudo().search([('name', '=', 'VIP Customer (Demo)')], limit=1)
    if not vip_partner:
        vip_partner = env['res.partner'].sudo().create({
            'name': 'VIP Customer (Demo)',
            'email': 'vip.demo@example.com',
            'phone': '+91 98470 99999',
            'customer_rank': 1,
        })

    if p_loyalty:
        ensure_card(p_loyalty, 'VIP-CLUB-1001', 150, 'RestoCafe VIP Demo Card', partner=vip_partner)

    p_gc = LoyaltyProgram.search([('program_type', '=', 'gift_card')], limit=1)
    if p_gc:
        ensure_card(p_gc, 'GIFTCARD-100', 100, 'Demo Gift Card ₹100')

    p_ew = LoyaltyProgram.search([('program_type', '=', 'ewallet')], limit=1)
    if p_ew:
        ensure_card(p_ew, 'EWALLET-500', 500, 'Demo eWallet ₹500', partner=vip_partner)

    _logger.info("Hudson POS: Successfully configured rich demo data for all 6 Loyalty & Discount program types.")


def _load_stock_inventory(env):
    """
    Ensures POS storable products have positive inventory on hand in the main internal stock location.
    """
    StockLocation = env['stock.location'].sudo()
    StockQuant = env['stock.quant'].sudo()
    ProductProduct = env['product.product'].sudo()

    stock_location = StockLocation.search([
        ('usage', '=', 'internal'),
        ('company_id', 'in', [env.company.id, False])
    ], order='id asc', limit=1)

    if not stock_location:
        return

    pos_products = ProductProduct.search([
        ('available_in_pos', '=', True),
        ('is_storable', '=', True),
    ])
    # never change the stock of products that existed before this install run (user data)
    pos_products -= preexisting(pos_products)

    target_qty = 100.0
    for prod in pos_products:
        quant = StockQuant.search([
            ('product_id', '=', prod.id),
            ('location_id', '=', stock_location.id)
        ], limit=1)

        current_qty = quant.quantity if quant else 0.0
        if current_qty < 20.0:
            diff = target_qty - current_qty
            try:
                StockQuant._update_available_quantity(prod, stock_location, diff)
            except Exception:
                pass


def _load_recruitment_demo_data(env):
    """
    Ensures Restaurant & Cafe recruitment job openings are active, published to the website,
    and populated with sample applicants across hiring pipeline stages.
    """
    _logger.info("Hudson POS: Verifying recruitment demo data and website job publishing...")

    if 'hr.job' not in env:
        _logger.warning("Hudson POS: hr.job model not available, skipping recruitment demo data.")
        return

    HrJob = env['hr.job'].sudo()
    demo_job_xml_ids = [
        'job_resto_chef',
        'job_resto_supervisor',
        'job_barista',
        'job_service_captain',
    ]

    for xml_id in demo_job_xml_ids:
        job = env.ref(f'hudson_pos_demo_data.{xml_id}', raise_if_not_found=False)
        if job and job.exists():
            write_vals = {}
            if hasattr(job, 'is_published') and not job.is_published:
                write_vals['is_published'] = True
            if hasattr(job, 'website_published') and not job.website_published:
                write_vals['website_published'] = True
            if hasattr(job, 'active') and not job.active:
                write_vals['active'] = True
            if write_vals:
                try:
                    job.write(write_vals)
                except Exception as e:
                    _logger.warning("Could not set published state for job %s: %s", job.name, e)

    _logger.info("Hudson POS: Recruitment demo data published to website successfully.")


def _load_kitchen_display_demo_data(env):
    """
    Deprecated no-op: Kitchen Display demo configurations were removed from
    hudson_pos_demo_data. A single editable default Kitchen Display is now
    created on install by hudson_kitchen_display.
    """
    _logger.info("Hudson POS: Kitchen Display demo data disabled (handled by hudson_kitchen_display).")
    return []


def _load_sample_pos_orders(env):
    """
    Creates sample closed POS orders to demonstrate the reporting and order history
    for the Restaurant POS. Orders are created in 'done' state without opening a session.
    """
    _logger.info("Hudson POS: Creating sample POS orders...")

    if 'pos.order' not in env:
        _logger.warning("Hudson POS: pos.order model not available. Skipping sample orders.")
        return

    PosConfig = env['pos.config'].sudo()
    PosOrder = env['pos.order'].sudo()
    PosSession = env['pos.session'].sudo()
    ProductProduct = env['product.product'].sudo()

    # Only create if no orders exist yet
    existing_orders = PosOrder.search([], limit=1)
    if existing_orders:
        _logger.info("Hudson POS: POS orders already exist, skipping sample order creation.")
        return

    # Get the Restaurant POS config
    resto_config = PosConfig.search([('name', '=', 'Restaurant')], limit=1)
    if not resto_config:
        _logger.warning("Hudson POS: Restaurant POS config not found. Skipping sample orders.")
        return

    # We need a session to create orders - create a rescue/demo session
    # Check if there's an open session
    open_session = PosSession.search([
        ('config_id', '=', resto_config.id),
        ('state', 'in', ['opening_control', 'opened']),
    ], limit=1)

    if open_session:
        _logger.info("Hudson POS: POS session already open, skipping sample orders to avoid conflicts.")
        return

    # Get sample products
    def find_product(name):
        prod = ProductProduct.search([('name', '=', name), ('available_in_pos', '=', True)], limit=1)
        return prod

    sample_order_defs = [
        {
            'xml_id': 'sample_order_table1_dinner',
            'name': 'Table 01 — Dinner',
            'lines': [
                ('Cheese Burger', 2, 320.0),
                ('Coca-Cola', 2, 65.0),
                ('Warm Apple Pie', 1, 180.0),
            ],
        },
        {
            'xml_id': 'sample_order_table2_lunch',
            'name': 'Table 02 — Lunch',
            'lines': [
                ('Pasta Bolognese', 2, 290.0),
                ('Fanta', 2, 60.0),
            ],
        },
        {
            'xml_id': 'sample_order_table3_breakfast',
            'name': 'Table 03 — Cafe Order',
            'lines': [
                ('Espresso', 2, 85.0),
                ('Artisan Chocolate Croissant', 2, 120.0),
            ],
        },
        {
            'xml_id': 'sample_order_table4_sushi',
            'name': 'Table 04 — Special',
            'lines': [
                ('Lunch Maki 18pc', 1, 450.0),
                ('Green Tea', 2, 75.0),
                ('New York Cheesecake', 2, 220.0),
            ],
        },
        {
            'xml_id': 'sample_order_table5_pizza',
            'name': 'Table 05 — Evening',
            'lines': [
                ('Pizza Margherita', 1, 380.0),
                ('Milkshake Banana', 1, 150.0),
                ('Tiramisu', 1, 190.0),
            ],
        },
    ]

    # Try to create a temporary session to place orders
    try:
        from datetime import datetime, timedelta

        # Create session directly
        session = PosSession.create({'config_id': resto_config.id})

        # Set state to 'opened' directly (safe for demo data initialization)
        session.write({
            'state': 'opened',
            'start_at': datetime.now() - timedelta(days=1),
        })

        base_date = datetime.now() - timedelta(days=1)
        created_count = 0

        for i, order_def in enumerate(sample_order_defs):
            # Check if already created via ir.model.data
            existing = env.ref(
                f"hudson_pos_demo_data.{order_def['xml_id']}",
                raise_if_not_found=False
            )
            if existing and existing.exists():
                continue

            order_lines = []
            total = 0.0
            for prod_name, qty, price in order_def['lines']:
                prod = find_product(prod_name)
                if not prod:
                    _logger.warning("Hudson POS: Product not found: %s", prod_name)
                    continue
                subtotal = qty * price
                total += subtotal
                order_lines.append((0, 0, {
                    'product_id': prod.id,
                    'qty': qty,
                    'price_unit': price,
                    'price_subtotal': subtotal,
                    'price_subtotal_incl': subtotal,
                }))

            if not order_lines:
                continue

            order_date = base_date - timedelta(hours=i * 2)

            try:
                order = PosOrder.create({
                    'name': order_def['name'],
                    'session_id': session.id,
                    'config_id': resto_config.id,
                    'date_order': order_date,
                    'lines': order_lines,
                    'state': 'paid',
                    'amount_total': total,
                    'amount_paid': total,
                    'amount_tax': 0.0,
                    'amount_return': 0.0,
                })

                # Register in ir.model.data
                env['ir.model.data'].sudo().create({
                    'module': 'hudson_pos_demo_data',
                    'name': order_def['xml_id'],
                    'model': 'pos.order',
                    'res_id': order.id,
                    'noupdate': True,
                })
                created_count += 1
                _logger.info("Hudson POS: Created sample order '%s' (total=%.2f)", order_def['name'], total)

            except Exception as e:
                _logger.warning("Hudson POS: Could not create sample order '%s': %s", order_def['name'], e)

        # Close the session cleanly
        try:
            session.write({'state': 'closed', 'stop_at': datetime.now()})
        except Exception as e:
            _logger.warning("Hudson POS: Could not close demo session: %s", e)

        _logger.info("Hudson POS: Created %d sample POS orders successfully.", created_count)

    except Exception as e:
        _logger.error("Hudson POS: Failed to create sample POS session/orders: %s", e)
        import traceback
        _logger.error(traceback.format_exc())


def clear_pos_demo_data(env):
    """
    Cleanly clears demo data records created under hudson_pos_demo_data.
    """
    _logger.info("Hudson POS: Starting safe demo data cleanup...")

    # 0. First, clear HINV- Inventory Suite (BoMs, Reordering Rules, POs, Transfers, Ingredients, Packaging, Locations, Vendors)
    # Existing Restaurant & Cafe POS products are preserved cleanly by clear_inventory_suite_demo_data.
    try:
        from .demo_inventory_suite import clear_inventory_suite_demo_data
        clear_inventory_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not clear Inventory suite demo data: %s", e)

    # 1. Next, clear Business Suite (Sales, Purchase, MRP, Events, Maintenance, Survey)
    # This cleanly removes orders/BOMs referencing demo products before product deletion.
    try:
        from .demo_business_suite import clear_business_suite_demo_data
        clear_business_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not clear Business suite demo data: %s", e)

    # 2. Clear sample POS orders and combo items referencing demo products
    try:
        with env.cr.savepoint():
            demo_imd_orders = env['ir.model.data'].sudo().search([
                ('module', '=', 'hudson_pos_demo_data'),
                ('model', '=', 'pos.order'),
            ])
            order_ids = [d.res_id for d in demo_imd_orders]
            demo_orders = env['pos.order'].sudo().browse(order_ids).exists() if order_ids else env['pos.order'].sudo()
            sample_orders = demo_orders | env['pos.order'].sudo().search([
                ('pos_reference', 'like', 'Order 00001-')
            ])
            if sample_orders:
                non_cancelled = sample_orders.filtered(lambda o: o.state not in ('draft', 'cancel'))
                if non_cancelled:
                    non_cancelled.write({'state': 'cancel'})
                sample_orders.mapped('lines').unlink()
                sample_orders.unlink()
    except Exception as e:
        _logger.warning("Could not unlink sample POS orders: %s", e)

    try:
        with env.cr.savepoint():
            demo_imd_tmpls = env['ir.model.data'].sudo().search([
                ('module', '=', 'hudson_pos_demo_data'),
                ('model', '=', 'product.template')
            ])
            tmpl_ids = [d.res_id for d in demo_imd_tmpls]
            if tmpl_ids and 'product.combo.item' in env:
                variants = env['product.product'].sudo().search([('product_tmpl_id', 'in', tmpl_ids)])
                if variants:
                    combo_items = env['product.combo.item'].sudo().search([('product_id', 'in', variants.ids)])
                    combos = combo_items.mapped('combo_id')
                    combo_items.unlink()
                    empty_demo_combos = combos.filtered(
                        lambda c: not c.combo_item_ids and c.name in [
                            'Burgers', 'Drinks', 'Sushi Choices', 'Pasta Choices', 'Dessert Choices'
                        ]
                    )
                    if empty_demo_combos:
                        empty_demo_combos.unlink()
    except Exception as e:
        _logger.warning("Could not unlink demo combo items: %s", e)

    # 3. Clear HR Suite (Payroll, Leaves, Attendance, Fleet, Lunch, Expenses, Employees)
    try:
        from .demo_hr_suite import clear_hr_suite_demo_data
        clear_hr_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not clear HR suite demo data: %s", e)

    # 4. Clear stock quants
    try:
        with env.cr.savepoint():
            demo_imd_tmpls = env['ir.model.data'].sudo().search([
                ('module', '=', 'hudson_pos_demo_data'),
                ('model', '=', 'product.template')
            ])
            tmpl_ids = [d.res_id for d in demo_imd_tmpls]
            if tmpl_ids:
                variants = env['product.product'].sudo().search([('product_tmpl_id', 'in', tmpl_ids)])
                if variants:
                    quants = env['stock.quant'].sudo().search([('product_id', 'in', variants.ids)])
                    if quants:
                        quants.unlink()
    except Exception as e:
        _logger.warning("Could not unlink quants: %s", e)

    # 4b. Cleanup demo loyalty cards
    if 'loyalty.card' in env:
        try:
            with env.cr.savepoint():
                demo_codes = ['COUPON15', 'BURGER50', 'FESTIVE20', 'NEXTVISIT15', 'VIP-CLUB-1001', 'GIFTCARD-100', 'EWALLET-500']
                env['loyalty.card'].sudo().search([('code', 'in', demo_codes)]).unlink()
        except Exception:
            pass

    # 5. Ordered removal of XML demo records
    models_order = [
        'hr.applicant',
        'hr.job',
        'hr.department',
        'slide.slide',
        'slide.channel',
        'pos.order',
        'pos.prep.display',
        'product.combo',
        'restaurant.table',
        'restaurant.floor',
        'product.template',
        'pos.category',
        'pos.course',
        'pos.note',
        'product.tag',
        'product.pricelist',
        'loyalty.program',
    ]

    for model_name in models_order:
        data_records = env['ir.model.data'].sudo().search([
            ('module', '=', 'hudson_pos_demo_data'),
            ('model', '=', model_name)
        ])
        for data in data_records:
            try:
                with env.cr.savepoint():
                    rec = env[model_name].sudo().browse(data.res_id)
                    if rec.exists():
                        rec.unlink()
            except Exception:
                try:
                    with env.cr.savepoint():
                        rec = env[model_name].sudo().browse(data.res_id)
                        if rec.exists() and hasattr(rec, 'active'):
                            rec.write({'active': False})
                        if rec.exists() and hasattr(rec, 'available_in_pos'):
                            rec.write({'available_in_pos': False})
                except Exception:
                    pass

        try:
            with env.cr.savepoint():
                data_records.unlink()
        except Exception:
            pass

    # 6. Ensure remaining POS configs do not retain missing/empty pricelist state
    try:
        with env.cr.savepoint():
            for cfg in env['pos.config'].sudo().search([('use_pricelist', '=', True)]):
                if not cfg.pricelist_id or not cfg.pricelist_id.active:
                    fallback_pl = env['product.pricelist'].sudo().search([
                        ('company_id', 'in', [cfg.company_id.id, False]),
                        ('currency_id', '=', cfg.currency_id.id),
                    ], order='sequence asc, id asc', limit=1)
                    if fallback_pl:
                        write_pl = {'pricelist_id': fallback_pl.id}
                        if fallback_pl not in cfg.available_pricelist_ids:
                            write_pl['available_pricelist_ids'] = [Command.link(fallback_pl.id)]
                        cfg.write(write_pl)
                    else:
                        cfg.write({'use_pricelist': False, 'pricelist_id': False})
    except Exception as e:
        _logger.warning("Could not sanitize POS pricelists after demo cleanup: %s", e)

    _logger.info("Hudson POS: Demo data cleared safely.")
    return True
