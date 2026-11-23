/**
 * Portal / public page of Knowledge (/knowledge/article/<id>).
 *
 * The page is rendered by the server (controllers/main.py, template
 * hudson_knowledge.knowledge_portal_page); this interaction adds the
 * behaviour of the Odoo Online portal app:
 *   - sidebar: expand / collapse (remembered per browser), mobile toggle
 *   - "⋮" menus: Open in new tab, Add to Favorite, Create a Copy,
 *     Add a sub-article, Move to Trash, Last Edited
 *   - search dialog (Ctrl+K)
 *   - the editor, for the articles the user can edit (lazy bundle
 *     hudson_knowledge.assets_portal_editor)
 */
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { loadBundle } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

const OPEN_KEY = "hudson_knowledge.portal.open_articles";
const EDITOR_MODULE = "@hudson_knowledge/portal/editor/knowledge_portal_editor";

function h(tag, attrs = {}, children = []) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (value === undefined || value === null || value === false) {
            continue;
        }
        if (key === "class") {
            el.className = value;
        } else if (key === "text") {
            el.textContent = value;
        } else if (key === "icon") {
            el.dataset.icon = value;
        } else {
            el.setAttribute(key, value);
        }
    }
    for (const child of [].concat(children)) {
        if (child) {
            el.append(child);
        }
    }
    return el;
}

function icon(name) {
    return h("i", { class: "oi", icon: name, "aria-hidden": "true" });
}

function readOpenIds() {
    try {
        return new Set(JSON.parse(window.localStorage.getItem(OPEN_KEY) || "[]"));
    } catch {
        return new Set();
    }
}

function writeOpenIds(ids) {
    try {
        window.localStorage.setItem(OPEN_KEY, JSON.stringify([...ids].slice(-300)));
    } catch {
        // private window / storage disabled: the tree simply starts collapsed
    }
}

function relativeDate(sqlDate) {
    if (!sqlDate || !window.luxon) {
        return "";
    }
    return window.luxon.DateTime.fromSQL(sqlDate, { zone: "utc" }).toRelative() || "";
}

export class KnowledgePortal extends Interaction {
    static selector = ".o_knowledge_portal";

    dynamicContent = {
        ".o_kp_caret": { "t-on-click.prevent.stop.noUpdate": this.onToggleItem },
        ".o_kp_item_more": { "t-on-click.prevent.stop.noUpdate": this.onItemMenu },
        ".o_kp_item_add": { "t-on-click.prevent.stop.noUpdate": this.onItemAdd },
        ".o_kp_more_btn": { "t-on-click.prevent.stop.noUpdate": this.onArticleMenu },
        ".o_kp_fav_btn": { "t-on-click.prevent.noUpdate": this.onFavoriteButton },
        ".o_kp_create_btn": { "t-on-click.prevent.stop.noUpdate": () => this.createArticle(false) },
        ".o_kp_search_btn": { "t-on-click.prevent.noUpdate": this.openSearch },
        ".o_kp_sidebar_toggle": { "t-on-click.prevent.noUpdate": this.toggleSidebar },
        ".o_kp_backdrop": { "t-on-click.noUpdate": this.toggleSidebar },
        ".o_kp_link": { "t-on-click.noUpdate": this.closeSidebarOnMobile },
        _document: {
            "t-on-click.noUpdate": this.onDocumentClick,
            "t-on-keydown.noUpdate": this.onKeydown,
        },
    };

    setup() {
        this.articleId = parseInt(this.el.dataset.articleId) || false;
        this.canWrite = this.el.dataset.canWrite === "1";
        this.isPublic = this.el.dataset.publicUser === "1";
        this.menuEl = null;
        this.searchEl = null;
        this.busy = false;
    }

    async willStart() {
        if (this.canWrite) {
            await loadBundle("hudson_knowledge.assets_portal_editor");
        }
    }

    start() {
        this.restoreTree();
        this.el.querySelector(".o_kp_item_row.o_kp_active")?.scrollIntoView({ block: "nearest" });
        if (this.canWrite) {
            this.mountEditor();
        }
    }

    destroy() {
        this.closeMenu();
        this.closeSearch();
    }

