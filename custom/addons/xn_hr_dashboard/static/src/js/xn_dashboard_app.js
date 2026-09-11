/** @odoo-module **/
/**
 * The Auditree HR dashboard.
 *
 * This is a replacement client action, not a patch. It renders its own markup
 * and reuses the vendor's Python endpoints plus this module's xn_* ones, so
 * hrms_dashboard stays installed for its data layer while none of its
 * templates or its stylesheet are ever rendered.
 *
 * Two deliberate departures from the vendor component:
 *
 *  1. No Chart.js. Every chart here is laid out from numbers computed in this
 *     file and drawn with CSS boxes or a hand-built SVG path. Odoo 17 does not
 *     put Chart.js in web.assets_backend, so the vendor's canvases depend on a
 *     loadBundle that fails silently and leaves them blank. Removing the
 *     dependency removes the failure mode.
 *  2. Every figure is shaped here, not in the template. Templates hold no
 *     arithmetic, so what is drawn and what is counted cannot drift apart.
 *
 * Odoo 16 differences: client actions take `props` validation differently and
 * useService("user") is `session` there.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

/** Leave-chart geometry, in the SVG's own viewBox units. */
const CHART = { x0: 40, x1: 305, yTop: 16, yBottom: 94 };

function percent(value, total) {
    if (!total || total <= 0) {
        return 0;
    }
    return Math.max(0, Math.min(100, (value / total) * 100));
}

function round(value, places = 0) {
    const factor = 10 ** places;
    return Math.round((Number(value) || 0) * factor) / factor;
}

/** Server dates arrive as strings; show something readable or the raw value. */
function readableDate(value) {
    if (!value) {
        return "";
    }
    const parsed = new Date(String(value).replace(" ", "T"));
    if (Number.isNaN(parsed.getTime())) {
        return String(value);
    }
    return parsed.toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
    });
}

/** "in 4 days" / "today" / "tomorrow", from a whole number of days. */
function inDays(days) {
    const value = Number(days);
    if (!Number.isFinite(value)) {
        return "";
    }
    if (value <= 0) {
        return "today";
    }
    if (value === 1) {
        return "tomorrow";
    }
    return `in ${value} days`;
}

