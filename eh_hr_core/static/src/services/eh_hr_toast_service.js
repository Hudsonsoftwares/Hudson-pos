/** @odoo-module **/
import { registry } from "@web/core/registry";

const hrToastService = {
    dependencies: ["notification"],
    start(env, { notification }) {
        const seen = new Map();
        function emit(type, message, key) {
            const k = key || message;
            const now = Date.now();
            const last = seen.get(k);
            if (last && now - last < 3000) return;
            seen.set(k, now);
            notification.add(message, { type });
        }
        return {
            success: (m, key) => emit("success", m, key),
            warn:    (m, key) => emit("warning", m, key),
            danger:  (m, key) => emit("danger",  m, key),
            info:    (m, key) => emit("info",    m, key),
        };
    },
};

registry.category("services").add("hr.toast", hrToastService);
