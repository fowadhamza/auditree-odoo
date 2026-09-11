/** @odoo-module **/
/**
 * The Auditree Forecast dashboard.
 *
 * Charts are laid out from numbers computed here and drawn as plain SVG, the
 * same choice xn_hr_dashboard made and for the same reason: Odoo 17 does not
 * put Chart.js in web.assets_backend, so a canvas-based chart depends on a
 * loadBundle that fails silently and leaves the box blank. Hand-built SVG has
 * no such failure mode and needs no third-party asset.
 *
 * All arithmetic lives in this file. The template only places values, so what
 * is drawn and what is totalled cannot drift apart.
 *
 * The rupee sign is written as a \u20B9 escape, not a literal glyph: source
 * files in this repo are kept ASCII-only (see CLAUDE.md), because non-ASCII
 * characters have been corrupted by Windows-side writes before.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

const RUPEE = "\u20B9";

/** Plot geometry, in each SVG's own viewBox units. */
const PLOT = { x0: 56, x1: 592, yTop: 12, yBottom: 168 };

const SERIES_COLORS = {
    inflow: "#16a34a",
    salary: "#dc2626",
    expense: "#f59e0b",
    revenue: "#16a34a",
    expenses: "#dc2626",
    net: "#0f172a",
    cash: "#0f172a",
};

/** Grey ramp for categorical marks, matching the source app's palette. */
const CATEGORY_COLORS = [
    "#0f172a", "#334155", "#64748b", "#94a3b8", "#cbd5e1",
    "#475569", "#1e293b", "#7c8ba1", "#a8b3c2", "#e2e8f0",
];

/** Indian digit grouping: 12,34,567 rather than 1,234,567. */
function groupIndian(digits) {
    if (digits.length <= 3) {
        return digits;
    }
    const last3 = digits.slice(-3);
    const rest = digits.slice(0, -3);
    return rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",") + "," + last3;
}

/** Full amount, e.g. -Rs 12,34,567. */
function formatInr(value) {
    const number = Math.round(Number(value) || 0);
    const sign = number < 0 ? "-" : "";
    return sign + RUPEE + groupIndian(String(Math.abs(number)));
}

/** Compact amount for axes and bar labels, e.g. Rs 12.3L or Rs 1.2Cr. */
function formatShort(value) {
    const number = Number(value) || 0;
    const sign = number < 0 ? "-" : "";
    const abs = Math.abs(number);
    if (abs >= 10000000) {
        return sign + RUPEE + (abs / 10000000).toFixed(1) + "Cr";
    }
    if (abs >= 100000) {
        return sign + RUPEE + (abs / 100000).toFixed(1) + "L";
    }
    if (abs >= 1000) {
        return sign + RUPEE + Math.round(abs / 1000) + "K";
    }
    return sign + RUPEE + Math.round(abs);
}

function formatPct(value) {
    return (Number(value) || 0).toFixed(1) + "%";
}

/**
 * Surface what actually failed instead of one generic sentence.
 *
 * Odoo wraps server faults in more than one shape - an RPCError carries
 * `data.message`, a plain fault carries `message`, and a bug in this file
 * throws an ordinary Error. Reporting only the fallback once hid a stale
 * registry ("method does not exist", fixed by restarting Odoo) behind
 * "Could not load", so every shape is unwrapped here.
 */
function describeError(error) {
    if (!error) {
        return "Could not load the forecast dashboard.";
    }
    const fault = (error.data && error.data.message)
        || (error.message && error.message.data && error.message.data.message)
        || (typeof error.message === "string" && error.message)
        || String(error);
    return "Could not load the forecast dashboard: " + fault;
}

/**
 * A y-scale covering every value in the series, always including zero so a
 * negative month reads as below the baseline rather than off the bottom.
 */
function makeScale(values) {
    const numbers = values.map((v) => Number(v) || 0);
    let min = Math.min(0, ...numbers);
    let max = Math.max(0, ...numbers);
    if (min === max) {
        max = min + 1;
    }
    const span = max - min;
    const height = PLOT.yBottom - PLOT.yTop;
    return {
        min,
        max,
        y: (value) => PLOT.yBottom - ((Number(value) || 0) - min) / span * height,
        zeroY: PLOT.yBottom - (0 - min) / span * height,
    };
}

/** Evenly spaced x centres for n categories across the plot. */
function makeBands(count) {
    if (count <= 0) {
        return { step: 0, centre: () => PLOT.x0 };
    }
    const step = (PLOT.x1 - PLOT.x0) / count;
    return { step, centre: (i) => PLOT.x0 + step * (i + 0.5) };
}

