// /** ********************************************************************************
//     Copyright 2024 Subteno - Timothée Vannier (https://www.subteno.com).
//     License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
//  **********************************************************************************/
import {KanbanRecord} from "@web/views/kanban/kanban_record";
import {useFileViewer} from "@web/core/file_viewer/file_viewer_hook";
import {useService} from "@web/core/utils/hooks";
import {loadPDFJSAssets} from "@web/core/utils/pdfjs";
import {onMounted, onPatched} from "@odoo/owl";

const videoReadableTypes = ["x-matroska", "mp4", "webm"];
const audioReadableTypes = ["mp3", "ogg", "wav", "aac", "mpa", "flac", "m4a"];

export class FileKanbanRecord extends KanbanRecord {
    setup() {
        super.setup();
        this.store = useService("mail.store");
        this.fileViewer = useFileViewer();

        const triggerRender = () => {
            const mimetype = this.props.record?.data?.mimetype;
            if (mimetype === "application/pdf") {
                this.renderPdfThumbnail();
            }
        };

        onMounted(triggerRender);
        onPatched(triggerRender);
    }

    getRootEl() {
        if (typeof this.rootRef === "function") {
            return this.rootRef();
        }
        return this.rootRef?.el || null;
    }

    async renderPdfThumbnail() {
        const rootEl = this.getRootEl();
        if (!rootEl) return;
        const canvas = rootEl.querySelector("canvas.dms_pdf_thumbnail_canvas");
        if (!canvas) return;

        const fileId = this.props.record.resId || this.props.record.data.id;
        if (!fileId) return;

        if (canvas.dataset.renderedFileId === String(fileId)) {
            return;
        }

        try {
            await loadPDFJSAssets();
            const pdfLib = window.pdfjsLib || globalThis.pdfjsLib;
            if (pdfLib && pdfLib.GlobalWorkerOptions && !pdfLib.GlobalWorkerOptions.workerSrc) {
                pdfLib.GlobalWorkerOptions.workerSrc = "/web/static/lib/pdfjs/build/pdf.worker.js";
            }
            const loadingTask = pdfLib.getDocument({
                url: `/web/content/dms.file/${fileId}/content`,
                cMapUrl: '/web/static/lib/pdfjs/build/pdf.js/web/cmaps/',
                cMapPacked: true,
                standardFontDataUrl: '/web/static/lib/pdfjs/build/pdf.js/web/standard_fonts/',
                renderInteractiveForms: true,
            });
            const pdf = await loadingTask.promise;
            const page = await pdf.getPage(1);

            const containerWidth = canvas.parentElement?.clientWidth || 280;
            const viewport = page.getViewport({ scale: 1.0 });
            // Scale so document fills width without left/right gaps
            const targetWidth = Math.max(containerWidth, 280) * 1.5;
            const scale = targetWidth / viewport.width;
            const scaledViewport = page.getViewport({ scale: scale });

            const context = canvas.getContext("2d");
            canvas.width = scaledViewport.width;
            canvas.height = scaledViewport.height;
            canvas.style.width = "100%";
            canvas.style.height = "auto";
            canvas.style.display = "block";

            await page.render({ 
                canvasContext: context, 
                viewport: scaledViewport,
                intent: 'print',
                annotationMode: 2 // ENABLE_FORMS
            }).promise;

            canvas.dataset.renderedFileId = String(fileId);
        } catch (e) {
            console.error("Failed to render PDF thumbnail for file", fileId, e);
        }
    }

    isVideo(mimetype) {
        return videoReadableTypes.includes(mimetype);
    }

    isAudio(mimetype) {
        return audioReadableTypes.includes(mimetype);
    }

    /**
     * @override
     *
     * Top half (preview thumbnail): Opens previewer.
     * Bottom half (name / metadata): Toggles document selection natively.
     */
    onGlobalClick(ev) {
        if (
            ev.target.closest(".o_kanban_manage_toggle_button") ||
            ev.target.closest(".o_dropdown_menu") ||
            ev.target.closest("button") ||
            ev.target.closest("a[type]")
        ) {
            return super.onGlobalClick(ev);
        }

        // 1. Top half: Document preview
        if (ev.target.closest(".o_kanban_dms_file_preview")) {
            const self = this;
            let file_type = "";
            if (self.props.record.data.name) {
                const parts = self.props.record.data.name.split(".");
                if (parts.length > 1) {
                    file_type = parts[parts.length - 1];
                }
            }
            let mimetype = "";

            if (self.isVideo(file_type)) {
                mimetype = `video/${file_type}`;
            } else if (self.isAudio(file_type)) {
                mimetype = "audio/mpeg";
            } else {
                mimetype = self.props.record.data.mimetype;
            }

            const data = {
                id: self.props.record.resId,
                filename: self.props.record.data.name,
                name: self.props.record.data.name,
                mimetype: mimetype,
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
            return;
        }

        // 2. Bottom half: Native record selection toggle
        this.props.record.toggleSelection();
    }
}
