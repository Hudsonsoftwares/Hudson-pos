# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.
"""Decorated restaurant floor plans for the POS demo (pos_restaurant floor plan editor format).

Each floor gets a designed layout, as if drawn in Point of Sale > Floor plan > Edit:

  Main Floor ("Resto Cafe - Main Dining", wooden floor)
    walls with the street entrance, door and welcome mat, reception desk, waiting lounge,
    open kitchen with pass counter, dessert display, coffee & mocktail bar with bar stools,
    window seats, red leather booths, a family dining area on a rug, the chef's table,
    restrooms, palms and zone labels; chairs drawn around every table.

  Patio ("Garden Patio", stone tiles)
    hedges, a fountain, parasols over the café tables, fairy lights, a live grill station,
    a fire-pit lounge, the door to the main dining room, rattan chairs around every table.

Format (see pos_restaurant/static/src/app/services/floor_plan): restaurant.floor.floor_plan_layout =
{bgColor, decorations: [...]}, restaurant.table.floor_plan_layout = {uuid, shape, left, top, width,
height, color}. Decorations are shapes ('rect', 'circle'), 'line', 'text' and 'image' (an image by
url; the illustrations are SVG files of this module: static/src/img/floor_plan). Decorations are
drawn below the tables, in list order.
"""
import hashlib
import logging
import math

_logger = logging.getLogger(__name__)

DATA_MODULE = 'hudson_pos_demo_data'
THEME_MODULE = 'hudson_pos_theme'
IMG = f'/{THEME_MODULE}/static/src/img/floor_plan'
ODOO_IMG = '/pos_restaurant/static/floor_plan'

WALL = '#4e342e'
CHAIR_MAIN = ('#8d6e63', '#5d4037')
CHAIR_PATIO = ('#c8a97e', '#8d6e63')


# --------------------------------------------------------------------------- element helpers
def _uuid(*parts):
    return hashlib.md5('/'.join(map(str, parts)).encode()).hexdigest()[:16]


def rect(key, left, top, width, height, color=None, opacity=1, border=None, border_width=0,
         radius=0, text=None, font=16, textcolor='#3e2723', bold=False, shape='rect', border_style='solid'):
    el = {'uuid': _uuid('rect', key), 'shape': shape, 'left': left, 'top': top, 'width': width, 'height': height,
          'roundedCorner': radius}
    if color:
        el.update(color=color, opacity=opacity)
    else:
        el['allowBackground'] = False
    if border:
        el.update(borderColor=border, borderWidth=border_width or 2, borderStyle=border_style)
    if text:
        el.update(text=text, fontSize=font, textcolor=textcolor, textAlign='center')
        if bold:
            el['fontWeight'] = 'bold'
    return el


def label(key, left, top, width, text, font=16, color='#3e2723', bold=True, italic=False):
    el = {'uuid': _uuid('text', key), 'shape': 'text', 'left': left, 'top': top, 'width': width,
          'height': int(font * 1.6), 'text': text, 'fontSize': font, 'textcolor': color,
          'textAlign': 'center', 'allowBackground': False, 'allowBorder': False}
    if bold:
        el['fontWeight'] = 'bold'
    if italic:
        el['fontStyle'] = 'italic'
    return el


def image(key, name, left, top, width, height, rotation=0, odoo=False):
    el = {
        'uuid': _uuid('img', key),
        'shape': 'image',
        'name': name,
        'url': f"{ODOO_IMG if odoo else IMG}/{name}",
        'left': left,
        'top': top,
        'width': width,
        'height': height,
        'allowText': False,
        'allowBorder': False,
        'allowBackground': False,
    }
    if rotation:
        el['rotation'] = rotation
    return el


def line(key, left, top, width, thickness=6, color='#ffca28', style='dotted', rotation=0):
    el = {'uuid': _uuid('line', key), 'shape': 'line', 'left': left, 'top': top, 'width': width,
          'height': thickness, 'color': color, 'style': style, 'rounded': True}
    if rotation:
        el['rotation'] = rotation
    return el


def wall(key, left, top, width, height):
    return rect(key, left, top, width, height, color=WALL, radius=3)


