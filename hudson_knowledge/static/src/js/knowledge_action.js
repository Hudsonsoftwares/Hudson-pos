/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import {
    Component,
    proxy,
    signal,
    onMounted,
    onWillStart,
    onWillUnmount,
    markup,
    useProps,
    useApp,
} from "@odoo/owl";

const useState = proxy || ((obj) => obj);

// Fields that can't be changed while an article is locked (see Lock Content).
const LOCKED_CONTENT_FIELDS = ["name", "icon", "cover_image_url", "cover_position", "body_html"];

function useRef(name) {
    const s = signal.ref();
    Object.defineProperty(s, "el", {
        get() {
            return s();
        },
    });
    return s;
}

function enableOwl2TemplateScope(comp) {
    const node = comp.__owl__;
    if (!node || !node.app || !comp.constructor.template) return;
    const templateFn = node.app.getTemplate(comp.constructor.template);
    const target = { this: comp, __owl__: node };
    const proxyCtx = new Proxy(target, {
        get(t, prop, receiver) {
            if (prop in t) {
                return t[prop];
            }
            if (prop in comp) {
                const val = comp[prop];
                return typeof val === "function" ? val.bind(comp) : val;
            }
            if (typeof globalThis !== "undefined" && prop in globalThis) {
                return globalThis[prop];
            }
            return undefined;
        },
        set(t, prop, val, receiver) {
            // Owl creates loop / t-set scopes with Object.create(ctx): a write
            // on such a child scope must land on the child itself (receiver),
            // not on the shared root target, otherwise every t-foreach
            // iteration overwrites the same variable and all click handlers
            // see the last item of the loop.
            return Reflect.set(t, prop, val, receiver);
        },
        has(t, prop) {
            return prop in t || prop in comp || (typeof globalThis !== "undefined" && prop in globalThis);
        },
    });
    node.renderFn = () => templateFn.call(comp, proxyCtx, node);
}
import { Wysiwyg } from "@html_editor/wysiwyg";
import { MAIN_PLUGINS } from "@html_editor/plugin_sets";
import { KnowledgeEditorPlugin, isHudsonAIAvailable } from "./knowledge_wysiwyg_commands";
import { EmbeddedComponentPlugin } from "@html_editor/others/embedded_component_plugin";
import { HtmlViewer } from "@html_editor/components/html_viewer/html_viewer";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { router } from "@web/core/browser/router";
import { useSetupAction } from "@web/search/action_hook";
import { FormStatusIndicator } from "@web/views/form/form_status_indicator/form_status_indicator";
import { Chatter } from "@mail/chatter/web_portal_project/chatter";
import { browser } from "@web/core/browser/browser";
import { KnowledgePropertiesPanel } from "./knowledge_properties_panel";

// Remembers whether the chatter panel is open (per browser, like Odoo Online).
const CHATTER_STORAGE_KEY = "hudson_knowledge.chatter_open";
// Remembers whether the aside menu (sidebar) is collapsed.
const SIDEBAR_STORAGE_KEY = "hudson_knowledge.sidebar_collapsed";

// Captured before the action service rewrites the URL.
const INITIAL_ARTICLE_ID = parseInt(router.current?.article_id) || false;
let initialArticleConsumed = false;
import { KnowledgeShareDialog, KnowledgeMoveDialog } from "./knowledge_share_dialog";
import {
    createItemViewHost,
    getItemViewEmbedding,
    upgradeLegacyItemViews,
} from "./knowledge_item_view";
import { rpc } from "@web/core/network/rpc";
import { usePopover } from "@web/core/popover/popover_hook";
import { EmojiPicker, loader } from "@web/core/emoji_picker/emoji_picker";
import { MediaDialog } from "@html_editor/main/media/media_dialog/media_dialog";

function cleanHtmlContent(html) {
    if (!html || !html.trim()) {
        return `<h1><br></h1><p><br></p>`;
    }
    let str = String(html).trim();
    let passes = 0;
    while (passes < 3 && /&lt;\/?(h[1-6]|p|div|span|ul|ol|li|strong|em|table|tr|td|th|b|i|u|a|blockquote|pre|code|br|hr)\b/i.test(str)) {
        str = str
            .replace(/&lt;/g, "<")
            .replace(/&gt;/g, ">")
            .replace(/&amp;/g, "&")
            .replace(/&quot;/g, '"')
            .replace(/&#39;/g, "'");
        passes++;
    }

    // Strip any legacy data-placeholder attributes
    str = str.replace(/\s*data-placeholder="[^"]*"/gi, "");
    // Old hand-made item kanban/list/calendar blocks -> embedded Odoo views
    str = upgradeLegacyItemViews(str);

    if (!/<h1\b/i.test(str)) {
        str = `<h1><br></h1>` + str;
    }
    return str;
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function getInitialArticleHtml() {
    return `<h1><br></h1><p><br></p>`;
}

function updateEmptyHeadingClasses(root) {
    if (!root) return;
    const headings = root.querySelectorAll("h1, h2, h3");
    for (const h of headings) {
        const text = (h.textContent || "").replace(/[\n\r\uFEFF\s]/g, "");
        if (text.length === 0) {
            h.classList.add("o_empty_heading");
        } else {
            h.classList.remove("o_empty_heading");
        }
    }
}

function computeHtmlDiff(olderHtml, currentHtml) {
    if (!olderHtml && !currentHtml) return "";
    if (olderHtml === currentHtml) return currentHtml;

    const tokenize = (html) => {
        const tokens = [];
        const regex = /(<[^>]+>|[^<>\s]+|\s+)/g;
        let match;
        while ((match = regex.exec(html)) !== null) {
            tokens.push(match[0]);
        }
        return tokens;
    };

    const oldTokens = tokenize(olderHtml || "");
    const curTokens = tokenize(currentHtml || "");

    const m = Math.min(oldTokens.length, 1500);
    const n = Math.min(curTokens.length, 1500);

    const dp = Array.from({ length: m + 1 }, () => new Uint16Array(n + 1));
    for (let i = 1; i <= m; i++) {
        for (let j = 1; j <= n; j++) {
            if (oldTokens[i - 1] === curTokens[j - 1]) {
                dp[i][j] = dp[i - 1][j - 1] + 1;
            } else {
                dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1]);
            }
        }
    }

    let i = m, j = n;
    const result = [];
    while (i > 0 || j > 0) {
        if (i > 0 && j > 0 && oldTokens[i - 1] === curTokens[j - 1]) {
            result.unshift(oldTokens[i - 1]);
            i--;
            j--;
        } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
            const tok = curTokens[j - 1];
            if (tok.startsWith("<")) {
                result.unshift(tok);
            } else if (tok.trim().length > 0) {
                result.unshift(`<ins class="o_diff_ins">${tok}</ins>`);
            } else {
                result.unshift(tok);
            }
            j--;
        } else if (i > 0 && (j === 0 || dp[i][j - 1] < dp[i - 1][j])) {
            const tok = oldTokens[i - 1];
            if (!tok.startsWith("<") && tok.trim().length > 0) {
                result.unshift(`<del class="o_diff_del">${tok}</del>`);
            }
            i--;
        }
    }
    return result.join("");
}

// ─────────────────────────────────────────────────────────────────
// Knowledge Emoji Picker Component (Integrated, Zero-Crash)
// ─────────────────────────────────────────────────────────────────
const EMOJI_CATEGORIES = [
    { id: "smileys", name: "Smileys & Emotion", icon: "😀" },
    { id: "people", name: "People & Body", icon: "👍" },
    { id: "nature", name: "Animals & Nature", icon: "🐱" },
    { id: "food", name: "Food & Drink", icon: "🍕" },
    { id: "travel", name: "Travel & Places", icon: "🚗" },
    { id: "activities", name: "Activities", icon: "⚽" },
    { id: "objects", name: "Objects", icon: "💡" },
    { id: "symbols", name: "Symbols", icon: "❤️" },
    { id: "flags", name: "Flags", icon: "🚩" },
];

