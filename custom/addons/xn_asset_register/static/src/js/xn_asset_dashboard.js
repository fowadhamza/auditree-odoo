/** @odoo-module **/
/**
 * The Auditree asset register dashboard.
 *
 * No Chart.js, for the same reason xn_hr_dashboard avoids it: Odoo 17 ships it
 * only in web.assets_backend's absent sibling web.chartjs_lib, so a canvas
 * drawn without an explicit loadBundle stays blank with no error in the
 * console. Everything here is a CSS box or a hand-built SVG, which cannot fail
 * that way.
 *
 * All arithmetic happens in the Python endpoint or in shape() below. The
 * template holds no maths, so what is drawn and what is counted cannot drift.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

/** Donut geometry, in the SVG's own viewBox units. */
const DONUT = { cx: 60, cy: 60, r: 44, stroke: 22 };

/** Fixed colours per condition so the donut and the bars always agree. */
const CONDITION_COLOUR = {
    very_good: "#1b806a",
    good: "#5ba86f",
    average: "#d9a441",
    bad: "#e07a3f",
    not_working: "#c0392b",
    unknown: "#9aa6b2",
};

const SERIES_COLOUR = [
    "#2b6cb0", "#1b806a", "#8e44ad", "#d9a441", "#c0392b",
    "#3d7ea6", "#5ba86f", "#a0699c", "#b0894a", "#9aa6b2",
];

function pct(value, total) {
    if (!total || total <= 0) {
        return 0;
    }
    return Math.max(0, Math.min(100, (value / total) * 100));
}

/**
 * Indian digit grouping: 19,19,204 rather than 1,919,204. The company reports
 * in rupees and the payslip layout in xn_auditree_erp already groups this way,
 * so the dashboard matching it keeps the two readable side by side.
 */
function inr(value) {
    const n = Math.round(Number(value) || 0);
    const s = String(Math.abs(n));
    let out;
    if (s.length <= 3) {
        out = s;
    } else {
        const tail = s.slice(-3);
        let head = s.slice(0, -3);
        const parts = [];
        while (head.length > 2) {
            parts.unshift(head.slice(-2));
            head = head.slice(0, -2);
        }
        if (head) {
            parts.unshift(head);
        }
        out = parts.join(",") + "," + tail;
    }
    return (n < 0 ? "-" : "") + out;
}

/** 1919204 -> "19.2L". Keeps the headline tile readable at a glance. */
function compact(value) {
    const n = Number(value) || 0;
    if (Math.abs(n) >= 10000000) {
        return (n / 10000000).toFixed(1) + "Cr";
    }
    if (Math.abs(n) >= 100000) {
        return (n / 100000).toFixed(1) + "L";
    }
    if (Math.abs(n) >= 1000) {
        return (n / 1000).toFixed(1) + "K";
    }
    return String(Math.round(n));
}

/** One arc of the condition donut, as an SVG dash offset. */
function donutSegments(items, total) {
    const circumference = 2 * Math.PI * DONUT.r;
    let consumed = 0;
    return items.map((item) => {
        const share = total > 0 ? item.count / total : 0;
        const length = share * circumference;
        const seg = {
            ...item,
            colour: CONDITION_COLOUR[item.key] || "#9aa6b2",
            dash: `${length} ${circumference - length}`,
            offset: -consumed,
            share: Math.round(share * 1000) / 10,
        };
        consumed += length;
        return seg;
    });
}

export class XnAssetDashboard extends Component {
    static template = "xn_asset_register.Dashboard";
    static props = {
        action: { type: Object, optional: true },
        actionId: { type: [Number, Boolean], optional: true },
        className: { type: String, optional: true },
        updateActionState: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.inr = inr;
        this.compact = compact;
        this.state = useState({
            loading: true,
            error: false,
            data: null,
            view: "count", // "count" or "value"
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.error = false;
        try {
            const data = await this.orm.call(
                "maintenance.equipment", "xn_asset_dashboard_data", []
            );
            this.state.data = this.shape(data);
        } catch (error) {
            // A readable line beats an empty dashboard. The usual cause is a
            // user without the Asset Register Manager group reaching the menu
            // through a stale cached menu tree.
            this.state.error =
                (error && error.data && error.data.message) ||
                (error && error.message) ||
                "Could not load the asset dashboard.";
        } finally {
            this.state.loading = false;
        }
    }

    /** Everything the template needs, precomputed. */
    shape(data) {
        const total = data.headline.total || 0;

        const condition = donutSegments(data.condition, total);

        const maxCatCount = Math.max(1, ...data.category.map((c) => c.count));
        const maxCatValue = Math.max(1, ...data.category.map((c) => c.value));
        const category = data.category.map((c, i) => ({
            ...c,
            colour: SERIES_COLOUR[i % SERIES_COLOUR.length],
            countPct: pct(c.count, maxCatCount),
            valuePct: pct(c.value, maxCatValue),
            sharePct: Math.round(pct(c.value, data.headline.total_value) * 10) / 10,
        }));

        const maxHolder = Math.max(1, ...data.holders.map((h) => h.count));
        const holders = data.holders.slice(0, 10).map((h) => ({
            ...h,
            barPct: pct(h.count, maxHolder),
        }));

        const maxYearCount = Math.max(1, ...data.years.map((y) => y.count));
        const maxYearValue = Math.max(1, ...data.years.map((y) => y.value));
        const years = data.years.map((y) => ({
            ...y,
            countPct: pct(y.count, maxYearCount),
            valuePct: pct(y.value, maxYearValue),
        }));

        const maxBand = Math.max(1, ...data.age_bands.map((b) => b.count));
        const ageBands = data.age_bands.map((b, i) => ({
            ...b,
            barPct: pct(b.count, maxBand),
            // Older bands read warmer, so the replacement tail is obvious.
            colour: ["#1b806a", "#5ba86f", "#d9a441", "#e07a3f", "#c0392b"][i] ||
                "#9aa6b2",
        }));

        const custody = [
            {
                key: "assigned",
                label: "With employees",
                count: data.headline.assigned,
                colour: "#2b6cb0",
                barPct: pct(data.headline.assigned, total),
            },
            {
                key: "at_location",
                label: "In inventory",
                count: data.headline.at_location,
                colour: "#8e94a3",
                barPct: pct(data.headline.at_location, total),
            },
        ];

        const topCategory = category[0] || null;

        return {
            ...data,
            condition,
            category,
            holders,
            years,
            ageBands,
            custody,
            topCategory,
            concentration: topCategory
                ? Math.round(pct(topCategory.value, data.headline.total_value))
                : 0,
            donut: DONUT,
            circumference: 2 * Math.PI * DONUT.r,
        };
    }

    toggleView() {
        this.state.view = this.state.view === "count" ? "value" : "count";
    }

    async open(key, value) {
        const action = await this.orm.call(
            "maintenance.equipment", "xn_asset_dashboard_open",
            [key, value === undefined ? null : value]
        );
        this.action.doAction(action);
    }
}

registry.category("actions").add("xn_asset_dashboard", XnAssetDashboard);