def chairs(key, table, colors, size=26):
    """Chairs around a table: (shape, left, top, width, height, seats)."""
    shape, left, top, width, height, seats = table
    fill, edge = colors
    out = []

    def chair(i, cx, cy):
        out.append(rect(f'{key}-chair-{i}', int(cx - size / 2), int(cy - size / 2), size, size,
                        color=fill, border=edge, border_width=2, radius=8,
                        shape='circle' if shape == 'circle' else 'rect'))

    cx, cy = left + width / 2, top + height / 2
    gap = size / 2 - 4  # chairs tucked slightly under the table edge
    if shape == 'circle' or (seats <= 2 and width == height):
        r = width / 2 + gap
        n = max(seats, 2)
        start = -90 if n != 2 else 180
        for i in range(n):
            a = math.radians(start + i * 360 / n)
            chair(i, cx + r * math.cos(a), cy + r * math.sin(a))
        return out
    if seats == 4 and abs(width - height) < 20:
        for i, (dx, dy) in enumerate(((0, -1), (1, 0), (0, 1), (-1, 0))):
            chair(i, cx + dx * (width / 2 + gap), cy + dy * (height / 2 + gap))
        return out
    # long table: chairs on both long sides, one at each end when seats allow
    ends = 2 if seats >= 6 else 0
    per_side = (seats - ends) // 2
    for side, y in enumerate((top - gap, top + height + gap)):
        for j in range(per_side):
            chair(f'{side}-{j}', left + width * (j + 1) / (per_side + 1), y)
    if ends:
        chair('end-l', left - gap, cy)
        chair('end-r', left + width + gap, cy)
    return out


# --------------------------------------------------------------------------- Main Floor
# table number -> (shape, left, top, width, height, seats, color)
MAIN_TABLES = {
    # window seats (2) along the front windows
    1: ('circle', 600, 70, 76, 76, 2, 'turquoise'),
    5: ('circle', 760, 70, 76, 76, 2, 'turquoise'),
    9: ('circle', 920, 70, 76, 76, 2, 'turquoise'),
    # red leather booths along the left wall
    2: ('rect', 64, 316, 124, 84, 4, 'red'),
    3: ('rect', 64, 486, 124, 84, 4, 'red'),
    # dining room on the rug
    6: ('square', 372, 300, 92, 92, 4, 'green'),
    7: ('square', 548, 300, 92, 92, 4, 'green'),
    10: ('square', 372, 470, 92, 92, 4, 'green'),
    11: ('square', 548, 470, 92, 92, 4, 'green'),
    # family tables (6)
    4: ('rect', 728, 304, 176, 88, 6, 'orange'),
    8: ('rect', 728, 474, 176, 88, 6, 'orange'),
    # chef's table (8) next to the open kitchen
    12: ('oval', 100, 656, 210, 84, 8, 'purple'),
}
BOOTH_TABLES = (2, 3)


