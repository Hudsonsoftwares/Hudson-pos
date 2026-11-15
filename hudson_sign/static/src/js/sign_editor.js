/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, proxy, useProps, t, onMounted, onWillUnmount, onPatched } from "@odoo/owl";
import { loadPDFJSAssets } from "@web/core/utils/pdfjs";
import { Dialog } from "@web/core/dialog/dialog";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

// -----------------------------------------------------------------------------
// Role Color Palette (keep in sync with ROLE_PALETTE in hudson_sign_template.py)
// -----------------------------------------------------------------------------
export const ROLE_PALETTE = [
    { color: "#e2dcf3", borderColor: "#a495d6", textColor: "#2e2252", name: "Lavender" },
    { color: "#d1fae5", borderColor: "#10b981", textColor: "#065f46", name: "Emerald" },
    { color: "#fef3c7", borderColor: "#f59e0b", textColor: "#92400e", name: "Amber" },
    { color: "#e0e7ff", borderColor: "#6366f1", textColor: "#3730a3", name: "Indigo" },
    { color: "#fce7f3", borderColor: "#ec4899", textColor: "#9d174d", name: "Rose" },
    { color: "#e0f2fe", borderColor: "#0ea5e9", textColor: "#075985", name: "Sky" },
    { color: "#ffedd5", borderColor: "#f97316", textColor: "#9a3412", name: "Orange" },
    { color: "#f3e8ff", borderColor: "#a855f7", textColor: "#6b21a8", name: "Purple" },
    { color: "#ccfbf1", borderColor: "#14b8a6", textColor: "#115e59", name: "Teal" },
];

// Fields whose placeholder is shown (and editable) in the editor
const PLACEHOLDER_TYPES = ["signature", "initial", "text", "multiline", "selection", "date", "stamp", "strikethrough"];
// Fields whose text can be aligned
const ALIGN_TYPES = ["text", "multiline", "selection", "date"];
// Fields whose placeholder spans several lines
const MULTILINE_TYPES = ["multiline", "stamp"];
const SQUARE_TYPES = ["checkbox", "radio"];

const SAVE_DELAY = 700;
const MIN_ZOOM = 25;
const MAX_ZOOM = 400;
const AUTO_ZOOM_MAX = 1.5;
const PAGE_GAP = 12;

export const ZOOM_PRESETS = [
    { value: "auto", label: "Automatic Zoom" },
    { value: "page-actual", label: "Actual Size" },
    { value: "page-fit", label: "Page Fit" },
    { value: "page-width", label: "Page Width" },
    { value: "50", label: "50%" },
    { value: "75", label: "75%" },
    { value: "100", label: "100%" },
    { value: "125", label: "125%" },
    { value: "150", label: "150%" },
    { value: "200", label: "200%" },
    { value: "300", label: "300%" },
    { value: "400", label: "400%" },
];

// Default size (in px at 100% zoom) of a field dropped on the document
const DEFAULT_SIZES = {
    signature: [180, 36],
    initial: [80, 36],
    multiline: [220, 70],
    stamp: [220, 96],
    checkbox: [26, 26],
    radio: [26, 26],
    strikethrough: [160, 26],
};

function multiplyTransform(m1, m2) {
    return [
        m1[0] * m2[0] + m1[2] * m2[1],
        m1[1] * m2[0] + m1[3] * m2[1],
        m1[0] * m2[2] + m1[2] * m2[3],
        m1[1] * m2[2] + m1[3] * m2[3],
        m1[0] * m2[4] + m1[2] * m2[5] + m1[4],
        m1[1] * m2[4] + m1[3] * m2[5] + m1[5],
    ];
}

// -----------------------------------------------------------------------------
// Inline SVG icon: Odoo 20 no longer ships the Font Awesome stylesheet in the
// backend, so "fa fa-*" classes render nothing. Names follow Font Awesome
// (with or without the "fa-" prefix) so the field types keep their icon keys.
// -----------------------------------------------------------------------------
export class SignIcon extends Component {
    static template = "hudson_sign.SignIcon";
    props = useProps({
        name: t.string(),
        size: t.or([t.number(), t.string()]).optional(16),
        cls: t.string().optional(""),
    });

    get name() {
        return this.props.name.replace(/^fa-/, "");
    }
}

// -----------------------------------------------------------------------------
// Signer Settings Dialog Component
// -----------------------------------------------------------------------------
export class SignerSettingsDialog extends Component {
    static template = "hudson_sign.SignerSettingsDialog";
    static components = { Dialog, SignIcon };
    props = useProps({
        close: t.function().optional(),
        role: t.any().optional(),
        onConfirm: t.function().optional(),
    });

    setup() {
        this.palette = ROLE_PALETTE;
        this.state = proxy({
            name: this.props.role.name || "",
            authMethod: this.props.role.authMethod || "none",
            canDelegate: this.props.role.canDelegate || false,
            color: this.props.role.color || ROLE_PALETTE[0].color,
            borderColor: this.props.role.borderColor || ROLE_PALETTE[0].borderColor,
            textColor: this.props.role.textColor || ROLE_PALETTE[0].textColor,
        });
    }

    selectPalette(theme) {
        this.state.color = theme.color;
        this.state.borderColor = theme.borderColor;
        this.state.textColor = theme.textColor;
    }

    onConfirm() {
        this.props.onConfirm({ ...this.state });
        this.props.close();
    }
}

// -----------------------------------------------------------------------------
// Sign Template Editor
// Used by the Sign app and by "Setup Signatures" in the Documents app.
// -----------------------------------------------------------------------------
export class HudsonSignEditor extends Component {
    static template = "hudson_sign.SignEditor";
    static components = { SignIcon };
    props = useProps({
        ...standardActionServiceProps,
    });

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.zoomPresets = ZOOM_PRESETS;

        const action = this.props.action || {};
        const context = action.context || {};
        let templateId = context.active_id || action.params?.active_id;
        if (Array.isArray(templateId)) {
            templateId = templateId[0];
        }
        this.templateId = parseInt(templateId, 10) || false;
        // Opened from Sign > Templates (not from the Documents dashboard)
        this.fromTemplates = Boolean(context.hudson_sign_from_templates);

        this._saveTimer = null;
        this._savePromise = Promise.resolve();
        this._dirty = false;
        this._newRoleSeq = 0;
        this._nextItemId = 1;
        this._textCache = {};
        // Page sizes at 100% zoom, kept outside the reactive state
        this.basePages = [];

        this.state = proxy({
            template: null,
            views: {},
            allTags: [],
            templateTags: [],
            tagQuery: "",
            tagDropdownOpen: false,

            roles: [],
            currentRoleIndex: 0,
            tools: [],
            items: [],

            pages: [],
            zoomLevel: 100,
            zoomMode: "auto",
            currentPage: 1,
            showThumbnails: false,

            searchOpen: false,
            searchQuery: "",
            searchMatches: [],
            searchIndex: 0,

            docMenuOpen: false,
            gearMenuOpen: false,
            previewMode: false,
            renamingDocument: false,
            documentNameDraft: "",

            // Drag state
            dragType: null,
            dragTool: null,
            mouseX: 0,
            mouseY: 0,

            boxDragId: null,
            boxResizeId: null,
            boxResizeDir: null,
            dropInvalid: false, // Field being moved is (partially) outside the pages
            editingBoxId: null, // For properties popover
            dragStartX: 0,
            dragStartY: 0,
            boxStartRect: null,

            needsRender: false,
            needsThumbRender: false,
            isLoading: true,
            errorMessage: false,
            saving: false,

            openDropdownRoleId: null,
        });

