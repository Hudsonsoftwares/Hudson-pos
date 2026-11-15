/** @odoo-module **/
// Part of Hudson Community. See LICENSE file for full copyright and licensing details.

import { Component, proxy, signal, onMounted, onWillUnmount, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS, loadCSS } from "@web/core/assets";


/**
 * FsLiveMap — Live Technician Map
 *
 * An OWL client action that renders a Leaflet.js map showing all field
 * service technicians who currently have a timer running.  The map
 * auto-refreshes every 60 seconds.  Clicking a pin or a sidebar card opens
 * the corresponding field service order in the form view.
 */
export class FsLiveMap extends Component {
    static template = "hudson_field_service.FsLiveMap";
    props = useProps();
    mapRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.onTechClick = this.onTechClick.bind(this);
        this.onRefresh = this.onRefresh.bind(this);
        this.setFilter = this.setFilter.bind(this);

        this.state = proxy({
            technicians: [],
            loading: true,
            error: null,
            lastUpdated: null,
            selectedId: null,
            filter: "all",
        });

        /** @type {L.Map|null} */
        this.map = null;
        /** @type {Record<number, L.Marker>} */
        this.markers = {};
        /** @type {number|null} */
        this.refreshTimer = null;

        onMounted(async () => {
            try {
                await this._initLeaflet();
                this._createMap();
                
                // Fix map container size issue
                setTimeout(() => {
                    if (this.map) this.map.invalidateSize();
                }, 200);

                await this._loadTechnicians();
                // Auto-refresh every 60 s
                this.refreshTimer = setInterval(() => this._loadTechnicians(), 60000);
            } catch (e) {
                this.state.error = e.message || String(e);
                this.state.loading = false;
            }
        });