export class XnHrDashboard extends Component {
    static template = "xn_hr_dashboard.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.user = useService("user");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            isManager: false,
            employee: null,
            team: { birthdays: [], events: [], announcements: [] },
            anniversaries: { tracked: false, window: 30, rows: [] },
            leave: null,
            org: null,
        });

        onWillStart(() => this.load());
    }

    /**
     * Employee photos come from the image controller, never a data URI.
     *
     * An employee with no photo still has image_1920 populated, but with
     * Odoo's generated placeholder, which is an SVG document. Wrapping that in
     * "data:image/png;base64," produces a broken image, which is what the
     * vendor dashboard does. /web/image serves the right mime type, falls back
     * to the placeholder on its own, and is cached by the browser.
     */
    avatarUrl(employeeId) {
        return `/web/image?model=hr.employee&field=avatar_128&id=${employeeId}`;
    }

    /** One failed endpoint must not blank the page, so every call is caught. */
    async call(method, args = []) {
        try {
            return await this.orm.call("hr.employee", method, args);
        } catch (error) {
            console.warn(`xn_hr_dashboard: ${method} failed`, error);
            return null;
        }
    }

    async load() {
        this.state.isManager = await this.user.hasGroup("hr.group_hr_manager");

        const [details, upcoming, anniversaries, leaveTrend] = await Promise.all([
            this.call("xn_user_details"),
            this.call("xn_upcoming"),
            this.call("xn_work_anniversaries"),
            this.call("xn_leave_trend", [6]),
        ]);

        this.state.employee = this.shapeEmployee(details);
        this.state.team = this.shapeTeam(upcoming);
        this.state.anniversaries = anniversaries || {
            tracked: false,
            window: 30,
            rows: [],
        };
        this.state.leave = this.shapeLeave(leaveTrend);

        if (this.state.isManager) {
            const [tiles, health, pipeline, utilisation, attendance, turnover, departments] =
                await Promise.all([
                    this.call("xn_dashboard_tiles"),
                    this.call("xn_data_health"),
                    this.call("xn_recruitment_pipeline"),
                    this.call("xn_timesheet_utilisation", [6]),
                    this.call("xn_attendance_trend", [6]),
                    this.call("xn_turnover", [12]),
                    this.call("xn_headcount_by_department"),
                ]);
            this.state.org = this.shapeOrg({
                tiles,
                health,
                pipeline,
                utilisation,
                attendance,
                turnover,
                departments,
            });
        }

        this.state.loading = false;
    }

    // ------------------------------------------------------------------
    // Shaping. Everything the template renders is computed here.
    // ------------------------------------------------------------------

    shapeEmployee(row) {
        if (!row) {
            return null;
        }
        // Figures are grouped in thousands here rather than in the template,
        // so 18432 reads as 18,432 without the template doing any formatting.
        const figure = (value) => Number(value || 0).toLocaleString();

        return {
            id: row.id,
            name: row.name || "",
            job: row.job || "",
            department: row.department || "",
            checkedIn: Boolean(row.checked_in),
            figures: [
                { key: "payslips", label: "Payslips", value: figure(row.payslips) },
                { key: "timesheets", label: "Timesheets", value: figure(row.timesheets) },
                { key: "contracts", label: "Contracts", value: figure(row.contracts) },
                { key: "broad", label: "Broad factor", value: figure(row.broad_factor) },
            ],
        };
    }

    shapeTeam(upcoming) {
        const data = upcoming || {};
        return {
            // Absent modules are reported as such, so an empty Events panel
            // can say "not installed" rather than "nothing scheduled".
            eventsTracked: data.events_tracked !== false,
            announcementsTracked: data.announcements_tracked !== false,
            birthdays: (data.birthday || []).map((row) => ({
                id: row[0],
                name: row[1],
                date: row[2],
                job: row[3] || "",
                away: inDays(row[6]),
            })),
            events: (data.event || []).map((row) => ({
                name: row[0],
                from: readableDate(row[1]),
                venue: row[3] || "",
            })),
            announcements: (data.announcement || []).map((row) => ({
                title: (row[0] || "").trim(),
                meta: row[1] || "",
            })),
        };
    }

    /**
     * The leave line, as an SVG path in CHART's coordinate space.
     *
     * The scale is built from the data, and every tick label names a value the
     * chart actually reaches, so the axis cannot disagree with the line.
     */
    shapeLeave(rows) {
        if (!rows || !rows.length) {
            return null;
        }
        const values = rows.map((row) => Number(row.days) || 0);
        const labels = rows.map((row) => String(row.label || "").split(" ")[0]);
        const max = Math.max(1, ...values);
        const span = CHART.yBottom - CHART.yTop;
        const step = rows.length > 1 ? (CHART.x1 - CHART.x0) / (rows.length - 1) : 0;

        const points = values.map((value, index) => ({
            x: round(CHART.x0 + step * index, 1),
            y: round(CHART.yBottom - (value / max) * span, 1),
            value,
            label: labels[index],
            last: index === values.length - 1,
        }));

        const line = points
            .map((point, index) => `${index ? "L" : "M"}${point.x} ${point.y}`)
            .join(" ");

        const ticks = [];
        const tickValues = max >= 2 ? [max, Math.round(max / 2), 0] : [max, 0];
        for (const value of [...new Set(tickValues)]) {
            ticks.push({
                value,
                y: round(CHART.yBottom - (value / max) * span, 1),
            });
        }

        return {
            points,
            ticks,
            line,
            area: `${line} L${CHART.x1} ${CHART.yBottom} L${CHART.x0} ${CHART.yBottom} Z`,
            total: round(values.reduce((sum, value) => sum + value, 0), 1),
            empty: values.every((value) => value === 0),
        };
    }

    shapeOrg({ tiles, health, pipeline, utilisation, attendance, turnover, departments }) {
        const t = tiles || {};
        const org = {
            headcount: t.headcount || 0,
            attendanceCurrent: Boolean(t.attendance_current),
            attendanceEver: Boolean(t.attendance_ever),
            attendanceLast: readableDate(t.attendance_last),
            attendanceStaleDays: t.attendance_stale_days || 0,
            today: [
                { label: "Currently checked in", value: t.present_now || 0, key: "present_now" },
                { label: "On leave", value: t.on_leave_today || 0, key: "on_leave_today" },
                { label: "Arrived after schedule", value: t.late_today || 0, key: "late_today" },
            ],
            monthHours: round(t.month_hours || 0, 1),
            decisions: [
                {
                    key: "leave_to_approve",
                    value: t.leave_to_approve || 0,
                    label: "Leave requests",
                    hint: "waiting on you",
                },
                {
                    key: "allocation_to_approve",
                    value: t.allocation_to_approve || 0,
                    label: "Leave allocations",
                    hint: "waiting on you",
                },
                {
                    key: "applicants_open",
                    value: t.applicants_open || 0,
                    label: "Live applications",
                    hint: "still open",
                },
            ],
            departments: [],
            utilisation: null,
            attendance: null,
            pipeline: null,
            turnover: null,
            gaps: [],
        };

        // xn_headcount_by_department keeps the unassigned separate rather than
        // dropping them; they are shown as a final, visually distinct row.
        const deptData = departments || { rows: [], unassigned: 0 };
        const deptRows = (deptData.rows || []).map((row) => ({
            label: row.label,
            value: row.value,
            unassigned: false,
        }));
        if (deptData.unassigned) {
            deptRows.push({
                label: "No department",
                value: deptData.unassigned,
                unassigned: true,
            });
        }
        const deptMax = Math.max(1, ...deptRows.map((row) => row.value || 0));
        org.departments = deptRows.map((row) => ({
            ...row,
            width: round(percent(row.value, deptMax), 1),
        }));

        if (utilisation && utilisation.tracked) {
            org.utilisation = {
                capacityKnown: Boolean(utilisation.capacity_known),
                columns: (utilisation.labels || []).map((label, index) => {
                    const logged = (utilisation.logged || [])[index] || 0;
                    const capacity = (utilisation.capacity || [])[index] || 0;
                    return {
                        label: String(label).split(" ")[0],
                        logged: round(logged),
                        capacity: round(capacity),
                        height: round(percent(logged, capacity), 1),
                        share: Math.round(percent(logged, capacity)),
                    };
                }),
            };
        }

        if (attendance && attendance.tracked) {
            const hours = attendance.hours || [];
            const max = Math.max(1, ...hours);
            org.attendance = {
                columns: (attendance.labels || []).map((label, index) => ({
                    label: String(label).split(" ")[0],
                    hours: round(hours[index] || 0),
                    people: (attendance.people || [])[index] || 0,
                    height: round(percent(hours[index] || 0, max), 1),
                })),
            };
        }

        if (pipeline && pipeline.rows && pipeline.rows.length) {
            org.pipeline = {
                total: pipeline.total || 0,
                rows: pipeline.rows.map((row, index) => ({
                    label: row.label,
                    value: row.value,
                    width: round(percent(row.value, pipeline.total), 1),
                    tone: row.id ? `xn_seg_${(index % 3) + 1}` : "xn_seg_none",
                })),
            };
        }

        if (turnover && turnover.exits_tracked) {
            const joins = turnover.joins || [];
            const exits = turnover.exits || [];
            const max = Math.max(1, ...joins, ...exits);
            org.turnover = {
                totalJoins: turnover.total_joins || 0,
                totalExits: turnover.total_exits || 0,
                attrition: turnover.attrition || 0,
                months: (turnover.labels || []).map((label, index) => ({
                    label: String(label).split(" ")[0],
                    joins: joins[index] || 0,
                    exits: exits[index] || 0,
                    joinHeight: round(percent(joins[index] || 0, max), 1),
                    exitHeight: round(percent(exits[index] || 0, max), 1),
                })),
            };
        }

        const h = health || {};
        const active = h.active || 0;
        const gapRows = [
            { count: h.no_hire_date, what: "No joining date, so no anniversary and no tenure" },
            { count: h.no_birthday, what: "No date of birth, so no birthday and no age" },
            { count: h.no_department, what: "No department, so missing from the split above" },
            { count: h.no_job, what: "No job position" },
        ];
        org.gaps = gapRows
            .filter((row) => row.count)
            .map((row) => ({
                what: row.what,
                count: row.count,
                active,
                width: round(percent(row.count, active), 1),
            }));

        return org;
    }

    // ------------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------------

    /** The tile's count and the list it opens come from one server-side domain. */
    async openTile(key) {
        const action = await this.call("xn_open_tile", [key]);
        if (action) {
            this.actionService.doAction(action);
        }
    }

    openRecords(model, name, domain) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            domain,
            views: [
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
        });
    }

    openFigure(key) {
        const employee = this.state.employee;
        if (!employee) {
            return;
        }
        if (key === "payslips") {
            this.openRecords("hr.payslip", "My Payslips", [["employee_id", "=", employee.id]]);
        } else if (key === "contracts") {
            this.openRecords("hr.contract", "My Contracts", [["employee_id", "=", employee.id]]);
        } else if (key === "timesheets") {
            this.openRecords("account.analytic.line", "My Timesheets", [
                ["project_id", "!=", false],
                ["user_id", "=", this.user.userId],
            ]);
        }
    }

    /**
     * Check in or out. Uses this module's endpoint, not the vendor's
     * attendance_manual, which toggles the wrong employee. See
     * xn_attendance_toggle in models/hr_employee.py.
     */
    async toggleAttendance() {
        const result = await this.call("xn_attendance_toggle");
        if (!result || !result.ok) {
            const reason =
                result && result.reason === "no_employee"
                    ? "Your user is not linked to an employee, so attendance cannot be recorded."
                    : "Attendance could not be recorded.";
            this.notification.add(reason, { type: "danger" });
            return;
        }
        this.state.employee.checkedIn = result.checked_in;
        this.notification.add(result.checked_in ? "Checked in." : "Checked out.", {
            type: "success",
        });
    }
}

registry.category("actions").add("xn_hr_dashboard", XnHrDashboard);
