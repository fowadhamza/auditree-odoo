/** @odoo-module **/
/**
 * Activity timelines: a bar of 5-minute blocks across the working day,
 * coloured by what the person was doing (category of the main app, idle,
 * locked). Gaps are times the laptop sent nothing (off, asleep, away).
 *
 *  - xn_activity_day_timeline: form widget on a Daily Work Metrics day.
 *  - xn_activity_team_timeline: client action, one row per person for a
 *    date (Activity > Team Timeline).
 *
 * Drawn with positioned CSS boxes, no Chart.js (not in web.assets_backend).
 * Data comes from xn.activity.day.xn_timeline_data / xn_team_timeline,
 * which read as the current user, so record rules decide whose rows appear.
 * Minutes are laptop-local.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";

const { DateTime } = luxon;

const SLOT = 5;
const DAY_START = 8 * 60;
const DAY_END = 20 * 60;

function pad(n) {
    return String(n).padStart(2, "0");
}

function hhmm(minutes) {
    return `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
}

function mmss(seconds) {
    const s = Math.round(seconds || 0);
    return `${Math.floor(s / 60)}:${pad(s % 60)}`;
}

export function hoursMinutes(hours) {
    const m = Math.round((hours || 0) * 60);
    return `${Math.floor(m / 60)}:${pad(m % 60)}`;
}

/** Whole hours covering 08:00-20:00 and every slot of these days. */
export function timelineWindow(days) {
    let lo = DAY_START;
    let hi = DAY_END;
    for (const day of days) {
        for (const s of day.slots) {
            lo = Math.min(lo, s.m);
            hi = Math.max(hi, s.m + SLOT);
        }
    }
    return { lo: Math.floor(lo / 60) * 60, hi: Math.min(Math.ceil(hi / 60) * 60, 24 * 60) };
}

function ticks(lo, hi) {
    const span = hi - lo;
    const step = span > 14 * 60 ? 120 : 60;
    const out = [];
    let index = 0;
    for (let m = lo; m <= hi; m += step) {
        let shift = "-50%";
        if (m === lo) {
            shift = "0";
        } else if (m + step > hi) {
            shift = "-100%";
        }
        out.push({
            m,
            label: hhmm(m % (24 * 60)),
            left: ((m - lo) / span) * 100,
            shift,
            // Only every third label fits on a phone (see timeline.scss).
            minor: index % 3 !== 0,
        });
        index++;
    }
    return out;
}

export class XnTimelineAxis extends Component {
    static template = "xn_activity.TimelineAxis";
    static props = { lo: Number, hi: Number };

    get ticks() {
        return ticks(this.props.lo, this.props.hi);
    }
}

export class XnTimelineBar extends Component {
    static template = "xn_activity.TimelineBar";
    static props = { slots: Array, lo: Number, hi: Number, labels: Object };

    get gridlines() {
        return ticks(this.props.lo, this.props.hi).slice(1, -1);
    }

    get blocks() {
        const { lo, hi, labels } = this.props;
        const span = hi - lo;
        return this.props.slots
            .filter((s) => s.m >= lo && s.m < hi)
            .map((s) => ({
                key: s.m,
                cls: `o_xn_tl_block o_xn_tl_${s.s}`,
                style: `left:${((s.m - lo) / span) * 100}%;width:${(SLOT / span) * 100}%`,
                title:
                    `${hhmm(s.m)}-${hhmm(s.m + SLOT)}  ${labels[s.s] || s.s}\n` +
                    `${s.apps}\n` +
                    `Active ${mmss(s.a)}, idle ${mmss(s.i)}, locked ${mmss(s.l)}`,
            }));
    }
}

export class XnTimelineLegend extends Component {
    static template = "xn_activity.TimelineLegend";
    static props = { states: Array };
}

/**
 * Thin strip under a timeline bar: connection quality per 5-minute slot
 * (agent 1.3+). Each entry {m, q, title}; q is excellent / good / fair /
 * slow / offline / unknown.
 */
export class XnNetStrip extends Component {
    static template = "xn_activity.NetStrip";
    static props = { net: Array, lo: Number, hi: Number };

