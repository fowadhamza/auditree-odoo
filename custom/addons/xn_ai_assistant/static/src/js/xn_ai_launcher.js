/** @odoo-module **/

import { Component, useState, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

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
            draft: "",
            // {role: "user" | "bot" | "error", text: string}
            messages: [],
        });
    }

    toggle() {
        this.state.open = !this.state.open;
        if (this.state.open) {
            // The panel is rendered by the same tick that flips `open`, so the
            // input does not exist yet when this runs synchronously.
            setTimeout(() => this.inputRef.el && this.inputRef.el.focus(), 0);
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

    async send() {
        const question = (this.state.draft || "").trim();
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
                this.state.messages.push({ role: "bot", text: result.answer });
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

    onKeydown(ev) {
        // Enter sends, Shift+Enter is a newline. Matches every chat input
        // people already use, so it needs no explaining.
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }
}

registry.category("main_components").add("xn_ai_assistant.launcher", {
    Component: AiAssistantLauncher,
});
