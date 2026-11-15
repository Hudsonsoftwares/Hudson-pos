/** @odoo-module **/
// Part of Hudson Community. See LICENSE file for full copyright and licensing details.

import { loadCSS, loadJS } from "@web/core/assets";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { Layout } from "@web/search/layout";
import { usePager } from "@web/search/pager_hook";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { Component, onMounted, onWillStart, onWillUnmount, onWillUpdateProps, proxy, signal, useProps } from "@odoo/owl";

const { DateTime } = luxon;

const COLORS = ["#017e84", "#714b67", "#e8543e", "#0d6efd", "#f0ad4e", "#198754", "#d63384", "#6f42c1", "#20c997", "#fd7e14", "#0dcaf0", "#6c757d"];
// Google Maps directions: at most 9 stops between origin and destination
const MAX_WAYPOINTS = 9;

/**
 * Map view of the shifts (``fs_map``), like Online's Planning map: the shifts
 * are pinned at their customer's address, coloured by group (resource by
 * default), with a side panel listing the groups and a Google Maps route per
 * group.
 */
export class FsMapController extends Component {
    static template = "hudson_planning.FsMapView";
    static components = { Layout, SearchBar, CogMenu };
    props = useProps();

    rootRef = signal.ref();
    mapRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.searchBarToggler = useSearchBarToggler();

        this.state = proxy({
            records: [],
            groups: [],
            groupFieldString: "",
            total: 0,
            offset: 0,
            limit: this.props.archInfo.limit,
            expanded: {},
            error: false,
            loading: true,
        });
        this.map = null;
        this.layers = [];
        this.markers = {};

        usePager(() => ({
            offset: this.state.offset,
            limit: this.state.limit,
            total: this.state.total,
            onUpdate: async ({ offset, limit }) => {
                this.state.offset = offset;
                this.state.limit = limit;
                await this.load();
            },
        }));
        useSetupAction({ rootRef: this.rootRef });