        onWillUnmount(() => {
            if (this.refreshTimer) {
                clearInterval(this.refreshTimer);
                this.refreshTimer = null;
            }
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
    }

    // ── Private helpers ───────────────────────────────────────────────

    async _initLeaflet() {
        await loadCSS("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css");
        await loadJS("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js");
    }

    _createMap() {
        const el = (typeof this.mapRef === "function" ? this.mapRef() : this.mapRef?.el) || document.querySelector(".fs-map-container");
        if (!el) return;

        this.map = window.L.map(el, { zoomControl: true }).setView([20, 0], 2);

        // OpenStreetMap tile layer
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(this.map);
    }

    async _loadTechnicians() {
        if (!this.map) return;
        try {
            const data = await this.orm.call(
                "field.service.active.timer",
                "search_read",
                [
                    [
                        ["current_latitude", "!=", 0],
                        ["current_longitude", "!=", 0],
                    ],
                ],
                {
                    fields: [
                        "id", "order_id", "employee_id", "user_id", "start_time",
                        "current_latitude", "current_longitude",
                        "order_id_partner_id", "order_id_title", "is_outside_radius",
                        "customer_latitude", "customer_longitude", "location_radius"
                    ],
                }
            );

            // Fetch extra order details (like radius, customer info) if needed,
            // or just rely on related fields. I will add related fields to field.service.active.timer!

            this.state.technicians = data;
            this.state.loading = false;
            this.state.lastUpdated = new Date();
            this._syncMarkers(this.filteredTechnicians);
        } catch (e) {
            console.error("[FsLiveMap] Failed to load technicians:", e);
            let errMsg = e.message || String(e);
            if (errMsg.includes("Odoo Server Error") || errMsg.includes("RPC_ERROR")) {
                this.state.error = "No employees are available with map.";
            } else {
                this.state.error = "No employees are available with map.";
            }
            this.state.loading = false;
        }
    }

    _syncMarkers(technicians) {
        if (!this.map) return;

        const currentIds = new Set(technicians.map((t) => t.id));

        // Remove stale markers and circles
        for (const idStr of Object.keys(this.markers)) {
            const id = parseInt(idStr);
            if (!currentIds.has(id)) {
                this.markers[id].remove();
                delete this.markers[id];
                if (this.circles && this.circles[id]) {
                    this.circles[id].remove();
                    delete this.circles[id];
                }
            }
        }
        
        if (!this.circles) this.circles = {};

        // Add / update markers
        for (const tech of technicians) {
            const lat = tech.current_latitude;
            const lng = tech.current_longitude;
            if (!lat || !lng) continue;

            const pos = [lat, lng];
            const popup = this._buildPopup(tech);
            
            // Draw Radius Circle
            if (tech.customer_latitude && tech.customer_longitude && tech.location_radius) {
                const center = [tech.customer_latitude, tech.customer_longitude];
                if (this.circles[tech.id]) {
                    this.circles[tech.id].setLatLng(center).setRadius(tech.location_radius);
                    this.circles[tech.id].setStyle({
                        color: tech.is_outside_radius ? '#dc3545' : '#0d6efd',
                        fillColor: tech.is_outside_radius ? '#dc3545' : '#0d6efd',
                    });
                } else {
                    this.circles[tech.id] = window.L.circle(center, {
                        color: tech.is_outside_radius ? '#dc3545' : '#0d6efd',
                        fillColor: tech.is_outside_radius ? '#dc3545' : '#0d6efd',
                        fillOpacity: 0.14,
                        weight: 2,
                        dashArray: '4, 4',
                        radius: tech.location_radius
                    }).addTo(this.map);
                    this.circles[tech.id].bindTooltip(`${tech.partner_id ? tech.partner_id[1] : 'Customer'} - Allowed Geofence (${tech.location_radius} m)`, { sticky: true });
                }
            }

            // Custom pin icon
            const icon = window.L.divIcon({
                className: "",
                html: this._buildPinHtml(tech),
                iconSize: [40, 50],
                iconAnchor: [20, 50],
                popupAnchor: [0, -54],
            });

            if (this.markers[tech.id]) {
                this.markers[tech.id]
                    .setLatLng(pos)
                    .setIcon(icon)
                    .getPopup()
                    .setContent(popup);
            } else {
                const marker = window.L.marker(pos, { icon })
                    .addTo(this.map)
                    .bindPopup(popup, { maxWidth: 260 });
                this.markers[tech.id] = marker;
            }
        }

        // Auto-fit bounds
        const itemsToFit = Object.values(this.markers);
        if (this.circles) {
            itemsToFit.push(...Object.values(this.circles));
        }
        if (itemsToFit.length > 0) {
            const group = window.L.featureGroup(itemsToFit);
            this.map.fitBounds(group.getBounds().pad(0.3), { maxZoom: 14 });
        }
    }

    _buildPinHtml(tech) {
        const initials = this._getInitials(tech.employee_id?.[1] || "?");
        const pinBg = tech.is_outside_radius 
            ? "linear-gradient(135deg, #dc3545, #a71d2a)" 
            : "linear-gradient(135deg, #017e84, #014d52)";
        return `
            <div style="
                width:40px; height:40px; border-radius:50% 50% 50% 0;
                transform: rotate(-45deg);
                background: ${pinBg};
                box-shadow: 0 3px 10px rgba(0,0,0,0.3);
                display:flex; align-items:center; justify-content:center;
                border: 2px solid white;
            ">
                <span style="
                    transform: rotate(45deg);
                    color: #fff; font-weight:700; font-size:13px;
                    font-family: sans-serif; line-height:1;
                ">${initials}</span>
            </div>
            ${tech.is_outside_radius ? '<div style="position:absolute; top:-8px; right:-10px; background:white; border-radius:50%; padding:2px;"><i class="fa fa-exclamation-circle text-danger" style="font-size:16px;"></i></div>' : ''}
        `;
    }

    _buildPopup(tech) {
        const userName = tech.employee_id?.[1] || "Unknown";
        const customerName = tech.order_id_partner_id?.[1] || "No customer";
        const orderRef = tech.order_id?.[1] || "";
        const title = tech.order_id_title || "";
        const updated = tech.start_time
            ? `Started: ${new Date(tech.start_time).toLocaleTimeString()}`
            : "";
        const warning = tech.is_outside_radius
            ? `<div style="color:#dc3545; font-weight:bold; margin: 4px 0;"><i class="fa fa-exclamation-triangle"></i> Outside Customer Radius</div>`
            : "";

        return `
            <div class="fs-map-popup">
                <strong>${this._escHtml(userName)}</strong>
                <div class="fs-popup-order">${this._escHtml(orderRef)} — ${this._escHtml(title)}</div>
                <div class="fs-popup-customer">👤 ${this._escHtml(customerName)}</div>
                ${warning}
                <div class="fs-popup-updated">${this._escHtml(updated)}</div>
                <a href="/web#model=field.service.order&id=${tech.id}&view_type=form" target="_blank">
                    Open Order →
                </a>
            </div>
        `;
    }

    _getInitials(name) {
        return name
            .split(" ")
            .slice(0, 2)
            .map((w) => w[0]?.toUpperCase() || "")
            .join("");
    }

    _escHtml(str) {
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    // ── Event handlers ────────────────────────────────────────────────

    async onRefresh() {
        this.state.loading = true;
        await this._loadTechnicians();
        this.notification.add("Map refreshed", { type: "info", sticky: false });
    }

    onTechClick(techId) {
        this.state.selectedId = techId;
        const marker = this.markers[techId];
        if (marker) {
            this.map.panTo(marker.getLatLng(), { animate: true });
            marker.openPopup();
        }
    }

    setFilter(filterType) {
        this.state.filter = filterType;
        this._syncMarkers(this.filteredTechnicians);
    }

    get filteredTechnicians() {
        if (this.state.filter === "in_zone") {
            return this.state.technicians.filter((t) => !t.is_outside_radius);
        } else if (this.state.filter === "away") {
            return this.state.technicians.filter((t) => t.is_outside_radius);
        }
        return this.state.technicians;
    }

    onOpenOrder(techId) {
        const tech = this.state.technicians.find(t => t.id === techId);
        if (!tech) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "field.service.order",
            res_id: tech.order_id[0],
            views: [[false, "form"]],
            target: "current",
        });
    }

    get formattedLastUpdate() {
        if (!this.state.lastUpdated) return "";
        return this.state.lastUpdated.toLocaleTimeString();
    }

    getAvatarInitials(tech) {
        return this._getInitials(tech.employee_id?.[1] || "?");
    }
}

registry.category("actions").add("fs_live_map", FsLiveMap);