        this.onOutsidePointerDown = (e) => {
            if (this.state.openDropdownRoleId && !e.target.closest('.o_signer_menu_toggle') && !e.target.closest('.o_signer_dropdown_menu')) {
                this.state.openDropdownRoleId = null;
            }
            if (this.state.docMenuOpen && !e.target.closest('.o_sign_doc_menu')) {
                this.state.docMenuOpen = false;
            }
            if (this.state.gearMenuOpen && !e.target.closest('.o_sign_gear_menu')) {
                this.state.gearMenuOpen = false;
            }
            if (this.state.editingBoxId && !e.target.closest('.o_dms_box_popover') && !e.target.closest('.signature-box')) {
                this.closePopover();
            }
        };

        this.onWindowMouseMoveBound = this.onWindowMouseMove.bind(this);
        this.onWindowMouseUpBound = this.onWindowMouseUp.bind(this);
        this.onKeyDownBound = this.onKeyDown.bind(this);
        this.onResizeBound = () => {
            if (["auto", "page-fit", "page-width"].includes(this.state.zoomMode)) {
                this.setZoomMode(this.state.zoomMode);
            }
            this.positionPopover();
        };

        onMounted(async () => {
            window.addEventListener('mousemove', this.onWindowMouseMoveBound);
            window.addEventListener('mouseup', this.onWindowMouseUpBound);
            window.addEventListener('pointerdown', this.onOutsidePointerDown, true);
            window.addEventListener('keydown', this.onKeyDownBound);
            window.addEventListener('resize', this.onResizeBound);
            await this.loadData();
        });

        onPatched(() => {
            this.positionPopover();
            if (this.state.needsRender) {
                this.state.needsRender = false;
                this.renderAllPages();
            }
            if (this.state.needsThumbRender) {
                this.state.needsThumbRender = false;
                this.renderThumbnails();
            }
        });

