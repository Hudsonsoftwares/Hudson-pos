/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ViewButton } from "@web/views/view_button/view_button";
import { SearchPanel } from "@web/search/search_panel/search_panel";

export const FA_TO_MS = {
    // Files & Folders
    "fa-folder": "folder",
    "fa-folder-o": "folder",
    "fa-folder-open": "folder_open",
    "fa-folder-open-o": "folder_open",
    "fa-file": "description",
    "fa-file-o": "description",
    "fa-file-text": "description",
    "fa-file-text-o": "description",
    "fa-file-pdf-o": "picture_as_pdf",
    "fa-file-excel-o": "table_chart",
    "fa-file-archive-o": "folder_zip",
    "fa-files-o": "content_copy",

    // Common Actions & UI
    "fa-download": "download",
    "fa-upload": "upload",
    "fa-cloud-upload": "upload",
    "fa-refresh": "refresh",
    "fa-repeat": "refresh",
    "fa-retweet": "refresh",
    "fa-sync": "refresh",
    "fa-undo": "undo",
    "fa-pencil": "edit",
    "fa-pencil-square-o": "edit",
    "fa-edit": "edit",
    "fa-trash": "delete",
    "fa-trash-o": "delete",
    "fa-check": "check",
    "fa-check-circle": "check",
    "fa-check-square-o": "check",
    "fa-times": "close",
    "fa-close": "close",
    "fa-info": "info",
    "fa-info-circle": "info",
    "fa-exclamation": "priority_high",
    "fa-exclamation-triangle": "warning",
    "fa-warning": "warning",
    "fa-question-circle": "help",
    "fa-search": "search",
    "fa-filter": "filter_alt",
    "fa-print": "print",
    "fa-share": "share",
    "fa-share-alt": "share",
    "fa-send": "send",
    "fa-envelope": "mail",
    "fa-envelope-o": "mail",
    "fa-comments": "forum",
    "fa-comments-o": "mode_comment",
    "fa-comment": "mode_comment",
    "fa-bell": "notifications",
    "fa-bolt": "flash_on",
    "fa-magic": "wand_stars",
    "fa-cogs": "settings",
    "fa-cog": "settings",
    "fa-wrench": "build",
    "fa-history": "history",
    "fa-bars": "menu",
    "fa-th": "grid_view",
    "fa-list": "view_list",
    "fa-list-alt": "list_alt",
    "fa-table": "table_chart",
    "fa-external-link": "open_in_new",
    "fa-link": "link",
    "fa-chain-broken": "link_off",
    "fa-paperclip": "attach_file",

    // Users & Org
    "fa-users": "group",
    "fa-user": "person",
    "fa-user-plus": "person_add",
    "fa-user-md": "medical_services",
    "fa-address-card": "badge",
    "fa-id-card": "badge",
    "fa-building": "work",
    "fa-university": "account_balance",

    // Tools, Stats, Commerce
    "fa-tags": "tag",
    "fa-tag": "tag",
    "fa-money": "payments",
    "fa-credit-card": "credit_card",
    "fa-calculator": "calculate",
    "fa-line-chart": "show_chart",
    "fa-bar-chart": "bar_chart",
    "fa-pie-chart": "pie_chart",
    "fa-calendar": "calendar_today",
    "fa-calendar-plus-o": "calendar_today",
    "fa-calendar-times-o": "calendar_today",
    "fa-clock-o": "schedule",
    "fa-camera": "photo_camera",
    "fa-archive": "archive",
    "fa-inbox": "inbox",
    "fa-shopping-cart": "shopping_cart",
    "fa-truck": "local_shipping",
    "fa-shield": "security",
    "fa-star": "star",
    "fa-star-o": "star",
    "fa-lock": "lock",
    "fa-unlock": "lock_open",
    "fa-unlock-alt": "lock_open",
    "fa-eye": "visibility",
    "fa-eye-slash": "visibility_off",
    "fa-book": "book",
    "fa-tasks": "task",
    "fa-map-marker": "location_on",
    "fa-crosshairs": "my_location",
    "fa-bullseye": "my_location",
    "fa-cubes": "inventory_2",
    "fa-medkit": "medical_services",
    "fa-stethoscope": "stethoscope",
    "fa-heartbeat": "emergency",
    "fa-barcode": "qr_code",
    "fa-life-ring": "support",
    "fa-plug": "power",
    "fa-flask": "science",
    "fa-exchange": "swap_horiz",
    "fa-newspaper-o": "newspaper",

    // Navigation & Arrows
    "fa-arrow-right": "arrow_forward",
    "fa-arrow-left": "arrow_back",
    "fa-arrow-up": "arrow_upward",
    "fa-arrow-down": "arrow_downward",
    "fa-arrow-circle-right": "east",
    "fa-forward": "fast_forward",
};

export function cleanOdooIcon(iconStr) {
    if (!iconStr || typeof iconStr !== "string") {
        return { name: iconStr, extraClass: "" };
    }
    const parts = iconStr.trim().split(/\s+/);
    let rawIcon = parts[0];
    let extraClass = parts.slice(1).join(" ");

    // Handle prefixed "fa fa-something"
    if (rawIcon === "fa" && parts.length > 1) {
        rawIcon = parts[1];
        extraClass = parts.slice(2).join(" ");
    }

    if (FA_TO_MS[rawIcon]) {
        return { name: FA_TO_MS[rawIcon], extraClass };
    }

    // Generic fallback for any remaining fa- or icon with hyphens
    if (rawIcon.startsWith("fa-")) {
        let stripped = rawIcon.replace(/^fa-/, "").replace(/-o$/, "").replace(/-alt$/, "");
        stripped = stripped.replace(/-/g, "_");
        return { name: stripped, extraClass };
    }

    return { name: rawIcon, extraClass };
}

patch(ViewButton.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.icon && this.icon.name) {
            const { name, extraClass } = cleanOdooIcon(this.icon.name);
            this.icon.name = name;
            if (extraClass) {
                this.icon.class = `${this.icon.class || ""} ${extraClass}`.trim();
            }
        }
    },
});

patch(SearchPanel.prototype, {
    get sections() {
        const sections = super.sections;
        if (sections && Array.isArray(sections)) {
            for (const section of sections) {
                if (section.icon) {
                    const { name, extraClass } = cleanOdooIcon(section.icon);
                    section.icon = name;
                    if (extraClass && section.iconClass) {
                        section.iconClass = `${section.iconClass} ${extraClass}`.trim();
                    }
                }
            }
        }
        return sections;
    },
});
