/** @odoo-module */

import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import * as owl from "@odoo/owl";

const onWillStart = owl.onWillStart || ((fn) => fn());
const onWillDestroy = owl.onWillDestroy || (() => {});
const useState = owl.useState || owl.reactive || ((obj) => obj);

patch(Navbar.prototype, {
    setup() {
        super.setup(...arguments);
        this.bus = useService("bus_service");
        this.toggleDeliveryDropdown = this.toggleDeliveryDropdown.bind(this);
        
        const initialDeliveryState = {
            isOpen: false,
            newOrdersCount: 0,
            platforms: []
        };
        
        try {
            this.deliveryState = useState(initialDeliveryState);
        } catch (e) {
            this.deliveryState = initialDeliveryState;
        }

        this._deliveryNotificationHandler = this._onDeliveryNotification.bind(this);

        onWillStart(async () => {
            await this._loadDeliveryData();
            if (this.bus && this.pos && this.pos.config) {
                this.bus.addEventListener("notification", this._deliveryNotificationHandler);
                this.bus.addChannel(`pos_delivery_connector-${this.pos.config.id}`);
            }
        });

        onWillDestroy(() => {
            if (this.bus) {
                this.bus.removeEventListener("notification", this._deliveryNotificationHandler);
            }
        });
    },

    get deliveryDropdownOpen() {
        return this.deliveryState ? this.deliveryState.isOpen : false;
    },

    get deliveryNewCount() {
        return this.deliveryState ? this.deliveryState.newOrdersCount : 0;
    },

    get deliveryPlatforms() {
        return this.deliveryState ? this.deliveryState.platforms : [];
    },

    toggleDeliveryDropdown() {
        if (!this.deliveryState) return;
        this.deliveryState.isOpen = !this.deliveryState.isOpen;
        if (this.deliveryState.isOpen) {
            this._loadDeliveryData();
        }
    },

    _playDeliverySound() {
        try {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextClass) return;
            const ctx = new AudioContextClass();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(587.33, ctx.currentTime);
            osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.15);
            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.4);
        } catch (e) {
            console.debug("Audio notification blocked or unsupported", e);
        }
    },

    async _loadDeliveryData() {
        try {
            const orders = (this.pos && this.pos.get_order_list) ? this.pos.get_order_list() : (this.pos && this.pos.orders ? this.pos.orders : []);
            if (!Array.isArray(orders)) {
                if (this.deliveryState) {
                    this.deliveryState.platforms = [];
                    this.deliveryState.newOrdersCount = 0;
                }
                return;
            }

            const deliveryOrders = orders.filter(o => o && o.is_delivery_order);
            const newCount = deliveryOrders.filter(o => !o.delivery_status || o.delivery_status === 'new' || o.state === 'draft').length;
            
            const platformsMap = {};
            for (const o of deliveryOrders) {
                if (!o) continue;
                let pid = 'general';
                let pname = 'Online Delivery';

                if (o.delivery_platform_id) {
                    if (Array.isArray(o.delivery_platform_id)) {
                        pid = o.delivery_platform_id[0] || 'general';
                        pname = o.delivery_platform_id[1] || 'Online Delivery';
                    } else if (typeof o.delivery_platform_id === 'object' && o.delivery_platform_id !== null) {
                        pid = o.delivery_platform_id.id || 'general';
                        pname = o.delivery_platform_id.name || 'Online Delivery';
                    } else if (typeof o.delivery_platform_id === 'number' || typeof o.delivery_platform_id === 'string') {
                        pid = o.delivery_platform_id;
                        if (this.pos && this.pos.models && this.pos.models['pos.delivery.platform']) {
                            const rec = this.pos.models['pos.delivery.platform'].get(pid);
                            pname = (rec && rec.name) ? rec.name : `Platform #${pid}`;
                        } else {
                            pname = `Platform #${pid}`;
                        }
                    }
                }

                if (!platformsMap[pid]) {
                    platformsMap[pid] = { id: pid, name: pname, newCount: 0, ongoingCount: 0, doneCount: 0 };
                }

                if (o.delivery_status === 'delivered' || o.state === 'paid' || o.state === 'done') {
                    platformsMap[pid].doneCount++;
                } else if (o.delivery_status === 'new' || o.state === 'draft') {
                    platformsMap[pid].newCount++;
                } else {
                    platformsMap[pid].ongoingCount++;
                }
            }

            if (this.deliveryState) {
                this.deliveryState.platforms = Object.values(platformsMap);
                this.deliveryState.newOrdersCount = newCount;
            }
        } catch (err) {
            console.warn("Error loading delivery initial data:", err);
            if (this.deliveryState) {
                this.deliveryState.platforms = [];
                this.deliveryState.newOrdersCount = 0;
            }
        }
    },

    async _onDeliveryNotification({ detail: notifications }) {
        let hasNewDelivery = false;
        if (Array.isArray(notifications)) {
            for (const notif of notifications) {
                if (notif && notif.type === "DELIVERY_ORDER_SYNC") {
                    hasNewDelivery = true;
                }
            }
        }
        if (hasNewDelivery) {
            this._playDeliverySound();
            if (this.pos && this.pos._loadMissingPosOrders) {
                await this.pos._loadMissingPosOrders();
            }
            await this._loadDeliveryData();
        }
    }
});