def _main_decorations():
    d = []
    # zones (drawn first, below everything)
    d.append(rect('main-kitchen-zone', 34, 34, 350, 220, color='#efe6da', border='#8d6e63', border_width=2, radius=6))
    d.append(rect('main-rug', 336, 270, 600, 330, color='#b5651d', opacity=0.16, border='#b5651d',
                  border_width=3, radius=28, border_style='dashed'))
    d.append(rect('main-restroom-zone', 1066, 594, 150, 150, color='#e3eef3', border='#90a4ae', border_width=2, radius=6))
    d.append(rect('main-lounge-zone', 356, 632, 192, 128, color='#efebe9', opacity=0.8, radius=10))
    d.append(rect('main-window', 560, 34, 480, 10, color='#81d4fa', opacity=0.9, radius=4))
    # walls, with the street entrance in the bottom wall (x 580..720)
    d += [
        wall('main-wall-top', 20, 20, 1210, 14),
        wall('main-wall-left', 20, 20, 14, 760),
        wall('main-wall-right', 1216, 20, 14, 760),
        wall('main-wall-bottom-l', 20, 766, 560, 14),
        wall('main-wall-bottom-r', 720, 766, 510, 14),
        wall('main-wall-kitchen', 34, 254, 260, 10),
        wall('main-wall-restroom', 1056, 594, 10, 150),
    ]
    # chairs (below the tables)
    for number, (shape, left, top, width, height, seats, _color) in MAIN_TABLES.items():
        if number in BOOTH_TABLES:
            continue
        d += chairs(f'main-{number}', (shape, left, top, width, height, seats), CHAIR_MAIN)
    # bar stools
    for i in range(6):
        d.append(rect(f'main-stool-{i}', 1036, 96 + i * 62, 32, 32, color='#3e2723', border='#c9a227',
                      border_width=2, shape='circle'))
    # furniture & illustrations
    d += [
        image('main-kitchen', 'kitchen_line.svg', 58, 56, 300, 140),
        image('main-dessert', 'dessert_display.svg', 402, 58, 140, 71),
        image('main-bar', 'bar_counter.svg', 1078, 64, 124, 400),
        image('main-reception', 'reception_desk.svg', 760, 644, 190, 105),
        image('main-lounge', 'lounge_set.svg', 362, 634, 180, 126),
        image('main-door', 'door.svg', 610, 688, 80, 80, odoo=True),
        image('main-toilet-1', 'toilet.svg', 1086, 640, 46, 46, odoo=True),
        image('main-toilet-2', 'toilet.svg', 1150, 640, 46, 46, odoo=True),
    ]
    for number in BOOTH_TABLES:
        _s, left, top, width, height, _seats, _c = MAIN_TABLES[number]
        d.append(image(f'main-booth-{number}-a', 'booth_sofa.svg', left - 8, top - 40, width + 16, 44))
        d.append(image(f'main-booth-{number}-b', 'booth_sofa.svg', left - 8, top + height - 4, width + 16, 44, rotation=180))
    for i, (x, y) in enumerate(((200, 274), (1000, 680), (262, 500), (960, 280), (470, 150))):
        d.append(image(f'main-palm-{i}', 'palm_plant.svg', x, y, 64, 64))
    d.append(rect('main-mat', 580, 786, 140, 24, color='#6d4c41', radius=6, text='WELCOME', font=12,
                  textcolor='#ffe0b2', bold=True))
    # labels
    d += [
        label('main-title', 400, 214, 520, 'Resto Cafe · Main Dining', font=26, color='#4e342e'),
        label('main-lbl-kitchen', 84, 206, 250, 'OPEN KITCHEN', font=15, color='#6d4c41'),
        label('main-lbl-window', 600, 158, 400, 'Window Seats', font=14, color='#00838f', italic=True),
        label('main-lbl-bar', 1010, 470, 210, 'Coffee & Mocktail Bar', font=14, color='#6d4c41'),
        label('main-lbl-booths', 196, 440, 130, 'Booths', font=14, color='#7b1f2b'),
        label('main-lbl-family', 728, 420, 176, 'Family Dining', font=14, color='#b5651d', italic=True),
        label('main-lbl-chef', 100, 612, 210, "Chef's Table", font=14, color='#6a1b9a'),
        label('main-lbl-reception', 770, 612, 170, 'Reception', font=15, color='#4e342e'),
        label('main-lbl-lounge', 360, 604, 190, 'Waiting Lounge', font=13, color='#546e7a'),
        label('main-lbl-restroom', 1066, 700, 150, 'Restrooms', font=13, color='#455a64'),
        label('main-lbl-entrance', 560, 814, 180, '▲ ENTRANCE', font=14, color='#4e342e'),
        label('main-lbl-dessert', 402, 132, 140, 'Desserts', font=12, color='#0277bd'),
    ]
    return d