const EMOJI_DATA = [
    // Smileys & Emotion
    { emoji: "😀", name: "grinning face", cat: "smileys" },
    { emoji: "😃", name: "smiling face with big eyes", cat: "smileys" },
    { emoji: "😄", name: "smiling face with smiling eyes", cat: "smileys" },
    { emoji: "😁", name: "beaming face with smiling eyes", cat: "smileys" },
    { emoji: "😆", name: "grinning squinting face", cat: "smileys" },
    { emoji: "😅", name: "grinning face with sweat", cat: "smileys" },
    { emoji: "🤣", name: "rolling on the floor laughing", cat: "smileys" },
    { emoji: "😂", name: "face with tears of joy", cat: "smileys" },
    { emoji: "🙂", name: "slightly smiling face", cat: "smileys" },
    { emoji: "🙃", name: "upside-down face", cat: "smileys" },
    { emoji: "😉", name: "winking face", cat: "smileys" },
    { emoji: "😊", name: "smiling face with smiling eyes", cat: "smileys" },
    { emoji: "😇", name: "smiling face with halo", cat: "smileys" },
    { emoji: "🥰", name: "smiling face with hearts", cat: "smileys" },
    { emoji: "😍", name: "smiling face with heart-eyes", cat: "smileys" },
    { emoji: "🤩", name: "star-struck", cat: "smileys" },
    { emoji: "😘", name: "face blowing a kiss", cat: "smileys" },
    { emoji: "😗", name: "kissing face", cat: "smileys" },
    { emoji: "😚", name: "kissing face with closed eyes", cat: "smileys" },
    { emoji: "😙", name: "kissing face with smiling eyes", cat: "smileys" },
    { emoji: "😋", name: "face savoring food", cat: "smileys" },
    { emoji: "😛", name: "face with tongue", cat: "smileys" },
    { emoji: "😜", name: "winking face with tongue", cat: "smileys" },
    { emoji: "🤪", name: "zany face", cat: "smileys" },
    { emoji: "😝", name: "squinting face with tongue", cat: "smileys" },
    { emoji: "🤑", name: "money-mouth face", cat: "smileys" },
    { emoji: "🤗", name: "smiling face with open hands", cat: "smileys" },
    { emoji: "🤭", name: "face with hand over mouth", cat: "smileys" },
    { emoji: "🤫", name: "shushing face", cat: "smileys" },
    { emoji: "🤔", name: "thinking face", cat: "smileys" },
    { emoji: "🤐", name: "zipper-mouth face", cat: "smileys" },
    { emoji: "🤨", name: "face with raised eyebrow", cat: "smileys" },
    { emoji: "😐", name: "neutral face", cat: "smileys" },
    { emoji: "😑", name: "expressionless face", cat: "smileys" },
    { emoji: "😶", name: "face without mouth", cat: "smileys" },
    { emoji: "😏", name: "smirking face", cat: "smileys" },
    { emoji: "😒", name: "unamused face", cat: "smileys" },
    { emoji: "🙄", name: "face with rolling eyes", cat: "smileys" },
    { emoji: "😬", name: "grimacing face", cat: "smileys" },
    { emoji: "🤥", name: "lying face", cat: "smileys" },
    { emoji: "😌", name: "relieved face", cat: "smileys" },
    { emoji: "😔", name: "pensive face", cat: "smileys" },
    { emoji: "😪", name: "sleepy face", cat: "smileys" },
    { emoji: "🤤", name: "drooling face", cat: "smileys" },
    { emoji: "😴", name: "sleeping face", cat: "smileys" },
    { emoji: "😷", name: "face with medical mask", cat: "smileys" },
    { emoji: "🤒", name: "face with thermometer", cat: "smileys" },
    { emoji: "🤕", name: "face with head-bandage", cat: "smileys" },
    { emoji: "🤢", name: "nauseated face", cat: "smileys" },
    { emoji: "🤮", name: "face vomiting", cat: "smileys" },
    { emoji: "🥵", name: "hot face", cat: "smileys" },
    { emoji: "🥶", name: "cold face", cat: "smileys" },
    { emoji: "🥴", name: "woozy face", cat: "smileys" },
    { emoji: "😵", name: "knocked-out face", cat: "smileys" },
    { emoji: "🤯", name: "exploding head", cat: "smileys" },
    { emoji: "🥳", name: "partying face", cat: "smileys" },
    { emoji: "😎", name: "smiling face with sunglasses", cat: "smileys" },
    { emoji: "🤓", name: "nerd face", cat: "smileys" },
    { emoji: "🧐", name: "face with monocle", cat: "smileys" },
    { emoji: "😕", name: "confused face", cat: "smileys" },
    { emoji: "😟", name: "worried face", cat: "smileys" },
    { emoji: "🙁", name: "slightly frowning face", cat: "smileys" },
    { emoji: "😮", name: "face with open mouth", cat: "smileys" },
    { emoji: "😯", name: "hushed face", cat: "smileys" },
    { emoji: "😲", name: "astonished face", cat: "smileys" },
    { emoji: "😳", name: "flushed face", cat: "smileys" },
    { emoji: "🥺", name: "pleading face", cat: "smileys" },
    { emoji: "😦", name: "frowning face with open mouth", cat: "smileys" },
    { emoji: "😧", name: "anguished face", cat: "smileys" },
    { emoji: "😨", name: "fearful face", cat: "smileys" },
    { emoji: "😰", name: "anxious face with sweat", cat: "smileys" },
    { emoji: "😥", name: "sad but relieved face", cat: "smileys" },
    { emoji: "😢", name: "crying face", cat: "smileys" },
    { emoji: "😭", name: "loudly crying face", cat: "smileys" },
    { emoji: "😱", name: "face screaming in fear", cat: "smileys" },
    { emoji: "😖", name: "confounded face", cat: "smileys" },
    { emoji: "😣", name: "persevering face", cat: "smileys" },
    { emoji: "😞", name: "disappointed face", cat: "smileys" },
    { emoji: "😓", name: "downcast face with sweat", cat: "smileys" },
    { emoji: "😩", name: "weary face", cat: "smileys" },
    { emoji: "😫", name: "tired face", cat: "smileys" },
    { emoji: "🥱", name: "yawning face", cat: "smileys" },
    { emoji: "😤", name: "face with steam from nose", cat: "smileys" },
    { emoji: "😡", name: "pouting face", cat: "smileys" },
    { emoji: "😠", name: "angry face", cat: "smileys" },
    { emoji: "🤬", name: "face with symbols on mouth", cat: "smileys" },
    { emoji: "😈", name: "smiling face with horns", cat: "smileys" },
    { emoji: "👿", name: "angry face with horns", cat: "smileys" },
    { emoji: "💀", name: "skull", cat: "smileys" },
    { emoji: "💩", name: "pile of poo", cat: "smileys" },
    { emoji: "🤡", name: "clown face", cat: "smileys" },
    { emoji: "👹", name: "ogre", cat: "smileys" },
    { emoji: "👺", name: "goblin", cat: "smileys" },
    { emoji: "👻", name: "ghost", cat: "smileys" },
    { emoji: "👽", name: "alien", cat: "smileys" },
    { emoji: "🤖", name: "robot", cat: "smileys" },
    { emoji: "😺", name: "grinning cat", cat: "smileys" },
    { emoji: "😸", name: "grinning cat with smiling eyes", cat: "smileys" },
    { emoji: "😹", name: "cat with tears of joy", cat: "smileys" },
    { emoji: "😻", name: "smiling cat with heart-eyes", cat: "smileys" },
    { emoji: "😼", name: "cat with wry smile", cat: "smileys" },
    { emoji: "😽", name: "kissing cat", cat: "smileys" },
    { emoji: "🙀", name: "weary cat", cat: "smileys" },
    { emoji: "😿", name: "crying cat", cat: "smileys" },
    { emoji: "😾", name: "pouting cat", cat: "smileys" },
    { emoji: "🙈", name: "see-no-evil monkey", cat: "smileys" },
    { emoji: "🙉", name: "hear-no-evil monkey", cat: "smileys" },
    { emoji: "🙊", name: "speak-no-evil monkey", cat: "smileys" },

    // People & Body
    { emoji: "👋", name: "waving hand", cat: "people" },
    { emoji: "✋", name: "raised hand", cat: "people" },
    { emoji: "👌", name: "OK hand", cat: "people" },
    { emoji: "🤌", name: "pinched fingers", cat: "people" },
    { emoji: "🤏", name: "pinching hand", cat: "people" },
    { emoji: "✌️", name: "victory hand", cat: "people" },
    { emoji: "🤞", name: "crossed fingers", cat: "people" },
    { emoji: "🤟", name: "love-you gesture", cat: "people" },
    { emoji: "🤘", name: "sign of the horns", cat: "people" },
    { emoji: "🤙", name: "call me hand", cat: "people" },
    { emoji: "👈", name: "backhand index pointing left", cat: "people" },
    { emoji: "👉", name: "backhand index pointing right", cat: "people" },
    { emoji: "👆", name: "backhand index pointing up", cat: "people" },
    { emoji: "👇", name: "backhand index pointing down", cat: "people" },
    { emoji: "☝️", name: "index pointing up", cat: "people" },
    { emoji: "👍", name: "thumbs up", cat: "people" },
    { emoji: "👎", name: "thumbs down", cat: "people" },
    { emoji: "✊", name: "raised fist", cat: "people" },
    { emoji: "👊", name: "oncoming fist", cat: "people" },
    { emoji: "👏", name: "clapping hands", cat: "people" },
    { emoji: "🙌", name: "raising hands", cat: "people" },
    { emoji: "👐", name: "open hands", cat: "people" },
    { emoji: "🤲", name: "palms up together", cat: "people" },
    { emoji: "🤝", name: "handshake", cat: "people" },
    { emoji: "🙏", name: "folded hands", cat: "people" },
    { emoji: "✍️", name: "writing hand", cat: "people" },
    { emoji: "💪", name: "flexed biceps", cat: "people" },
    { emoji: "🧠", name: "brain", cat: "people" },
    { emoji: "👀", name: "eyes", cat: "people" },

    // Animals & Nature
    { emoji: "🐶", name: "dog face", cat: "nature" },
    { emoji: "🐱", name: "cat face", cat: "nature" },
    { emoji: "🐭", name: "mouse face", cat: "nature" },
    { emoji: "🐹", name: "hamster face", cat: "nature" },
    { emoji: "🐰", name: "rabbit face", cat: "nature" },
    { emoji: "🦊", name: "fox", cat: "nature" },
    { emoji: "🐻", name: "bear", cat: "nature" },
    { emoji: "🐼", name: "panda", cat: "nature" },
    { emoji: "🐨", name: "koala", cat: "nature" },
    { emoji: "🐯", name: "tiger face", cat: "nature" },
    { emoji: "🦁", name: "lion", cat: "nature" },
    { emoji: "🐮", name: "cow face", cat: "nature" },
    { emoji: "🐷", name: "pig face", cat: "nature" },
    { emoji: "🐸", name: "frog", cat: "nature" },
    { emoji: "🐵", name: "monkey face", cat: "nature" },
    { emoji: "🐔", name: "chicken", cat: "nature" },
    { emoji: "🐧", name: "penguin", cat: "nature" },
    { emoji: "🐦", name: "bird", cat: "nature" },
    { emoji: "🦆", name: "duck", cat: "nature" },
    { emoji: "🦅", name: "eagle", cat: "nature" },
    { emoji: "🦉", name: "owl", cat: "nature" },
    { emoji: "🦄", name: "unicorn", cat: "nature" },
    { emoji: "🐝", name: "honeybee", cat: "nature" },
    { emoji: "🦋", name: "butterfly", cat: "nature" },
    { emoji: "🌸", name: "cherry blossom", cat: "nature" },
    { emoji: "🌹", name: "rose", cat: "nature" },
    { emoji: "🌻", name: "sunflower", cat: "nature" },
    { emoji: "🌲", name: "evergreen tree", cat: "nature" },
    { emoji: "🌴", name: "palm tree", cat: "nature" },
    { emoji: "🍀", name: "four leaf clover", cat: "nature" },

    // Food & Drink
    { emoji: "🍎", name: "red apple", cat: "food" },
    { emoji: "🍌", name: "banana", cat: "food" },
    { emoji: "🍉", name: "watermelon", cat: "food" },
    { emoji: "🍇", name: "grapes", cat: "food" },
    { emoji: "🍓", name: "strawberry", cat: "food" },
    { emoji: "🍒", name: "cherries", cat: "food" },
    { emoji: "🥑", name: "avocado", cat: "food" },
    { emoji: "🥕", name: "carrot", cat: "food" },
    { emoji: "🌽", name: "ear of corn", cat: "food" },
    { emoji: "🍞", name: "bread", cat: "food" },
    { emoji: "🥐", name: "croissant", cat: "food" },
    { emoji: "🧀", name: "cheese wedge", cat: "food" },
    { emoji: "🍔", name: "hamburger", cat: "food" },
    { emoji: "🍟", name: "french fries", cat: "food" },
    { emoji: "🍕", name: "pizza", cat: "food" },
    { emoji: "🌭", name: "hot dog", cat: "food" },
    { emoji: "🌮", name: "taco", cat: "food" },
    { emoji: "🍣", name: "sushi", cat: "food" },
    { emoji: "🍜", name: "steaming bowl", cat: "food" },
    { emoji: "🍦", name: "soft ice cream", cat: "food" },
    { emoji: "🎂", name: "birthday cake", cat: "food" },
    { emoji: "🍫", name: "chocolate bar", cat: "food" },
    { emoji: "☕", name: "hot beverage", cat: "food" },
    { emoji: "🍺", name: "beer mug", cat: "food" },
    { emoji: "🍷", name: "wine glass", cat: "food" },

    // Travel & Places
    { emoji: "🚗", name: "automobile", cat: "travel" },
    { emoji: "🚕", name: "taxi", cat: "travel" },
    { emoji: "🏎️", name: "racing car", cat: "travel" },
    { emoji: "🚑", name: "ambulance", cat: "travel" },
    { emoji: "🚒", name: "fire engine", cat: "travel" },
    { emoji: "🚲", name: "bicycle", cat: "travel" },
    { emoji: "✈️", name: "airplane", cat: "travel" },
    { emoji: "🚀", name: "rocket", cat: "travel" },
    { emoji: "⛵", name: "sailboat", cat: "travel" },
    { emoji: "🛸", name: "flying saucer", cat: "travel" },
    { emoji: "🏠", name: "house", cat: "travel" },
    { emoji: "🏢", name: "office building", cat: "travel" },
    { emoji: "🏥", name: "hospital", cat: "travel" },
    { emoji: "🏦", name: "bank", cat: "travel" },
    { emoji: "🏨", name: "hotel", cat: "travel" },
    { emoji: "🏖️", name: "beach with umbrella", cat: "travel" },
    { emoji: "⛰️", name: "mountain", cat: "travel" },

    // Activities
    { emoji: "⚽", name: "soccer ball", cat: "activities" },
    { emoji: "🏀", name: "basketball", cat: "activities" },
    { emoji: "🎾", name: "tennis", cat: "activities" },
    { emoji: "🏐", name: "volleyball", cat: "activities" },
    { emoji: "🥊", name: "boxing glove", cat: "activities" },
    { emoji: "🎯", name: "bullseye", cat: "activities" },
    { emoji: "🎮", name: "video game", cat: "activities" },
    { emoji: "🎨", name: "artist palette", cat: "activities" },
    { emoji: "🎸", name: "guitar", cat: "activities" },
    { emoji: "🎬", name: "clapper board", cat: "activities" },

    // Objects
    { emoji: "💡", name: "light bulb", cat: "objects" },
    { emoji: "📱", name: "mobile phone", cat: "objects" },
    { emoji: "💻", name: "laptop", cat: "objects" },
    { emoji: "📷", name: "camera", cat: "objects" },
    { emoji: "⏰", name: "alarm clock", cat: "objects" },
    { emoji: "💰", name: "money bag", cat: "objects" },
    { emoji: "💳", name: "credit card", cat: "objects" },
    { emoji: "💎", name: "gem stone", cat: "objects" },
    { emoji: "🔧", name: "wrench", cat: "objects" },
    { emoji: "🔨", name: "hammer", cat: "objects" },
    { emoji: "📦", name: "package", cat: "objects" },
    { emoji: "📄", name: "page facing up", cat: "objects" },
    { emoji: "📊", name: "bar chart", cat: "objects" },
    { emoji: "📋", name: "clipboard", cat: "objects" },
    { emoji: "📌", name: "pushpin", cat: "objects" },
    { emoji: "📎", name: "paperclip", cat: "objects" },
    { emoji: "🔒", name: "locked", cat: "objects" },
    { emoji: "🔑", name: "key", cat: "objects" },
    { emoji: "📁", name: "file folder", cat: "objects" },
    { emoji: "📅", name: "calendar", cat: "objects" },
    { emoji: "📚", name: "books", cat: "objects" },
    { emoji: "✉️", name: "envelope", cat: "objects" },
    { emoji: "✏️", name: "pencil", cat: "objects" },

    // Symbols
    { emoji: "❤️", name: "red heart", cat: "symbols" },
    { emoji: "🧡", name: "orange heart", cat: "symbols" },
    { emoji: "💛", name: "yellow heart", cat: "symbols" },
    { emoji: "💚", name: "green heart", cat: "symbols" },
    { emoji: "💙", name: "blue heart", cat: "symbols" },
    { emoji: "💜", name: "purple heart", cat: "symbols" },
    { emoji: "🖤", name: "black heart", cat: "symbols" },
    { emoji: "⭐", name: "star", cat: "symbols" },
    { emoji: "✨", name: "sparkles", cat: "symbols" },
    { emoji: "🔥", name: "fire", cat: "symbols" },
    { emoji: "🎉", name: "party popper", cat: "symbols" },
    { emoji: "🏆", name: "trophy", cat: "symbols" },
    { emoji: "🥇", name: "1st place medal", cat: "symbols" },
    { emoji: "✔️", name: "check mark", cat: "symbols" },
    { emoji: "✅", name: "check mark button", cat: "symbols" },
    { emoji: "❌", name: "cross mark", cat: "symbols" },
    { emoji: "⚠️", name: "warning", cat: "symbols" },
    { emoji: "🛑", name: "stop sign", cat: "symbols" },
    { emoji: "🔔", name: "bell", cat: "symbols" },

    // Flags
    { emoji: "🚩", name: "triangular flag", cat: "flags" },
    { emoji: "🏁", name: "chequered flag", cat: "flags" },
    { emoji: "🏳️", name: "white flag", cat: "flags" },
    { emoji: "🏴", name: "black flag", cat: "flags" },
];

export class KnowledgeEmojiPicker extends Component {
    static template = "hudson_knowledge.KnowledgeEmojiPicker";
    props = useProps();

    setup() {
        this.categories = EMOJI_CATEGORIES;
        this.state = useState({
            searchTerm: "",
            activeCategory: "smileys",
            hoveredItem: null,
        });
        enableOwl2TemplateScope(this);
    }