/** Show at most ~8 x labels so they stay readable at 15 months. */
function labelEvery(count) {
    return Math.max(1, Math.ceil(count / 8));
}

/** Three gridline values: min, midpoint, max. */
function gridLines(scale) {
    const mid = (scale.min + scale.max) / 2;
    return [scale.max, mid, scale.min].map((value) => ({
        value,
        label: formatShort(value),
        y: scale.y(value),
    }));
}

export class ForecastDashboard extends Component {
    static template = "xn_auditree_forecast.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.formatInr = formatInr;
        this.formatShort = formatShort;
        this.formatPct = formatPct;
        this.state = useState({
            loading: true,
            error: false,
            hasData: false,
            message: "",
            raw: null,
            charts: null,
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        this.state.error = false;
        try {
            const data = await this.orm.call("forecast.config", "get_dashboard_data", []);
            this.state.hasData = !!data.has_data;
            this.state.message = data.message || "";
            this.state.raw = data;
            this.state.charts = data.has_data ? this.buildCharts(data) : null;
        } catch (error) {
            this.state.error = true;
            this.state.message = describeError(error);
        } finally {
            this.state.loading = false;
        }
    }

    /** Shape every chart's geometry once, so the template holds no arithmetic. */
    buildCharts(data) {
        return {
            cashTrend: this.buildAreaChart(data.cash_trend),
            inflowOutflow: this.buildGroupedBars(data.inflow_outflow, [
                { key: "inflow", name: "Inflow", color: SERIES_COLORS.inflow },
                { key: "salary_out", name: "Salary Outflow", color: SERIES_COLORS.salary },
                { key: "expense_out", name: "Expense Outflow", color: SERIES_COLORS.expense },
            ]),
            monthlyProfit: this.buildLineChart(data.monthly_profit, [
                { key: "revenue", name: "Revenue", color: SERIES_COLORS.revenue, dashed: false },
                { key: "expenses", name: "Expenses", color: SERIES_COLORS.expenses, dashed: false },
                { key: "net", name: "Net Profit", color: SERIES_COLORS.net, dashed: true },
            ]),
            revenueByClient: this.buildHorizontalBars(data.revenue_by_client),
            expenseBreakdown: this.buildDonut(data.expense_breakdown),
            windowProgress: this.buildProgress(data.window),
            alerts: this.buildAlerts(data.kpi),
        };
    }

    buildProgress(window) {
        const total = window.total_months || 0;
        const elapsed = window.elapsed_months || 0;
        return {
            elapsed,
            total,
            pct: total > 0 ? (elapsed / total) * 100 : 0,
        };
    }

    /** Cash risk and loss-making banners, mirroring the source app's rules. */
    buildAlerts(kpi) {
        const alerts = [];
        if (kpi.min_closing_balance < kpi.low_cash_threshold) {
            alerts.push({
                id: "low_cash",
                text: "Lowest cash balance is " + formatInr(kpi.min_closing_balance)
                    + " in " + kpi.min_closing_month + ", below the "
                    + formatInr(kpi.low_cash_threshold) + " threshold.",
            });
        }
        if (kpi.net_profit < 0) {
            alerts.push({
                id: "loss",
                text: "Net profit before tax is negative ("
                    + formatPct(kpi.margin_pct) + " margin).",
            });
        }
        return alerts;
    }

    /** Closing cash over time: a filled area under a polyline. */
    buildAreaChart(points) {
        if (!points || !points.length) {
            return { empty: true };
        }
        const scale = makeScale(points.map((p) => p.value));
        const bands = makeBands(points.length);
        const every = labelEvery(points.length);
        const coords = points.map((p, i) => ({
            x: bands.centre(i),
            y: scale.y(p.value),
            label: p.label,
            value: p.value,
            showLabel: i % every === 0,
        }));
        const line = coords.map((c) => c.x + "," + c.y).join(" ");
        const area = PLOT.x0 + "," + scale.zeroY + " " + line + " "
            + PLOT.x1 + "," + scale.zeroY;
        return {
            empty: false,
            color: SERIES_COLORS.cash,
            line,
            area,
            points: coords,
            grid: gridLines(scale),
            zeroY: scale.zeroY,
        };
    }

    /** Several bars side by side within each month's band. */
    buildGroupedBars(rows, series) {
        if (!rows || !rows.length) {
            return { empty: true };
        }
        const values = [];
        rows.forEach((row) => series.forEach((s) => values.push(row[s.key])));
        const scale = makeScale(values);
        const bands = makeBands(rows.length);
        const every = labelEvery(rows.length);
        const barWidth = Math.max(2, (bands.step * 0.7) / series.length);

        const bars = [];
        rows.forEach((row, i) => {
            const groupLeft = bands.centre(i) - (barWidth * series.length) / 2;
            series.forEach((s, j) => {
                const value = Number(row[s.key]) || 0;
                const y = scale.y(value);
                bars.push({
                    id: i + "-" + s.key,
                    x: groupLeft + barWidth * j,
                    y: Math.min(y, scale.zeroY),
                    width: barWidth,
                    height: Math.abs(scale.zeroY - y),
                    color: s.color,
                    title: row.label + " " + s.name + ": " + formatInr(value),
                });
            });
        });
        return {
            empty: false,
            bars,
            legend: series.map((s) => ({ name: s.name, color: s.color })),
            grid: gridLines(scale),
            zeroY: scale.zeroY,
            labels: rows.map((row, i) => ({
                x: bands.centre(i), label: row.label, showLabel: i % every === 0,
            })).filter((l) => l.showLabel),
        };
    }

    /** Multi-series line chart with a zero reference line. */
    buildLineChart(rows, series) {
        if (!rows || !rows.length) {
            return { empty: true };
        }
        const values = [];
        rows.forEach((row) => series.forEach((s) => values.push(row[s.key])));
        const scale = makeScale(values);
        const bands = makeBands(rows.length);
        const every = labelEvery(rows.length);

        const lines = series.map((s) => ({
            name: s.name,
            color: s.color,
            dashed: s.dashed,
            path: rows.map((row, i) => bands.centre(i) + "," + scale.y(row[s.key])).join(" "),
        }));
        return {
            empty: false,
            lines,
            legend: series.map((s) => ({ name: s.name, color: s.color, dashed: s.dashed })),
            grid: gridLines(scale),
            zeroY: scale.zeroY,
            labels: rows.map((row, i) => ({
                x: bands.centre(i), label: row.label, showLabel: i % every === 0,
            })).filter((l) => l.showLabel),
        };
    }

    /**
     * Revenue by client as horizontal bars. A bar chart, not a pie: comparing
     * lengths on a shared baseline is easier than comparing angles, and client
     * counts here run past what a pie stays readable at.
     */
    buildHorizontalBars(rows) {
        if (!rows || !rows.length) {
            return { empty: true };
        }
        const max = Math.max(...rows.map((r) => Math.abs(Number(r.value) || 0)), 1);
        const rowHeight = 26;
        return {
            empty: false,
            height: rows.length * rowHeight + 8,
            rows: rows.map((row, i) => ({
                name: row.name,
                y: i * rowHeight + 4,
                height: rowHeight - 10,
                width: Math.max(1, (Math.abs(row.value) / max) * 100),
                color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                amount: formatInr(row.value),
            })),
        };
    }

    /**
     * Expense mix as a donut, built from stroke-dasharray arcs on concentric
     * circles - no path arithmetic, and it degrades to nothing if a slice is 0.
     */
    buildDonut(rows) {
        if (!rows || !rows.length) {
            return { empty: true };
        }
        const total = rows.reduce((sum, r) => sum + (Number(r.value) || 0), 0);
        if (total <= 0) {
            return { empty: true };
        }
        const radius = 60;
        const circumference = 2 * Math.PI * radius;
        let offset = 0;
        const slices = rows.map((row, i) => {
            const share = (Number(row.value) || 0) / total;
            const length = share * circumference;
            const slice = {
                name: row.name,
                color: CATEGORY_COLORS[i % CATEGORY_COLORS.length],
                dash: length + " " + (circumference - length),
                offset: -offset,
                pct: formatPct(share * 100),
                amount: formatInr(row.value),
            };
            offset += length;
            return slice;
        });
        return {
            empty: false,
            radius,
            circumference,
            slices,
            total: formatInr(total),
        };
    }

    /** Tile click-through to the matching report, same targets as the web app. */
    openReport(xmlId) {
        this.action.doAction("xn_auditree_forecast." + xmlId);
    }

    openPnl() {
        this.openReport("action_forecast_monthly_line");
    }

    openCashFlow() {
        this.openReport("action_forecast_cash_flow_month");
    }

    openEmployees() {
        this.openReport("action_forecast_employee");
    }

    openSettings() {
        this.openReport("action_forecast_config");
    }
}

registry.category("actions").add("xn_auditree_forecast_dashboard", ForecastDashboard);