        onWillStart(async () => {
            this.isManager = await user.hasGroup("hudson_planning.group_planning_manager");
            await this.load(this.props);
        });
        onWillUpdateProps(async (nextProps) => {
            this.state.offset = 0;
            await this.load(nextProps);
        });
        onMounted(async () => {
            try {
                await loadCSS("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css");
                await loadJS("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js");
                const L = window.L;
                this.map = L.map(this.mapRef(), { zoomControl: true }).setView([20, 0], 2);
                L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                    maxZoom: 19,
                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                }).addTo(this.map);
                // "Open" links of the pins' popups
                this.map.on("popupopen", (ev) => {
                    for (const link of ev.popup.getElement()?.querySelectorAll("[data-slot-id]") || []) {
                        link.addEventListener("click", (e) => {
                            e.preventDefault();
                            this.openRecord(parseInt(link.dataset.slotId));
                        });
                    }
                });
                setTimeout(() => this.map && this.map.invalidateSize(), 200);
                this.renderMarkers();
            } catch (e) {
                this.state.error = e.message || String(e);
            }
        });
        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
    }

    // -------------------------------------------------------------------------
    // Data
    // -------------------------------------------------------------------------

    async load(props = this.props) {
        this.state.loading = true;
        const data = await this.orm.call("fs.planning.slot", "get_map_view_data", [
            props.domain,
            props.groupBy.length ? props.groupBy : [this.props.archInfo.defaultGroupBy],
            this.state.offset,
            this.state.limit,
        ], { context: props.context });
        this.state.records = data.records;
        this.state.groups = data.groups;
        this.state.groupFieldString = data.group_field_string;
        this.state.total = data.total;
        // Few groups: all open (like Online), many: closed
        const open = data.groups.length <= 6;
        this.state.expanded = Object.fromEntries(data.groups.map((g) => [this.groupId(g), open]));
        this.state.loading = false;
        this.renderMarkers();
    }

    groupId(group) {
        return String(group.key);
    }

    groupColor(group) {
        const index = this.state.groups.findIndex((g) => g.key === group.key);
        return COLORS[index % COLORS.length];
    }

    groupRecords(group) {
        return this.state.records.filter((r) => r.group_key === group.key);
    }

    isExpanded(group) {
        return this.state.expanded[this.groupId(group)];
    }

    get locatedCount() {
        return this.state.records.filter((r) => r.latitude || r.longitude).length;
    }

    recordTime(record) {
        const start = deserializeDateTime(record.date_start);
        const end = deserializeDateTime(record.date_end);
        const sameDay = start.hasSame(end, "day");
        return `${start.toFormat("ccc d MMM")}, ${start.toLocaleString(DateTime.TIME_SIMPLE)} - ${
            sameDay ? "" : end.toFormat("d MMM") + ", "
        }${end.toLocaleString(DateTime.TIME_SIMPLE)}`;
    }

    // -------------------------------------------------------------------------
    // Map
    // -------------------------------------------------------------------------

    renderMarkers() {
        if (!this.map) {
            return;
        }
        const L = window.L;
        for (const layer of this.layers) {
            layer.remove();
        }
        this.layers = [];
        this.markers = {};
        // One pin per address, with the number of shifts there
        const places = new Map();
        for (const record of this.state.records) {
            if (!(record.latitude || record.longitude)) {
                continue;
            }
            const key = `${record.latitude.toFixed(5)},${record.longitude.toFixed(5)}`;
            if (!places.has(key)) {
                places.set(key, []);
            }
            places.get(key).push(record);
        }
        for (const records of places.values()) {
            const first = records[0];
            const group = this.state.groups.find((g) => g.key === first.group_key);
            const marker = L.marker([first.latitude, first.longitude], {
                icon: L.divIcon({
                    className: "",
                    html: this._pinHtml(records.length > 1 ? String(records.length) : "", this.groupColor(group)),
                    iconSize: [30, 40],
                    iconAnchor: [15, 40],
                    popupAnchor: [0, -40],
                }),
            }).bindPopup(this._popupHtml(records), { maxWidth: 300 });
            marker.addTo(this.map);
            this.layers.push(marker);
            for (const record of records) {
                this.markers[record.id] = marker;
            }
        }
        if (this.layers.length) {
            this.map.fitBounds(L.featureGroup(this.layers).getBounds().pad(0.2), { maxZoom: 13 });
        }
    }

    _pinHtml(label, color) {
        return `<div class="o_fs_map_pin" style="background:${color}"><span>${this._esc(label)}</span></div>`;
    }

    _popupHtml(records) {
        const first = records[0];
        const items = records.map((r) => `
            <div class="o_fs_map_popup_record">
                <a href="#" data-slot-id="${r.id}"><strong>${this._esc(r.name)}</strong></a>
                <div class="text-muted">${this._esc(this.recordTime(r))}</div>
            </div>`).join("");
        const url = this._directionsUrl([first]);
        return `
            <div class="o_fs_map_popup">
                <div class="fw-bold">${this._esc(first.partner_name)}</div>
                <div class="text-muted mb-2">${this._esc(first.address)}</div>
                ${items}
                <a class="btn btn-sm btn-secondary mt-2" target="_blank" rel="noopener" href="${url}">${this._esc(_t("Navigate to"))}</a>
            </div>`;
    }

    _esc(value) {
        const div = document.createElement("div");
        div.textContent = value == null ? "" : String(value);
        return div.innerHTML;
    }

    _directionsUrl(records) {
        const stops = records.map((r) => `${r.latitude},${r.longitude}`);
        const destination = stops[stops.length - 1];
        const waypoints = stops.slice(0, -1).slice(0, MAX_WAYPOINTS);
        let url = `https://www.google.com/maps/dir/?api=1&travelmode=driving&destination=${encodeURIComponent(destination)}`;
        if (waypoints.length) {
            url += `&waypoints=${encodeURIComponent(waypoints.join("|"))}`;
        }
        return url;
    }

    // -------------------------------------------------------------------------
    // Handlers
    // -------------------------------------------------------------------------

    toggleGroup(group) {
        const id = this.groupId(group);
        this.state.expanded[id] = !this.state.expanded[id];
    }

    /** Google Maps route through the group's addresses, in time order. */
    navigateGroup(group) {
        const located = this.groupRecords(group).filter((r) => r.latitude || r.longitude);
        if (located.length) {
            window.open(this._directionsUrl(located), "_blank", "noopener");
        }
    }

    navigateAll() {
        const located = this.state.records.filter((r) => r.latitude || r.longitude);
        if (located.length) {
            window.open(this._directionsUrl(located), "_blank", "noopener");
        }
    }

    onRecordClick(record) {
        const marker = this.markers[record.id];
        if (marker && this.map) {
            this.map.setView(marker.getLatLng(), Math.max(this.map.getZoom(), 14));
            marker.openPopup();
        } else {
            this.openRecord(record.id);
        }
    }

    openRecord(resId) {
        this.props.selectRecord(resId);
    }

    onClickNew() {
        this.props.createRecord();
    }
}

class FsMapArchParser {
    parse(arch) {
        const limit = parseInt(arch.getAttribute("limit") || "80");
        return {
            defaultGroupBy: arch.getAttribute("default_group_by") || "resource_id",
            limit: limit > 0 ? limit : 80,
            canCreate: arch.getAttribute("create") !== "0" && arch.getAttribute("create") !== "false",
        };
    }
}

export const fsMapView = {
    type: "fs_map",
    Controller: FsMapController,
    ArchParser: FsMapArchParser,
    searchMenuTypes: ["filter", "groupBy", "favorite"],
    props: (genericProps, view) => ({
        ...genericProps,
        archInfo: new view.ArchParser().parse(genericProps.arch),
    }),
};

registry.category("views").add("fs_map", fsMapView);