# --------------------------------------------------------------------------- Patio
PATIO_TABLES = {
    101: ('circle', 116, 120, 76, 76, 2, 'blue'),
    105: ('circle', 116, 320, 76, 76, 2, 'blue'),
    109: ('circle', 116, 520, 76, 76, 2, 'blue'),
    102: ('circle', 312, 112, 96, 96, 4, 'turquoise'),
    106: ('circle', 312, 312, 96, 96, 4, 'turquoise'),
    110: ('circle', 312, 512, 96, 96, 4, 'turquoise'),
    108: ('rect', 520, 110, 184, 90, 6, 'orange'),
    104: ('rect', 520, 590, 184, 90, 6, 'orange'),
    103: ('square', 812, 262, 96, 96, 4, 'green'),
    107: ('square', 812, 442, 96, 96, 4, 'green'),
    111: ('square', 980, 262, 96, 96, 4, 'green'),
    112: ('rect', 962, 442, 220, 100, 8, 'purple'),
}
UMBRELLAS = {101: 'umbrella_red.svg', 105: 'umbrella_teal.svg', 109: 'umbrella_red.svg',
             102: 'umbrella_teal.svg', 106: 'umbrella_red.svg', 110: 'umbrella_teal.svg'}


def _patio_decorations():
    d = []
    # brown perimeter walls (around the garden)
    d += [
        wall('patio-wall-top', 14, 8, 1222, 14),
        wall('patio-wall-bottom', 14, 766, 1222, 14),
        wall('patio-wall-left-a', 14, 8, 14, 306),
        wall('patio-wall-left-b', 14, 464, 14, 310),
        wall('patio-wall-right', 1222, 8, 14, 766),
    ]
    hedge = dict(color='#558b2f', border='#33691e', border_width=3, radius=18)
    d += [
        rect('patio-lawn', 26, 26, 1196, 728, color='#9ccc65', opacity=0.18, radius=24),
        rect('patio-hedge-top', 20, 14, 1210, 26, **hedge),
        rect('patio-hedge-bottom', 20, 742, 1210, 26, **hedge),
        rect('patio-hedge-right', 1204, 14, 26, 754, **hedge),
        rect('patio-hedge-left-a', 20, 14, 26, 300, **hedge),
        rect('patio-hedge-left-b', 20, 464, 26, 304, **hedge),
        rect('patio-path', 20, 314, 90, 150, color='#d7ccc8', opacity=0.55, radius=12),
    ]
    # fairy lights over the café tables
    d += [line('patio-lights-1', 60, 236, 1120), line('patio-lights-2', 60, 466, 700),
          line('patio-lights-3', 60, 636, 1120)]
    for number, (shape, left, top, width, height, seats, _c) in PATIO_TABLES.items():
        d += chairs(f'patio-{number}', (shape, left, top, width, height, seats), CHAIR_PATIO)
    # parasols drawn under the café tables (tables are rendered above decorations)
    for number, img in UMBRELLAS.items():
        _s, left, top, width, height, _seats, _c = PATIO_TABLES[number]
        size = 150
        d.append(image(f'patio-umbrella-{number}', img, int(left + width / 2 - size / 2),
                       int(top + height / 2 - size / 2), size, size))
    d += [
        image('patio-fountain', 'fountain.svg', 540, 300, 150, 150),
        image('patio-grill', 'bbq_grill.svg', 980, 64, 170, 100),
        image('patio-firepit', 'firepit_lounge.svg', 930, 590, 220, 150),
        image('patio-door', 'door.svg', 32, 350, 80, 80, rotation=90, odoo=True),
    ]
    for i, (x, y) in enumerate(((60, 676), (1140, 300), (770, 640), (760, 60), (450, 660))):
        d.append(image(f'patio-palm-{i}', 'palm_plant.svg', x, y, 60, 60))
    d += [
        label('patio-title', 450, 470, 350, 'Garden Patio', font=26, color='#33691e'),
        label('patio-lbl-fountain', 515, 260, 200, 'Fountain', font=13, color='#0277bd', italic=True),
        label('patio-lbl-grill', 965, 170, 200, 'Live Grill Station', font=14, color='#bf360c'),
        label('patio-lbl-firepit', 930, 566, 220, 'Fire-pit Lounge', font=14, color='#e65100'),
        label('patio-lbl-door', 50, 436, 200, '◀ To Main Dining', font=13, color='#4e342e'),
        label('patio-lbl-cafe', 90, 40, 360, 'Café Tables under Parasols', font=14, color='#00695c', italic=True),
    ]
    return d


