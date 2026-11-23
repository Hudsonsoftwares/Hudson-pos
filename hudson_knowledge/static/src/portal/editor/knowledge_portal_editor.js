/**
 * Article editor of the Knowledge portal page. Loaded lazily (bundle
 * hudson_knowledge.assets_portal_editor) and mounted by the KnowledgePortal
 * interaction when the visitor can edit the article.
 *
 * Like the backend app, the article title is its first <h1> and changes are
 * saved automatically.
 */
import { Component, markup, onMounted, onWillUnmount, useListener, useProps } from "@odoo/owl";
import { Wysiwyg } from "@html_editor/wysiwyg";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { rpc } from "@web/core/network/rpc";

const ARTICLE_MODEL = "knowledge.management.article";
// File attachments, signatures and translation need backend services.
const REMOVED_PLUGINS = new Set(["file", "userSignature", "translate"]);
const SAVE_DELAY = 800;

function cleanText(text) {
    return (text || "").replace(/[\n\r﻿​]/g, " ").replace(/\s+/g, " ").trim();
}

export class KnowledgePortalEditor extends Component {
    static template = "hudson_knowledge.KnowledgePortalEditor";
    static components = { Wysiwyg };
    props = useProps();

    setup() {
        let content = this.props.content || "";
        if (!/<h1\b/i.test(content)) {
            content = `<h1><br></h1>${content || "<p><br></p>"}`;
        }
        this.config = {
            content: markup(content),
            Plugins: MAIN_PLUGINS.filter((P) => !REMOVED_PLUGINS.has(P.id)),
            classList: ["o_kp_body", "o_knowledge_body"],
            onChange: () => this.onChange(),
            getRecordInfo: () => ({ resModel: ARTICLE_MODEL, resId: this.props.articleId }),
            dropImageAsAttachment: true,
            direction: "ltr",
        };
        this.lastTitle = cleanText(this.props.title);
        this.lastBody = null;
        this.timer = null;
        this.savePromise = null;
        this.props.register(this);
        useListener(window, "beforeunload", () => this.flushOnUnload());
        onMounted(() => this.onEditorReady());
        onWillUnmount(() => this.flushOnUnload());
    }

    /** Called by Wysiwyg in its setup: the editable is not attached yet. */
    onLoad(editor) {
        this.editor = editor;
    }

    /** Child components are mounted first: the editor is ready here. */
    onEditorReady() {
        if (!this.editorAlive) {
            return;
        }
        this.lastBody = this.getBody();
        const h1 = this.editor.editable.querySelector("h1");
        if (h1 && !cleanText(h1.innerText)) {
            // new article: start typing the title
            this.editor.shared.selection.setCursorStart(h1);
        }
    }

    get editorAlive() {
        return Boolean(this.editor && !this.editor.isDestroyed && this.editor.editable);
    }

    getBody() {
        return this.editorAlive ? this.editor.getContent() : this.lastBody;
    }

    /** First <h1>, else the first line of text (same rule as the backend). */
    getTitle() {
        const editable = this.editor?.editable;
        if (!editable) {
            return this.lastTitle;
        }
        const h1 = editable.querySelector("h1");
        let title = h1 ? cleanText(h1.innerText) : "";
        if (!title) {
            for (const block of editable.children) {
                if (block !== h1 && !block.matches("[data-oe-protected], [data-embedded]")) {
                    title = cleanText(block.innerText);
                    if (title) {
                        break;
                    }
                }
            }
        }
        if (title.length > 100) {
            title = `${title.slice(0, 100).trim()}…`;
        }
        return title || "Untitled";
    }

    get isDirty() {
        return this.getBody() !== this.lastBody || this.getTitle() !== this.lastTitle;
    }

    onChange() {
        const title = this.getTitle();
        if (title !== this.lastTitle) {
            this.props.onTitle(title);
        }
        if (this.isDirty) {
            this.props.onStatus("unsaved");
            clearTimeout(this.timer);
            this.timer = setTimeout(() => this.save(), SAVE_DELAY);
        }
    }

    onBlur() {
        if (this.isDirty) {
            this.save();
        }
    }

    _values() {
        const vals = {};
        const body = this.getBody();
        const title = this.getTitle();
        if (body !== this.lastBody) {
            vals.body_html = body;
        }
        if (title !== this.lastTitle) {
            vals.name = title;
        }
        return { vals, body, title };
    }

    async save() {
        clearTimeout(this.timer);
        this.timer = null;
        if (this.savePromise) {
            await this.savePromise;
        }
        if (this.editorAlive) {
            await this.editor.shared.imageSave?.savePendingImages?.();
        }
        const { vals, body, title } = this._values();
        if (!Object.keys(vals).length) {
            this.props.onStatus("saved");
            return;
        }
        this.props.onStatus("saving");
        this.savePromise = rpc(`/knowledge/portal/article/${this.props.articleId}/save`, vals);
        try {
            await this.savePromise;
            this.lastBody = body;
            this.lastTitle = title;
            this.props.onStatus(this.isDirty ? "unsaved" : "saved");
        } catch (error) {
            this.props.onStatus("error");
            throw error;
        } finally {
            this.savePromise = null;
        }
    }

    /** Called before the interaction runs an action (copy, favorite...). */
    async flush() {
        if (this.timer || this.isDirty) {
            await this.save();
        } else if (this.savePromise) {
            await this.savePromise;
        }
    }

    /** Page is being left: send the pending changes with a keepalive request. */
    flushOnUnload() {
        if (!this.editorAlive || !this.isDirty) {
            return;
        }
        clearTimeout(this.timer);
        const { vals, body, title } = this._values();
        this.lastBody = body;
        this.lastTitle = title;
        fetch(`/knowledge/portal/article/${this.props.articleId}/save`, {
            method: "POST",
            keepalive: true,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", id: Date.now(), params: vals }),
        });
    }
}