    get currentCategoryTitle() {
        if (this.state.searchTerm.trim()) {
            return "Search Results";
        }
        const cat = this.categories.find((c) => c.id === this.state.activeCategory);
        return cat ? `${cat.icon} ${cat.name}` : "Smileys & Emotion";
    }

    get displayedEmojis() {
        const term = this.state.searchTerm.trim().toLowerCase().replace(/:/g, "");
        if (term) {
            return EMOJI_DATA.filter(
                (item) => item.name.toLowerCase().includes(term) || item.emoji.includes(term)
            );
        }
        return EMOJI_DATA.filter((item) => item.cat === this.state.activeCategory);
    }

    onSearchInput(ev) {
        this.state.searchTerm = ev.target.value;
    }

    onSelectCategory(catId) {
        this.state.activeCategory = catId;
        this.state.searchTerm = "";
    }

    onHoverEmoji(item) {
        this.state.hoveredItem = item;
    }

    onLeaveEmoji() {
        this.state.hoveredItem = null;
    }

    onSelectEmoji(emoji) {
        this.props.onSelect(emoji);
        this.props.close?.();
    }

    onRemoveEmoji(ev) {
        ev.stopPropagation();
        this.props.onRemove?.();
        this.props.close?.();
    }
}

// ── Ensure Odoo core EmojiPicker never crashes in content editor (Issue 4) ──
if (loader) {
    const origLoadEmoji = loader.loadEmoji;
    loader.loadEmoji = async () => {
        if (window.odoo?.loader?.modules?.has("@web/core/emoji_picker/emoji_data")) {
            return;
        }
        try {
            if (origLoadEmoji) await origLoadEmoji();
        } catch (e) {
            console.warn("loadEmoji bundle failed, using fallback data", e);
        }
    };
}

if (window.odoo?.loader?.modules && !window.odoo.loader.modules.has("@web/core/emoji_picker/emoji_data")) {
    const fallbackCategories = [
        { name: "Smileys & Emotion", displayName: "Smileys & Emotion", title: "😃", sortId: 1 },
        { name: "People & Body", displayName: "People & Body", title: "👋", sortId: 2 },
        { name: "Animals & Nature", displayName: "Animals & Nature", title: "🐱", sortId: 3 },
        { name: "Food & Drink", displayName: "Food & Drink", title: "🍕", sortId: 4 },
        { name: "Travel & Places", displayName: "Travel & Places", title: "🚗", sortId: 5 },
        { name: "Activities", displayName: "Activities", title: "⚽", sortId: 6 },
        { name: "Objects", displayName: "Objects", title: "💡", sortId: 7 },
        { name: "Symbols", displayName: "Symbols", title: "❤️", sortId: 8 },
        { name: "Flags", displayName: "Flags", title: "🚩", sortId: 9 },
    ];
    const fallbackEmojis = EMOJI_DATA.map((e) => ({
        name: e.name,
        codepoints: e.emoji,
        category: EMOJI_CATEGORIES.find(c => c.id === e.cat)?.name || "Smileys & Emotion",
        keywords: [e.name],
        shortcodes: [e.name.replace(/\s+/g, "_")],
        emoticons: [],
    }));
    window.odoo.loader.modules.set("@web/core/emoji_picker/emoji_data", {
        getCategories: () => fallbackCategories,
        getEmojis: () => fallbackEmojis,
    });
}

try {
    patch(EmojiPicker.prototype, {
        setup() {
            super.setup(...arguments);
            onWillStart(async () => {
                if (!this.categories || !this.categories.length) {
                    this.categories = [
                        { name: "Smileys & Emotion", displayName: "Smileys & Emotion", title: "😃", sortId: 1 },
                        { name: "People & Body", displayName: "People & Body", title: "👋", sortId: 2 },
                        { name: "Animals & Nature", displayName: "Animals & Nature", title: "🐱", sortId: 3 },
                        { name: "Food & Drink", displayName: "Food & Drink", title: "🍕", sortId: 4 },
                        { name: "Travel & Places", displayName: "Travel & Places", title: "🚗", sortId: 5 },
                        { name: "Activities", displayName: "Activities", title: "⚽", sortId: 6 },
                        { name: "Objects", displayName: "Objects", title: "💡", sortId: 7 },
                        { name: "Symbols", displayName: "Symbols", title: "❤️", sortId: 8 },
                        { name: "Flags", displayName: "Flags", title: "🚩", sortId: 9 },
                    ];
                    if (!this.state.categoryId) {
                        this.state.categoryId = 1;
                    }
                }
            });
        },
    });
} catch (e) {
    console.warn("EmojiPicker prototype patch skipped", e);
}

// ─────────────────────────────────────────────────────────────────
// Curated Unsplash Covers (Matching Images 2 & 3)
// ─────────────────────────────────────────────────────────────────
const CURATED_COVERS = [
    // Image 2: Matera ancient cave city at sunset
    {
        id: "matera",
        url: "https://images.unsplash.com/photo-1516483638261-f4dbaf036963?auto=format&fit=crop&w=1600&q=80",
        photographer: "Matera Sunset",
        category: "travel",
    },
    // Image 3: Exact 15 Car Covers with Photographer Credits
    {
        id: "car_1",
        url: "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=800&q=80",
        photographer: "Josh Berquist",
        category: "cars",
    },
    {
        id: "car_2",
        url: "https://images.unsplash.com/photo-1614162692292-7ac56d7f7f1e?auto=format&fit=crop&w=800&q=80",
        photographer: "Campbell",
        category: "cars",
    },
    {
        id: "car_3",
        url: "https://images.unsplash.com/photo-1542282088-72c9c27ed0cd?auto=format&fit=crop&w=800&q=80",
        photographer: "Olav Tvedt",
        category: "cars",
    },
    {
        id: "car_4",
        url: "https://images.unsplash.com/photo-1552519507-da3b142c6e3d?auto=format&fit=crop&w=800&q=80",
        photographer: "Erik Mclean",
        category: "cars",
    },
    {
        id: "car_5",
        url: "https://images.unsplash.com/photo-1603584173870-7f23fdae1b7a?auto=format&fit=crop&w=800&q=80",
        photographer: "Tyler Clemmensen",
        category: "cars",
    },
    {
        id: "car_6",
        url: "https://images.unsplash.com/photo-1583121274602-3e2820c69888?auto=format&fit=crop&w=800&q=80",
        photographer: "Peter Broomfield",
        category: "cars",
    },
    {
        id: "car_7",
        url: "https://images.unsplash.com/photo-1502877338535-766e1452684a?auto=format&fit=crop&w=800&q=80",
        photographer: "Ville Kaisla",
        category: "cars",
    },
    {
        id: "car_8",
        url: "https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?auto=format&fit=crop&w=800&q=80",
        photographer: "Sven D",
        category: "cars",
    },
    {
        id: "car_9",
        url: "https://images.unsplash.com/photo-1525609004556-c46c7d6cf023?auto=format&fit=crop&w=800&q=80",
        photographer: "Dhiva Krishna",
        category: "cars",
    },
    {
        id: "car_10",
        url: "https://images.unsplash.com/photo-1617814076367-b759c7d7e738?auto=format&fit=crop&w=800&q=80",
        photographer: "Hyundai Motor Group",
        category: "cars",
    },
    {
        id: "car_11",
        url: "https://images.unsplash.com/photo-1568605117036-5fe5e7bab0b7?auto=format&fit=crop&w=800&q=80",
        photographer: "Joshua Koblin",
        category: "cars",
    },
    {
        id: "car_12",
        url: "https://images.unsplash.com/photo-1617788138017-80ad40651399?auto=format&fit=crop&w=800&q=80",
        photographer: "Yuvraj Singh",
        category: "cars",
    },
    {
        id: "car_13",
        url: "https://images.unsplash.com/photo-1541348263662-e0c866661ba5?auto=format&fit=crop&w=800&q=80",
        photographer: "Evgeny",
        category: "cars",
    },
    {
        id: "car_14",
        url: "https://images.unsplash.com/photo-1511919884226-fd3cad34687c?auto=format&fit=crop&w=800&q=80",
        photographer: "Florian Schneider",
        category: "cars",
    },
    {
        id: "car_15",
        url: "https://images.unsplash.com/photo-1549399542-7e3f8b79c341?auto=format&fit=crop&w=800&q=80",
        photographer: "Lance Asper",
        category: "cars",
    },
    // Nature
    {
        id: "nature_1",
        url: "https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?auto=format&fit=crop&w=800&q=80",
        photographer: "Kalen Emsley",
        category: "nature",
    },
    {
        id: "nature_2",
        url: "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&w=800&q=80",
        photographer: "Luca Bravo",
        category: "nature",
    },
    {
        id: "nature_3",
        url: "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?auto=format&fit=crop&w=800&q=80",
        photographer: "Sean Oulashin",
        category: "nature",
    },
    // Architecture
    {
        id: "arch_1",
        url: "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=800&q=80",
        photographer: "Simone Hutsch",
        category: "architecture",
    },
    {
        id: "arch_2",
        url: "https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=800&q=80",
        photographer: "Dan Freeman",
        category: "architecture",
    },
    // Travel
    {
        id: "travel_1",
        url: "https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?auto=format&fit=crop&w=800&q=80",
        photographer: "Sprengben",
        category: "travel",
    },
    {
        id: "travel_2",
        url: "https://images.unsplash.com/photo-1493976040374-85c8e12f0c0e?auto=format&fit=crop&w=800&q=80",
        photographer: "Tianshu Liu",
        category: "travel",
    },
    // Space
    {
        id: "space_1",
        url: "https://images.unsplash.com/photo-1506703719100-a0f3a48c0f86?auto=format&fit=crop&w=800&q=80",
        photographer: "NASA",
        category: "space",
    },
    // Minimal
    {
        id: "min_1",
        url: "https://images.unsplash.com/photo-1494438639946-1ebd1d20bf85?auto=format&fit=crop&w=800&q=80",
        photographer: "Scott Webb",
        category: "minimal",
    },
    // Abstract
    {
        id: "abs_1",
        url: "https://images.unsplash.com/photo-1541701494587-cb58502866ab?auto=format&fit=crop&w=800&q=80",
        photographer: "Geordanna Cordero",
        category: "abstract",
    },
];

// ─────────────────────────────────────────────────────────────────
// Main Knowledge Client Action
// ─────────────────────────────────────────────────────────────────
export class KnowledgeClientAction extends Component {
    static template = "hudson_knowledge.KnowledgeClientAction";
    static components = {
        Wysiwyg, HtmlViewer, KnowledgeEmojiPicker, FormStatusIndicator, Chatter, KnowledgePropertiesPanel,
    };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialogService = useService("dialog");
        this.app = useApp();
        this.itemViewEmbeddings = [getItemViewEmbedding(this)];
        this.readonlyItemViewEmbeddings = [getItemViewEmbedding(this, true)];

        this.bodyContainer = useRef("bodyContainer");
        this.kebabMenu = useRef("kebabMenu");
        this.contentArea = useRef("contentArea");
        this.insertViewNameInput = useRef("insertViewNameInput");
        this.titleEmojiRef = useRef("titleEmoji");
        this.toolbarEmojiRef = useRef("toolbarEmoji");
        this.titleEmoji = this.titleEmojiRef;
        this.toolbarEmoji = this.toolbarEmojiRef;
        this.kebabBtn = useRef("kebabBtn");
        this.coverImg = useRef("coverImg");

        // Save like an Odoo form view: when leaving the action (breadcrumbs,
        // menus), when the browser tab gets hidden and when the page closes.
        useSetupAction({
            beforeLeave: () => this.saveArticle(),
            beforeVisibilityChange: () => {
                if (document.visibilityState === "hidden") {
                    return this.saveArticle();
                }
            },
            beforeUnload: () => this._urgentSave(),
        });
        this._boundDocumentClick = this._onDocumentClick.bind(this);

        this.emojiPopover = usePopover(KnowledgeEmojiPicker, {
            position: "bottom-start",
            closeOnClickOutside: true,
        });

        this.state = useState({
            loading: true,
            sidebar: {
                favorites: [],
                workspace: [],
                shared: [],
                private: [],
            },
            currentArticle: null,
            expandedIds: [],
            isDragging: false,
            childrenMap: {},
            showKebab: false,
            showChatter: this._readChatterPref(),
            sidebarCollapsed: this._readSidebarPref(),
            // Properties panel: opened with "Add Properties", or shown when the
            // article has properties (unless closed for that article).
            propertiesOpenFor: false,
            propertiesHiddenFor: false,
            propertiesCreateRequest: 0,
            editorKey: 0,
            showAIDialog: false,
            aiPrompt: "",
            aiPlaceholder: "",
            aiPreset: "plan",
            aiGenerating: false,
            showTemplateDialog: false,
            availableTemplates: [],
            templateCategories: [],
            selectedTemplateId: false,
            showSaveTemplateDialog: false,
            saveTemplateName: "",
            saveTemplateCategoryId: false,
            saveTemplateCategories: [],
            savingTemplate: false,
            showInsertViewModal: false,
            showItemDbMenu: false,
            insertViewType: "kanban",
            insertViewName: "",
            saveStatus: "saved",
            showItemPromptModal: false,
            itemPromptTitle: "",
            itemPromptLabel: "",
            itemPromptValue: "",
            itemPromptShowDelete: false,
            // Cover modal state
            showCoverModal: false,
            coverSearchQuery: "",
            coverActiveCategory: "all",
            showAddUrlTray: false,
            customCoverUrl: "",
            unsplashConfigured: false,
            coverPageLimit: 15,
            // Cover drag repositioning
            isRepositioningCover: false,
            savedCoverPosition: "50%",
            // Sidebar context menu
            sidebarMenu: {
                isOpen: false,
                article: null,
                x: 0,
                y: 0,
            },
            // Version History modal state (Matching Image 1)
            showHistoryModal: false,
            historyVersions: [],
            selectedHistoryVersion: null,
            historyShowComparison: true,
            historyIsFullscreen: false,
            historyLoading: false,
        });