        onWillUnmount(() => {
            window.removeEventListener('mousemove', this.onWindowMouseMoveBound);
            window.removeEventListener('mouseup', this.onWindowMouseUpBound);
            window.removeEventListener('pointerdown', this.onOutsidePointerDown, true);
            window.removeEventListener('keydown', this.onKeyDownBound);
            window.removeEventListener('resize', this.onResizeBound);
            this._stopAutoScroll();
            this.saveNow();
        });
    }

    // ---- Data Loading -------------------------------------------------------

    async loadData() {
        if (!this.templateId) {
            return this.actionService.doAction("hudson_sign.action_hudson_sign_template", { clearBreadcrumbs: true });
        }
        const data = await this.orm.call("hudson.sign.template", "get_editor_data", [[this.templateId]]);
        this.state.template = data.template;
        this.state.views = data.views;
        this.state.tools = data.tools;
        this.state.allTags = data.tags;
        this.state.templateTags = data.tags.filter(tag => data.template.tag_ids.includes(tag.id));
        this.state.roles = data.roles;
        // Positions are ratios until the pages are measured (see renderPDF)
        this.pendingItems = data.items;

        try {
            const response = await fetch(`/web/content/${data.template.attachment_id}`);
            if (!response.ok) {
                throw new Error(response.statusText || "Could not download the PDF document.");
            }
            await this.renderPDF(new Uint8Array(await response.arrayBuffer()));
        } catch (err) {
            this.state.isLoading = false;
            this.state.errorMessage = err.message || "Failed to render PDF preview.";
        }
    }

    async renderPDF(bytes) {
        this.state.isLoading = true;
        this.state.errorMessage = false;
        await loadPDFJSAssets();
        const pdfLib = window.pdfjsLib || globalThis.pdfjsLib;
        if (!pdfLib) {
            throw new Error("PDF.js engine is unavailable");
        }
        if (pdfLib.GlobalWorkerOptions && !pdfLib.GlobalWorkerOptions.workerSrc) {
            pdfLib.GlobalWorkerOptions.workerSrc = "/web/static/lib/pdfjs/build/pdf.worker.js";
        }
        // Kept outside the reactive state: PDF.js objects must not be proxied
        this.pdfDoc = await pdfLib.getDocument({
            data: bytes,
            cMapUrl: '/web/static/lib/pdfjs/build/pdf.js/web/cmaps/',
            cMapPacked: true,
            standardFontDataUrl: '/web/static/lib/pdfjs/build/pdf.js/web/standard_fonts/',
        }).promise;
        this.basePages = [];
        for (let i = 1; i <= this.pdfDoc.numPages; i++) {
            const page = await this.pdfDoc.getPage(i);
            const viewport = page.getViewport({ scale: 1 });
            this.basePages.push({ num: i, width: viewport.width, height: viewport.height });
        }
        this.state.zoomLevel = this.computeModeZoom(this.state.zoomMode) || 100;
        this.state.pages = this.computePages();

        if (this.pendingItems) {
            this.state.items = this.pendingItems.map(item => {
                const page = this.getPage(item.page);
                return {
                    ...item,
                    x: item.x * page.width,
                    y: item.y * page.height,
                    width: item.width * page.width,
                    height: item.height * page.height,
                };
            });
            this.pendingItems = null;
        }
        this.state.isLoading = false;
        this.state.needsRender = true;
        this.state.needsThumbRender = this.state.showThumbnails;
    }

    computePages() {
        const scale = (this.state.zoomLevel || 100) / 100;
        return this.basePages.map(p => ({ num: p.num, width: p.width * scale, height: p.height * scale }));
    }

    async renderAllPages() {
        if (!this.pdfDoc) return;
        this.renderTasks = this.renderTasks || {};
        const outputScale = window.devicePixelRatio || 1;

        for (const pageInfo of this.state.pages) {
            const canvas = document.getElementById('hudson-sign-canvas-' + pageInfo.num);
            if (!canvas) continue;

            if (this.renderTasks[pageInfo.num]) {
                try {
                    this.renderTasks[pageInfo.num].cancel();
                } catch (_) {}
            }

            try {
                const page = await this.pdfDoc.getPage(pageInfo.num);
                const viewport = page.getViewport({ scale: (this.state.zoomLevel || 100) / 100 });

                canvas.width = Math.floor(viewport.width * outputScale);
                canvas.height = Math.floor(viewport.height * outputScale);
                canvas.style.width = Math.floor(viewport.width) + "px";
                canvas.style.height = Math.floor(viewport.height) + "px";

                const renderTask = page.render({
                    canvasContext: canvas.getContext('2d'),
                    transform: outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : null,
                    viewport,
                });
                this.renderTasks[pageInfo.num] = renderTask;
                await renderTask.promise;
            } catch (e) {
                if (e?.name !== "RenderingCancelledException") {
                    console.error("Canvas render error:", e);
                }
            }
        }
    }

    async renderThumbnails() {
        if (!this.pdfDoc) return;
        for (const base of this.basePages) {
            const canvas = document.getElementById('hudson-sign-thumb-' + base.num);
            if (!canvas || canvas.dataset.rendered) continue;
            try {
                const page = await this.pdfDoc.getPage(base.num);
                const viewport = page.getViewport({ scale: 110 / base.width });
                canvas.width = Math.floor(viewport.width);
                canvas.height = Math.floor(viewport.height);
                await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
                canvas.dataset.rendered = "1";
            } catch (e) {
                if (e?.name !== "RenderingCancelledException") {
                    console.error("Thumbnail render error:", e);
                }
            }
        }
    }

    retryLoad() {
        this.loadData();
    }

    // ---- Saving -------------------------------------------------------------

    scheduleSave() {
        this._dirty = true;
        clearTimeout(this._saveTimer);
        this._saveTimer = setTimeout(() => this.saveNow(), SAVE_DELAY);
    }

    saveNow() {
        clearTimeout(this._saveTimer);
        if (!this._dirty || !this.templateId || this.pendingItems || !this.state.pages.length) {
            return this._savePromise;
        }
        this._dirty = false;
        this._savePromise = this._savePromise.then(() => this._save()).catch((err) => {
            this._dirty = true;
            this.notification.add(err?.data?.message || err?.message || "Could not save the template.", { type: "danger" });
        });
        return this._savePromise;
    }

    async _save() {
        const roles = this.state.roles.map(role => ({
            id: role.id,
            name: role.name,
            color: role.color,
            borderColor: role.borderColor,
            textColor: role.textColor,
            authMethod: role.authMethod,
            canDelegate: role.canDelegate,
        }));
        const items = this.state.items.map(item => {
            const page = this.getPage(item.page);
            return {
                typeId: item.typeId,
                roleId: item.roleId,
                page: item.page,
                x: item.x / page.width,
                y: item.y / page.height,
                width: item.width / page.width,
                height: item.height / page.height,
                placeholder: item.placeholder,
                alignment: item.alignment,
                mandatory: item.mandatory,
                readonly: item.readonly,
                options: item.options,
                radioGroupName: item.radioGroupName,
                radioOptionValue: item.radioOptionValue,
            };
        });
        this.state.saving = true;
        try {
            const roleMap = await this.orm.call("hudson.sign.template", "save_from_editor", [[this.templateId], roles, items]);
            // Swap the temporary ids of new roles for their database ids
            for (const role of this.state.roles) {
                const dbId = roleMap[String(role.id)];
                if (dbId && dbId !== role.id) {
                    for (const item of this.state.items) {
                        if (item.roleId === role.id) item.roleId = dbId;
                    }
                    if (this.state.openDropdownRoleId === role.id) this.state.openDropdownRoleId = dbId;
                    role.id = dbId;
                }
            }
        } finally {
            this.state.saving = false;
        }
    }

    // ---- Navigation ---------------------------------------------------------

    get backLabel() {
        const breadcrumbs = this.env.config?.breadcrumbs || [];
        if (breadcrumbs.length > 1) {
            return breadcrumbs[breadcrumbs.length - 2].name;
        }
        return this.fromTemplates ? "Templates" : "Documents";
    }

    /** A document uploaded in the Documents dashboard that is not a template yet */
    get isUnsavedDraft() {
        const template = this.state.template;
        return Boolean(template && !template.active && !template.dms_file_id && !this.fromTemplates);
    }

    async onBack() {
        await this.saveNow();
        if (this.isUnsavedDraft) {
            this.dialog.add(ConfirmationDialog, {
                title: "Confirmation",
                body: "Your changes will be discarded. Would you like to save them as a template?",
                confirmLabel: "Save & close",
                confirm: async () => {
                    await this.saveAsTemplate();
                    return this._leaveEditor();
                },
                cancelLabel: "Discard",
                cancel: () => this._leaveEditor(),
                // Closing the dialog keeps the editor open
                dismiss: () => {},
            });
            return;
        }
        return this._leaveEditor();
    }

    _leaveEditor() {
        const fileId = this.state.template?.dms_file_id;
        if (fileId) {
            return this.actionService.doAction({
                type: "ir.actions.act_window",
                res_model: "dms.file",
                res_id: fileId,
                views: [[false, "form"]],
                target: "current",
            });
        }
        const breadcrumbs = this.env.config?.breadcrumbs || [];
        if (breadcrumbs.length > 1) {
            return breadcrumbs[breadcrumbs.length - 2].onSelected();
        }
        const action = this.fromTemplates ? "hudson_sign.action_hudson_sign_template" : "hudson_sign.action_hudson_sign_request";
        return this.actionService.doAction(action, { clearBreadcrumbs: true });
    }

    async openSendModal(isSignNow) {
        if (!this.state.items.length) {
            this.notification.add("Please add at least one field to the document.", { type: "warning" });
            return;
        }
        await this.saveNow();
        const action = await this.orm.call("hudson.sign.template", isSignNow ? "action_sign_now" : "action_send", [[this.templateId]]);
        return this.actionService.doAction(action);
    }

    toggleGearMenu() {
        this.state.gearMenuOpen = !this.state.gearMenuOpen;
    }

    get canSaveAsTemplate() {
        const template = this.state.template;
        return Boolean(template && (!template.active || template.dms_file_id));
    }

    /**
     * Save icon of the control panel: flush the fields right away. A draft
     * uploaded in the Documents dashboard becomes a template at the same time.
     */
    async onSaveClick() {
        if (this.state.saving || this._savingTemplate) {
            return;
        }
        this._savingTemplate = true;
        try {
            if (this.pendingItems || !this.state.pages.length) {
                this.notification.add("Please wait until the document has loaded.", { type: "warning" });
                return;
            }
            this._dirty = true;
            await this.saveNow();
            if (this._dirty) {
                // The save failed: the error was already notified
                return;
            }
            if (this.isUnsavedDraft) {
                return await this.saveAsTemplate();
            }
            this.notification.add(`"${this.state.template.name}" has been saved.`, { type: "success" });
        } finally {
            this._savingTemplate = false;
        }
    }

    async saveAsTemplate() {
        this.state.gearMenuOpen = false;
        await this.saveNow();
        const template = await this.orm.call("hudson.sign.template", "action_save_as_template", [[this.templateId]]);
        if (!template.copied) {
            this.state.template.active = true;
            this.notification.add(`"${template.name}" is now available in Templates.`, { type: "success" });
            return;
        }
        this.notification.add(`A copy of "${template.name}" is now available in Templates.`, {
            type: "success",
            buttons: [{
                name: "Open",
                primary: true,
                onClick: () => this.actionService.doAction(template.action),
            }],
        });
    }

    async togglePreview() {
        this.state.gearMenuOpen = false;
        this.closePopover();
        await this.saveNow();
        this.state.previewMode = !this.state.previewMode;
        // The sidebar is hidden in preview: refit the document to the new width
        if (["auto", "page-fit", "page-width"].includes(this.state.zoomMode)) {
            setTimeout(() => this.setZoomMode(this.state.zoomMode));
        }
    }

    openTemplateProperties() {
        this.state.gearMenuOpen = false;
        this.dialog.add(FormViewDialog, {
            resModel: "hudson.sign.template",
            resId: this.templateId,
            viewId: this.state.views.template_form || false,
            title: "Template Properties",
            canExpand: false,
            context: { hudson_sign_editor: true },
            onRecordSaved: async () => {
                const [template] = await this.orm.read("hudson.sign.template", [this.templateId], ["name", "tag_ids"]);
                this.state.template.name = template.name;
                const tags = await this.orm.searchRead("hudson.sign.template.tag", [], ["name", "color"]);
                this.state.allTags = tags;
                this.state.templateTags = tags.filter(tag => template.tag_ids.includes(tag.id));
            },
        });
    }

    // ---- Document -----------------------------------------------------------

    toggleDocMenu() {
        this.state.docMenuOpen = !this.state.docMenuOpen;
    }

    startRenameDocument() {
        this.state.docMenuOpen = false;
        this.state.documentNameDraft = this.state.template.document_name || "";
        this.state.renamingDocument = true;
        setTimeout(() => {
            const input = document.querySelector('.o_hudson_sign_editor .o_sign_doc_rename');
            input?.focus();
            input?.select();
        });
    }

    async onDocumentNameKeydown(ev) {
        if (ev.key === "Enter") {
            await this.confirmRenameDocument();
        } else if (ev.key === "Escape") {
            this.state.renamingDocument = false;
        }
    }

    async confirmRenameDocument() {
        if (!this.state.renamingDocument) return;
        this.state.renamingDocument = false;
        const name = this.state.documentNameDraft.trim();
        if (!name || name === this.state.template.document_name) return;
        this.state.template.document_name = await this.orm.call(
            "hudson.sign.template", "rename_document", [[this.templateId], name]);
    }

    downloadDocument() {
        this.state.docMenuOpen = false;
        window.open(`/web/content/${this.state.template.attachment_id}?download=true`, "_blank");
    }

    // ---- Tags ---------------------------------------------------------------

    get tagsModel() {
        return "hudson.sign.template";
    }

    get tagsResId() {
        return this.templateId;
    }

    get availableTags() {
        const query = this.state.tagQuery.trim().toLowerCase();
        return this.state.allTags.filter(tag =>
            !this.state.templateTags.find(tt => tt.id === tag.id) &&
            (!query || tag.name.toLowerCase().includes(query)));
    }

    get canCreateTag() {
        const query = this.state.tagQuery.trim().toLowerCase();
        return query && !this.state.allTags.find(tag => tag.name.toLowerCase() === query);
    }

    onTagInput(ev) {
        this.state.tagQuery = ev.target.value;
        this.state.tagDropdownOpen = true;
    }

    onTagBlur() {
        // Let a click on a suggestion land before closing
        setTimeout(() => (this.state.tagDropdownOpen = false), 150);
    }

    async onTagKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            const [first] = this.availableTags;
            if (first) {
                await this.addTag(first.id);
            } else if (this.canCreateTag) {
                await this.createTag();
            }
        } else if (ev.key === "Backspace" && !this.state.tagQuery && this.state.templateTags.length) {
            await this.removeTag(this.state.templateTags.at(-1).id);
        } else if (ev.key === "Escape") {
            this.state.tagDropdownOpen = false;
        }
    }

    async addTag(tagId) {
        this.state.tagQuery = "";
        await this.orm.write(this.tagsModel, [this.tagsResId], { tag_ids: [[4, tagId]] });
        const tag = this.state.allTags.find(tag => tag.id === tagId);
        if (tag) this.state.templateTags.push(tag);
    }

    async createTag() {
        const name = this.state.tagQuery.trim();
        if (!name) return;
        const [tagId] = await this.orm.create("hudson.sign.template.tag", [{ name }]);
        this.state.allTags.push({ id: tagId, name, color: 0 });
        await this.addTag(tagId);
    }

    async removeTag(tagId) {
        await this.orm.write(this.tagsModel, [this.tagsResId], { tag_ids: [[3, tagId]] });
        this.state.templateTags = this.state.templateTags.filter(tag => tag.id !== tagId);
    }

    // ---- Roles --------------------------------------------------------------

    selectRole(index) {
        this.state.currentRoleIndex = index;
    }

    toggleRoleDropdown(roleId) {
        this.state.openDropdownRoleId = this.state.openDropdownRoleId === roleId ? null : roleId;
    }

    editRoleAndClose(roleId) {
        this.state.openDropdownRoleId = null;
        this.editRole(roleId);
    }

    deleteRoleAndClose(roleId) {
        this.state.openDropdownRoleId = null;
        this.deleteRole(roleId);
    }

    editRole(roleId) {
        const role = this.state.roles.find(r => r.id === roleId);
        if (!role) return;
        this.dialog.add(SignerSettingsDialog, {
            role,
            onConfirm: (data) => {
                Object.assign(role, data);
                this.scheduleSave();
            },
        });
    }

    deleteRole(roleId) {
        this.state.roles = this.state.roles.filter(r => r.id !== roleId);
        this.state.items = this.state.items.filter(i => i.roleId !== roleId);
        if (this.state.currentRoleIndex >= this.state.roles.length) {
            this.state.currentRoleIndex = Math.max(0, this.state.roles.length - 1);
        }
        this.scheduleSave();
    }

    onAddRole() {
        const nextIdx = this.state.roles.length + 1;
        const theme = ROLE_PALETTE[(nextIdx - 1) % ROLE_PALETTE.length];
        this.state.roles.push({
            id: `new_${++this._newRoleSeq}`,
            name: `Signer ${nextIdx}`,
            color: theme.color,
            borderColor: theme.borderColor,
            textColor: theme.textColor,
            authMethod: "none",
            canDelegate: false,
        });
        this.state.currentRoleIndex = this.state.roles.length - 1;
        this.scheduleSave();
    }

    get currentRole() {
        return this.state.roles[this.state.currentRoleIndex] || this.state.roles[0] || {
            id: false,
            name: "Signer 1",
            ...ROLE_PALETTE[0],
        };
    }

    getRole(roleId) {
        return this.state.roles.find(r => r.id === roleId) || this.currentRole;
    }

    getRoleColor(roleId) {
        return this.getRole(roleId).color;
    }

    getRoleBorderColor(roleId) {
        return this.getRole(roleId).borderColor;
    }

    getRoleTextColor(roleId) {
        return this.getRole(roleId).textColor;
    }

    getRoleBoxCount(roleId) {
        return this.state.items.filter(i => i.roleId === roleId).length;
    }

    // ---- Field types --------------------------------------------------------

    openAddFieldDialog() {
        this.dialog.add(FormViewDialog, {
            resModel: "hudson.sign.item.type",
            viewId: this.state.views.item_type_form || false,
            title: "Add Field",
            canExpand: false,
            context: { default_item_type: "text", default_mandatory: true },
            onRecordSaved: async () => {
                this.state.tools = await this.orm.call("hudson.sign.item.type", "get_editor_tools", []);
            },
        });
    }

    // ---- Zoom ---------------------------------------------------------------

    get zoomSelectValue() {
        const mode = this.state.zoomMode;
        if (mode === "custom") {
            const preset = ZOOM_PRESETS.find(p => p.value === String(this.state.zoomLevel));
            return preset ? preset.value : "custom";
        }
        return mode;
    }

    get scrollEl() {
        return document.querySelector('.o_hudson_sign_editor .o_sign_pdf_scroll');
    }

    computeModeZoom(mode) {
        const first = this.basePages[0];
        if (!first) return null;
        if (mode === "page-actual") return 100;
        if (!isNaN(parseInt(mode, 10))) return parseInt(mode, 10);
        const el = this.scrollEl;
        const availWidth = Math.max(200, (el ? el.clientWidth : 900) - 2 * PAGE_GAP);
        const availHeight = Math.max(200, (el ? el.clientHeight : 700) - 2 * PAGE_GAP);
        const widthScale = availWidth / first.width;
        const heightScale = availHeight / first.height;
        let scale;
        if (mode === "page-width") {
            scale = widthScale;
        } else if (mode === "page-fit") {
            scale = Math.min(widthScale, heightScale);
        } else {
            scale = Math.min(AUTO_ZOOM_MAX, widthScale);
        }
        return Math.floor(scale * 100);
    }

    zoomIn() {
        this.setZoom((this.state.zoomLevel || 100) + 10);
    }

    zoomOut() {
        this.setZoom((this.state.zoomLevel || 100) - 10);
    }

    onZoomSelect(ev) {
        const value = ev.target.value;
        if (value !== "custom") {
            this.setZoomMode(value);
        }
    }

    setZoomMode(mode) {
        const zoom = this.computeModeZoom(mode);
        if (zoom) {
            this.setZoom(zoom, mode);
        }
    }

    async setZoom(val, mode = "custom") {
        let newZoom = Math.round(val);
        if (isNaN(newZoom) || newZoom < MIN_ZOOM) newZoom = MIN_ZOOM;
        if (newZoom > MAX_ZOOM) newZoom = MAX_ZOOM;
        this.state.zoomMode = mode;
        if (newZoom === this.state.zoomLevel || !this.pdfDoc) return;

        const ratio = newZoom / (this.state.zoomLevel || 100);
        this.state.zoomLevel = newZoom;
        for (const item of this.state.items) {
            item.x *= ratio;
            item.y *= ratio;
            item.width *= ratio;
            item.height *= ratio;
        }
        this.state.pages = this.computePages();
        this.state.needsRender = true;
    }

    get fieldFontSize() {
        return Math.max(9, Math.round(13 * (this.state.zoomLevel || 100) / 100));
    }

    // ---- Pages --------------------------------------------------------------

    onViewerScroll(ev) {
        this.positionPopover();
        const el = ev.currentTarget;
        const middle = el.scrollTop + el.clientHeight / 3;
        let current = 1;
        for (const pageEl of el.querySelectorAll('.o_dms_pdf_page')) {
            if (pageEl.offsetTop <= middle) {
                current = parseInt(pageEl.dataset.pageNum, 10);
            }
        }
        if (current !== this.state.currentPage) {
            this.state.currentPage = current;
        }
    }

    goToPage(num) {
        const pageNum = Math.min(Math.max(1, parseInt(num, 10) || 1), this.state.pages.length || 1);
        this.state.currentPage = pageNum;
        const el = this.scrollEl;
        const pageEl = this._getPageEl(pageNum);
        if (el && pageEl) {
            el.scrollTo({ top: pageEl.offsetTop - PAGE_GAP, behavior: "smooth" });
        }
    }

    onPageInputChange(ev) {
        this.goToPage(ev.target.value);
        ev.target.value = this.state.currentPage;
    }

    toggleThumbnails() {
        this.state.showThumbnails = !this.state.showThumbnails;
        this.state.needsThumbRender = this.state.showThumbnails;
        if (["auto", "page-fit", "page-width"].includes(this.state.zoomMode)) {
            // The available width changed: refit once the sidebar is laid out
            setTimeout(() => this.setZoomMode(this.state.zoomMode));
        }
    }

    // ---- Search -------------------------------------------------------------

    toggleSearch() {
        this.state.searchOpen = !this.state.searchOpen;
        if (this.state.searchOpen) {
            setTimeout(() => document.querySelector('.o_hudson_sign_editor .o_sign_search_input')?.focus());
        } else {
            this.state.searchMatches = [];
        }
    }

    async _getTextContent(pageNum) {
        if (!this._textCache[pageNum]) {
            const page = await this.pdfDoc.getPage(pageNum);
            this._textCache[pageNum] = {
                content: await page.getTextContent(),
                transform: page.getViewport({ scale: 1 }).transform,
            };
        }
        return this._textCache[pageNum];
    }

    async runSearch() {
        const query = this.state.searchQuery.trim().toLowerCase();
        const matches = [];
        if (query && this.pdfDoc) {
            for (const base of this.basePages) {
                const { content, transform } = await this._getTextContent(base.num);
                for (const item of content.items) {
                    const text = (item.str || "").toLowerCase();
                    if (!text) continue;
                    let index = text.indexOf(query);
                    if (index < 0) continue;
                    const tx = multiplyTransform(transform, item.transform);
                    const fontHeight = Math.hypot(tx[2], tx[3]);
                    const charWidth = item.width / text.length;
                    while (index >= 0) {
                        matches.push({
                            page: base.num,
                            x: (tx[4] + charWidth * index) / base.width,
                            y: (tx[5] - fontHeight) / base.height,
                            w: (charWidth * query.length) / base.width,
                            h: (fontHeight * 1.2) / base.height,
                        });
                        index = text.indexOf(query, index + query.length);
                    }
                }
            }
        }
        this.state.searchMatches = matches;
        this.state.searchIndex = 0;
        this.scrollToMatch();
    }

    onSearchKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            if (this.state.searchMatches.length && this._lastQuery === this.state.searchQuery) {
                this.nextMatch(ev.shiftKey ? -1 : 1);
            } else {
                this._lastQuery = this.state.searchQuery;
                this.runSearch();
            }
        } else if (ev.key === "Escape") {
            this.toggleSearch();
        }
    }

    nextMatch(step) {
        const count = this.state.searchMatches.length;
        if (!count) return;
        this.state.searchIndex = (this.state.searchIndex + step + count) % count;
        this.scrollToMatch();
    }

    scrollToMatch() {
        const match = this.state.searchMatches[this.state.searchIndex];
        const el = this.scrollEl;
        const pageEl = match && this._getPageEl(match.page);
        if (el && pageEl) {
            const top = pageEl.offsetTop + match.y * this.getPage(match.page).height - el.clientHeight / 2;
            el.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
        }
    }

    getMatchesForPage(pageNum) {
        return this.state.searchMatches
            .map((match, index) => ({ ...match, index }))
            .filter(match => match.page === pageNum);
    }

    // ---- Tools ---------------------------------------------------------------

    getToolIcon(type) {
        const tool = this.state.tools.find(t => t.type === type);
        return tool ? tool.icon : "fa-pencil-square-o";
    }

    getToolLabel(type) {
        const tool = this.state.tools.find(t => t.type === type);
        return tool ? tool.label : type;
    }

    getBoxLabel(box) {
        return box.label || this.getToolLabel(box.type);
    }

    hasPlaceholder(box) {
        return PLACEHOLDER_TYPES.includes(box.type);
    }

    canAlign(box) {
        return ALIGN_TYPES.includes(box.type);
    }

    isMultilineBox(box) {
        return MULTILINE_TYPES.includes(box.type);
    }

    getPage(num) {
        return this.state.pages.find(p => p.num === num) || { width: 800, height: 1100 };
    }

    getItemsForPage(pageNum) {
        return this.state.items.filter(i => i.page === pageNum);
    }

    get activeBox() {
        const id = this.state.boxDragId || this.state.boxResizeId || this.state.editingBoxId;
        return id ? this.state.items.find(b => b.id === id) : null;
    }

    getGuidesForPage(pageNum) {
        const box = this.activeBox;
        if (!box || box.page !== pageNum) return [];
        return [
            { key: "v1", vertical: true, pos: box.x },
            { key: "v2", vertical: true, pos: box.x + box.width },
            { key: "h1", vertical: false, pos: box.y },
            { key: "h2", vertical: false, pos: box.y + box.height },
        ];
    }

    /**
     * Elbow connectors linking the options of each radio group, drawn under the
     * fields: down from the centre of an option, then across to the next one.
     */
    getRadioLinks(pageNum) {
        const groups = {};
        for (const item of this.state.items) {
            if (item.type === "radio" && item.page === pageNum && item.radioGroupName) {
                (groups[item.radioGroupName] = groups[item.radioGroupName] || []).push(item);
            }
        }
        const links = [];
        for (const [group, options] of Object.entries(groups)) {
            for (let i = 1; i < options.length; i++) {
                const a = options[i - 1];
                const b = options[i];
                const ax = a.x + a.width / 2;
                const ay = a.y + a.height / 2;
                const bx = b.x + b.width / 2;
                const by = b.y + b.height / 2;
                links.push({ key: `${group}_${i}`, path: `M ${ax} ${ay} V ${by} H ${bx}` });
            }
        }
        return links;
    }

    getChoiceIconSize(box) {
        return Math.max(10, Math.round(Math.min(box.width, box.height) * 0.8));
    }

    getSelectionOptions(box) {
        return (box.options || "").split("\n").map(o => o.trim()).filter(Boolean);
    }

    // ---- Drag & Drop --------------------------------------------------------

    getDefaultSize(type) {
        const [width, height] = DEFAULT_SIZES[type] || [160, 26];
        const scale = (this.state.zoomLevel || 100) / 100;
        return { width: width * scale, height: height * scale };
    }

    startDrag(e, tool) {
        e.preventDefault();
        this.closePopover();
        this.state.dragTool = tool;
        this.state.dragType = tool.type;
        this.state.mouseX = e.clientX;
        this.state.mouseY = e.clientY;
    }

    _getPageEl(pageNum) {
        return document.querySelector(`.o_hudson_sign_editor .o_dms_pdf_page[data-page-num="${pageNum}"]`);
    }

    onWindowMouseMove(e) {
        this._lastPointer = { x: e.clientX, y: e.clientY };
        if (this.state.dragType) {
            this.state.mouseX = e.clientX;
            this.state.mouseY = e.clientY;
            this._startAutoScroll();
        } else if (this.state.boxDragId) {
            this._moveDraggedBox(e.clientX, e.clientY);
            this._startAutoScroll();
        } else if (this.state.boxResizeId) {
            const box = this.state.items.find(b => b.id === this.state.boxResizeId);
            if (!box) return;
            this._resizeBox(box, e.clientX - this.state.dragStartX, e.clientY - this.state.dragStartY);
        }
    }

    _moveDraggedBox(clientX, clientY) {
        const box = this.state.items.find(b => b.id === this.state.boxDragId);
        const pageEl = box && this._getPageEl(box.page);
        if (!pageEl) return;
        // Free move, also over the other pages and outside of them: the drop decides
        const pageRect = pageEl.getBoundingClientRect();
        box.x = clientX - this._grabOffset.x - pageRect.left;
        box.y = clientY - this._grabOffset.y - pageRect.top;
        this.state.dropInvalid = !this._findDropPage(box);
    }

    /**
     * While a field is dragged near (or past) an edge of the document area,
     * scroll it, faster the closer to the edge; the field stays under the pointer.
     */
    _startAutoScroll() {
        if (this._autoScrollFrame) return;
        const EDGE = 60;
        const MAX_SPEED = 22;
        const speedFor = (pos, start, end) => {
            if (pos < start + EDGE) return -MAX_SPEED * Math.min(1, (start + EDGE - pos) / EDGE);
            if (pos > end - EDGE) return MAX_SPEED * Math.min(1, (pos - (end - EDGE)) / EDGE);
            return 0;
        };
        const step = () => {
            this._autoScrollFrame = null;
            const el = this.scrollEl;
            const pointer = this._lastPointer;
            if (!el || !pointer || !(this.state.dragType || this.state.boxDragId)) return;
            const rect = el.getBoundingClientRect();
            const bottom = rect.top + el.clientHeight;
            const right = rect.left + el.clientWidth;
            // Not while the pointer is over the sidebar (where new fields come from)
            const overWidth = pointer.x >= rect.left && pointer.x <= right;
            const overHeight = pointer.y >= rect.top && pointer.y <= bottom;
            const dy = overWidth ? speedFor(pointer.y, rect.top, bottom) : 0;
            const dx = overWidth && overHeight ? speedFor(pointer.x, rect.left, right) : 0;
            const top = el.scrollTop;
            const left = el.scrollLeft;
            if (dy) el.scrollTop += dy;
            if (dx) el.scrollLeft += dx;
            const scrolled = el.scrollTop !== top || el.scrollLeft !== left;
            if (scrolled && this.state.boxDragId) {
                this._moveDraggedBox(pointer.x, pointer.y);
            }
            if (dy || dx) {
                // Keep going while the pointer stays at the edge
                this._autoScrollFrame = requestAnimationFrame(step);
            }
        };
        this._autoScrollFrame = requestAnimationFrame(step);
    }

    _stopAutoScroll() {
        if (this._autoScrollFrame) {
            cancelAnimationFrame(this._autoScrollFrame);
            this._autoScrollFrame = null;
        }
    }

    /**
     * Page fully containing the field being moved, with the field position on it;
     * null when the field is (even partially) outside of every page.
     */
    _findDropPage(box) {
        const fromEl = this._getPageEl(box.page);
        if (!fromEl) return null;
        const from = fromEl.getBoundingClientRect();
        const left = from.left + box.x;
        const top = from.top + box.y;
        const tolerance = 0.5;
        for (const pageEl of document.querySelectorAll('.o_hudson_sign_editor .o_sign_pages .o_dms_pdf_page')) {
            const rect = pageEl.getBoundingClientRect();
            if (left >= rect.left - tolerance && top >= rect.top - tolerance &&
                left + box.width <= rect.right + tolerance && top + box.height <= rect.bottom + tolerance) {
                return {
                    page: parseInt(pageEl.getAttribute('data-page-num'), 10),
                    x: Math.min(Math.max(0, left - rect.left), rect.width - box.width),
                    y: Math.min(Math.max(0, top - rect.top), rect.height - box.height),
                };
            }
        }
        return null;
    }

    /** Resize from the handle ``boxResizeDir`` (n, s, e, w or a corner), inside the page. */
    _resizeBox(box, dx, dy) {
        const dir = this.state.boxResizeDir || 'se';
        const start = this.state.boxStartRect;
        const page = this.getPage(box.page);
        const square = SQUARE_TYPES.includes(box.type);
        const minW = square ? 14 : 20;
        const minH = 14;
        const clamp = (value, min, max) => Math.max(min, Math.min(value, max));
        let left = start.x;
        let top = start.y;
        let right = start.x + start.width;
        let bottom = start.y + start.height;
        if (dir.includes('e')) right = clamp(right + dx, left + minW, page.width);
        if (dir.includes('w')) left = clamp(left + dx, 0, right - minW);
        if (dir.includes('s')) bottom = clamp(bottom + dy, top + minH, page.height);
        if (dir.includes('n')) top = clamp(top + dy, 0, bottom - minH);

        if (!square) {
            Object.assign(box, { x: left, y: top, width: right - left, height: bottom - top });
            return;
        }
        // Checkbox / radio: stay square, anchored on the opposite side of the handle
        const horizontal = dir.includes('e') || dir.includes('w');
        const vertical = dir.includes('n') || dir.includes('s');
        let size = horizontal && vertical ? Math.max(right - left, bottom - top)
            : horizontal ? right - left : bottom - top;
        const maxW = dir.includes('w') ? start.x + start.width : page.width - start.x;
        const maxH = dir.includes('n') ? start.y + start.height : page.height - start.y;
        size = Math.max(minH, Math.min(size, maxW, maxH));
        box.x = dir.includes('w') ? start.x + start.width - size : start.x;
        box.y = dir.includes('n') ? start.y + start.height - size : start.y;
        // All options of a radio group keep the same size
        const boxes = box.type === "radio" && box.radioGroupName ? this.getRadioGroup(box) : [box];
        for (const option of boxes) {
            const optionPage = this.getPage(option.page);
            const optionSize = option === box ? size
                : Math.min(size, optionPage.width - option.x, optionPage.height - option.y);
            option.width = optionSize;
            option.height = optionSize;
        }
    }

    onWindowMouseUp(e) {
        this._stopAutoScroll();
        if (this.state.boxDragId || this.state.boxResizeId) {
            const moved = this.state.dragStartX !== e.clientX || this.state.dragStartY !== e.clientY;
            if (this.state.boxDragId && !moved) {
                // Was just a click, open properties
                this.state.editingBoxId = this.state.boxDragId;
            }
            if (this.state.boxDragId && moved) {
                const box = this.state.items.find(b => b.id === this.state.boxDragId);
                const target = box && this._findDropPage(box);
                const start = this.state.boxStartRect;
                if (box) {
                    // Dropped on a page: it moves there; (partially) outside: back where it was
                    Object.assign(box, target
                        ? { page: target.page, x: target.x, y: target.y }
                        : { page: start.page, x: start.x, y: start.y });
                }
            }
            this.state.dropInvalid = false;
            this.state.boxDragId = null;
            this.state.boxResizeId = null;
            if (moved) this.scheduleSave();
            return;
        }

        if (!this.state.dragType) return;
        const tool = this.state.dragTool;
        const type = this.state.dragType;
        this.state.dragType = null;
        this.state.dragTool = null;

        let targetPageNum = null;
        let targetRect = null;
        for (const pageEl of document.querySelectorAll('.o_hudson_sign_editor .o_dms_pdf_page')) {
            const rect = pageEl.getBoundingClientRect();
            if (e.clientX >= rect.left && e.clientX <= rect.right &&
                e.clientY >= rect.top && e.clientY <= rect.bottom) {
                targetPageNum = parseInt(pageEl.getAttribute('data-page-num'), 10);
                targetRect = rect;
                break;
            }
        }
        if (!targetPageNum || !this.currentRole.id) return;

        const { width, height } = this.getDefaultSize(type);
        const dropX = Math.min(Math.max(0, e.clientX - targetRect.left), targetRect.width - width);
        const dropY = Math.min(Math.max(0, e.clientY - targetRect.top), targetRect.height - height);

        const base = {
            typeId: tool.id,
            type,
            label: tool.label,
            page: targetPageNum,
            roleId: this.currentRole.id,
            width,
            height,
            placeholder: tool.placeholder ?? tool.label,
            mandatory: tool.mandatory ?? true,
            readonly: tool.readonly ?? false,
            options: tool.options || '',
            alignment: 'left',
            radioGroupName: '',
            radioOptionValue: '',
        };

        if (type === 'radio') {
            // A radio field is a group of options; start with two, linked by a connector
            const groupId = 'RadioGroup_' + Date.now();
            const first = { ...base, id: this._newItemId(), x: dropX, y: dropY, radioGroupName: groupId, radioOptionValue: 'Option 1' };
            this.state.items.push(first);
            this.state.items.push(this._nextRadioOption(first, 2));
        } else {
            // The properties open on a click on the field, not when it is dropped
            this.state.items.push({ ...base, id: this._newItemId(), x: dropX, y: dropY });
        }
        this.scheduleSave();
    }

    _newItemId() {
        return `new_item_${this._nextItemId++}`;
    }

    getRadioGroup(box) {
        return this.state.items.filter(i => i.type === "radio" && i.radioGroupName === box.radioGroupName);
    }

    /**
     * New option of a radio group: on the same line, right of the last option,
     * wrapping to a new line under the first one when the page edge is reached.
     */
    _nextRadioOption(from, index) {
        const page = this.getPage(from.page);
        const group = from.radioGroupName ? this.getRadioGroup(from) : [];
        const last = group.at(-1) || from;
        const first = group[0] || from;
        const gap = last.width;
        let x = last.x + last.width + gap;
        let y = last.y;
        if (x + last.width > page.width) {
            x = first.x;
            y = last.y + last.height + gap;
        }
        return {
            ...last,
            id: this._newItemId(),
            x: Math.min(Math.max(0, x), page.width - last.width),
            y: Math.min(Math.max(0, y), page.height - last.height),
            radioOptionValue: 'Option ' + index,
        };
    }

    getRadioGroupCount(box) {
        return this.getRadioGroup(box).length;
    }

    /** Add or remove options so that the group of ``box`` has ``value`` options (at least two). */
    setRadioGroupCount(box, value) {
        const count = Math.min(Math.max(2, parseInt(value, 10) || 2), 30);
        let group = this.getRadioGroup(box);
        while (group.length < count) {
            this.state.items.push(this._nextRadioOption(group.at(-1), group.length + 1));
            group = this.getRadioGroup(box);
        }
        if (group.length > count) {
            // Drop the last options, keeping the one being edited
            const removable = group.filter(i => i.id !== box.id).slice(-(group.length - count)).map(i => i.id);
            this.state.items = this.state.items.filter(i => !removable.includes(i.id));
        }
        this.scheduleSave();
    }

    startBoxDrag(e, box) {
        if (e.button !== 0 || this.state.previewMode) return;
        if (e.target.closest('.o_dms_box_popover')) return;
        if (e.target.closest('.o_sign_resize')) return;
        e.preventDefault();
        if (this.state.editingBoxId && this.state.editingBoxId !== box.id) {
            this.closePopover();
        }
        // Where the field was grabbed: it follows the pointer, even while scrolling
        const rect = e.currentTarget.getBoundingClientRect();
        this._grabOffset = { x: e.clientX - rect.left, y: e.clientY - rect.top };
        this.state.boxDragId = box.id;
        this.state.dragStartX = e.clientX;
        this.state.dragStartY = e.clientY;
        this.state.boxStartRect = { x: box.x, y: box.y, page: box.page };
    }

    startBoxResize(e, box, dir = 'se') {
        e.preventDefault();
        if (this.state.previewMode) return;
        this.state.boxResizeId = box.id;
        this.state.boxResizeDir = dir;
        this.state.dragStartX = e.clientX;
        this.state.dragStartY = e.clientY;
        this.state.boxStartRect = { x: box.x, y: box.y, width: box.width, height: box.height };
    }

    onKeyDown(ev) {
        if (!this.state.editingBoxId) return;
        const tag = ev.target.tagName;
        if (["INPUT", "TEXTAREA", "SELECT"].includes(tag) || ev.target.isContentEditable) return;
        if (ev.key === "Delete" || ev.key === "Backspace") {
            ev.preventDefault();
            this.deleteBox(this.state.editingBoxId);
        } else if (ev.key === "Escape") {
            this.closePopover();
        }
    }

    // ---- Box Properties -----------------------------------------------------

    deleteBox(boxId) {
        const box = this.state.items.find(b => b.id === boxId);
        this.state.items = this.state.items.filter(b => b.id !== boxId);
        if (box?.type === "radio" && box.radioGroupName) {
            // A lone radio option is useless: drop the group when its last sibling goes
            const siblings = this.state.items.filter(i => i.radioGroupName === box.radioGroupName);
            if (siblings.length === 1) {
                this.state.items = this.state.items.filter(i => i.id !== siblings[0].id);
            }
        }
        if (this.state.editingBoxId === boxId) {
            this.state.editingBoxId = null;
        }
        this.scheduleSave();
    }

    duplicateBox(boxId) {
        const box = this.state.items.find(b => b.id === boxId);
        if (!box) return;
        let copy;
        if (box.type === "radio" && box.radioGroupName) {
            // Duplicating a radio option adds an option to its group
            const count = this.state.items.filter(i => i.radioGroupName === box.radioGroupName).length;
            copy = this._nextRadioOption(box, count + 1);
        } else {
            copy = { ...JSON.parse(JSON.stringify(box)), id: this._newItemId() };
            const page = this.getPage(box.page);
            copy.y = Math.min(box.y + box.height + 10, page.height - box.height);
        }
        this.state.items.push(copy);
        this.state.editingBoxId = copy.id;
        this.scheduleSave();
    }

    /**
     * Keep the properties popover inside the visible part of the document:
     * right of the field when it fits, else left, else below or above it.
     */
    positionPopover() {
        const popover = document.querySelector('.o_hudson_sign_editor .o_sign_popover');
        const container = this.scrollEl;
        if (!popover || !container) return;
        const gap = 12;
        const margin = 8;
        Object.assign(popover.style, { left: "", top: "", maxHeight: "", overflowY: "" });

        const area = container.getBoundingClientRect();
        const areaLeft = area.left + margin;
        const areaTop = area.top + margin;
        const areaRight = area.left + container.clientWidth - margin;
        const areaBottom = area.top + container.clientHeight - margin;
        const maxHeight = areaBottom - areaTop;
        if (popover.offsetHeight > maxHeight) {
            Object.assign(popover.style, { maxHeight: `${maxHeight}px`, overflowY: "auto" });
        }
        const field = popover.parentElement.getBoundingClientRect();
        const width = popover.offsetWidth;
        const height = popover.offsetHeight;
        const clamp = (value, min, max) => Math.max(min, Math.min(value, max));

        let left;
        let top;
        if (field.right + gap + width <= areaRight) {
            left = field.right + gap;
            top = clamp(field.top, areaTop, areaBottom - height);
        } else if (field.left - gap - width >= areaLeft) {
            left = field.left - gap - width;
            top = clamp(field.top, areaTop, areaBottom - height);
        } else {
            left = clamp(field.left, areaLeft, areaRight - width);
            top = field.bottom + gap + height <= areaBottom ? field.bottom + gap : field.top - gap - height;
            top = clamp(top, areaTop, areaBottom - height);
        }
        // The popover is positioned relative to its field
        popover.style.left = `${left - field.left}px`;
        popover.style.top = `${top - field.top}px`;
    }

    closePopover() {
        if (this.state.editingBoxId) {
            this.state.editingBoxId = null;
            // Properties are edited in place (t-model): persist them on close
            this.scheduleSave();
        }
    }

    setAlignment(box, alignment) {
        box.alignment = alignment;
    }

    onMandatoryChange(box, mandatory) {
        if (box.type === "radio" && box.radioGroupName) {
            for (const item of this.state.items) {
                if (item.radioGroupName === box.radioGroupName) {
                    item.mandatory = mandatory;
                }
            }
        }
    }
}

