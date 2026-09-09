/** @odoo-module **/
/**
 * Extends the vendor HRMS dashboard instead of forking it.
 *
 * Three things this file is careful about:
 *
 *  1. Chart.js is NOT in web.assets_backend in Odoo 17 - it lives in the
 *     web.chartjs_lib bundle, which the graph view loads on demand. Without
 *     the loadBundle below, `Chart` is undefined and every canvas stays blank.
 *  2. Only HR managers may call the org endpoints, so they are not called at
 *     all for anyone else. Firing six RPCs that are guaranteed to raise
 *     AccessError is not error handling.
 *  3. No chart here has two y-scales. Hours and headcount are different units
 *     and get their own plot.
 *
 * Odoo 16 differences: patch() takes a name as its second argument, and you
 * call this._super() rather than super.setup().
 */

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { onWillStart, onMounted, onWillUnmount, useState } from "@odoo/owl";

const ACTION_TAG = "hr_dashboard";

const actions = registry.category("actions");
const HrDashboard = actions.contains(ACTION_TAG) ? actions.get(ACTION_TAG) : null;

/** Palette read from CSS custom properties, so dark mode is handled once. */
function xnPalette() {
    const css = getComputedStyle(document.documentElement);
    const read = (name, fallback) =>
        (css.getPropertyValue(name) || "").trim() || fallback;
    return {
        s1: read("--xn-series-1", "#2a78d6"),
        s2: read("--xn-series-2", "#eb6834"),
        ink: read("--xn-chart-ink", "#6d6169"),
        grid: read("--xn-chart-grid", "rgba(0,0,0,.08)"),
    };
}