        this._savePromise = null;
        this._lastSavedTitle = "";
        this._lastSavedBodyHtml = "";
        this._savedRange = null;
        this._lastTargetBlock = null;
        this._targetInsertionBlock = null;
        this._itemPromptResolver = null;
        this.editor = null;

        this._onDocSelectionChange = () => {
            if (!this.editor?.editable) return;
            const sel = window.getSelection();
            if (sel && sel.anchorNode && this.editor.editable.contains(sel.anchorNode)) {
                let curr = sel.anchorNode.nodeType === Node.ELEMENT_NODE ? sel.anchorNode : sel.anchorNode.parentElement;
                while (curr && curr.parentElement && curr.parentElement !== this.editor.editable) {
                    curr = curr.parentElement;
                }
                if (curr && curr.parentElement === this.editor.editable) {
                    this._lastTargetBlock = curr;
                }
            }
        };

        onMounted(async () => {
            await this._loadSidebar();
            // "Open in new tab" / invitation links: /odoo/action-...?article_id=ID
            const urlArticleId = parseInt(router.current?.article_id)
                || (!initialArticleConsumed && INITIAL_ARTICLE_ID);
            initialArticleConsumed = true;
            const resId = this.props.action?.params?.res_id || this.props.action?.params?.article_id || urlArticleId;
            if (resId) {
                await this.openArticle(resId);
            } else {
                const topId = await this.orm.call(
                    "knowledge.management.article",
                    "get_top_article",
                    []
                );
                if (topId) {
                    await this.openArticle(topId);
                } else {
                    this.state.loading = false;
                }
            }
            document.addEventListener("click", this._boundDocumentClick);
            document.addEventListener("selectionchange", this._onDocSelectionChange);
        });