registry.category("actions").add("hudson_sign.template_builder", HudsonSignEditor);

// -----------------------------------------------------------------------------
// Sent document viewer
// Opened from Sign > Documents; the form view stays available under "Details".
// -----------------------------------------------------------------------------
const SIGNER_STATE_LABELS = {
    draft: "Waiting for previous signers",
    sent: "Awaiting Signature",
    signed: "Signed",
};

export class HudsonSignDocumentViewer extends HudsonSignEditor {
    static template = "hudson_sign.SignDocumentViewer";

    setup() {
        super.setup();
        // The editor reads active_id as a template: here it is the sign request
        this.requestId = this.templateId;
        this.templateId = false;
        this.state.request = null;
        this.state.signers = [];
    }

    async loadData() {
        if (!this.requestId) {
            return this.actionService.doAction("hudson_sign.action_hudson_sign_request", { clearBreadcrumbs: true });
        }
        const data = await this.orm.call("hudson.sign.request", "get_viewer_data", [[this.requestId]]);
        this.state.request = data.request;
        this.state.signers = data.signers;
        // Signers take the place of the editor roles to colour their fields
        this.state.roles = data.signers;
        this.state.allTags = data.tags;
        this.state.templateTags = data.tags.filter(tag => data.request.tag_ids.includes(tag.id));
        this.pendingItems = data.items;
        this.state.items = [];
        this._textCache = {};
        try {
            const bytes = Uint8Array.from(atob(data.pdf), c => c.charCodeAt(0));
            await this.renderPDF(bytes);
        } catch (err) {
            this.state.isLoading = false;
            this.state.errorMessage = err.message || "Failed to render PDF preview.";
        }
    }

