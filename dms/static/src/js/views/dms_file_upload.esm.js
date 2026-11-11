import {useBus, useService} from "@web/core/utils/hooks";
import {useEffect, useRef, proxy} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {AlertDialog} from "@web/core/confirmation_dialog/confirmation_dialog";

export function createFileDropZoneExtension() {
    return {
        setup() {
            super.setup(...arguments);
            const useStateHook = (typeof proxy === "function" ? proxy : (typeof owl !== "undefined" && (owl.proxy || owl.useState) ? (owl.proxy || owl.useState) : (typeof useState === "function" ? useState : (obj => obj))));
            this.dragState = useStateHook({
                showDragZone: false,
            });
            
            if (typeof owl !== "undefined" && owl.useRef) {
                this.root = owl.useRef("root");
            } else if (typeof useRef === "function") {
                this.root = useRef("root");
            } else {
                this.root = {
                    get el() {
                        return document.querySelector('.o_kanban_renderer') || document.querySelector('.o_list_renderer') || document.body;
                    }
                };
            }

            useEffect(
                (el) => {
                    if (!el) {
                        return;
                    }
                    const highlight = this.highlight.bind(this);
                    const unhighlight = this.unhighlight.bind(this);
                    const drop = this.onDrop.bind(this);
                    el.addEventListener("dragover", highlight);
                    el.addEventListener("dragleave", unhighlight);
                    el.addEventListener("drop", drop);
                    return () => {
                        el.removeEventListener("dragover", highlight);
                        el.removeEventListener("dragleave", unhighlight);
                        el.removeEventListener("drop", drop);
                    };
                },

                () => [document.querySelector(".o_content")]
            );
        },

        highlight(ev) {
            ev.stopPropagation();
            ev.preventDefault();
            this.dragState.showDragZone = true;
        },

        unhighlight(ev) {
            ev.stopPropagation();
            ev.preventDefault();
            this.dragState.showDragZone = false;
        },

        async onDrop(ev) {
            ev.preventDefault();
            this.dragState.showDragZone = false;
            await this.env.bus.trigger("change_file_input", {
                files: ev.dataTransfer.files,
            });
        },
    };
}