    // ── Sidebar tree ─────────────────────────────────────────────────
    restoreTree() {
        const open = readOpenIds();
        for (const li of this.el.querySelectorAll(".o_kp_item.o_kp_has_children")) {
            if (open.has(li.dataset.articleId)) {
                li.classList.add("o_kp_open");
            }
        }
        // the ancestors of the current article are opened by the server
        for (const li of this.el.querySelectorAll(".o_kp_item.o_kp_open")) {
            open.add(li.dataset.articleId);
        }
        writeOpenIds(open);
    }

    onToggleItem(ev) {
        const li = ev.currentTarget.closest(".o_kp_item");
        const isOpen = li.classList.toggle("o_kp_open");
        const open = readOpenIds();
        if (isOpen) {
            open.add(li.dataset.articleId);
        } else {
            open.delete(li.dataset.articleId);
        }
        writeOpenIds(open);
    }

    toggleSidebar() {
        this.el.classList.toggle("o_kp_sidebar_open");
    }

    closeSidebarOnMobile() {
        this.el.classList.remove("o_kp_sidebar_open");
    }

    // ── "⋮" menus ────────────────────────────────────────────────────
    _itemInfo(el) {
        const d = el.dataset;
        return {
            id: parseInt(d.articleId),
            name: d.name || "",
            url: d.url,
            isFavorite: d.favorite === "1",
            canWrite: d.canWrite === "1",
            canTrash: d.canTrash === "1",
            writeDate: d.writeDate,
            writer: d.writer || "",
        };
    }

    onItemMenu(ev) {
        const li = ev.currentTarget.closest(".o_kp_item");
        this.openMenu(ev.currentTarget, this._itemInfo(li), false);
    }

    onArticleMenu(ev) {
        this.openMenu(ev.currentTarget, this._itemInfo(this.el.querySelector(".o_kp_topbar")), true);
    }

    onItemAdd(ev) {
        const li = ev.currentTarget.closest(".o_kp_item");
        this.createArticle(parseInt(li.dataset.articleId));
    }

    openMenu(anchor, info, isCurrent) {
        const sameAnchor = this.menuEl && this.menuAnchor === anchor;
        this.closeMenu();
        if (sameAnchor) {
            return;
        }
        const entries = [];
        const entry = (iconName, label, action, cls = "") =>
            h("button", { type: "button", class: `o_kp_menu_item ${cls}` }, [icon(iconName), h("span", { text: label })]);
        const actions = [];
        const add = (iconName, label, action, cls) => {
            const button = entry(iconName, label, action, cls);
            actions.push([button, action]);
            entries.push(button);
        };
        if (!isCurrent) {
            add("open_in_new", _t("Open in new tab"), () => window.open(info.url, "_blank", "noopener"));
        }
        if (!this.isPublic) {
            if (entries.length) {
                entries.push(h("div", { class: "o_kp_menu_sep" }));
            }
            add("star", info.isFavorite ? _t("Remove from Favorites") : _t("Add to Favorite"), () =>
                this.toggleFavorite(info.id)
            );
            add("content_copy", _t("Create a Copy"), () => this.copyArticle(info.id));
            if (info.canWrite) {
                add("add", _t("Add a sub-article"), () => this.createArticle(info.id));
            }
            if (info.canTrash) {
                add("delete", _t("Move to Trash"), () => this.trashArticle(info), "o_kp_menu_danger");
            }
        }
        if (info.writeDate) {
            const writer = info.writer || "";
            entries.push(h("div", { class: "o_kp_menu_sep" }));
            entries.push(
                h("div", { class: "o_kp_menu_info" }, [
                    h("div", { class: "o_kp_menu_info_title", text: `${_t("Last Edited")} · ${relativeDate(info.writeDate)}` }),
                    writer &&
                        h("div", { class: "o_kp_menu_info_user" }, [
                            h("span", {
                                class: "o_kp_avatar",
                                text: writer.trim().charAt(0).toUpperCase(),
                                style: `background-color: hsl(${[...writer].reduce((a, c) => a + c.charCodeAt(0), 0) % 360}, 45%, 45%)`,
                            }),
                            h("span", { text: writer }),
                        ]),
                ])
            );
        }
        if (!entries.length) {
            return;
        }
        const menu = h("div", { class: "o_kp_menu", role: "menu" }, entries);
        document.body.append(menu);
        for (const [button, action] of actions) {
            this.addListener(button, "click.prevent.stop.noUpdate", () => {
                this.closeMenu();
                action();
            });
        }
        const rect = anchor.getBoundingClientRect();
        const width = menu.offsetWidth;
        const height = menu.offsetHeight;
        let left = rect.left;
        if (left + width > window.innerWidth - 8) {
            left = Math.max(8, rect.right - width);
        }
        let top = rect.bottom + 4;
        if (top + height > window.innerHeight - 8) {
            top = Math.max(8, rect.top - height - 4);
        }
        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;
        this.menuEl = menu;
        this.menuAnchor = anchor;
        anchor.closest(".o_kp_item_row")?.classList.add("o_kp_menu_open");
    }

