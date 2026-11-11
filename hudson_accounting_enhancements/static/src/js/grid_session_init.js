/** @odoo-module **/

import * as owl from "@odoo/owl";
import { session } from "@web/session";

// Owl 3 (Odoo 20) compatibility polyfill: in Owl 3, useState was replaced by proxy.
// Polyfill useState so legacy Owl 2 components across custom modules function properly.
if (typeof owl !== "undefined" && owl.proxy && !owl.useState) {
    try {
        owl.useState = owl.proxy;
    } catch (_) {}
}
if (typeof globalThis !== "undefined" && globalThis.owl && globalThis.owl.proxy && !globalThis.owl.useState) {
    try {
        globalThis.owl.useState = globalThis.owl.proxy;
    } catch (_) {}
}
if (typeof window !== "undefined" && window.owl && window.owl.proxy && !window.owl.useState) {
    try {
        window.owl.useState = window.owl.proxy;
    } catch (_) {}
}

if (session && !session.view_info) {
    session.view_info = {};
}
if (session && session.view_info) {
    session.view_info.grid = {
        icon: "grid_view",
        display_name: "Grid",
        multi_record: true,
    };
}

// Fallback for navigator.clipboard on plain HTTP IP deployments
if (typeof window !== "undefined" && (!window.navigator || !window.navigator.clipboard)) {
    try {
        Object.defineProperty(window.navigator, "clipboard", {
            value: {
                writeText: async (text) => {
                    const textArea = document.createElement("textarea");
                    textArea.value = text || "";
                    textArea.style.position = "fixed";
                    textArea.style.opacity = "0";
                    textArea.style.pointerEvents = "none";
                    document.body.appendChild(textArea);
                    textArea.focus();
                    textArea.select();
                    try {
                        document.execCommand("copy");
                    } finally {
                        document.body.removeChild(textArea);
                    }
                },
                readText: async () => "",
            },
            configurable: true,
        });
    } catch (_) {
        // Ignore if read-only
    }
}

