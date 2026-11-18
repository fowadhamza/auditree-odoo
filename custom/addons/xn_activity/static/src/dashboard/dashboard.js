/** @odoo-module **/
/**
 * Activity > Dashboard (client action xn_activity_dashboard).
 *
 * All figures come from xn.activity.day.xn_dashboard_data, which reads as
 * the current user: HR and the board see everyone, a reporting manager
 * their team, anyone else themselves. The server only sends the
 * "attention" list to the Board of Directors and "to_sort" to HR, so the
 * template shows those panels when the data is there.
 *
 * Charts are CSS boxes (no Chart.js, see timeline.js).
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import {
    XnTimelineAxis,
    XnTimelineBar,
    XnTimelineLegend,
    hoursMinutes,
    timelineWindow,
} from "@xn_activity/timeline/timeline";

const CATEGORY_LABELS = {
    productive: "Productive",
    neutral: "Neutral",
    unclassified: "Unclassified",
    unproductive: "Unproductive",
    system: "Windows / System",
    idle: "Idle",
};

const TIMELINE_STATES = [
    ["productive", "Productive"],
    ["neutral", "Neutral"],
    ["unclassified", "Unclassified"],
    ["unproductive", "Unproductive"],
    ["system", "Windows / System"],
    ["idle", "Idle"],
    ["locked", "Locked"],
];

const PERIODS = [
    ["week", "This week"],
    ["last", "Last week"],
    ["month", "This month"],
];

const BAR_PX = 220;

function delta(now, prev, fmt, better = 1) {
    if (prev === null || prev === undefined) {
        return { text: "", cls: "" };
    }
    const d = now - prev;
    if (Math.abs(d) < 1e-9) {
        return { text: "no change", cls: "o_xn_dash_flat" };
    }
    // better: 1 = up is good, -1 = down is good, 0 = neither (neutral).
    let cls = "o_xn_dash_flat";
    if (better) {
        cls = d * better > 0 ? "o_xn_dash_up" : "o_xn_dash_down";
    }
    return { text: `${d > 0 ? "+" : "-"}${fmt(Math.abs(d))} vs previous`, cls };
}

export class XnActivityDashboard extends Component {
    static template = "xn_activity.Dashboard";
    static components = { XnTimelineAxis, XnTimelineBar, XnTimelineLegend };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.periods = PERIODS;
        this.timelineStates = TIMELINE_STATES;
        this.state = useState({ period: "week", department: "", loading: true, data: null });
        onWillStart(() => this.load());
    }

    async load() {
        // Only the latest request may fill the page: a slower earlier reply
        // must not overwrite it (the buttons would then show one period and
        // the figures another).
        const token = (this.loadToken = (this.loadToken || 0) + 1);
        this.state.loading = true;
        const data = await this.orm.call("xn.activity.day", "xn_dashboard_data", [
            this.state.period,
            parseInt(this.state.department) || false,
        ]);
        if (token !== this.loadToken) {
            return;
        }
        this.state.data = data;
        this.state.loading = false;
    }

    setPeriod(period) {
        this.state.period = period;
        return this.load();
    }

    onDepartmentChange(ev) {
        this.state.department = ev.target.value;
        return this.load();
    }

    // ------------------------------------------------------------------
    // Shaped figures (templates hold no arithmetic)
    // ------------------------------------------------------------------

    get kpis() {
        const k = this.state.data.kpis;
        const pct = (v) => `${Math.round(v)} pts`;
        const prevDays = k.prev.days ? k.prev : null;
        const out = [
            {
                label: "Avg productive / day",
                value: hoursMinutes(k.now.productive),
                ...delta(k.now.productive, prevDays && prevDays.productive, hoursMinutes),
            },
            {
                label: "Avg screen time / day",
                value: hoursMinutes(k.now.screen),
                ...delta(k.now.screen, prevDays && prevDays.screen, hoursMinutes, 0),
            },
            {
                label: "Days on target",
                value: k.now.days ? `${Math.round(k.now.on_target)}%` : "-",
                ...delta(k.now.on_target, prevDays && prevDays.on_target, pct),
            },
            {
                label: `Under target ${3}+ days`,
                value: String(k.low_people),
                ...delta(k.low_people, k.low_people_prev, (v) => String(v), -1),
            },
        ];
        const l = this.state.data.laptops;
        if (l.total) {
            out.push({
                label: "Laptops reporting",
                value: `${l.reporting} / ${l.total}`,
                text: l.stale ? `${l.stale} silent for 2+ working days` : "all reporting",
                cls: l.stale ? "o_xn_dash_down" : "o_xn_dash_up",
            });
        }
        return out;
    }

    get byDay() {
        const data = this.state.data;
        const max = Math.max(data.target, ...data.by_day.map((d) => d.screen), 1);
        const scale = BAR_PX / max;
        return {
            targetStyle: `bottom:${Math.round(data.target * scale)}px`,
            targetLabel: hoursMinutes(data.target),
            days: data.by_day.map((d) => ({
                key: d.date,
                label: d.label,
                total: d.people ? hoursMinutes(d.screen) : "",
                title: d.people
                    ? `${d.label}: productive ${hoursMinutes(d.productive)} of ${hoursMinutes(d.screen)} screen time, ${d.people} people`
                    : `${d.label}: no activity`,
                barStyle: `height:${Math.round(d.screen * scale)}px`,
                otherStyle: `height:${Math.round((d.screen - d.productive) * scale)}px`,
            })),
        };
    }

    get split() {
        const rows = this.state.data.split.filter((s) => s.hours > 0);
        return rows.map((s) => ({
            key: s.key,
            label: CATEGORY_LABELS[s.key],
            pct: `${Math.round(s.pct)}%`,
            hours: hoursMinutes(s.hours),
            barStyle: `width:${s.pct}%`,
            cls: `o_xn_tl_${s.key}`,
        }));
    }

    get unclassifiedPct() {
        const u = this.state.data.split.find((s) => s.key === "unclassified");
        return u && u.pct >= 5 ? Math.round(u.pct) : 0;
    }

    get departments() {
        return this.state.data.departments_table.map((r) => ({
            ...r,
            key: r.id || r.name,
            screenText: hoursMinutes(r.screen),
            productiveText: hoursMinutes(r.productive),
            pct: `${Math.round(r.on_target)}%`,
            barStyle: `width:${r.on_target}%`,
            deltaText:
                r.delta === null
                    ? "-"
                    : `${r.delta > 0 ? "+" : ""}${Math.round(r.delta)} pts`,
            deltaCls:
                r.delta === null || Math.round(r.delta) === 0
                    ? "o_xn_dash_flat"
                    : r.delta > 0
                    ? "o_xn_dash_up"
                    : "o_xn_dash_down",
        }));
    }

    get attention() {
        return (this.state.data.attention || []).map((a) => ({
            ...a,
            productiveText: hoursMinutes(a.productive),
        }));
    }

    get apps() {
        const apps = this.state.data.apps;
        const max = Math.max(...apps.map((a) => a.hours), 0.01);
        return apps.map((a) => ({
            ...a,
            key: a.name,
            catLabel: CATEGORY_LABELS[a.category] || a.category,
            hoursText: hoursMinutes(a.hours),
            barStyle: `width:${Math.round((a.hours / max) * 100)}%`,
            barCls: `o_xn_tl_${a.category}`,
        }));
    }

    get today() {
        const days = this.state.data.today || [];
        const labels = Object.fromEntries(TIMELINE_STATES);
        return { days, labels, bounds: timelineWindow(days) };
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------

    openTeamTimeline() {
        return this.action.doAction("xn_activity.action_xn_activity_team_timeline");
    }

    openDay(id) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "xn.activity.day",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openPersonDays(employeeId, name) {
        const data = this.state.data;
        return this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "xn.activity.day",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["employee_id", "=", employeeId],
                ["date", ">=", data.start],
                ["date", "<=", data.end],
            ],
            target: "current",
        });
    }

    openApps() {
        return this.action.doAction("xn_activity.action_xn_activity_app", {
            additionalContext: { search_default_unclassified: 1 },
        });
    }
}

registry.category("actions").add("xn_activity_dashboard", XnActivityDashboard);