    closeMenu() {
        if (this.menuEl) {
            this.menuEl.remove();
            this.menuAnchor?.closest(".o_kp_item_row")?.classList.remove("o_kp_menu_open");
            this.menuEl = null;
            this.menuAnchor = null;
        }
    }

    onDocumentClick(ev) {
        if (this.menuEl && !this.menuEl.contains(ev.target)) {
            this.closeMenu();
        }
    }

    onKeydown(ev) {
        if (ev.key === "Escape") {
            this.closeMenu();
            this.closeSearch();
        } else if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "k") {
            ev.preventDefault();
            this.openSearch();
        }
    }

    // ── Actions ──────────────────────────────────────────────────────
    async _call(route, params = {}) {
        if (this.busy) {
            return null;
        }
        this.busy = true;
        try {
            await this.editor?.flush();
            return await this.waitFor(rpc(route, params));
        } finally {
            this.busy = false;
        }
    }

    _go(url) {
        window.location.assign(url);
    }

    async onFavoriteButton() {
        await this.toggleFavorite(this.articleId);
    }

    async toggleFavorite(articleId) {
        const res = await this._call(`/knowledge/portal/article/${articleId}/favorite`);
        if (res) {
            window.location.reload();
        }
    }

    async createArticle(parentId) {
        const res = await this._call("/knowledge/portal/article/create", { parent_id: parentId || false });
        if (res) {
            if (parentId) {
                const open = readOpenIds();
                open.add(String(parentId));
                writeOpenIds(open);
            }
            this._go(res.url);
        }
    }

    async copyArticle(articleId) {
        const res = await this._call(`/knowledge/portal/article/${articleId}/copy`);
        if (res) {
            this._go(res.url);
        }
    }

    trashArticle(info) {
        this.services.dialog.add(ConfirmationDialog, {
            title: _t("Move to Trash"),
            body: _t('Move "%s" and its sub-articles to the trash?', info.name),
            confirmLabel: _t("Move to Trash"),
            confirm: async () => {
                const res = await this._call(`/knowledge/portal/article/${info.id}/trash`);
                if (res) {
                    this._go(info.id === this.articleId ? res.url : window.location.href);
                }
            },
            cancel: () => {},
        });
    }

    // ── Search ───────────────────────────────────────────────────────
    openSearch() {
        if (this.searchEl) {
            this.searchEl.querySelector("input").focus();
            return;
        }
        this.closeMenu();
        const input = h("input", {
            type: "text",
            class: "o_kp_search_input",
            placeholder: _t("Search an article..."),
            "aria-label": _t("Search an article"),
        });
        const results = h("div", { class: "o_kp_search_results" });
        const panel = h("div", { class: "o_kp_search_panel", role: "dialog" }, [
            h("div", { class: "o_kp_search_bar" }, [icon("search"), input]),
            results,
        ]);
        const overlay = h("div", { class: "o_kp_search_overlay" }, [panel]);
        document.body.append(overlay);
        this.searchEl = overlay;
        this.searchResults = results;
        this.searchIndex = 0;
        this.addListener(overlay, "click.noUpdate", (ev) => ev.target === overlay && this.closeSearch());
        this.addListener(input, "input.noUpdate", this.debounced(() => this.runSearch(input.value), 200));
        this.addListener(input, "keydown.noUpdate", (ev) => this.onSearchKeydown(ev));
        input.focus();
        this.runSearch("");
    }

    closeSearch() {
        this.searchEl?.remove();
        this.searchEl = null;
    }

    async runSearch(term) {
        let items;
        if (this.isPublic) {
            // anonymous visitors: the published tree is entirely in the sidebar
            const needle = term.trim().toLowerCase();
            const seen = new Set();
            items = [];
            for (const li of this.el.querySelectorAll(".o_kp_item")) {
                const info = this._itemInfo(li);
                if (seen.has(info.id) || (needle && !info.name.toLowerCase().includes(needle))) {
                    continue;
                }
                seen.add(info.id);
                items.push({ id: info.id, name: info.name, icon: li.dataset.icon || "", path: "", url: info.url });
            }
        } else {
            items = await this.waitFor(rpc("/knowledge/portal/search", { term }));
        }
        if (!this.searchEl) {
            return;
        }
        this.searchItems = items;
        this.searchIndex = 0;
        this.renderSearchResults();
    }

    renderSearchResults() {
        const results = this.searchResults;
        results.replaceChildren();
        if (!this.searchItems.length) {
            results.append(h("div", { class: "o_kp_search_empty", text: _t("No article found") }));
            return;
        }
        this.searchItems.forEach((item, index) => {
            const link = h("a", { href: item.url, class: "o_kp_search_result" }, [
                h("span", { class: "o_kp_item_icon", text: item.icon || "" }, item.icon ? [] : [icon("description")]),
                h("span", { class: "o_kp_search_name", text: item.name }),
                item.path && h("span", { class: "o_kp_search_path", text: item.path }),
            ]);
            if (index === this.searchIndex) {
                link.classList.add("o_kp_search_selected");
            }
            results.append(link);
        });
    }

    onSearchKeydown(ev) {
        const items = this.searchItems || [];
        if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
            ev.preventDefault();
            if (items.length) {
                const delta = ev.key === "ArrowDown" ? 1 : -1;
                this.searchIndex = (this.searchIndex + delta + items.length) % items.length;
                this.renderSearchResults();
                this.searchResults.querySelector(".o_kp_search_selected")?.scrollIntoView({ block: "nearest" });
            }
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            const item = items[this.searchIndex];
            if (item) {
                this._go(item.url);
            }
        }
    }

    // ── Editor ───────────────────────────────────────────────────────
    mountEditor() {
        const module = odoo.loader.modules.get(EDITOR_MODULE);
        const host = this.el.querySelector(".o_kp_body_host");
        const raw = this.el.querySelector(".o_kp_raw_body");
        if (!module || !host || !raw) {
            return;
        }
        const saveState = this.el.querySelector(".o_kp_save_state");
        host.replaceChildren();
        host.classList.add("o_kp_editing");
        this.mountComponent(host, module.KnowledgePortalEditor, {
            articleId: this.articleId,
            content: raw.value,
            title: this.el.dataset.articleName || "",
            register: (editor) => {
                this.editor = editor;
            },
            onStatus: (status) => {
                if (saveState) {
                    saveState.dataset.status = status;
                    saveState.title = {
                        saved: _t("Saved"),
                        unsaved: _t("Unsaved changes"),
                        saving: _t("Saving..."),
                        error: _t("The changes could not be saved"),
                    }[status];
                }
            },
            onTitle: (title) => this.updateTitle(title),
        });
    }

    updateTitle(title) {
        for (const el of this.el.querySelectorAll(
            `.o_kp_item[data-article-id="${this.articleId}"] > .o_kp_item_row .o_kp_item_name, .o_kp_title_current`
        )) {
            el.textContent = title;
        }
        for (const el of this.el.querySelectorAll(`.o_kp_item[data-article-id="${this.articleId}"], .o_kp_topbar`)) {
            el.dataset.name = title;
        }
        document.title = title;
    }
}

registry.category("public.interactions").add("hudson_knowledge.portal", KnowledgePortal);