    get tagsModel() {
        return "hudson.sign.request";
    }

    get tagsResId() {
        return this.requestId;
    }

    get myPendingSigner() {
        return this.state.request?.state === "sent" && this.state.signers.find(s => s.isMe && s.state === "sent");
    }

    get backLabel() {
        const breadcrumbs = this.env.config?.breadcrumbs || [];
        return breadcrumbs.length > 1 ? breadcrumbs[breadcrumbs.length - 2].name : "Documents";
    }

    getSignerStateLabel(signer) {
        if (signer.state !== "signed" && this.state.request.state === "canceled") return "Cancelled";
        if (signer.state !== "signed" && this.state.request.state === "expired") return "Expired";
        return SIGNER_STATE_LABELS[signer.state] || signer.state;
    }

    onBack() {
        const breadcrumbs = this.env.config?.breadcrumbs || [];
        if (breadcrumbs.length > 1) {
            return breadcrumbs[breadcrumbs.length - 2].onSelected();
        }
        return this.actionService.doAction("hudson_sign.action_hudson_sign_request", { clearBreadcrumbs: true });
    }

    async _callAndRun(method) {
        const action = await this.orm.call("hudson.sign.request", method, [[this.requestId]]);
        if (action) {
            await this.actionService.doAction(action);
        }
    }

    async runMenuAction(method) {
        this.state.docMenuOpen = false;
        await this._callAndRun(method);
    }

    signNow() {
        return this._callAndRun("action_sign_now");
    }

    downloadDocument() {
        return this._callAndRun("action_download");
    }

    async sendReminder() {
        await this._callAndRun("action_send_reminder");
    }

    cancelRequest() {
        this.state.docMenuOpen = false;
        this.dialog.add(ConfirmationDialog, {
            title: "Cancel request",
            body: "Signers will no longer be able to sign this document. Continue?",
            confirmLabel: "Cancel request",
            confirmClass: "btn-danger",
            cancelLabel: "Discard",
            confirm: async () => {
                await this.orm.call("hudson.sign.request", "action_cancel", [[this.requestId]]);
                await this.loadData();
            },
            cancel: () => {},
        });
    }
}

registry.category("actions").add("hudson_sign.document_viewer", HudsonSignDocumentViewer);
