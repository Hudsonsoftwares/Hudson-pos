/** @odoo-module **/
// Part of Hudson Community. See LICENSE file for full copyright and licensing details.

import { Component, proxy, signal, onMounted, onWillUnmount, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS, loadCSS } from "@web/core/assets";

const COLORS = ["#017e84", "#714b67", "#0d6efd", "#fd7e14", "#d63384", "#198754", "#6f42c1", "#dc3545", "#20c997", "#6c757d"];
const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function startOfDay(d) {
    const r = new Date(d);
    r.setHours(0, 0, 0, 0);
    return r;
}
function addDays(d, n) {
    const r = new Date(d);
    r.setDate(r.getDate() + n);
    return r;
}
function toUtcStr(d) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
}
function parseUtc(str) {
    return new Date(str.replace(" ", "T") + "Z");
}

/**
 * FsJobMap — field service jobs on a map, at their customer's location.
 *
 * Action context:
 *  - map_mode: "resource" (pins coloured per technician) or "timeline"
 *    (each technician's jobs of the day numbered and linked in time order)
 *  - my_only: only the current user's jobs (Planning > My > Map)
 */
export class FsJobMap extends Component {
    static template = "hudson_field_service.FsJobMap";
    props = useProps();
    mapRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        const context = (this.props.action && this.props.action.context) || {};
        this.mapMode = context.map_mode === "timeline" ? "timeline" : "resource";
        this.myOnly = Boolean(context.my_only);

        this.state = proxy({
            day: startOfDay(new Date()),
            jobs: [],
            loading: true,
            locating: false,
            error: null,
            resourceFilter: null, // resource id shown alone, or null for all
            selectedId: null,
            travelTimes: {},      // resource id -> driving minutes (Mapbox)
        });
        this.mapboxToken = false;

        this.map = null;
        this.layers = [];
        this.markers = {};

