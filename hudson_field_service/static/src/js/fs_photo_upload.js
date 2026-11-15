/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, proxy, signal, useProps } from "@odoo/owl";

/**
 * "Photos" button of a job: opens the device's file picker (or camera) and
 * adds the selected pictures to the job, without any intermediate window.
 */
export class FieldServicePhotoUpload extends Component {
    static template = "hudson_field_service.FieldServicePhotoUpload";
    props = useProps();

    fileInput = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({ uploading: false });
    }

    get record() {
        return this.props.record;
    }

    get isShift() {
        return this.record.resModel === "fs.planning.slot";
    }

    get orderId() {
        if (!this.isShift) {
            return this.record.resId;
        }
        const order = this.record.data.field_service_order_id;
        return order && (order.id ?? order[0]);
    }

    get photoCount() {
        return (this.isShift ? this.record.data.fs_photo_count : this.record.data.photo_count) || 0;
    }

    onClick() {
        if (!this.state.uploading) {
            this.fileInput().click();
        }
    }

    _readFile(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result.split(",")[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    async onFilesSelected(ev) {
        const files = [...ev.target.files].filter((file) => file.type.startsWith("image/"));
        ev.target.value = "";
        if (!files.length) {
            return;
        }
        this.state.uploading = true;
        try {
            await this.record.save();
            const values = [];
            for (const file of files) {
                values.push({ order_id: this.orderId, image: await this._readFile(file), name: file.name });
            }
            await this.orm.create("field.service.image", values);
            await this.record.load();
            this.notification.add(
                files.length === 1 ? "Photo added to the job." : `${files.length} photos added to the job.`,
                { type: "success" }
            );
        } finally {
            this.state.uploading = false;
        }
    }
}

registry.category("view_widgets").add("fs_photo_upload", { component: FieldServicePhotoUpload });
