/** @odoo-module **/

import { Component, useState, useRef, markup } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { escape } from "@web/core/utils/strings";

// Matches a bare http(s) URL up to the first whitespace, then trims trailing
// punctuation so "see https://x/doc." does not produce a link ending in a dot.
const URL_RE = /https?:\/\/[^\s<>"']+/g;
const TRAILING_PUNCTUATION = /[.,;:!?)\]}]+$/;

/**
 * Floating assistant launcher, bottom right of the web client.
 *
 * Registered in main_components rather than systray: a systray item is
 * rendered inside the top bar and cannot escape it, so a panel anchored to
 * the bottom of the screen has to be mounted at the web client root instead.
 *
 * Deliberately not built on Discuss. A Discuss-backed bot delivers its reply
 * over the websocket bus, and when the bus does not deliver, nothing errors:
 * the message is posted, the database is correct, and the screen silently
 * stays stale. That failure mode is documented in this repo for workers > 0
 * and it bit us during development.
 *
 * This calls the controller over ordinary RPC and renders what comes back, so
 * a reply either appears or raises. No bus, no gevent worker, no nginx
 * websocket route to keep in step.
 */
export class AiAssistantLauncher extends Component {
    static template = "xn_ai_assistant.Launcher";
    static props = {};

    setup() {
        this.rpc = useService("rpc");
        this.inputRef = useRef("input");
        this.threadRef = useRef("thread");
        this.state = useState({
            open: false,
            pending: false,
            restored: false,
            draft: "",
            // {role: "user" | "bot" | "error", text, logId?, rating?}
            messages: [],
        });
    }

    /**
     * Render one message as safe HTML with bare URLs turned into links.
     *
     * Order matters and is the whole security argument: the text is escaped
     * FIRST, then links are built from the already-escaped string. Linkifying
     * before escaping would let model output inject markup into the panel,
     * and model output includes whatever a SharePoint document happened to be
     * called.
     */
    formatted(text) {
        const safe = escape(text || "");
        const linked = safe.replace(URL_RE, (match) => {
            const trailing = (match.match(TRAILING_PUNCTUATION) || [""])[0];
            const url = trailing ? match.slice(0, -trailing.length) : match;
            return (
                `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>` +
                trailing
            );
        });
        return markup(linked.replace(/\n/g, "<br/>"));
    }

    toggle() {
        this.state.open = !this.state.open;
        if (this.state.open) {
            // The panel is rendered by the same tick that flips `open`, so the
            // input does not exist yet when this runs synchronously.
            setTimeout(() => this.inputRef.el && this.inputRef.el.focus(), 0);
            this.restoreHistory();
        }
    }

    /**
     * Redraw a conversation the server still remembers.
     *
     * Memory lives in the session, so it survives a page refresh while the
     * component's own state does not. Without this the panel opens empty
     * while the next answer quietly uses three exchanges of context the
     * person cannot see, which is worse than having no memory at all.
     *
     * Runs once per page load: after that the in-memory list is the truth,
     * and refetching would duplicate anything just sent.
     */
    async restoreHistory() {
        if (this.state.restored || this.state.messages.length) {
            this.state.restored = true;
            return;
        }
        this.state.restored = true;
        try {
            const result = await this.rpc("/xn_ai/assistant/history", {});
            if (result && result.ok && result.messages.length) {
                this.state.messages = result.messages;
                this.scrollToEnd();
            }
        } catch (error) {
            // A conversation that cannot be restored is an empty panel, which
            // is the same as before this existed. Nothing to tell the user.
        }
    }

    close() {
        this.state.open = false;
    }

    scrollToEnd() {
        setTimeout(() => {
            const el = this.threadRef.el;
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        }, 0);
    }

    async send(text) {
        const question = (typeof text === "string" ? text : this.state.draft || "").trim();
        if (!question || this.state.pending) {
            return;
        }
        this.state.messages.push({ role: "user", text: question });
        this.state.draft = "";
        this.state.pending = true;
        this.scrollToEnd();

        try {
            const result = await this.rpc("/xn_ai/assistant/ask", { question });
            if (result && result.ok) {
                this.state.messages.push({
                    role: "bot",
                    text: result.answer,
                    logId: result.log_id || null,
                    rating: null,
                });
            } else {
                this.state.messages.push({
                    role: "error",
                    text: (result && result.error) || "Something went wrong.",
                });
            }
        } catch (error) {
            this.state.messages.push({
                role: "error",
                text: "Could not reach the assistant. Please try again.",
            });
        } finally {
            this.state.pending = false;
            this.scrollToEnd();
        }
    }

    /** Fill and send one of the example prompts. */
    askExample(text) {
        this.send(text);
    }

    /**
     * Rate an answer. Optimistic: the thumb fills immediately and is reverted
     * if the server refuses, because a rating that appears not to register
     * gets clicked repeatedly and then not given at all.
     */
    async rate(message, rating) {
        if (!message.logId || message.rating === rating) {
            return;
        }
        const previous = message.rating;
        message.rating = rating;
        try {
            const result = await this.rpc("/xn_ai/assistant/feedback", {
                log_id: message.logId,
                rating: rating,
            });
            if (!result || !result.ok) {
                message.rating = previous;
            }
        } catch (error) {
            message.rating = previous;
        }
    }

    /** Forget the conversation, on the server as well as on screen. */
    async clearConversation() {
        this.state.messages = [];
        try {
            await this.rpc("/xn_ai/assistant/clear", {});
        } catch (error) {
            // The visible conversation is already gone; a failure here only
            // means the server still holds context it will stop using once
            // the session ends.
        }
    }

    onKeydown(ev) {
        // Enter sends, Shift+Enter is a newline. Matches every chat input
        // people already use, so it needs no explaining.
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
        if (ev.key === "Escape") {
            this.close();
        }
    }
}

registry.category("main_components").add("xn_ai_assistant.launcher", {
    Component: AiAssistantLauncher,
});
