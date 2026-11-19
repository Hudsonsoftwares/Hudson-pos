/** @odoo-module */

import { AddDecorPopup } from "@pos_restaurant/app/screens/floor_screen/floor_plan_editor/add_decor_popup/add_decor_popup";
import { FloorPlanEditor } from "@pos_restaurant/app/screens/floor_screen/floor_plan_editor/floor_plan_editor";
import { FloorPlanStore } from "@pos_restaurant/app/services/floor_plan/floor_plan_service";
import { Image as FloorImage } from "@pos_restaurant/app/services/floor_plan/elements/image";
import { patch } from "@web/core/utils/patch";

export const HUDSON_DECOR_NAMES = new Set([
    "dining_chair.svg",
    "patio_chair.svg",
    "bar_stool.svg",
    "booth_sofa.svg",
    "garden_hedge.svg",
    "palm_plant.svg",
    "lawn_patch.svg",
    "dining_rug.svg",
    "lounge_set.svg",
    "reception_desk.svg",
    "bar_counter.svg",
    "kitchen_line.svg",
    "dessert_display.svg",
    "restroom_sign.svg",
    "welcome_mat.svg",
    "bbq_grill.svg",
    "firepit_lounge.svg",
    "fountain.svg",
    "umbrella_teal.svg",
    "umbrella_red.svg",
]);

// Fallback UUID lookup to auto-repair any elements saved previously without a name
export const UUID_TO_DECOR_NAME = {
    "28d88b9d51d22483": "bar_counter.svg",
    "38acf61a22f87beb": "reception_desk.svg",
    "98596ceaa31ed8cc": "lounge_set.svg",
    "4875299cd8376cad": "door.svg",
    "aca727049ad3ed77": "toilet.svg",
    "cd4cdf205d7fe5ae": "toilet.svg",
    "fec82884eb669869": "booth_sofa.svg",
    "0e482da1a01e924d": "booth_sofa.svg",
    "64ea2daf6ed8d9ab": "booth_sofa.svg",
    "c8d061c24ae17ba5": "booth_sofa.svg",
    "7a5f2e38dbd45b23": "palm_plant.svg",
    "cf37f833d008d617": "palm_plant.svg",
    "e717a6930cb3ec20": "palm_plant.svg",
    "56b6b111059f56e3": "palm_plant.svg",
    "02ab3e8bc6980a5a": "palm_plant.svg",
    "ed2741d1c2bedbe7": "dessert_display.svg",
    "c834bf8bf9d46800": "umbrella_red.svg",
    "24155e5c7e6e2459": "umbrella_teal.svg",
    "765e7a48379e86f4": "umbrella_red.svg",
    "60d89c05c2f1ba39": "umbrella_teal.svg",
    "0fc5ebe96547a093": "umbrella_red.svg",
    "6f9312a280e9980f": "umbrella_teal.svg",
    "9925be7d0b914b88": "fountain.svg",
    "21cb64642caa9eee": "bbq_grill.svg",
    "3fbd5f40e23023fc": "firepit_lounge.svg",
    "5647badbbcc9e8fe": "door.svg",
    "9e3d9be07e192947": "palm_plant.svg",
    "6fc2fd64a2135b4b": "palm_plant.svg",
    "f437065494108412": "palm_plant.svg",
    "e8c1471b54b222c5": "palm_plant.svg",
    "de9f896e02209113": "palm_plant.svg",
};

export function getHudsonDecorUrl(filename) {
    if (!filename) return "";
    if (HUDSON_DECOR_NAMES.has(filename) || (filename.endsWith(".svg") && !["door.svg", "toilet.svg", "plant.svg"].includes(filename))) {
        return `/hudson_pos_theme/static/src/img/floor_plan/${filename}`;
    }
    return `/pos_restaurant/static/floor_plan/${filename}`;
}

// 1. Patch AddDecorPopup so custom buttons insert draggable decor elements
patch(AddDecorPopup.prototype, {
    addCustomDecor(filename) {
        const url = getHudsonDecorUrl(filename);
        this.addImage({ name: filename, url });
    },

    getCustomDecorUrl(filename) {
        return getHudsonDecorUrl(filename);
    },

    getAssetUrl(name) {
        if (HUDSON_DECOR_NAMES.has(name) || (name && name.endsWith(".svg") && !["door.svg", "toilet.svg", "plant.svg"].includes(name))) {
            return getHudsonDecorUrl(name);
        }
        return super.getAssetUrl(name);
    },
});

// 2. Patch FloorPlanEditor so createImageShapeData loads the URL correctly
patch(FloorPlanEditor.prototype, {
    async createImageShapeData(data) {
        if (data && data.name && !data.url) {
            data.url = getHudsonDecorUrl(data.name);
        }
        return super.createImageShapeData(data);
    },
});

// 3. Patch FloorPlanStore so when decor is loaded from database, url & name are always intact
patch(FloorPlanStore.prototype, {
    createDecorFromData(data) {
        if (data && data.shape === "image") {
            if (!data.name && UUID_TO_DECOR_NAME[data.uuid]) {
                data.name = UUID_TO_DECOR_NAME[data.uuid];
            }
            if (data.name) {
                data.url = getHudsonDecorUrl(data.name);
            }
        }
        return super.createDecorFromData(data);
    },
});

// 4. Patch FloorImage so getCssStyle always outputs the correct URL, and raw always preserves name
patch(FloorImage.prototype, {
    getCssStyle(...args) {
        if (!this.name && UUID_TO_DECOR_NAME[this.uuid]) {
            this.name = UUID_TO_DECOR_NAME[this.uuid];
        }
        if (this.name) {
            this.url = getHudsonDecorUrl(this.name);
        }
        let style = super.getCssStyle(...args);
        if (this.url && !this.url.includes("/web/image/undefined")) {
            style += `background-image: url('${this.url}') !important;`;
            style += `background-size: contain !important;`;
            style += `background-position: center !important;`;
            style += `background-repeat: no-repeat !important;`;
        }
        return style;
    },

    get raw() {
        if (!this.name && UUID_TO_DECOR_NAME[this.uuid]) {
            this.name = UUID_TO_DECOR_NAME[this.uuid];
        }
        const data = super.raw;
        if (this.name) {
            data.name = this.name;
        }
        return data;
    },
});