FLOORS = {
    # floor xmlid: (background, decorations builder, tables, table xmlid prefix)
    'floor_main': ('texture-wood-h', _main_decorations, MAIN_TABLES, 'table_main_'),
    'floor_patio': ('texture-tile-2', _patio_decorations, PATIO_TABLES, 'table_patio_'),
}


def table_layout(floor_key, number, spec):
    shape, left, top, width, height, _seats, color = spec
    return {'uuid': _uuid('table', floor_key, number), 'shape': shape, 'left': left, 'top': top,
            'width': width, 'height': height, 'color': color}


def floor_layout(background, builder):
    return {'bgColor': background, 'decorations': builder()}


def apply_floor_plans(env):
    """Write the designed layouts on the demo floors and their tables."""
    from .demo_guard import unguarded
    if 'restaurant.floor' not in env:
        return
    with unguarded():
        for floor_xid, (background, builder, tables, table_prefix) in FLOORS.items():
            floor = env.ref(f'{DATA_MODULE}.{floor_xid}', raise_if_not_found=False)
            if not floor:
                name = 'Main Floor' if floor_xid == 'floor_main' else 'Patio'
                floor = env['restaurant.floor'].search([('name', '=', name)], limit=1)
            if not floor:
                continue
            floor.write({'floor_plan_layout': floor_layout(background, builder)})
            for number, spec in tables.items():
                table = env.ref(f'{DATA_MODULE}.{table_prefix}{number}', raise_if_not_found=False)
                if not table:
                    table = env['restaurant.table'].search([('floor_id', '=', floor.id), ('table_number', '=', number)], limit=1)
                if table:
                    table.write({'floor_plan_layout': table_layout(floor_xid, number, spec)})
    _logger.info("Hudson POS demo: decorated floor plans applied.")


# --------------------------------------------------------------------------- upgrade of old demo floors
_OLD_BACKGROUNDS = {'floor_main': 'texture-wood-v', 'floor_patio': 'texture-stone-v'}


def _is_untouched_old_layout(floor_xid, floor):
    """True when the floor still has exactly the plain grid of the previous demo versions:
    old background, no decorations and every table on its generated grid position."""
    layout = floor.floor_plan_layout or {}
    if layout.get('decorations') or layout.get('bgImage'):
        return False
    if layout.get('bgColor') not in (None, _OLD_BACKGROUNDS[floor_xid]):
        return False
    for idx, table in enumerate(floor.table_ids.sorted('table_number')):
        tl = table.floor_plan_layout or {}
        row, col = divmod(idx, 4)
        if tl.get('left') != 80 + col * 170 or tl.get('top') != 80 + row * 160:
            return False
        if tl.get('width') != 100 or tl.get('height') != 100:
            return False
    return True


def upgrade_untouched_floor_plans(env):
    """Give existing databases the decorated floor plans, but only for demo floors nobody changed."""
    from .demo_guard import unguarded
    if 'restaurant.floor' not in env:
        return []
    upgraded = []
    with unguarded():
        for floor_xid, (background, builder, tables, table_prefix) in FLOORS.items():
            floor = env.ref(f'{DATA_MODULE}.{floor_xid}', raise_if_not_found=False)
            if not floor:
                name = 'Main Floor' if floor_xid == 'floor_main' else 'Patio'
                floor = env['restaurant.floor'].search([('name', '=', name)], limit=1)
            if not floor or not _is_untouched_old_layout(floor_xid, floor):
                continue
            floor.write({'floor_plan_layout': floor_layout(background, builder)})
            for number, spec in tables.items():
                table = env.ref(f'{DATA_MODULE}.{table_prefix}{number}', raise_if_not_found=False)
                if not table:
                    table = env['restaurant.table'].search([('floor_id', '=', floor.id), ('table_number', '=', number)], limit=1)
                if table:
                    table.write({'floor_plan_layout': table_layout(floor_xid, number, spec)})
            upgraded.append(floor.name)
    return upgraded
    return upgraded
