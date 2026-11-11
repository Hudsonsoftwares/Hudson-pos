/** ********************************************************************************
    Copyright 2024 Subteno - Timothée Vannier (https://www.subteno.com).
    License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
 **********************************************************************************/
import { BinaryField } from "@web/views/fields/binary/binary_field";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import { useService } from "@web/core/utils/hooks";

export class PreviewRecordField extends BinaryField {
    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.fileViewer = useFileViewer();
    }

    onFilePreview() {
        const self = this;
        const data = {
            id: self.props.record.resId,
            filename: self.props.record.data.display_name || "",
            name: self.props.record.data.display_name || "",
            mimetype: self.props.record.data.mimetype,
            model_name: self.props.record.resModel,
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

PreviewRecordField.template = "dms.FilePreviewField";

const previewRecordField = {
    component: PreviewRecordField,
    displayName: _t("Preview Record"),
    supportedTypes: ["binary"],
    extractProps: () => {
        return {};
    },
};
registry.category("fields").add("preview_binary", previewRecordField);
