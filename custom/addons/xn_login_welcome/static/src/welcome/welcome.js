/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";

const SHOW_MS = 2200; // time on screen before the fade-out starts
const FADE_MS = 450; // must match the fade-out in welcome.scss

function prefersReducedMotion() {
    return Boolean(
        window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
}

/**
 * Full-screen greeting shown once per login. The server sets
 * session.xn_show_welcome on the first web client load of a session only
 * (models/ir_http.py), so reloads and new tabs skip it.
 */
export class XnLoginWelcome extends Component {
    static template = "xn_login_welcome.Welcome";
    static props = {};

    setup() {
        const show = Boolean(session.xn_show_welcome) && !prefersReducedMotion();
        // Consume the flag so a later re-render of the main components does
        // not bring the overlay back.
        delete session.xn_show_welcome;
        this.state = useState({ visible: show, leaving: false });
        this.timers = [];
        if (!show) {
            return;
        }
        const now = new Date();
        const hour = now.getHours();
        const greeting =
            hour < 12 ? _t("Good morning") : hour < 17 ? _t("Good afternoon") : _t("Good evening");
        // Full name: for names like "Shaik Danyal" or "Mohammed Junaid" the
        // first word alone is not what people are called.
        const name = (session.name || "").trim();
        this.greeting = name ? `${greeting}, ${name}` : greeting;
        this.dateLine = now.toLocaleDateString(undefined, {
            weekday: "long",
            day: "numeric",
            month: "long",
            year: "numeric",
        });
        const companies = session.user_companies || {};
        const companyId = companies.current_company;
        const company = (companies.allowed_companies || {})[companyId];
        this.companyName = (company && company.name) || "";
        this.logoUrl =
            companyId && session.xn_welcome_has_logo
                ? `/web/image/res.company/${companyId}/logo`
                : "";
        this.initial = (this.companyName || name || "?").charAt(0).toUpperCase();
        delete session.xn_welcome_has_logo;

        onMounted(() => {
            this.timers.push(setTimeout(() => this.dismiss(), SHOW_MS));
        });
        onWillUnmount(() => this.timers.forEach(clearTimeout));
    }

    dismiss() {
        if (!this.state.visible || this.state.leaving) {
            return;
        }
        this.state.leaving = true;
        this.timers.push(setTimeout(() => (this.state.visible = false), FADE_MS));
    }
}

registry.category("main_components").add("xn_login_welcome", { Component: XnLoginWelcome });
