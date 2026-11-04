import { registry } from "@web/core/registry";
import { Base } from "@point_of_sale/app/models/related_models";
import { _t } from "@web/core/l10n/translation";

export class AppointmentBooking extends Base {
    static pythonModel = "appointment.booking";

    setup(vals) {
        super.setup(vals);
        this.name = vals.name || "";
        this.party_size = vals.party_size || 1;
        this.state = vals.state || "confirmed";
        this.start_datetime = vals.start_datetime || "";
        this.end_datetime = vals.end_datetime || "";
        this.guest_details = vals.guest_details || "";
        this.customer_name = vals.customer_name || (this.partner_id?.name || "");
        this.customer_phone = vals.customer_phone || (this.partner_id?.phone || this.partner_id?.mobile || "");
    }

    get customerDisplayName() {
        return this.customer_name || this.partner_id?.name || _t("Walk-in Guest");
    }

    get customerDisplayPhone() {
        return this.customer_phone || this.partner_id?.phone || this.partner_id?.mobile || "";
    }

    get startTimeStr() {
        if (!this.start_datetime) return "";
        try {
            const dt = luxon.DateTime.fromSQL ? luxon.DateTime.fromSQL(this.start_datetime) : luxon.DateTime.fromISO(this.start_datetime);
            return dt.isValid ? dt.toFormat("HH:mm") : this.start_datetime.substring(11, 16);
        } catch {
            return this.start_datetime.substring(11, 16);
        }
    }

    get endTimeStr() {
        if (!this.end_datetime) return "";
        try {
            const dt = luxon.DateTime.fromSQL ? luxon.DateTime.fromSQL(this.end_datetime) : luxon.DateTime.fromISO(this.end_datetime);
            return dt.isValid ? dt.toFormat("HH:mm") : this.end_datetime.substring(11, 16);
        } catch {
            return this.end_datetime.substring(11, 16);
        }
    }

    get startDateStr() {
        if (!this.start_datetime) return "";
        return this.start_datetime.substring(0, 10);
    }

    get tableRecords() {
        if (!this.table_ids || !this.models["restaurant.table"]) return [];
        return this.table_ids.map(id => this.models["restaurant.table"].get(id)).filter(Boolean);
    }

    get tableDisplayNames() {
        const tables = this.tableRecords;
        if (!tables.length) return _t("No Table");
        return tables.map(t => `${t.floor_id?.name ? t.floor_id.name + " " : ""}${t.table_number}`).join(", ");
    }
}

registry.category("pos_available_models").add(AppointmentBooking.pythonModel, AppointmentBooking);