        onWillUnmount(() => {
            document.removeEventListener("click", this._boundDocumentClick);
            document.removeEventListener("selectionchange", this._onDocSelectionChange);
            this.editor = null;
        });
        enableOwl2TemplateScope(this);
    }

    // ── Editor Configuration & Keys ───────────────────────────────

    /** True while the open article has no content at all (new article). */
    get isArticleBodyEmpty() {
        const html = this.state.currentArticle?.body_html || "";
        if (/<(img|iframe|video|table|li|hr)\b|data-embedded/i.test(html)) {
            return false;
        }
        const text = html
            .replace(/<[^>]*>/g, "")
            .replace(/&nbsp;|[\s​﻿]/g, "");
        return text.length === 0;
    }

    get showGetStarted() {
        return (
            this.isArticleBodyEmpty &&
            !this.isInTrash &&
            !this.isArticleReadonly &&
            !this.state.currentArticle?.is_locked &&
            this.state.currentArticle?.user_can_write !== false
        );
    }

    get isAIAvailable() {
        return isHudsonAIAvailable();
    }

    onToggleItemDbMenu(ev) {
        ev.stopPropagation();
        this.state.showItemDbMenu = !this.state.showItemDbMenu;
    }

    onPickItemDb(viewType) {
        this.state.showItemDbMenu = false;
        this.openInsertViewModal(viewType);
    }

    get wysiwygKey() {
        return `art_${this.state.currentArticle?.id || 0}_${this.state.editorKey}`;
    }

    get editorConfig() {
        const article = this.state.currentArticle;
        let bodyHtml = article?.body_html || "";
        bodyHtml = cleanHtmlContent(bodyHtml);

        return {
            content: markup(bodyHtml),
            Plugins: [
                ...MAIN_PLUGINS,
                EmbeddedComponentPlugin,
                KnowledgeEditorPlugin,
            ],
            resources: {
                embedded_components: this.itemViewEmbeddings,
            },
            embeddedComponentInfo: { app: this.app, env: this.env },
            knowledgeAction: this,
            classList: ["o_knowledge_body", "note-editable"],
            onChange: () => this.onEditorChange(),
            dropImageAsAttachment: true,
            direction: "ltr",
            baseContainers: ["DIV", "P"],
        };
    }

    getReadonlyBody() {
        return markup(cleanHtmlContent(this.state.currentArticle?.body_html || ""));
    }

    get readonlyViewerConfig() {
        return {
            value: this.getReadonlyBody(),
            embeddedComponents: this.readonlyItemViewEmbeddings,
        };
    }

    async onEditorLoad(editor) {
        this.editor = editor;
        const artId = this.state.currentArticle?.id;
        setTimeout(() => {
            if (this.editor?.editable && this.state.currentArticle) {
                // The editor normalizes the stored HTML: use its output as the
                // clean state, so merely opening an article never looks dirty.
                if (
                    this.state.currentArticle.id === artId &&
                    this.state.saveStatus === "saved" &&
                    !this._savePromise
                ) {
                    this._lastSavedBodyHtml = this._getEditorHtml();
                }
                updateEmptyHeadingClasses(this.editor.editable);
                if (this._focusTitleOnLoad === this.state.currentArticle.id) {
                    this._focusTitleOnLoad = null;
                    const h1 = this.editor.editable.querySelector("h1");
                    if (h1 && !(h1.textContent || "").trim()) {
                        this.editor.editable.focus();
                        const range = document.createRange();
                        range.setStart(h1, 0);
                        range.collapse(true);
                        const sel = window.getSelection();
                        sel.removeAllRanges();
                        sel.addRange(range);
                    }
                }
                this.editor.editable.addEventListener("input", () => {
                    updateEmptyHeadingClasses(this.editor.editable);
                    this.onEditorChange();
                });
                const savePointerLocation = (ev) => {
                    let target = ev?.target;
                    if (!target && window.getSelection) {
                        const sel = window.getSelection();
                        if (sel && sel.anchorNode) {
                            target = sel.anchorNode.nodeType === Node.ELEMENT_NODE ? sel.anchorNode : sel.anchorNode.parentElement;
                        }
                    }
                    if (target && this.editor?.editable?.contains(target)) {
                        let curr = target;
                        while (curr && curr.parentElement && curr.parentElement !== this.editor.editable) {
                            curr = curr.parentElement;
                        }
                        if (curr && curr.parentElement === this.editor.editable) {
                            this._lastTargetBlock = curr;
                        }
                    }
                    this._savedRange = this._getEditorSelectionRange();
                };
                this.editor.editable.addEventListener("mouseup", savePointerLocation);
                this.editor.editable.addEventListener("keyup", savePointerLocation);
                this.editor.editable.addEventListener("click", savePointerLocation);
            }
        }, 40);
    }

    onToolbarTitleInput(ev) {
        if (this.isArticleReadonly) return;
        const val = ev.target.value;
        this.state.currentArticle.name = val;
        this._syncArticleToSidebar(this.state.currentArticle.id, { name: val || "Untitled" });
        if (this.editor?.editable) {
            const h1 = this.editor.editable.querySelector("h1");
            if (h1 && h1.innerText.trim() !== val.trim()) {
                h1.innerText = val;
            }
            updateEmptyHeadingClasses(this.editor.editable);
        }
        this._refreshDirty();
    }

    onToolbarTitleChange(ev) {
        if (this.isArticleReadonly) return;
        const val = ev.target.value.trim() || "Untitled";
        this.state.currentArticle.name = val;
        this._syncArticleToSidebar(this.state.currentArticle.id, { name: val });
        this._refreshDirty();
    }

    onCloseArticle() {
        this.state.currentArticle = null;
    }

    // ── Chatter panel (toolbar toggle, Odoo Online) ───────────────

    _readChatterPref() {
        try {
            return browser.localStorage.getItem(CHATTER_STORAGE_KEY) === "1";
        } catch {
            return false;
        }
    }

    onToggleChatter() {
        this.state.showChatter = !this.state.showChatter;
        this.state.showKebab = false;
        try {
            browser.localStorage.setItem(CHATTER_STORAGE_KEY, this.state.showChatter ? "1" : "0");
        } catch {
            // Storage unavailable (private mode): the panel still toggles.
        }
    }

    // ── Toggle aside menu (collapse / expand the sidebar) ─────────

    _readSidebarPref() {
        try {
            return browser.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1";
        } catch {
            return false;
        }
    }

    onToggleSidebar() {
        this.state.sidebarCollapsed = !this.state.sidebarCollapsed;
        this.onCloseSidebarMenu?.();
        try {
            browser.localStorage.setItem(SIDEBAR_STORAGE_KEY, this.state.sidebarCollapsed ? "1" : "0");
        } catch {
            // Storage unavailable (private mode): the sidebar still toggles.
        }
    }

    // ── Properties panel ("Add Properties", Odoo Online) ──────────

    /** Properties need a parent article: it holds their definition. */
    get canAddProperties() {
        const art = this.state.currentArticle;
        return !!(art && art.parent_id && !this.isArticleReadonly);
    }

    get showPropertiesPanel() {
        const art = this.state.currentArticle;
        if (!art || !art.parent_id || this.state.propertiesHiddenFor === art.id) {
            return false;
        }
        return !!art.has_properties || this.state.propertiesOpenFor === art.id;
    }

    onAddProperties() {
        const art = this.state.currentArticle;
        this.state.showKebab = false;
        if (!art) return;
        this._pendingPropertyCreate = true;
        this.state.propertiesHiddenFor = false;
        this.state.propertiesOpenFor = art.id;
        this.state.propertiesCreateRequest++;
    }

    onCloseProperties() {
        const art = this.state.currentArticle;
        this.state.propertiesOpenFor = false;
        this.state.propertiesHiddenFor = art ? art.id : false;
    }

    consumePropertyCreateRequest() {
        const pending = !!this._pendingPropertyCreate;
        this._pendingPropertyCreate = false;
        return pending;
    }

    registerPropertiesPanel(panel, oldPanel) {
        if (panel) {
            this._propertiesPanel = panel;
        } else if (this._propertiesPanel === oldPanel) {
            this._propertiesPanel = null;
        }
    }

    onPropertiesSaved(articleId, hasProperties) {
        const art = this.state.currentArticle;
        if (art && art.id === articleId) {
            art.has_properties = hasProperties;
        }
    }

    // ── Save / Discard (Odoo's FormStatusIndicator) ───────────────

    /** Unsaved title/body changes, like a dirty form record. */
    get isDirty() {
        return Boolean(
            this.state.currentArticle &&
            !this.isArticleReadonly &&
            this.state.saveStatus === "unsaved"
        );
    }

    _getEditorHtml() {
        if (this.editor?.editable && !this.editor.isDestroyed) {
            const el = this.editor.getElContent ? this.editor.getElContent() : null;
            if (el) return el.innerHTML;
        }
        return this.state.currentArticle?.body_html || "";
    }

    /** Values to write: only the fields that differ from the last save. */
    _getChanges() {
        const article = this.state.currentArticle;
        if (!article || this.isArticleReadonly) return null;
        const name = (article.name || "Untitled").trim() || "Untitled";
        const body = this._getEditorHtml();
        const vals = {};
        if (name !== this._lastSavedTitle) vals.name = name;
        if (body !== this._lastSavedBodyHtml) vals.body_html = body;
        return Object.keys(vals).length ? { id: article.id, vals, name, body } : null;
    }

    _refreshDirty() {
        this.state.saveStatus = this._getChanges() ? "unsaved" : "saved";
    }

    _markDirty() {
        if (this.state.currentArticle && !this.isArticleReadonly) {
            this.state.saveStatus = "unsaved";
        }
    }

    /**
     * Saves the pending changes of the open article (no-op when clean).
     * Concurrent calls wait for the running write; edits typed during the
     * write keep the article dirty.
     */
    async saveArticle() {
        // Pending property values of the open article (properties panel).
        await this._propertiesPanel?.flush().catch(() => {});
        if (this._savePromise) {
            await this._savePromise.catch(() => {});
        }
        const changes = this._getChanges();
        if (!changes) {
            if (this.state.currentArticle) this.state.saveStatus = "saved";
            return true;
        }
        this._savePromise = (async () => {
            try {
                await this.orm.write("knowledge.management.article", [changes.id], changes.vals);
                this._lastSavedTitle = changes.name;
                this._lastSavedBodyHtml = changes.body;
                if (this.state.currentArticle?.id === changes.id) {
                    this.state.currentArticle.body_html = changes.body;
                    this._refreshDirty();
                }
                if (changes.vals.name) {
                    await this._loadSidebar();
                }
                return true;
            } catch (e) {
                // Stay dirty: the user can retry or discard (the RPC error
                // dialog explains what went wrong).
                this.state.saveStatus = "unsaved";
                throw e;
            } finally {
                this._savePromise = null;
            }
        })();
        return this._savePromise;
    }

    /** Page is closing: no time for an awaited RPC, send it as a beacon. */
    _urgentSave() {
        const changes = this._getChanges();
        if (!changes || !navigator.sendBeacon) return;
        const payload = {
            jsonrpc: "2.0",
            method: "call",
            id: Date.now(),
            params: {
                model: "knowledge.management.article",
                method: "write",
                args: [[changes.id], changes.vals],
                kwargs: {},
            },
        };
        navigator.sendBeacon(
            "/web/dataset/call_kw/knowledge.management.article/write",
            new Blob([JSON.stringify(payload)], { type: "application/json" })
        );
    }

    /** Status indicator "Save manually" (cloud) button. */
    async onForceSave() {
        await this.saveArticle();
    }

    /** Status indicator "Discard all changes" button: back to the last save. */
    async onDiscardChanges() {
        if (!this.state.currentArticle) return;
        const articleId = this.state.currentArticle.id;
        this.state.saveStatus = "saved";
        await this.openArticle(articleId, { discard: true });
        await this._loadSidebar();
    }

    onEditorBlur() {
        if (!this.editor || this.editor.isDestroyed || !this.editor.editable || !this.state.currentArticle) {
            return;
        }
        try {
            updateEmptyHeadingClasses(this.editor.editable);
            const el = this.editor.getElContent ? this.editor.getElContent() : null;
            const content = el?.innerHTML;
            if (content !== undefined) {
                this.state.currentArticle.body_html = content;
                this._syncTitleFromEditor();
                this._refreshDirty();
            }
        } catch (e) {
            console.warn("Editor blur save skipped:", e);
        }
    }

    onEditorChange() {
        if (!this.editor || this.editor.isDestroyed || !this.editor.editable || !this.state.currentArticle) {
            return;
        }
        try {
            updateEmptyHeadingClasses(this.editor.editable);
            const el = this.editor.getElContent ? this.editor.getElContent() : null;
            const content = el?.innerHTML;
            if (content !== undefined) {
                this.state.currentArticle.body_html = content;
                this._syncTitleFromEditor();

                // Typing back the saved text makes the article clean again.
                this._refreshDirty();
            }
        } catch (e) {
            console.warn("Editor change save skipped:", e);
        }
    }

    /**
     * The article title is the first <h1>. When it is left empty (e.g. the
     * user started typing in the paragraph below it), fall back to the first
     * line of text written in the article so the sidebar never stays
     * "Untitled" for an article that has content.
     */
    _getTitleFromEditable(editable) {
        const clean = (txt) => (txt || "").replace(/[\n\r﻿​]/g, " ").replace(/\s+/g, " ").trim();
        const h1 = editable.querySelector("h1");
        let title = h1 ? clean(h1.innerText) : "";
        if (!title) {
            for (const block of editable.children) {
                if (block === h1 || block.matches("[data-oe-protected], [data-embedded], .o_knowledge_behavior_anchor")) {
                    continue;
                }
                title = clean(block.innerText);
                if (title) break;
            }
        }
        if (title.length > 100) {
            title = title.slice(0, 100).trim() + "…";
        }
        return title || "Untitled";
    }

    _syncTitleFromEditor() {
        if (!this.editor?.editable || !this.state.currentArticle) return;
        const title = this._getTitleFromEditable(this.editor.editable);
        if (this.state.currentArticle.name !== title) {
            this.state.currentArticle.name = title;
            this._syncArticleToSidebar(this.state.currentArticle.id, { name: title });
            this._markDirty();
        }
    }

    // ── Click Handlers for In-Editor Jump Buttons ──────────────────

    onEditorContainerClick(ev) {
        if (this.state.showItemDbMenu) {
            this.state.showItemDbMenu = false;
        }
        const jumpBtn = ev.target.closest(".o_knowledge_jump_item");
        if (!jumpBtn) return;
        ev.preventDefault();
        ev.stopPropagation();

        const action = jumpBtn.dataset.action;
        if (action === "template") {
            this.onBrowseTemplates();
        } else if (action === "kanban") {
            this.openInsertViewModal("kanban");
        } else if (action === "list") {
            this.openInsertViewModal("list");
        } else if (action === "calendar") {
            this.openInsertViewModal("calendar");
        } else if (action === "ai") {
            this.onOpenAIGenerator();
        }
    }

    // ── Data Loading & Article Selection ──────────────────────────

    async _loadSidebar() {
        const data = await this.orm.call(
            "knowledge.management.article",
            "get_sidebar_articles",
            []
        );
        this.state.sidebar = data || {
            favorites: [],
            workspace: [],
            shared: [],
            private: [],
        };
    }

    async _refreshExpandedChildren() {
        if (!this.state.expandedIds || !this.state.expandedIds.length) return;
        // Reload every open branch: this also refreshes the child_count (caret)
        // of nested articles, which only their parent's list carries.
        await Promise.all(this.state.expandedIds.map(async (parentId) => {
            try {
                const children = await this.orm.call(
                    "knowledge.management.article",
                    "get_article_children",
                    [parentId]
                );
                this.state.childrenMap[parentId] = children || [];
            } catch (e) {
                console.warn("Failed to refresh children for", parentId, e);
            }
        }));
    }

    _syncArticleToSidebar(articleId, updates) {
        if (!articleId) return;
        const updateList = (list) => {
            if (!list || !list.length) return;
            for (const item of list) {
                if (item.id === articleId) {
                    Object.assign(item, updates);
                }
            }
        };
        if (this.state.sidebar) {
            updateList(this.state.sidebar.favorites);
            updateList(this.state.sidebar.workspace);
            updateList(this.state.sidebar.shared);
            updateList(this.state.sidebar.private);
        }
        if (this.state.childrenMap) {
            for (const pid in this.state.childrenMap) {
                updateList(this.state.childrenMap[pid]);
            }
        }
    }

    _removeArticleFromSidebarState(articleId) {
        const filterOut = (list) => list ? list.filter(a => a.id !== articleId) : [];
        if (this.state.sidebar) {
            this.state.sidebar.favorites = filterOut(this.state.sidebar.favorites);
            this.state.sidebar.workspace = filterOut(this.state.sidebar.workspace);
            this.state.sidebar.shared = filterOut(this.state.sidebar.shared);
            this.state.sidebar.private = filterOut(this.state.sidebar.private);
        }
        if (this.state.childrenMap) {
            for (const pid in this.state.childrenMap) {
                this.state.childrenMap[pid] = filterOut(this.state.childrenMap[pid]);
            }
        }
    }

    _formatRelativeTime(dateStr) {
        if (!dateStr) return "recently";
        try {
            // Odoo datetimes are stored in UTC (e.g. "2026-09-21 14:45:00" or ISO string)
            const utcString = dateStr.endsWith("Z") ? dateStr : dateStr.replace(" ", "T") + "Z";
            const timestamp = Date.parse(utcString);
            if (isNaN(timestamp)) return "recently";
            const diffMs = Math.max(0, Date.now() - timestamp);
            const diffSecs = Math.floor(diffMs / 1000);
            if (diffSecs < 60) return "just now";
            const diffMins = Math.floor(diffSecs / 60);
            if (diffMins < 60) return `${diffMins}m ago`;
            const diffHours = Math.floor(diffMins / 60);
            if (diffHours < 24) return `${diffHours}h ago`;
            const diffDays = Math.floor(diffHours / 24);
            if (diffDays < 30) return `${diffDays}d ago`;
            const diffMonths = Math.floor(diffDays / 30);
            return `${diffMonths}mo ago`;
        } catch {
            return "recently";
        }
    }

    async openArticle(articleId, { discard = false } = {}) {
        // Switching article saves the current one, like a form pager.
        if (!discard) {
            await this.saveArticle();
        }
        this.state.loading = true;
        try {
            const records = await this.orm.call(
                "knowledge.management.article",
                "get_article_data",
                [],
                { context: { active_id: articleId } }
            ).catch(async () => {
                const recs = await this.orm.searchRead(
                    "knowledge.management.article",
                    [["id", "=", articleId]],
                    ["id", "name", "icon", "cover_image_url", "cover_position", "body_html",
                     "visibility", "is_locked", "full_width",
                     "write_uid", "write_date", "parent_id", "favorite_user_ids",
                     "active", "to_delete_date"],
                    { context: { active_test: false } }
                );
                if (!recs || !recs.length) return null;
                const r = recs[0];
                const uid = this.env.services.user?.userId || 1;
                return {
                    id: r.id,
                    name: r.name,
                    icon: r.icon || "",
                    cover_image_url: r.cover_image_url || false,
                    cover_position: r.cover_position || "50%",
                    body_html: cleanHtmlContent(r.body_html),
                    visibility: r.visibility,
                    is_locked: r.is_locked,
                    full_width: r.full_width,
                    is_user_favorite: (r.favorite_user_ids || []).includes(uid),
                    write_uid: r.write_uid
                        ? { id: r.write_uid[0], name: r.write_uid[1], avatar: `/web/image/res.users/${r.write_uid[0]}/avatar_128` }
                        : null,
                    write_date: r.write_date,
                    parent_id: r.parent_id ? r.parent_id[0] : false,
                    parent_name: r.parent_id ? r.parent_id[1] : false,
                    active: r.active,
                    to_delete_date: r.to_delete_date || false,
                };
            });

            if (!records) {
                this.state.loading = false;
                return;
            }

            records.body_html = cleanHtmlContent(records.body_html);
            if (records.is_article_item && records.name && records.name !== "Untitled") {
                // Items created from a view only have a name: show it as the title.
                records.body_html = records.body_html.replace(
                    /^<h1>(<br\s*\/?>)?<\/h1>/i,
                    () => `<h1>${escapeHtml(records.name)}</h1>`
                );
            }
            this.state.currentArticle = records;
            this.state.saveStatus = "saved";
            // Name of this action in the breadcrumbs of views opened from the article.
            this.env.config?.setDisplayName?.(records.name || "Untitled");
            // Keep the article in the URL (reload / share keeps it open).
            this.props.updateActionState?.({ article_id: records.id });
            this._lastSavedTitle = (records.name || "Untitled").trim();
            this._lastSavedBodyHtml = records.body_html || "";
            this.state.showKebab = false;
            this.state.editorKey++;
            setTimeout(() => {
                if (this.editor?.editable) {
                    updateEmptyHeadingClasses(this.editor.editable);
                }
            }, 60);
        } catch (e) {
            console.error("Failed to open article", e);
        }
        this.state.loading = false;
    }

    _findArticleById(id) {
        if (!id) return null;
        if (this.state.currentArticle && this.state.currentArticle.id === id) {
            return this.state.currentArticle;
        }
        const lists = [
            ...(this.state.sidebar?.favorites || []),
            ...(this.state.sidebar?.workspace || []),
            ...(this.state.sidebar?.shared || []),
            ...(this.state.sidebar?.private || []),
        ];
        for (const item of lists) {
            if (item.id === id) return item;
        }
        if (this.state.childrenMap) {
            for (const pid in this.state.childrenMap) {
                for (const item of (this.state.childrenMap[pid] || [])) {
                    if (item.id === id) return item;
                }
            }
        }
        return null;
    }

    async onNewArticle(parentId = false, visibility = "private") {
        // Save the open article first so the sidebar reload below does not
        // bring back its old name.
        await this.saveArticle();
        let vis = visibility;
        if (parentId) {
            const parent = this._findArticleById(parentId);
            if (parent && parent.visibility) {
                vis = parent.visibility;
            }
        }
        const initialHtml = getInitialArticleHtml();
        const newArt = await this.orm.create("knowledge.management.article", [{
            name: "Untitled",
            icon: "",
            parent_id: parentId || false,
            visibility: vis,
            body_html: initialHtml,
        }]);
        const newId = newArt[0];
        this._focusTitleOnLoad = newId;
        // Odoo Online: the new "Untitled" article shows up right away in the
        // sidebar, under its parent (expanded), at any depth. Its name then
        // follows the title typed in the editor (_syncTitleFromEditor).
        if (parentId && !this.state.expandedIds.includes(parentId)) {
            this.state.expandedIds.push(parentId);
        }
        await this._loadSidebar();
        await this._refreshExpandedChildren();
        await this.openArticle(newId);
    }

    // ── Insert View Modal (Kanban / List / Calendar) ──────────────

    _getEditorSelectionRange() {
        if (!this.editor?.editable) return null;
        const sel = window.getSelection();
        if (sel && sel.rangeCount > 0) {
            const range = sel.getRangeAt(0);
            if (this.editor.editable.contains(range.commonAncestorContainer)) {
                return range.cloneRange();
            }
        }
        return null;
    }

    openInsertViewModal(viewType, targetBlock = null) {
        this._savedRange = this._getEditorSelectionRange();
        this._targetInsertionBlock = targetBlock || this._lastTargetBlock || null;
        this.state.insertViewType = viewType;
        this.state.insertViewName = "";
        this.state.showInsertViewModal = true;
        setTimeout(() => {
            if (this.insertViewNameInput?.el) {
                this.insertViewNameInput.el.focus();
            }
        }, 80);
    }

    onCloseInsertViewModal() {
        this.state.showInsertViewModal = false;
    }

    onInsertViewKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.onConfirmInsertView();
        } else if (ev.key === "Escape") {
            this.onCloseInsertViewModal();
        }
    }

    // ── In-App Modal Dialog Helper (Replaces browser alert/prompt) ───
    promptDialog({ title, label, defaultValue = "", showDelete = false }) {
        return new Promise((resolve) => {
            this.state.itemPromptTitle = title || "Item Details";
            this.state.itemPromptLabel = label || "Name";
            this.state.itemPromptValue = defaultValue || "";
            this.state.itemPromptShowDelete = Boolean(showDelete);
            this.state.showItemPromptModal = true;
            this._itemPromptResolver = resolve;
            setTimeout(() => {
                const input = document.querySelector(".o_knowledge_modal input.form-control");
                if (input) {
                    input.focus();
                    input.select();
                }
            }, 60);
        });
    }

    onCloseItemPromptModal() {
        this.state.showItemPromptModal = false;
        if (this._itemPromptResolver) {
            this._itemPromptResolver(null);
            this._itemPromptResolver = null;
        }
    }

    onConfirmItemPrompt() {
        const val = (this.state.itemPromptValue || "").trim();
        this.state.showItemPromptModal = false;
        if (this._itemPromptResolver) {
            this._itemPromptResolver(val);
            this._itemPromptResolver = null;
        }
    }

    onItemPromptDelete() {
        this.state.showItemPromptModal = false;
        if (this._itemPromptResolver) {
            this._itemPromptResolver("__DELETE__");
            this._itemPromptResolver = null;
        }
    }

    onItemPromptKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.onConfirmItemPrompt();
        } else if (ev.key === "Escape") {
            this.onCloseItemPromptModal();
        }
    }

    async onConfirmInsertView() {
        if (!this.state.currentArticle) return;
        const viewType = this.state.insertViewType || "kanban";
        const articleId = this.state.currentArticle.id;
        const viewName = this.state.insertViewName.trim() || this.state.currentArticle.name || "";
        this.onCloseInsertViewModal();

        // Creates the default stages (New / Ongoing / Done) of the parent article.
        await this.orm.call("knowledge.management.article", "action_prepare_item_view", [[articleId], viewType]);
        if (!this.editor?.editable || this.state.currentArticle?.id !== articleId) return;

        const editable = this.editor.editable;
        const doc = editable.ownerDocument;
        const host = createItemViewHost(doc, viewType, viewName);
        const paragraph = doc.createElement("p");
        paragraph.append(doc.createElement("br"));

        const toTopBlock = (node) => {
            let el = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement);
            while (el && el.parentElement && el.parentElement !== editable) {
                el = el.parentElement;
            }
            return el && el.parentElement === editable ? el : null;
        };
        let anchor = toTopBlock(this._targetInsertionBlock) || toTopBlock(this._lastTargetBlock);
        if (!anchor && this._savedRange && editable.contains(this._savedRange.commonAncestorContainer)) {
            anchor = toTopBlock(this._savedRange.commonAncestorContainer);
        }
        if (anchor && anchor.tagName !== "H1" && !anchor.dataset.embedded && !anchor.textContent.trim()
            && !anchor.querySelector("img, iframe, [data-embedded]")) {
            anchor.replaceWith(host, paragraph);
        } else if (anchor) {
            anchor.after(host, paragraph);
        } else {
            editable.append(host, paragraph);
        }
        this._savedRange = null;
        this._lastTargetBlock = null;
        this._targetInsertionBlock = null;

        // Committing makes the EmbeddedComponentPlugin mount the Odoo view.
        this.editor.shared.history.commit();
        this.onEditorChange();
        this.saveArticle();
    }

    /**
     * Opens an article item (from the embedded kanban / list / calendar)
     * inside the Knowledge app, like in Odoo.
     */
    async openItemArticle(resId) {
        if (!resId) return;
        await this._flushPendingSave();
        await this.openArticle(resId);
    }

    async _flushPendingSave() {
        await this.saveArticle();
    }

    // ── AI Article Generator Modal ────────────────────────────────

    onOpenAIGenerator() {
        if (!isHudsonAIAvailable()) {
            // The generator needs the Hudson AI module.
            return;
        }
        this.state.showAIDialog = true;
        this.state.aiGenerating = false;
        this.selectAIPreset(this.state.aiPreset || "plan");
    }

    onCloseAIDialog() {
        if (this.state.aiGenerating) {
            return;
        }
        this.state.showAIDialog = false;
    }

    selectAIPreset(preset) {
        this.state.aiPreset = preset;
        const prompts = {
            plan: "Create a detailed project plan with goals, phases, milestones, team assignments, and risk mitigation.",
            meeting: "Document meeting minutes covering attendees, executive summary, discussion topics, decisions made, and action items with owners.",
            sop: "Write a standard operating procedure (SOP) with purpose, scope, prerequisites, step-by-step instructions, and quality checklist.",
            prd: "Draft a product requirements document (PRD) detailing problem statement, user personas, functional requirements, and success metrics.",
            custom: "",
        };
        // Suggestion is only a placeholder; the box stays empty for the user.
        this.state.aiPrompt = "";
        this.state.aiPlaceholder = prompts[preset] || "";
    }

    async onConfirmAIGenerate() {
        if (!this.state.currentArticle || this.state.aiGenerating) return;
        const instruction = (this.state.aiPrompt || this.state.aiPlaceholder || "").trim();
        if (!instruction) {
            this.notification.add("Describe what the article should be about.", { type: "warning" });
            return;
        }
        const articleId = this.state.currentArticle.id;
        this.state.aiGenerating = true;
        let result;
        try {
            // Route provided by the Hudson AI module.
            result = await rpc("/hudson_ai/write", { instruction }, { silent: true });
        } catch (e) {
            console.error("AI generation failed", e);
            result = { error: "Hudson AI could not be reached. Please try again." };
        } finally {
            this.state.aiGenerating = false;
        }
        if (result.error || !result.html) {
            // Keep the dialog open so the prompt is not lost.
            this.notification.add(result.error || "The AI returned an empty answer.", {
                title: "Hudson AI",
                type: "danger",
                sticky: true,
            });
            return;
        }
        this.state.showAIDialog = false;
        if (!this.state.currentArticle || this.state.currentArticle.id !== articleId) {
            // The user switched to another article while the AI was writing.
            return;
        }

        const title = result.title || this.state.currentArticle.name;
        this.state.currentArticle.name = title;
        this.state.currentArticle.body_html = result.html;
        this.state.editorKey++;

        await this.orm.write("knowledge.management.article", [articleId], {
            name: title,
            body_html: result.html,
        });
        await this._loadSidebar();

        this.notification.add("Article generated with Hudson AI.", { type: "success" });
    }

    // ── Template Browser & Loader ─────────────────────────────────

    async onBrowseTemplates() {
        try {
            const categories = await this.orm.call(
                "knowledge.management.article.template",
                "get_templates_by_category",
                []
            );
            this.state.templateCategories = categories || [];
            this.state.availableTemplates = this.state.templateCategories.flatMap((c) => c.templates);
            const first = this.state.availableTemplates[0];
            this.state.selectedTemplateId = first ? first.id : false;
            this.state.showTemplateDialog = true;
        } catch (e) {
            console.error("Failed to load templates", e);
            this.notification.add("Could not load the templates.", { type: "danger" });
        }
    }

    get selectedTemplate() {
        return this.state.availableTemplates.find((t) => t.id === this.state.selectedTemplateId) || null;
    }

    getTemplatePreviewHtml(tmpl) {
        return markup(cleanHtmlContent(tmpl?.body_html || ""));
    }

    onPreviewTemplate(tmpl) {
        this.state.selectedTemplateId = tmpl.id;
    }

    onCloseTemplateDialog() {
        this.state.showTemplateDialog = false;
    }

    async onSelectTemplate(tmpl) {
        if (!tmpl) return;
        const bodyHtml = tmpl.body_html || "<h1>Template</h1><p><br></p>";
        const vals = {
            name: tmpl.name,
            icon: tmpl.icon || "",
            body_html: bodyHtml,
            cover_image_url: tmpl.cover_image_url || false,
            cover_position: tmpl.cover_position || "50%",
        };
        this.state.showTemplateDialog = false;

        if (!this.state.currentArticle) {
            // No article open: create a new private article from the template.
            const created = await this.orm.create("knowledge.management.article", [{
                ...vals,
                visibility: "private",
            }]);
            await this._loadSidebar();
            await this.openArticle(created[0]);
        } else {
            const articleId = this.state.currentArticle.id;
            Object.assign(this.state.currentArticle, vals);
            this.state.editorKey++;
            await this.orm.write("knowledge.management.article", [articleId], vals);
            this._lastSavedTitle = vals.name;
            this._lastSavedBodyHtml = bodyHtml;
            await this._loadSidebar();
        }

        this.notification.add(`Template "${tmpl.name}" applied!`, { type: "success" });
    }

    async onDeleteTemplate(tmpl) {
        if (!tmpl) return;
        const confirmed = await new Promise((resolve) => {
            this.dialogService.add(ConfirmationDialog, {
                title: "Delete Template",
                body: `Do you really want to delete the template "${tmpl.name}"?`,
                confirmLabel: "Delete",
                confirm: () => resolve(true),
                cancel: () => resolve(false),
            }, { onClose: () => resolve(false) });
        });
        if (!confirmed) return;
        await this.orm.call(
            "knowledge.management.article.template",
            "action_delete_template",
            [[tmpl.id]]
        );
        await this.onBrowseTemplates();
        this.notification.add("Template deleted", { type: "info" });
    }

    // ── Sidebar Interactions ──────────────────────────────────────

    async onSelectArticle(articleId) {
        if (this.state.currentArticle?.id === articleId) return;
        await this._flushPendingSave();
        await this.openArticle(articleId);
    }

    async onToggleExpand(articleId) {
        const ids = this.state.expandedIds;
        const idx = ids.indexOf(articleId);
        if (idx >= 0) {
            this.state.expandedIds.splice(idx, 1);
        } else {
            this.state.expandedIds.push(articleId);
            if (!this.state.childrenMap[articleId]) {
                const children = await this.orm.call(
                    "knowledge.management.article",
                    "get_article_children",
                    [articleId]
                );
                this.state.childrenMap[articleId] = children;
            }
        }
    }

    async onNewChildArticle(parentId) {
        if (!parentId) return;
        await this.onNewArticle(parentId);
    }

    onArticleQuickMenu(ev, article) {
        ev.stopPropagation();
        ev.preventDefault();
        const rect = ev.currentTarget.getBoundingClientRect();
        const viewportHeight = window.innerHeight;
        let y = rect.top;
        if (y + 320 > viewportHeight) {
            y = Math.max(10, viewportHeight - 330);
        }
        this.state.sidebarMenu = {
            isOpen: true,
            article: article,
            x: rect.right + 6,
            y: y,
        };
    }

    onCloseSidebarMenu() {
        if (this.state.sidebarMenu) {
            this.state.sidebarMenu.isOpen = false;
        }
    }

    onSidebarOpenNewTab(article) {
        this.onCloseSidebarMenu();
        if (!article) return;
        const url = `${window.location.origin}/odoo/action-hudson_knowledge.action_knowledge_home?article_id=${article.id}`;
        window.open(url, "_blank");
    }

    async onSidebarToggleFavorite(article) {
        this.onCloseSidebarMenu();
        if (!article) return;
        const res = await this.orm.call(
            "knowledge.management.article",
            "action_set_favorite",
            [[article.id]]
        );
        article.is_user_favorite = typeof res === "boolean" ? res : !article.is_user_favorite;
        if (this.state.currentArticle && this.state.currentArticle.id === article.id) {
            this.state.currentArticle.is_user_favorite = article.is_user_favorite;
        }
        this._syncArticleToSidebar(article.id, { is_user_favorite: article.is_user_favorite });
        await this._loadSidebar();
    }

    async onSetArticleVisibility(article, newVisibility) {
        this.onCloseSidebarMenu();
        this.state.showKebab = false;
        if (!article || !newVisibility) return;
        await this.moveArticle(article, { category: newVisibility });
    }

    // ── Sidebar move: drag & drop / Move To ───────────────────────

    /**
     * Moves an article to the root of a section (category) or under another
     * article (parentId), before `beforeId` (or last). Odoo rules:
     *  - Private: only you; other users lose their access (confirmation)
     *  - Shared: the article must be shared with at least one person, so the
     *    Share dialog opens first when nobody is invited yet
     */
    async moveArticle(article, { category = false, parentId = false, beforeId = false } = {}) {
        if (!article) return false;
        if (parentId && parentId === article.id) return false;
        if (!parentId && category === "private") {
            if (article.visibility !== "private") {
                const confirmed = await new Promise((resolve) => {
                    this.dialogService.add(ConfirmationDialog, {
                        title: "Confirmation",
                        body: `Are you sure you want to move "${article.name}" to private? Only you will be able to access it.`,
                        confirmLabel: "Move to Private",
                        cancelLabel: "Discard",
                        confirm: () => resolve(true),
                        cancel: () => resolve(false),
                    }, { onClose: () => resolve(false) });
                });
                if (!confirmed) return false;
            }
        }
        if (!parentId && category === "workspace" && article.visibility === "private") {
            const confirmed = await new Promise((resolve) => {
                this.dialogService.add(ConfirmationDialog, {
                    title: "Confirmation",
                    body: `Are you sure you want to move "${article.name}" to the Workspace? It will be shared with all internal users.`,
                    confirmLabel: "Move to Workspace",
                    cancelLabel: "Discard",
                    confirm: () => resolve(true),
                    cancel: () => resolve(false),
                }, { onClose: () => resolve(false) });
            });
            if (!confirmed) return false;
        }
        if (!parentId && category === "shared") {
            if (article.visibility === "private") {
                const confirmed = await new Promise((resolve) => {
                    this.dialogService.add(ConfirmationDialog, {
                        title: "Move to Shared",
                        body: `Are you sure you want to move "${article.name}" from Private to Shared? It will become accessible to the members you invite, and at least one other member is required.`,
                        confirmLabel: "Move to Shared",
                        cancelLabel: "Cancel",
                        confirm: () => resolve(true),
                        cancel: () => resolve(false),
                    }, { onClose: () => resolve(false) });
                });
                if (!confirmed) return false;
            }
            const data =await this.orm.call("knowledge.management.article", "get_share_data", [[article.id]]);
            const others = data.members.filter((m) => !m.is_me && m.permission !== "none");
            if (!others.length) {
                this.notification.add("Invite at least one person to move this article to Shared.", { type: "info" });
                this.openShareDialog(article.id, { pendingCategory: "shared", beforeId });
                return false;
            }
        }
        try {
            await this.orm.call("knowledge.management.article", "action_move_article", [
                [article.id], category || false, parentId || false, beforeId || false,
            ]);
        } finally {
            if (parentId && !(this.state.expandedIds || []).includes(parentId)) {
                this.state.expandedIds.push(parentId);
            }
            await this._reloadAfterAccessChange(article.id);
        }
        return true;
    }

    async _reloadAfterAccessChange(articleId) {
        await this._loadSidebar();
        await this._refreshExpandedChildren();
        const current = this.state.currentArticle;
        if (!current || !articleId) return;
        try {
            const data = await this.orm.call("knowledge.management.article", "get_article_data", [], {
                context: { active_id: current.id },
            });
            Object.assign(current, {
                visibility: data.visibility,
                parent_id: data.parent_id,
                parent_name: data.parent_name,
                user_permission: data.user_permission,
                user_can_write: data.user_can_write,
            });
        } catch {
            // The current article is not accessible anymore.
            this.state.currentArticle = null;
            const topId = await this.orm.call("knowledge.management.article", "get_top_article", []);
            if (topId) await this.openArticle(topId);
        }
    }

    openShareDialog(articleId, { pendingCategory = false, beforeId = false } = {}) {
        let moved = false;
        this.dialogService.add(KnowledgeShareDialog, {
            articleId,
            onChanged: async (data) => {
                if (pendingCategory === "shared" && !moved
                        && data.members.some((m) => !m.is_me && m.permission !== "none")) {
                    moved = true;
                    if (data.visibility !== "shared" && data.is_root) {
                        await this.orm.call("knowledge.management.article", "action_move_article", [
                            [articleId], "shared", false, beforeId || false,
                        ]);
                    }
                }
                await this._reloadAfterAccessChange(articleId);
            },
        });
    }

    openMoveDialog(article) {
        this.dialogService.add(KnowledgeMoveDialog, {
            article,
            onMove: async (target) => {
                if (target.kind === "section") {
                    await this.moveArticle(article, { category: target.id });
                } else {
                    await this.moveArticle(article, { parentId: target.id });
                }
            },
        });
    }

    // Sidebar handlers read the article from the DOM (data-article-id): the
    // loop variable of the recursive t-call is not reliable at event time.
    _evArticleId(ev) {
        const el = ev.target.closest?.("[data-article-id]") || ev.currentTarget;
        return parseInt(el?.dataset?.articleId) || false;
    }

    _evArticle(ev) {
        const id = this._evArticleId(ev);
        const lists = [
            this.state.sidebar.favorites, this.state.sidebar.workspace,
            this.state.sidebar.shared, this.state.sidebar.private,
            ...Object.values(this.state.childrenMap || {}),
        ];
        for (const list of lists) {
            const found = (list || []).find((a) => a.id === id);
            if (found) return found;
        }
        return { id };
    }

    _evSection(ev) {
        return ev.target.closest?.("[data-section]")?.dataset.section || false;
    }

    // Native HTML5 drag & drop in the sidebar tree
    onSidebarDragStart(ev, article) {
        if (!article.user_can_write) {
            ev.preventDefault();
            this.notification.add("You need \"Can Edit\" access to move this article.", { type: "warning" });
            return;
        }
        this._dragArticle = article;
        ev.stopPropagation();
        ev.dataTransfer.effectAllowed = "move";
        // Defer: changing the DOM in dragstart cancels the drag in Chrome.
        setTimeout(() => { this.state.isDragging = true; }, 0);
        ev.dataTransfer.setData("text/plain", String(article.id));
        ev.currentTarget.classList.add("o_knowledge_dragging");
    }

    onSidebarDragEnd(ev) {
        ev.currentTarget.classList.remove("o_knowledge_dragging");
        this._clearDropMarkers();
        this._dragArticle = null;
        this.state.isDragging = false;
    }

    _clearDropMarkers() {
        for (const el of document.querySelectorAll(
            ".o_knowledge_drop_before, .o_knowledge_drop_after, .o_knowledge_drop_inside, .o_knowledge_drop_section"
        )) {
            el.classList.remove("o_knowledge_drop_before", "o_knowledge_drop_after",
                "o_knowledge_drop_inside", "o_knowledge_drop_section");
        }
    }

    _dropPosition(ev) {
        const rect = ev.currentTarget.getBoundingClientRect();
        const y = ev.clientY - rect.top;
        if (y < rect.height * 0.28) return "before";
        if (y > rect.height * 0.72) return "after";
        return "inside";
    }

    onSidebarItemDragOver(ev, target) {
        const dragged = this._dragArticle;
        if (!dragged || dragged.id === target.id) return;
        ev.preventDefault();
        ev.stopPropagation();
        ev.dataTransfer.dropEffect = "move";
        this._clearDropMarkers();
        ev.currentTarget.classList.add(`o_knowledge_drop_${this._dropPosition(ev)}`);
    }

    async onSidebarItemDrop(ev, target, section) {
        const dragged = this._dragArticle;
        ev.preventDefault();
        ev.stopPropagation();
        const position = this._dropPosition(ev);
        this._clearDropMarkers();
        this._dragArticle = null;
        this.state.isDragging = false;
        if (!dragged || dragged.id === target.id) return;
        try {
            if (position === "inside") {
                await this.moveArticle(dragged, { parentId: target.id });
                return;
            }
            const siblings = target.parent_id
                ? (this.state.childrenMap[target.parent_id] || [])
                : (this.state.sidebar[section] || []);
            const list = siblings.filter((s) => s.id !== dragged.id);
            const idx = list.findIndex((s) => s.id === target.id);
            const beforeId = position === "before" ? target.id : (list[idx + 1]?.id || false);
            if (target.parent_id && section !== "favorites") {
                await this.moveArticle(dragged, { parentId: target.parent_id, beforeId });
            } else if (section === "favorites") {
                await this.moveArticle(dragged, { category: target.visibility });
            } else {
                await this.moveArticle(dragged, { category: section, beforeId });
            }
        } catch (e) {
            this.notification.add(e.data?.message || e.message || String(e), { type: "danger" });
        }
    }

    onSidebarSectionDragOver(ev) {
        if (!this._dragArticle) return;
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        this._clearDropMarkers();
        ev.currentTarget.classList.add("o_knowledge_drop_section");
    }

    async onSidebarSectionDrop(ev, section) {
        const dragged = this._dragArticle;
        ev.preventDefault();
        this._clearDropMarkers();
        this._dragArticle = null;
        this.state.isDragging = false;
        if (!dragged) return;
        try {
            await this.moveArticle(dragged, { category: section });
        } catch (e) {
            this.notification.add(e.data?.message || e.message || String(e), { type: "danger" });
        }
    }

    onSidebarShare(article) {
        this.onCloseSidebarMenu();
        if (!article) return;
        this.openShareDialog(article.id);
    }

    async onSidebarRename(article) {
        this.onCloseSidebarMenu();
        if (!article) return;
        const newName = await this.promptDialog({
            title: "Rename Article",
            label: "Article Name",
            defaultValue: article.name,
        });
        if (newName && newName.trim() && newName !== article.name) {
            article.name = newName.trim();
            await this.orm.write("knowledge.management.article", [article.id], { name: article.name });
            if (this.state.currentArticle && this.state.currentArticle.id === article.id) {
                this.state.currentArticle.name = article.name;
            }
            await this._loadSidebar();
        }
    }

    onSidebarMoveTo(article) {
        this.onCloseSidebarMenu();
        if (!article) return;
        this.openMoveDialog(article);
    }

    async onSidebarCreateCopy(article) {
        this.onCloseSidebarMenu();
        if (!article) return;
        const res = await this.orm.call(
            "knowledge.management.article",
            "action_create_copy",
            [[article.id]]
        );
        await this._loadSidebar();
        if (res && res.res_id) {
            await this.openArticle(res.res_id);
        }
    }

    async onSidebarMoveToTrash(article) {
        this.onCloseSidebarMenu();
        if (!article) return;
        const artId = article.id;
        this._removeArticleFromSidebarState(artId);
        await this.orm.call(
            "knowledge.management.article",
            "action_move_to_trash",
            [[artId]]
        );
        await this._loadSidebar();
        await this._refreshExpandedChildren();
        if (this.state.currentArticle && this.state.currentArticle.id === artId) {
            const topId = await this.orm.call(
                "knowledge.management.article",
                "get_top_article",
                []
            );
            if (topId) {
                await this.openArticle(topId);
            } else {
                this.state.currentArticle = null;
            }
        }
        this.notification.add("Article moved to trash", { type: "info" });
    }

    getArticleLastEdited(article) {
        if (!article || !article.write_date) return "recently";
        return this._formatRelativeTime(article.write_date);
    }

    onSearch() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Search Articles",
            res_model: "knowledge.management.article",
            views: [[false, "list"], [false, "form"]],
            domain: [["active", "=", true]],
            target: "current",
        });
    }

    onShare() {
        if (!this.state.currentArticle) return;
        this.openShareDialog(this.state.currentArticle.id);
    }

    onOpenTrash() {
        this.action.doAction("hudson_knowledge.action_knowledge_trash");
    }

    // ── Trash (article opened from the Trash list) ────────────────

    get isInTrash() {
        return this.state.currentArticle?.active === false;
    }

    /** Locked, in the trash or without write access: nothing is editable
     *  (body, title, icon, cover). */
    /** Breadcrumbs of the actions below Knowledge (e.g. the vendor bill the
     *  article was opened from with the Knowledge button). */
    get appBreadcrumbs() {
        return (this.env.config?.breadcrumbs || []).slice(0, -1).filter(Boolean);
    }

    onAppBreadcrumbClick(ev) {
        const index = parseInt(ev.currentTarget.dataset.crumbIndex);
        this.appBreadcrumbs[index]?.onSelected();
    }

    get isArticleReadonly() {
        const art = this.state.currentArticle;
        return !art || art.is_locked || art.active === false || art.user_can_write === false;
    }

    getTrashDeletionDate() {
        const d = this.state.currentArticle?.to_delete_date;
        if (!d) return "";
        const [y, m, day] = d.split("-").map(Number);
        return new Date(y, m - 1, day).toLocaleDateString(undefined, {
            day: "numeric",
            month: "short",
        });
    }

    async onRestoreFromTrash() {
        const art = this.state.currentArticle;
        if (!art) return;
        await this.orm.call(
            "knowledge.management.article",
            "action_restore_from_trash",
            [[art.id]]
        );
        await this._loadSidebar();
        await this._refreshExpandedChildren();
        await this.openArticle(art.id);
        this.notification.add("Article restored", { type: "success" });
    }

    // ── Toolbar & Kebab Actions ───────────────────────────────────

    onToggleKebab(ev) {
        ev.stopPropagation();
        this.state.showKebab = !this.state.showKebab;
    }

    _onDocumentClick(ev) {
        if (this.state.showKebab) {
            const kebab = this.kebabMenu.el;
            if (kebab && !kebab.contains(ev.target)) {
                this.state.showKebab = false;
            }
        }
        if (this.state.sidebarMenu?.isOpen) {
            this.state.sidebarMenu.isOpen = false;
        }
    }

    async onToggleFavorite() {
        if (!this.state.currentArticle) return;
        const art = this.state.currentArticle;
        const res = await this.orm.call(
            "knowledge.management.article",
            "action_set_favorite",
            [[art.id]]
        );
        art.is_user_favorite = typeof res === "boolean" ? res : !art.is_user_favorite;
        this._syncArticleToSidebar(art.id, { is_user_favorite: art.is_user_favorite });
        await this._loadSidebar();
    }

    // ── Emoji & Icon Handlers (Image 1) ───────────────────────────

    openEmojiPicker(targetEl) {
        if (this.emojiPopover.isOpen) {
            this.emojiPopover.close();
            return;
        }
        const target = targetEl || this.titleEmojiRef?.el || this.toolbarEmojiRef?.el || document.body;
        this.emojiPopover.open(target, {
            onSelect: (emoji) => {
                if (!this.state.currentArticle) return;
                this.state.currentArticle.icon = emoji;
                this._syncArticleToSidebar(this.state.currentArticle.id, { icon: emoji });
                this._updateArticleField("icon", emoji);
                this.emojiPopover.close();
            },
            onRemove: () => {
                if (!this.state.currentArticle) return;
                this.state.currentArticle.icon = "";
                this._syncArticleToSidebar(this.state.currentArticle.id, { icon: "" });
                this._updateArticleField("icon", "");
                this.emojiPopover.close();
            },
            close: () => this.emojiPopover.close(),
        });
    }

    onEmojiClick(ev) {
        ev.stopPropagation();
        if (this.isArticleReadonly) return;
        this.openEmojiPicker(ev.currentTarget);
    }

    onAddIcon(ev) {
        this.state.showKebab = false;
        if (this.isArticleReadonly) return;
        const target = ev?.currentTarget || this.titleEmojiRef?.el || this.toolbarEmojiRef?.el;
        this.openEmojiPicker(target);
    }

    // ── Cover Image Handlers (Images 2 & 3) ────────────────────────

    get filteredCoverImages() {
        const query = (this.state.coverSearchQuery || "").trim().toLowerCase();
        const cat = this.state.coverActiveCategory || "all";
        return CURATED_COVERS.filter((img) => {
            const matchesCat = cat === "all" || img.category === cat;
            const matchesQuery =
                !query ||
                (img.photographer && img.photographer.toLowerCase().includes(query)) ||
                (img.category && img.category.toLowerCase().includes(query)) ||
                (img.id && img.id.toLowerCase().includes(query));
            return matchesCat && matchesQuery;
        }).slice(0, this.state.coverPageLimit);
    }

    onCoverSearchInput(ev) {
        this.state.coverSearchQuery = ev.target.value;
    }

    onCoverCategoryChange(ev) {
        this.state.coverActiveCategory = ev.target.value;
    }

    onLoadMoreCovers() {
        this.state.coverPageLimit += 15;
    }

    async onAddCover() {
        this.state.showKebab = false;
        if (this.isArticleReadonly) return;
        this.openCoverMediaDialog();
    }

    async onOpenCoverModal() {
        this.state.showKebab = false;
        if (this.isArticleReadonly) return;
        this.openCoverMediaDialog();
    }

    openCoverMediaDialog() {
        if (!this.state.currentArticle) return;
        this.dialogService.add(MediaDialog, {
            resModel: "knowledge.management.article",
            resId: this.state.currentArticle.id,
            onlyImages: true,
            save: (element) => {
                if (!element) return;
                let src = "";
                if (typeof element === "string") {
                    src = element;
                } else if (element.getAttribute) {
                    src = element.getAttribute("src") || element.getAttribute("data-src") || "";
                } else if (element.src) {
                    src = element.src;
                }
                if (src) {
                    this.state.currentArticle.cover_image_url = src;
                    this._updateArticleField("cover_image_url", src);
                }
            },
        });
    }

    onCloseCoverModal() {
        this.state.showCoverModal = false;
    }

    async onSelectCoverImage(url) {
        if (!url || !this.state.currentArticle) return;
        this.state.showCoverModal = false;
        this.state.currentArticle.cover_image_url = url;
        await this._updateArticleField("cover_image_url", url);
    }

    onUploadCoverFile(ev) {
        const file = ev.target?.files?.[0];
        if (!file || !this.state.currentArticle) return;
        const reader = new FileReader();
        reader.onload = async (e) => {
            const dataUrl = e.target.result;
            this.state.showCoverModal = false;
            this.state.currentArticle.cover_image_url = dataUrl;
            await this._updateArticleField("cover_image_url", dataUrl);
        };
        reader.readAsDataURL(file);
    }

    onToggleAddUrlMode() {
        this.state.showAddUrlTray = !this.state.showAddUrlTray;
        if (this.state.showAddUrlTray) {
            this.state.customCoverUrl = "";
        }
    }

    async onApplyCustomUrl() {
        const url = (this.state.customCoverUrl || "").trim();
        if (!url || !this.state.currentArticle) return;
        this.state.showCoverModal = false;
        this.state.currentArticle.cover_image_url = url;
        await this._updateArticleField("cover_image_url", url);
    }

    onAddUrlKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.onApplyCustomUrl();
        } else if (ev.key === "Escape") {
            this.state.showAddUrlTray = false;
        }
    }

    onStartRepositionCover() {
        if (this.isArticleReadonly) return;
        this.state.isRepositioningCover = true;
        this.state.savedCoverPosition = this.state.currentArticle.cover_position || "50%";
    }

    onCoverMouseDown(ev) {
        if (!this.state.isRepositioningCover || this.isArticleReadonly) return;
        ev.preventDefault();
        const startY = ev.clientY;
        const startPos = parseFloat(this.state.currentArticle.cover_position || "50%") || 50;
        const coverEl = this.coverImg?.el;
        const rect = coverEl ? coverEl.getBoundingClientRect() : { height: 240 };

        const onMouseMove = (moveEv) => {
            const deltaY = moveEv.clientY - startY;
            const percentDelta = (deltaY / rect.height) * 100;
            let newPos = Math.round(startPos - percentDelta);
            if (newPos < 0) newPos = 0;
            if (newPos > 100) newPos = 100;
            this.state.currentArticle.cover_position = newPos + "%";
        };

        const onMouseUp = () => {
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);
        };

        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
    }

    async onSaveCoverPosition() {
        if (!this.state.currentArticle) return;
        const pos = this.state.currentArticle.cover_position || "50%";
        this.state.isRepositioningCover = false;
        await this._updateArticleField("cover_position", pos);
        this.notification.add("Cover position saved", { type: "info" });
    }

    onCancelCoverPosition() {
        if (!this.state.currentArticle) return;
        this.state.currentArticle.cover_position = this.state.savedCoverPosition || "50%";
        this.state.isRepositioningCover = false;
    }

    async onRemoveCover() {
        if (this.isArticleReadonly) return;
        this.state.currentArticle.cover_image_url = false;
        await this._updateArticleField("cover_image_url", false);
    }

    async onToggleFullWidth() {
        this.state.showKebab = false;
        if (!this.state.currentArticle) return;
        const newVal = !this.state.currentArticle.full_width;
        await this._updateArticleField("full_width", newVal);
    }

    onMoveTo() {
        this.state.showKebab = false;
        if (!this.state.currentArticle) return;
        this.openMoveDialog(this.state.currentArticle);
    }

    async onToggleLock() {
        this.state.showKebab = false;
        if (!this.state.currentArticle) return;
        await this.orm.call(
            "knowledge.management.article",
            "action_toggle_lock",
            [[this.state.currentArticle.id]]
        );
        this.state.currentArticle.is_locked = !this.state.currentArticle.is_locked;
        if (this.state.currentArticle.is_locked && this.state.isRepositioningCover) {
            this.state.currentArticle.cover_position = this.state.savedCoverPosition || "50%";
            this.state.isRepositioningCover = false;
        }
        this.state.editorKey++;
    }

    async onCreateCopy() {
        this.state.showKebab = false;
        if (!this.state.currentArticle) return;
        const copied = await this.orm.call(
            "knowledge.management.article",
            "action_create_copy",
            [[this.state.currentArticle.id]]
        );
        await this._loadSidebar();
        if (copied && copied[0]) await this.openArticle(copied[0]);
    }

    async onDownloadPdf() {
        this.state.showKebab = false;
        const art = this.state.currentArticle;
        if (!art) return;
        // Pending edits must be in the PDF.
        await this.saveArticle();
        await this.action.doAction("hudson_knowledge.action_report_knowledge_article", {
            additionalContext: { active_id: art.id, active_ids: [art.id], active_model: "knowledge.management.article" },
        });
    }

    async onAddToTemplates() {
        this.state.showKebab = false;
        if (!this.state.currentArticle) return;
        try {
            const categories = await this.orm.call(
                "knowledge.management.article.template",
                "get_template_categories",
                []
            );
            this.state.saveTemplateCategories = categories || [];
        } catch (e) {
            this.state.saveTemplateCategories = [];
        }
        this.state.saveTemplateName = this.state.currentArticle.name || "Untitled";
        this.state.saveTemplateCategoryId = this.state.saveTemplateCategories[0]?.id || false;
        this.state.showSaveTemplateDialog = true;
    }

    onCloseSaveTemplateDialog() {
        if (this.state.savingTemplate) return;
        this.state.showSaveTemplateDialog = false;
    }

    onSaveTemplateCategoryChange(ev) {
        this.state.saveTemplateCategoryId = parseInt(ev.target.value) || false;
    }

    async onConfirmSaveTemplate() {
        const art = this.state.currentArticle;
        if (!art || this.state.savingTemplate) return;
        this.state.savingTemplate = true;
        try {
            // Save the latest editor content first so the template is up to date.
            await this._flushPendingSave();
            await this.orm.call(
                "knowledge.management.article",
                "action_save_as_template",
                [[art.id]],
                {
                    name: this.state.saveTemplateName || art.name,
                    category_id: this.state.saveTemplateCategoryId || false,
                }
            );
            this.state.showSaveTemplateDialog = false;
            this.notification.add("Article added to Templates!", { type: "success" });
        } catch (e) {
            console.error("Failed to save template", e);
            const detail = e?.data?.message || e?.message || "";
            this.notification.add(
                `Could not save the article as a template.${detail ? " " + detail : ""}`,
                { type: "danger" }
            );
        } finally {
            this.state.savingTemplate = false;
        }
    }

    async onMoveToTrash() {
        this.state.showKebab = false;
        if (!this.state.currentArticle) return;
        const artId = this.state.currentArticle.id;
        this._removeArticleFromSidebarState(artId);
        await this.orm.call(
            "knowledge.management.article",
            "action_move_to_trash",
            [[artId]]
        );
        this.state.currentArticle = null;
        await this._loadSidebar();
        await this._refreshExpandedChildren();
        const topId = await this.orm.call(
            "knowledge.management.article",
            "get_top_article",
            []
        );
        if (topId) await this.openArticle(topId);
        this.notification.add("Article moved to trash", { type: "info" });
    }

    async _updateArticleField(field, value) {
        if (!this.state.currentArticle) return;
        if (LOCKED_CONTENT_FIELDS.includes(field) && this.isArticleReadonly) return;
        await this.orm.write(
            "knowledge.management.article",
            [this.state.currentArticle.id],
            { [field]: value }
        );
        this.state.currentArticle[field] = value;
    }

    // ── Version History Methods (Matching Image 1) ────────────────
    async onOpenVersionHistory() {
        this.state.showKebab = false;
        if (!this.state.currentArticle) return;
        this.state.historyLoading = true;
        this.state.showHistoryModal = true;
        try {
            const versions = await this.orm.call(
                "knowledge.management.article",
                "get_version_history",
                [[this.state.currentArticle.id]]
            );
            this.state.historyVersions = versions || [];
            this.state.selectedHistoryVersion = this.state.historyVersions.length > 0 ? this.state.historyVersions[0] : null;
            this.state.historyShowComparison = true;
        } catch (err) {
            console.error("Failed to load version history", err);
            this.notification.add("Could not load version history", { type: "danger" });
        } finally {
            this.state.historyLoading = false;
        }
    }

    onCloseVersionHistory() {
        this.state.showHistoryModal = false;
    }

    onToggleHistoryFullscreen() {
        this.state.historyIsFullscreen = !this.state.historyIsFullscreen;
    }

    onSelectHistoryVersion(v) {
        this.state.selectedHistoryVersion = v;
    }

    onToggleHistoryComparison() {
        this.state.historyShowComparison = !this.state.historyShowComparison;
    }

    async onRestoreHistoryVersion() {
        if (!this.state.currentArticle || !this.state.selectedHistoryVersion) return;
        const vId = this.state.selectedHistoryVersion.id;
        try {
            await this.orm.call(
                "knowledge.management.article",
                "action_restore_version",
                [[this.state.currentArticle.id], vId]
            );
            this.state.currentArticle.name = this.state.selectedHistoryVersion.name;
            this.state.currentArticle.body_html = this.state.selectedHistoryVersion.body_html;
            this.state.editorKey++;
            this.state.showHistoryModal = false;
            this.notification.add("Article restored to selected version", { type: "success" });
            await this._loadSidebar();
        } catch (err) {
            console.error("Failed to restore version", err);
            this.notification.add("Failed to restore version", { type: "danger" });
        }
    }

    formatHistoryRelativeTime(isoString) {
        if (!isoString) return "Recently";
        try {
            const date = new Date(isoString);
            const now = new Date();
            const diffSec = Math.floor((now - date) / 1000);
            if (diffSec < 60) return "Just now";
            const diffMin = Math.floor(diffSec / 60);
            if (diffMin < 60) return `${diffMin} minute${diffMin > 1 ? "s" : ""} ago`;
            const diffHours = Math.floor(diffMin / 60);
            if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? "s" : ""} ago`;
            const diffDays = Math.floor(diffHours / 24);
            if (diffDays === 1) return "Yesterday";
            if (diffDays < 30) return `${diffDays} days ago`;
            return date.toLocaleDateString();
        } catch {
            return "Recently";
        }
    }

    _replaceDynamicBlocks(html) {
        if (!html) return "";
        let clean = html.replace(/<div[^>]*class="[^"]*o_knowledge_embedded_view_container[^"]*"[^>]*>[\s\S]*?<\/div>/gi,
            '<div class="o_history_dynamic_block"><span class="o_history_cube_icon">📦</span> Dynamic element</div>');
        clean = clean.replace(/<div[^>]*data-embedded="knowledgeItemView"[^>]*>\s*<\/div>/gi,
            '<div class="o_history_dynamic_block"><span class="o_history_cube_icon">📦</span> Dynamic element</div>');
        clean = clean.replace(/<div[^>]*data-embedded-view="[^"]*"[^>]*>[\s\S]*?<\/div>/gi,
            '<div class="o_history_dynamic_block"><span class="o_history_cube_icon">📦</span> Dynamic element</div>');
        return clean;
    }

    getHistoryDisplayHtml() {
        if (!this.state.selectedHistoryVersion) return "";
        const selClean = this._replaceDynamicBlocks(this.state.selectedHistoryVersion.body_html || "");
        if (!this.state.historyShowComparison) {
            return markup(selClean);
        }
        const curClean = this._replaceDynamicBlocks(this.state.currentArticle?.body_html || "");
        const diff = computeHtmlDiff(selClean, curClean);
        return markup(diff);
    }

    getHistorySelectedTitle() {
        return this.state.selectedHistoryVersion?.name || this.state.currentArticle?.name || "Untitled";
    }

    getLastEditedRelative() {
        const art = this.state.currentArticle;
        if (!art || !art.write_date) return "just now";
        return this._formatRelativeTime(art.write_date);
    }
}

// ─── Register Action in Registry ─────────────────────────────────
registry.category("actions").add(
    "hudson_knowledge.action_knowledge",
    KnowledgeClientAction
);
