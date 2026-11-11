/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { CharField, charField } from "@web/views/fields/char/char_field";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import { useService } from "@web/core/utils/hooks";

export class DmsFileNameField extends CharField {
    static template = "dms_enterprise_features.DmsFileNameField";
    

    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.fileViewer = useFileViewer();
    }

    get fileIcon() {
        const mimetype = this.props.record.data.mimetype || "";
        if (mimetype === "application/pdf") {
            return "fa-file-pdf-o text-danger";
        } else if (mimetype.startsWith("image/")) {
            return "fa-file-image-o text-info";
        }
        return false;
    }

    onIconClick(ev) {
        ev.stopPropagation(); // prevent opening the form view
        ev.preventDefault();

        const mimetype = this.props.record.data.mimetype;
        const name = this.props.record.data.name;

        // Helper functions from Kanban Record
        const videoReadableTypes = ["x-matroska", "mp4", "webm"];
        const audioReadableTypes = ["mp3", "ogg", "wav", "aac", "mpa", "flac", "m4a"];

        let file_type = "";
        if (name) {
            const parts = name.split(".");
            if (parts.length > 1) {
                file_type = parts[parts.length - 1];
            }
        }

        let viewerMimetype = "";
        if (videoReadableTypes.includes(file_type)) {
            viewerMimetype = `video/${file_type}`;
        } else if (audioReadableTypes.includes(file_type)) {
            viewerMimetype = "audio/mpeg";
        } else {
            viewerMimetype = mimetype;
        }

        const data = {
            id: this.props.record.resId,
            filename: name,
            name: name,
            mimetype: viewerMimetype,
            model_name: this.props.record.resModel,
        };

        let attachment;
        if (this.store && this.store["ir.attachment"]) {
            attachment = this.store["ir.attachment"].insert(data);
        } else if (this.store && this.store.Attachment) {
            attachment = this.store.Attachment.insert(data);
        } else if (this.store && this.store.models && this.store.models.Attachment) {
            attachment = this.store.models.Attachment.insert(data);
        } else {
            attachment = data;
        }

        this.fileViewer.open(attachment);
    }
}

registry.category("fields").add("dms_file_name_preview", {
    ...charField,
    component: DmsFileNameField,
});