    get blocks() {
        const { lo, hi } = this.props;
        const span = hi - lo;
        return this.props.net
            .filter((n) => n.m >= lo && n.m < hi)
            .map((n) => ({
                key: n.m,
                cls: `o_xn_tl_block o_xn_net_${n.q}`,
                style: `left:${((n.m - lo) / span) * 100}%;width:${(SLOT / span) * 100}%`,
                title: `${hhmm(n.m)}-${hhmm(n.m + SLOT)}  Connection: ${n.title}`,
            }));
    }
}

export const NET_QUALITIES = [
    ["excellent", "Excellent"],
    ["good", "Good"],
    ["fair", "Fair"],
    ["slow", "Slow"],
    ["offline", "Offline"],
];

export class XnNetLegend extends Component {
    static template = "xn_activity.NetLegend";
    static props = {};

    get qualities() {
        return NET_QUALITIES;
    }
}

const timelineComponents = {
    XnTimelineAxis,
    XnTimelineBar,
    XnTimelineLegend,
    XnNetStrip,
    XnNetLegend,
};

// ---------------------------------------------------------------------------
// Day form widget
// ---------------------------------------------------------------------------

export class XnDayTimeline extends Component {
    static template = "xn_activity.DayTimeline";
    static components = timelineComponents;
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ loaded: false, day: null, states: [] });
        onWillStart(() => this.load(this.props.record.resId));
        onWillUpdateProps((next) => {
            if (next.record.resId !== this.props.record.resId) {
                return this.load(next.record.resId);
            }
        });
    }

    async load(resId) {
        if (!resId) {
            Object.assign(this.state, { loaded: true, day: null });
            return;
        }
        const res = await this.orm.call("xn.activity.day", "xn_timeline_data", [[resId]]);
        Object.assign(this.state, {
            loaded: true,
            states: res.states,
            day: res.days[0] || null,
        });
    }

    get labels() {
        return Object.fromEntries(this.state.states);
    }

    get bounds() {
        return timelineWindow(this.state.day ? [this.state.day] : []);
    }
}

registry.category("view_widgets").add("xn_activity_day_timeline", {
    component: XnDayTimeline,
});

// ---------------------------------------------------------------------------
// Team Timeline client action
// ---------------------------------------------------------------------------

const STATUS = {
    good: "On Target",
    fair: "Below Target",
    low: "Under Half",
    none: "No Activity",
    pending: "In Progress",
    weekend: "Weekend",
    holiday: "Holiday",
    leave: "On Leave",
};

export class XnTeamTimeline extends Component {
    static template = "xn_activity.TeamTimeline";
    static components = timelineComponents;
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            date: DateTime.now().toISODate(),
            department: "",
            loading: true,
            data: { days: [], states: [], departments: [] },
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        const data = await this.orm.call("xn.activity.day", "xn_team_timeline", [this.state.date]);
        Object.assign(this.state, { data, date: data.date, loading: false });
    }

    shift(days) {
        this.state.date = DateTime.fromISO(this.state.date).plus({ days }).toISODate();
        return this.load();
    }

    today() {
        this.state.date = DateTime.now().toISODate();
        return this.load();
    }

    onDateChange(ev) {
        if (ev.target.value) {
            this.state.date = ev.target.value;
            return this.load();
        }
    }

    onDepartmentChange(ev) {
        this.state.department = ev.target.value;
    }

    get dateLabel() {
        return DateTime.fromISO(this.state.date).toFormat("cccc d LLLL yyyy");
    }

    get rows() {
        const dep = parseInt(this.state.department) || false;
        return this.state.data.days
            .filter((d) => !dep || d.department_id === dep)
            .map((d) => ({
                ...d,
                screen: hoursMinutes(d.screen_hours),
                productive: hoursMinutes(d.productive_hours),
                statusLabel: STATUS[d.status] || "",
            }));
    }

    get labels() {
        return Object.fromEntries(this.state.data.states);
    }

    get bounds() {
        return timelineWindow(this.rows);
    }

    get hasNet() {
        return this.state.data.days.some((d) => d.net && d.net.length);
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
}

registry.category("actions").add("xn_activity_team_timeline", XnTeamTimeline);
