import { registry } from "@web/core/registry";
import { Base } from "@point_of_sale/app/models/related_models";
import { _t } from "@web/core/l10n/translation";

export class AppointmentBooking extends Base {
    static pythonModel = "appointment.booking";

    setup(vals) {
        super.setup(vals);
    }

    get customerDisplayName() {
        if (this.customer_name && !this.customer_name.startsWith("Table Booking") && this.customer_name !== "False") {
            return this.customer_name;
        }
        if (this.partner_id?.name && !this.partner_id.name.startsWith("Table Booking") && this.partner_id.name !== "Resto Cafe" && this.partner_id.name !== "False") {
            return this.partner_id.name;
        }
        return (this.customer_name && this.customer_name !== "False") ? this.customer_name : (_t("Guest"));
    }

    get customerDisplayPhone() {
        return this.customer_phone || this.partner_id?.phone || this.partner_id?.mobile || "";
    }

    get customerDisplayEmail() {
        return this.customer_email || this.partner_id?.email || "";
    }

    _parseDt(val) {
        if (!val) return null;
        try {
            // 1. If already a Luxon DateTime instance (e.g. from Odoo deserializeDateTime)
            if (typeof val === "object" && typeof val.toFormat === "function" && val.isValid) {
                return val;
            }
            // 2. If JavaScript Date object
            if (val instanceof Date) {
                return luxon.DateTime.fromJSDate(val);
            }
            // 3. If String (ISO or SQL format in UTC from database)
            if (typeof val === "string") {
                const isIso = val.includes("T");
                const dt = isIso
                    ? luxon.DateTime.fromISO(val, { zone: "utc" })
                    : luxon.DateTime.fromSQL(val, { zone: "utc" });
                if (dt && dt.isValid) return dt.setZone("system");
                const fallback = luxon.DateTime.fromISO(val);
                if (fallback && fallback.isValid) return fallback.setZone("system");
            }
        } catch {
            return null;
        }
        return null;
    }

    get startTimeStr() {
        if (this.start_time_str) return this.start_time_str;
        const dt = this._parseDt(this.start_datetime);
        if (dt) return dt.toFormat("HH:mm");
        if (typeof this.start_datetime === "string" && this.start_datetime.length >= 16) {
            return this.start_datetime.substring(11, 16);
        }
        return "";
    }

    get endTimeStr() {
        if (this.end_time_str) return this.end_time_str;
        const dt = this._parseDt(this.end_datetime);
        if (dt) return dt.toFormat("HH:mm");
        if (typeof this.end_datetime === "string" && this.end_datetime.length >= 16) {
            return this.end_datetime.substring(11, 16);
        }
        return "";
    }

    get startDateStr() {
        if (this.start_date_str) return this.start_date_str;
        const dt = this._parseDt(this.start_datetime);
        if (dt) return dt.toFormat("yyyy-MM-dd");
        if (typeof this.start_datetime === "string" && this.start_datetime.length >= 10) {
            return this.start_datetime.substring(0, 10);
        }
        return "";
    }

    get startTimestamp() {
        const dt = this._parseDt(this.start_datetime);
        return dt ? dt.toMillis() : 0;
    }

    get endTimestamp() {
        const dt = this._parseDt(this.end_datetime);
        return dt ? dt.toMillis() : 0;
    }

    get startHourFraction() {
        const dt = this._parseDt(this.start_datetime);
        return dt ? (dt.hour + dt.minute / 60.0) : 0;
    }

    get endHourFraction() {
        const dt = this._parseDt(this.end_datetime);
        if (dt) return dt.hour + dt.minute / 60.0;
        return this.startHourFraction + (parseFloat(this.duration) || 1.5);
    }

    get tableRecords() {
        const raw = this.table_ids;
        if (!raw) return [];
        const tablesStore = this.models ? this.models["restaurant.table"] : null;
        
        let list = [];
        if (Array.isArray(raw)) {
            list = raw;
        } else if (raw instanceof Set) {
            list = Array.from(raw);
        } else if (typeof raw[Symbol.iterator] === "function") {
            list = Array.from(raw);
        } else {
            list = [raw];
        }

        return list.map(item => {
            if (!item) return null;
            if (typeof item === "object") {
                if (item.table_number !== undefined) return item;
                if (item.id && tablesStore) return tablesStore.get(item.id);
            }
            return tablesStore ? tablesStore.get(item) : null;
        }).filter(Boolean);
    }

    get tableDisplayNames() {
        const tables = this.tableRecords;
        if (!tables.length) return _t("No Table");
        return tables.map(t => `${t.floor_id?.name ? t.floor_id.name + " " : ""}${t.table_number || t.name || ''}`).join(", ");
    }
}

registry.category("pos_available_models").add(AppointmentBooking.pythonModel, AppointmentBooking);