export function createFileUploadExtension() {
    return {
        setup() {
            super.setup();
            this.notification = useService("notification");
            this.orm = useService("orm");
            this.http = useService("http");
            this.dialogService = useService("dialog");
            // Cache for upload config: { max_size_mb, forbidden_extensions }
            this._uploadConfig = null;
            
            if (typeof owl !== "undefined" && owl.useRef) {
                this.fileInput = owl.useRef("fileInput");
            } else if (typeof useRef === "function") {
                this.fileInput = useRef("fileInput");
            } else {
                this.fileInput = {
                    get el() {
                        return document.querySelector('input[name="ufile"]');
                    }
                };
            }

            useBus(this.env.bus, "change_file_input", async (ev) => {
                this.fileInput.el.files = ev.detail.files;
                await this.onChangeFileInput();
            });
        },

        uploadDocument() {
            this.fileInput.el.click();
        },

        /**
         * Fetch upload constraints from the server (cached per component lifecycle).
         * Returns { max_size_mb: Number, forbidden_extensions: String[] }
         */
        async _getUploadConfig() {
            if (!this._uploadConfig) {
                try {
                    this._uploadConfig = await this.orm.call("dms.file", "get_upload_config", []);
                } catch {
                    // fallback – no restrictions applied
                    this._uploadConfig = { max_size_mb: 0, forbidden_extensions: [] };
                }
            }
            return this._uploadConfig;
        },

        /**
         * Validate a list of File objects against the upload config.
         * Returns an array of error messages (empty = all OK).
         */
        async _validateFiles(files) {
            const config = await this._getUploadConfig();
            const errors = [];

            for (const file of files) {
                // --- Extension check ---
                if (config.forbidden_extensions && config.forbidden_extensions.length) {
                    const nameParts = file.name.split(".");
                    const ext = nameParts.length > 1
                        ? nameParts[nameParts.length - 1].toLowerCase()
                        : "";
                    if (ext && config.forbidden_extensions.includes(ext)) {
                        errors.push(
                            _t(
                                'File "%s" has a forbidden extension (.%s). This file type is not allowed.',
                                file.name,
                                ext
                            )
                        );
                        continue; // no need to check size if extension already invalid
                    }
                }

                // --- Size check ---
                if (config.max_size_mb && config.max_size_mb > 0) {
                    const maxBytes = config.max_size_mb * 1024 * 1024;
                    if (file.size > maxBytes) {
                        errors.push(
                            _t(
                                'File "%s" cannot be uploaded because it exceeds the upload limit of %s MB (file size: %s MB).',
                                file.name,
                                config.max_size_mb,
                                (file.size / (1024 * 1024)).toFixed(2)
                            )
                        );
                    }
                }
            }

            return errors;
        },

        /**
         * Show a modal dialog with just a Close button for upload validation errors.
         */
        _showUploadErrorDialog(title, body) {
            this.dialogService.add(AlertDialog, {
                title: title,
                body: body,
            });
        },

        async _resolveDirectoryId() {
            const checkDomain = (domain) => {
                if (!domain || !Array.isArray(domain)) return false;
                for (const item of domain) {
                    if (Array.isArray(item) && item.length === 3) {
                        if (item[0] === "directory_id" && ["=", "in", "child_of"].includes(item[1])) {
                            const val = item[2];
                            if (Array.isArray(val) && val.length) return typeof val[0] === "number" ? val[0] : parseInt(val[0]);
                            if (typeof val === "number") return val;
                            if (typeof val === "string" && !isNaN(parseInt(val))) return parseInt(val);
                        }
                    }
                }
                return false;
            };

            let dirId = checkDomain(this.props.domain) || checkDomain(this.env.searchModel?.domain);
            if (dirId) return dirId;

            if (this.env.searchModel?.sections) {
                for (const section of this.env.searchModel.sections) {
                    if (section.fieldName === "directory_id" && section.activeValueId) {
                        return typeof section.activeValueId === "number" ? section.activeValueId : parseInt(section.activeValueId);
                    }
                }
            }

            try {
                const dirs = await this.orm.search("dms.directory", [], { limit: 1 });
                if (dirs && dirs.length) {
                    return dirs[0];
                }
            } catch {
                // ignore
            }
            return false;
        },

        async onChangeFileInput(ev) {
            const self = this;
            const filesToUpload = ev && ev.target && ev.target.files ? ev.target.files : (this.fileInput?.el?.files);
            if (!filesToUpload || filesToUpload.length === 0) {
                return;
            }

            // --- Client-side validation: size & forbidden extensions ---
            const validationErrors = await this._validateFiles(Array.from(filesToUpload));
            if (validationErrors.length > 0) {
                if (this.fileInput?.el) {
                    this.fileInput.el.value = "";
                }
                const isMultiple = validationErrors.length > 1;
                this._showUploadErrorDialog(
                    isMultiple ? _t("Upload Errors") : _t("Upload Not Allowed"),
                    validationErrors.join("\n\n")
                );
                return;
            }

            const directory_id = await this._resolveDirectoryId();
            if (!directory_id) {
                return self.notification.add(_t("You must select a directory first"), {
                    type: "danger",
                });
            }

            const readFileAsBase64 = (file) => new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => {
                    const b64 = reader.result.split(",")[1];
                    resolve(b64);
                };
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });

            // Pre-check for duplicate files with the same name in the target directory
            const fileNames = Array.from(filesToUpload).map((f) => f.name);
            try {
                const existingFiles = await self.orm.searchRead(
                    "dms.file",
                    [
                        ["directory_id", "=", directory_id],
                        ["name", "in", fileNames],
                    ],
                    ["name"]
                );
                if (existingFiles && existingFiles.length > 0) {
                    const existingNames = existingFiles.map((f) => `"${f.name}"`).join(", ");
                    if (this.fileInput?.el) {
                        this.fileInput.el.value = "";
                    }
                    const msg = existingFiles.length === 1
                        ? _t("A file with the same name %s already exists in this folder.", existingNames)
                        : _t("Files %s already exist in this folder.", existingNames);
                    return self.notification.add(msg, { type: "danger" });
                }
            } catch (checkErr) {
                console.warn("Could not pre-check duplicate files:", checkErr);
            }

            let lastCreatedId = null;
            try {
                for (let i = 0; i < filesToUpload.length; i++) {
                    const file = filesToUpload[i];
                    const content = await readFileAsBase64(file);
                    const newIds = await self.orm.create("dms.file", [
                        {
                            name: file.name,
                            directory_id: directory_id,
                            content: content,
                        },
                    ]);
                    if (newIds && newIds.length) {
                        lastCreatedId = newIds[0];
                    }
                }
            } catch (err) {
                console.error("DMS File Upload Error:", err);
                // Check if this is a server-side size or extension validation error
                // and show it as a dialog instead of a raw notification.
                let errorMsg = _t("Failed to upload file.");
                let isValidationError = false;
                if (err && err.data && err.data.message) {
                    errorMsg = err.data.message;
                    isValidationError = true;
                } else if (err && err.data && err.data.data && err.data.data.message) {
                    errorMsg = err.data.data.message;
                    isValidationError = true;
                } else if (err && err.data && Array.isArray(err.data.arguments) && err.data.arguments[0]) {
                    errorMsg = err.data.arguments[0];
                    isValidationError = true;
                } else if (err && err.message && err.message !== "Odoo Server Error" && err.message !== "RPC_ERROR: Odoo Server Error") {
                    errorMsg = err.message;
                }

                if (isValidationError) {
                    // Server validation error (size/extension constraint) → show as dialog
                    this._showUploadErrorDialog(_t("Upload Not Allowed"), errorMsg);
                } else {
                    return self.notification.add(errorMsg, { type: "danger" });
                }
                return;
            } finally {
                if (this.fileInput?.el) {
                    this.fileInput.el.value = "";
                }
            }

            if (this.model && this.model.root) {
                await this.model.root.load();
            }

            if (lastCreatedId) {
                try {
                    await self.actionService.doAction({
                        type: "ir.actions.act_window",
                        name: _t("File Details"),
                        res_model: "dms.file",
                        res_id: lastCreatedId,
                        views: [[false, "form"]],
                        target: "current",
                    });
                } catch (actionErr) {
                    console.error("Error opening file form:", actionErr);
                }
            }
        },

    };
}