        onMounted(async () => {
            try {
                await loadCSS("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css");
                await loadJS("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js");
                const el = typeof this.mapRef === "function" ? this.mapRef() : this.mapRef?.el;
                this.map = window.L.map(el, { zoomControl: true }).setView([20, 0], 2);
                window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                    maxZoom: 19,
                    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                }).addTo(this.map);
                // Open the shift from the "Open" link of a pin's popup
                this.map.on("popupopen", (ev) => {
                    const link = ev.popup.getElement()?.querySelector("[data-slot-id]");
                    if (link) {
                        link.addEventListener("click", (e) => {
                            e.preventDefault();
                            this.openJob(parseInt(link.dataset.slotId));
                        });
                    }
                });
                setTimeout(() => this.map && this.map.invalidateSize(), 200);
                this.mapboxToken = await this.orm.call("fs.planning.slot", "get_mapbox_token", []);
                await this.loadJobs();
            } catch (e) {
                this.state.error = e.message || String(e);
                this.state.loading = false;
            }
        });

        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
    }

    // ── Data ─────────────────────────────────────────────────────────

    get title() {
        if (this.myOnly) {
            return "My Map";
        }
        return this.mapMode === "timeline" ? "Timeline" : "Jobs by Resource";
    }

    get dayLabel() {
        const d = this.state.day;
        return `${DAY_NAMES[d.getDay()]}, ${MONTH_NAMES[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
    }

    async loadJobs() {
        this.state.loading = true;
        const jobs = await this.orm.call("fs.planning.slot", "get_job_map_data", [
            toUtcStr(this.state.day),
            toUtcStr(addDays(this.state.day, 1)),
        ], { my_only: this.myOnly });
        this.state.travelTimes = {};
        this.state.jobs = jobs.map((job) => ({
            ...job,
            start: parseUtc(job.date_start),
            end: parseUtc(job.date_end),
            located: Boolean(job.latitude && job.longitude),
        }));
        if (this.state.resourceFilter !== null && !this.resources.some((r) => r.id === this.state.resourceFilter)) {
            this.state.resourceFilter = null;
        }
        this.state.loading = false;
        this._render();
    }

    /** Technicians with jobs that day, each with its jobs in time order. */
    get resources() {
        const byId = new Map();
        for (const job of this.state.jobs) {
            if (!byId.has(job.resource_id)) {
                byId.set(job.resource_id, {
                    id: job.resource_id,
                    name: job.resource_name,
                    color: COLORS[job.resource_id % COLORS.length],
                    jobs: [],
                });
            }
            byId.get(job.resource_id).jobs.push(job);
        }
        return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
    }

    get visibleResources() {
        const filter = this.state.resourceFilter;
        return filter === null ? this.resources : this.resources.filter((r) => r.id === filter);
    }

    get unlocatedCount() {
        return this.state.jobs.filter((j) => !j.located).length;
    }

    // ── Map rendering ────────────────────────────────────────────────

    _render() {
        if (!this.map) {
            return;
        }
        for (const layer of this.layers) {
            layer.remove();
        }
        this.layers = [];
        this.markers = {};
        const L = window.L;
        for (const resource of this.visibleResources) {
            const located = resource.jobs.filter((j) => j.located);
            located.forEach((job, index) => {
                const label = this.mapMode === "timeline" ? String(index + 1) : this._initials(resource.name);
                const marker = L.marker([job.latitude, job.longitude], {
                    icon: L.divIcon({
                        className: "",
                        html: this._pinHtml(label, resource.color),
                        iconSize: [36, 46],
                        iconAnchor: [18, 46],
                        popupAnchor: [0, -48],
                    }),
                }).bindPopup(this._popupHtml(job, resource), { maxWidth: 260 });
                marker.addTo(this.map);
                this.layers.push(marker);
                this.markers[job.id] = marker;
            });
            if (this.mapMode === "timeline" && located.length > 1) {
                const route = L.polyline(located.map((j) => [j.latitude, j.longitude]), {
                    color: resource.color,
                    weight: 3,
                    opacity: 0.8,
                    dashArray: "6, 6",
                }).addTo(this.map);
                this.layers.push(route);
                if (this.mapboxToken) {
                    this._drawDrivingRoute(resource, located, route);
                }
            }
        }
        if (this.layers.length) {
            this.map.fitBounds(L.featureGroup(this.layers).getBounds().pad(0.3), { maxZoom: 14 });
        }
    }

    /** Settings > Mapbox: replace the straight line by the driving route. */
    async _drawDrivingRoute(resource, jobs, straightLine) {
        const coords = jobs.slice(0, 25).map((j) => `${j.longitude},${j.latitude}`).join(";");
        try {
            const response = await fetch(
                `https://api.mapbox.com/directions/v5/mapbox/driving/${coords}?geometries=geojson&overview=full&access_token=${encodeURIComponent(this.mapboxToken)}`
            );
            const data = await response.json();
            const route = data.routes && data.routes[0];
            if (!route || !this.map) {
                return;
            }
            straightLine.setLatLngs(route.geometry.coordinates.map(([lng, lat]) => [lat, lng]));
            straightLine.setStyle({ dashArray: null, weight: 4 });
            this.state.travelTimes[resource.id] = Math.round(route.duration / 60);
        } catch (e) {
            console.warn("[FsJobMap] Mapbox route failed, keeping straight lines", e);
        }
    }

    _pinHtml(label, color) {
        return `
            <div style="width:36px; height:36px; border-radius:50% 50% 50% 0; transform:rotate(-45deg);
                        background:${color}; border:2px solid white; box-shadow:0 3px 10px rgba(0,0,0,0.3);
                        display:flex; align-items:center; justify-content:center;">
                <span style="transform:rotate(45deg); color:#fff; font-weight:700; font-size:12px; font-family:sans-serif;">
                    ${this._esc(label)}
                </span>
            </div>`;
    }

    _popupHtml(job, resource) {
        return `
            <div class="fs-map-popup">
                <strong>${this._esc(job.order_name)} — ${this._esc(job.title)}</strong>
                <div class="fs-popup-customer">👤 ${this._esc(job.partner_name)}</div>
                <div class="fs-popup-order">${this._esc(this.formatTime(job.start))} - ${this._esc(this.formatTime(job.end))} · ${this._esc(resource.name)}</div>
                ${job.phone ? `<div class="fs-popup-order">📞 ${this._esc(job.phone)}</div>` : ""}
                <a href="#" data-slot-id="${job.id}">Open →</a>
            </div>`;
    }

    _initials(name) {
        return name.split(" ").slice(0, 2).map((w) => w[0]?.toUpperCase() || "").join("");
    }

    _esc(str) {
        return String(str ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    formatTime(date) {
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }

    // ── Event handlers ───────────────────────────────────────────────

    async onPrevDay() {
        this.state.day = addDays(this.state.day, -1);
        await this.loadJobs();
    }

    async onNextDay() {
        this.state.day = addDays(this.state.day, 1);
        await this.loadJobs();
    }

    async onToday() {
        this.state.day = startOfDay(new Date());
        await this.loadJobs();
    }

    setResourceFilter(resourceId) {
        this.state.resourceFilter = this.state.resourceFilter === resourceId ? null : resourceId;
        this._render();
    }

    onJobClick(job) {
        this.state.selectedId = job.id;
        const marker = this.markers[job.id];
        if (marker) {
            this.map.panTo(marker.getLatLng(), { animate: true });
            marker.openPopup();
        }
    }

    openJob(slotId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Edit Shift",
            res_model: "fs.planning.slot",
            res_id: slotId,
            views: [[false, "form"]],
            target: "new",
        }, {
            onClose: () => this.loadJobs(),
        });
    }

    async onLocateCustomers() {
        this.state.locating = true;
        try {
            const ids = this.state.jobs.filter((j) => !j.located).map((j) => j.id);
            const located = await this.orm.call("fs.planning.slot", "action_locate_customers", [ids]);
            this.notification.add(`${located} customer(s) located.`, { type: located ? "success" : "warning" });
            await this.loadJobs();
        } finally {
            this.state.locating = false;
        }
    }
}

registry.category("actions").add("hudson_field_service.fs_job_map", FsJobMap);