if (HrDashboard) {
    patch(HrDashboard.prototype, {
        setup() {
            super.setup(...arguments);
            this.orm = useService("orm");
            this.xnAction = useService("action");
            this.xn = useState({
                loaded: false,
                permitted: false,
                chartsAvailable: true,
                anniversaries: { tracked: false, window: 30, rows: [] },
                tiles: {},
                health: {},
                pipeline: { rows: [], total: 0 },
                utilisation: {},
                attendance: {},
                turnover: {},
            });
            this._xnCharts = [];

            onWillStart(async () => {
                // Anniversaries sit in the "Your team" row, which everyone
                // sees, so this runs before the manager gate that gets in the
                // way of the organisation endpoints below.
                const anniversaries = await this.orm
                    .call("hr.employee", "xn_work_anniversaries", [])
                    .catch((error) => {
                        console.warn(
                            "xn_hr_dashboard: xn_work_anniversaries failed", error
                        );
                        return null;
                    });
                if (anniversaries) {
                    this.xn.anniversaries = anniversaries;
                }

                // The vendor already resolved this in its own onWillStart.
                const isManager = await this.user.hasGroup("hr.group_hr_manager");
                this.xn.permitted = isManager;
                if (!isManager) {
                    this.xn.loaded = true;
                    return;
                }

                try {
                    await loadBundle("web.chartjs_lib");
                } catch (error) {
                    console.warn("xn_hr_dashboard: Chart.js failed to load", error);
                }
                this.xn.chartsAvailable = typeof Chart !== "undefined";

                const call = (method, args = []) =>
                    this.orm.call("hr.employee", method, args).catch((error) => {
                        console.warn(`xn_hr_dashboard: ${method} failed`, error);
                        return null;
                    });

                const [tiles, health, pipeline, utilisation, attendance, turnover] =
                    await Promise.all([
                        call("xn_dashboard_tiles"),
                        call("xn_data_health"),
                        call("xn_recruitment_pipeline"),
                        call("xn_timesheet_utilisation", [6]),
                        call("xn_attendance_trend", [6]),
                        call("xn_turnover", [12]),
                    ]);

                Object.assign(this.xn, {
                    loaded: true,
                    tiles: tiles || {},
                    health: health || {},
                    pipeline: pipeline || { rows: [], total: 0 },
                    utilisation: utilisation || {},
                    attendance: attendance || {},
                    turnover: turnover || {},
                });
            });

            onMounted(() => this.xnRenderCharts());
            onWillUnmount(() => {
                this._xnCharts.forEach((chart) => chart.destroy());
                this._xnCharts = [];
            });
        },

        /** Opens exactly the records the tile counted. Domain stays server-side. */
        async xnOpenTile(key) {
            const action = await this.orm.call("hr.employee", "xn_open_tile", [key]);
            if (action) {
                this.xnAction.doAction(action);
            }
        },

        xnChart(id, config) {
            const canvas = document.querySelector(`#${id}`);
            if (!canvas) {
                return;
            }
            if (typeof Chart === "undefined") {
                this.xn.chartsAvailable = false;
                return;
            }
            this._xnCharts.push(new Chart(canvas, config));
        },

        xnBaseOptions(palette) {
            return {
                responsive: true,
                maintainAspectRatio: false,
                color: palette.ink,
                plugins: {
                    legend: { position: "bottom", labels: { boxWidth: 10, color: palette.ink } },
                },
                scales: {
                    x: { ticks: { color: palette.ink }, grid: { display: false } },
                    y: {
                        beginAtZero: true,
                        ticks: { color: palette.ink },
                        grid: { color: palette.grid },
                    },
                },
            };
        },

        xnRenderCharts() {
            if (!this.xn.permitted || typeof Chart === "undefined") {
                return;
            }
            const palette = xnPalette();
            const base = this.xnBaseOptions(palette);

            const pipeline = this.xn.pipeline;
            if (pipeline.rows && pipeline.rows.length) {
                this.xnChart("xn_pipeline_chart", {
                    type: "bar",
                    data: {
                        labels: pipeline.rows.map((row) => row.label),
                        datasets: [{
                            label: "Applications",
                            data: pipeline.rows.map((row) => row.value),
                            backgroundColor: palette.s1,
                            borderRadius: 4,
                        }],
                    },
                    options: {
                        ...base,
                        indexAxis: "y",
                        plugins: { legend: { display: false } },
                        scales: {
                            x: {
                                beginAtZero: true,
                                ticks: { precision: 0, color: palette.ink },
                                grid: { color: palette.grid },
                            },
                            y: { ticks: { color: palette.ink }, grid: { display: false } },
                        },
                    },
                });
            }

            const utilisation = this.xn.utilisation;
            if (utilisation.tracked) {
                const datasets = [{
                    label: "Hours logged",
                    data: utilisation.logged,
                    backgroundColor: palette.s1,
                    borderRadius: 4,
                }];
                // Same unit as the bars, so this shares their scale.
                if (utilisation.capacity_known) {
                    datasets.push({
                        label: "Capacity (estimate)",
                        data: utilisation.capacity,
                        type: "line",
                        borderColor: palette.s2,
                        backgroundColor: palette.s2,
                        borderDash: [5, 4],
                        borderWidth: 2,
                        pointRadius: 0,
                        fill: false,
                    });
                }
                this.xnChart("xn_utilisation_chart", {
                    type: "bar",
                    data: { labels: utilisation.labels, datasets },
                    options: base,
                });
            }

            const attendance = this.xn.attendance;
            if (attendance.tracked) {
                this.xnChart("xn_attendance_hours_chart", {
                    type: "line",
                    data: {
                        labels: attendance.labels,
                        datasets: [{
                            label: "Hours recorded",
                            data: attendance.hours,
                            borderColor: palette.s1,
                            backgroundColor: palette.s1,
                            borderWidth: 2,
                            tension: 0.3,
                            pointRadius: 3,
                        }],
                    },
                    options: { ...base, plugins: { legend: { display: false } } },
                });
                // Deliberately a second chart, not a second y-axis.
                this.xnChart("xn_attendance_people_chart", {
                    type: "line",
                    data: {
                        labels: attendance.labels,
                        datasets: [{
                            label: "People clocking in",
                            data: attendance.people,
                            borderColor: palette.s2,
                            backgroundColor: palette.s2,
                            borderWidth: 2,
                            tension: 0.3,
                            pointRadius: 3,
                        }],
                    },
                    options: {
                        ...base,
                        plugins: { legend: { display: false } },
                        scales: {
                            ...base.scales,
                            y: {
                                beginAtZero: true,
                                ticks: { precision: 0, color: palette.ink },
                                grid: { color: palette.grid },
                            },
                        },
                    },
                });
            }

            const turnover = this.xn.turnover;
            if (turnover.exits_tracked && turnover.labels && turnover.labels.length) {
                this.xnChart("xn_turnover_chart", {
                    type: "bar",
                    data: {
                        labels: turnover.labels,
                        datasets: [
                            {
                                label: "Joined",
                                data: turnover.joins,
                                backgroundColor: palette.s1,
                                borderRadius: 3,
                            },
                            {
                                label: "Left",
                                data: turnover.exits,
                                backgroundColor: palette.s2,
                                borderRadius: 3,
                            },
                        ],
                    },
                    options: {
                        ...base,
                        scales: {
                            ...base.scales,
                            y: {
                                beginAtZero: true,
                                ticks: { precision: 0, color: palette.ink },
                                grid: { color: palette.grid },
                            },
                        },
                    },
                });
            }
        },
    });
} else {
    console.warn(
        `xn_hr_dashboard: no client action registered under "${ACTION_TAG}" - ` +
        "update ACTION_TAG in xn_dashboard.js."
    );
}
