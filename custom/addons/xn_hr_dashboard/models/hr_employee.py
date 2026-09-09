# -*- coding: utf-8 -*-
"""Dashboard endpoints for the Auditree HR dashboard.

Design rules this file follows:

1. One definition per metric. A tile's count and the list it opens come from
   the same domain, produced by ``_xn_domains()``. There is no second copy of
   any domain in JS or in an action XML record.
2. A freshness flag is measured over the same window as the figure it guards.
   ``attendance_tracked`` computed over all time is what lets a "Today" row
   print four zeros three weeks after check-in stopped.
3. Every date window is bounded at both ends. A "last 30 days" figure with no
   upper bound silently counts future-dated records.
4. Nothing here writes.
5. sudo() is used only where the vendor already does it (org-wide counts), and
   every such method checks the HR-manager group first.
6. No SQL is built from user input. Where a column name varies with which
   modules are installed, it is chosen from the fixed tuples below and never
   from anything a caller supplies.

ASCII only - see CLAUDE.md section 3.3.
"""

import logging
from datetime import datetime, timedelta

import pytz
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError

_logger = logging.getLogger(__name__)

MANAGER_GROUP = "hr.group_hr_manager"

# Candidate columns, in preference order. Only names from these tuples ever
# reach a SQL string; nothing here is caller-supplied.
HIRE_COLUMNS = ("joining_date",)
EXIT_COLUMNS = ("departure_date", "resign_date")

# Attendance older than this makes the "Today" row report staleness rather
# than render zeros.
ATTENDANCE_STALE_DAYS = 3

# Model and label per tile key, so click-through can stay generic.
TILE_MODELS = {
    "present_now": ("hr.attendance", "Currently checked in"),
    "checked_in_today": ("hr.attendance", "Check-ins today"),
    "late_today": ("hr.attendance", "Arrived after schedule"),
    "on_leave_today": ("hr.leave", "On leave today"),
    "leave_to_approve": ("hr.leave", "Leave requests to approve"),
    "allocation_to_approve": ("hr.leave.allocation", "Allocations to approve"),
    "applicants_open": ("hr.applicant", "Live applications"),
    "timesheets_30d": ("account.analytic.line", "Timesheet lines, last 30 days"),
}


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @api.model
    def _xn_check_manager(self):
        """Org-wide figures are for HR managers.

        The client gates on the same group before calling, so reaching this
        raise means something called the endpoint directly.
        """
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError("This dashboard section is for HR managers.")

    @api.model
    def _xn_tz(self):
        return pytz.timezone(
            self.env.user.tz or self.env.company.resource_calendar_id.tz or "UTC"
        )

    @api.model
    def _xn_utc_bounds(self, day_from, day_to=None):
        """Local calendar days -> naive UTC datetimes, the way the ORM stores them."""
        tz = self._xn_tz()
        day_to = day_to or day_from
        start = tz.localize(datetime.combine(day_from, datetime.min.time()))
        end = tz.localize(
            datetime.combine(day_to + timedelta(days=1), datetime.min.time())
        )
        return (
            start.astimezone(pytz.utc).replace(tzinfo=None),
            end.astimezone(pytz.utc).replace(tzinfo=None),
        )

    @api.model
    def _xn_hire_expr(self):
        """SQL expression for an employee's start date.

        create_date is the last resort on purpose: 14 of the 60 employees on
        this database have no joining_date, and dropping them understates the
        attrition denominator rather than merely omitting a bar.
        """
        parts = [c for c in HIRE_COLUMNS if c in self._fields]
        parts.append("e.create_date::date")
        cols = ", ".join(p if p.startswith("e.") else "e." + p for p in parts)
        return "COALESCE(%s)" % cols

    @api.model
    def _xn_exit_expr(self):
        """SQL expression for an employee's exit date, or None if untracked.

        Standard departure_date comes first and the vendor's resign_date
        second: on this database departure_date is populated on all 32
        archived employees and resign_date on none, which is exactly why the
        vendor's own attrition chart reads zero.
        """
        parts = ["e." + c for c in EXIT_COLUMNS if c in self._fields]
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        return "COALESCE(%s)" % ", ".join(parts)

    @api.model
    def _xn_late_grace(self):
        param = self.env["ir.config_parameter"].sudo()
        try:
            return int(param.get_param("xn_hr_dashboard.late_grace_minutes", 15))
        except (TypeError, ValueError):
            _logger.warning(
                "xn_hr_dashboard.late_grace_minutes is not a whole number; using 15"
            )
            return 15

    @api.model
    def _xn_attendance_last(self):
        """Most recent check-in, or None. Bounded read, not a full count."""
        self.env.cr.execute("SELECT max(check_in) FROM hr_attendance")
        row = self.env.cr.fetchone()
        return row and row[0] or None

    # ------------------------------------------------------------------
    # single source of truth for tile domains
    # ------------------------------------------------------------------

    @api.model
    def _xn_domains(self):
        today = fields.Date.context_today(self)
        day_start, day_end = self._xn_utc_bounds(today)
        thirty_days = today - timedelta(days=30)
        return {
            "present_now": [
                ("check_in", ">=", day_start),
                ("check_out", "=", False),
            ],
            "checked_in_today": [
                ("check_in", ">=", day_start),
                ("check_in", "<", day_end),
            ],
            "late_today": [("id", "in", self._xn_late_attendance_ids())],
            "on_leave_today": [
                ("state", "=", "validate"),
                ("date_from", "<", day_end),
                ("date_to", ">=", day_start),
            ],
            "leave_to_approve": [("state", "in", ("confirm", "validate1"))],
            "allocation_to_approve": [("state", "in", ("confirm", "validate1"))],
            # Odoo archives refused applicants, not hired ones, so active
            # alone would count people who already have the job.
            "applicants_open": [
                ("active", "=", True),
                ("date_closed", "=", False),
            ],
            # Bounded at both ends. Without the upper bound this counts
            # future-dated lines - there are 26 of them on this database.
            "timesheets_30d": [
                ("project_id", "!=", False),
                ("date", ">=", thirty_days),
                ("date", "<=", today),
            ],
        }

    @api.model
    def _xn_late_attendance_ids(self):
        """Today's check-ins later than that employee's own schedule + grace.

        Done in Python over today's rows only, because the threshold is
        per-employee: it comes from their working schedule, not one company
        clock.
        """
        today = fields.Date.context_today(self)
        day_start, day_end = self._xn_utc_bounds(today)
        attendances = self.env["hr.attendance"].sudo().search([
            ("check_in", ">=", day_start),
            ("check_in", "<", day_end),
        ])
        if not attendances:
            return []
        tz = self._xn_tz()
        grace = self._xn_late_grace() / 60.0
        weekday = str(today.weekday())
        late_ids = []
        for att in attendances:
            calendar = (
                att.employee_id.resource_calendar_id
                or self.env.company.resource_calendar_id
            )
            if not calendar:
                continue
            starts = calendar.attendance_ids.filtered(
                lambda a: a.dayofweek == weekday
            ).mapped("hour_from")
            if not starts:
                continue
            local = pytz.utc.localize(att.check_in).astimezone(tz)
            actual = local.hour + local.minute / 60.0
            if actual > min(starts) + grace:
                late_ids.append(att.id)
        return late_ids

    # ------------------------------------------------------------------
    # tiles
    # ------------------------------------------------------------------

    @api.model
    def xn_dashboard_tiles(self):
        self._xn_check_manager()
        env = self.env
        today = fields.Date.context_today(self)
        domains = self._xn_domains()

        counts = {}
        for key, (model, _label) in TILE_MODELS.items():
            counts[key] = env[model].sudo().search_count(domains[key])

        month_start = today.replace(day=1)
        m_start, m_end = self._xn_utc_bounds(month_start, today)
        env.cr.execute(
            """
            SELECT COALESCE(SUM(worked_hours), 0)
              FROM hr_attendance
             WHERE check_in >= %s AND check_in < %s AND check_out IS NOT NULL
            """,
            (m_start, m_end),
        )
        month_hours = env.cr.fetchone()[0] or 0.0

        ts_groups = env["account.analytic.line"].sudo().read_group(
            domains["timesheets_30d"], ["unit_amount"], []
        )
        timesheet_hours = (ts_groups and ts_groups[0].get("unit_amount")) or 0.0

        # Freshness measured over the window the Today row actually covers,
        # not over the whole table.
        last_attendance = self._xn_attendance_last()
        stale_days = None
        if last_attendance:
            stale_days = (today - last_attendance.date()).days
        attendance_current = (
            stale_days is not None and stale_days <= ATTENDANCE_STALE_DAYS
        )

        return {
            "headcount": env["hr.employee"].sudo().search_count([("active", "=", True)]),
            "present_now": counts["present_now"],
            "checked_in_today": counts["checked_in_today"],
            "late_today": counts["late_today"],
            "on_leave_today": counts["on_leave_today"],
            "leave_to_approve": counts["leave_to_approve"],
            "allocation_to_approve": counts["allocation_to_approve"],
            "applicants_open": counts["applicants_open"],
            "month_hours": round(month_hours, 1),
            "timesheet_hours_30d": round(timesheet_hours, 1),
            "timesheet_lines_30d": counts["timesheets_30d"],
            "attendance_current": attendance_current,
            "attendance_ever": bool(last_attendance),
            "attendance_last": (
                fields.Date.to_string(last_attendance.date()) if last_attendance else False
            ),
            "attendance_stale_days": stale_days,
        }

    @api.model
    def xn_open_tile(self, key):
        """Click-through. Same domain the count came from."""
        self._xn_check_manager()
        if key not in TILE_MODELS:
            return False
        model, label = TILE_MODELS[key]
        return {
            "type": "ir.actions.act_window",
            "name": label,
            "res_model": model,
            "view_mode": "list,form",
            "domain": self._xn_domains()[key],
            "context": {"create": False},
            "target": "current",
        }

    # ------------------------------------------------------------------
    # charts
    # ------------------------------------------------------------------

    @api.model
    def xn_headcount_by_department(self):
        """Active headcount per department, with the unassigned reported."""
        self._xn_check_manager()
        groups = self.env["hr.employee"].sudo().read_group(
            [("active", "=", True)], ["id"], ["department_id"]
        )
        rows, unassigned = [], 0
        for grp in groups:
            if grp["department_id"]:
                rows.append({
                    "label": grp["department_id"][1],
                    "value": grp["department_id_count"],
                })
            else:
                unassigned = grp["department_id_count"]
        rows.sort(key=lambda r: r["value"], reverse=True)
        return {
            "rows": rows,
            "unassigned": unassigned,
            "total": sum(r["value"] for r in rows) + unassigned,
        }

    @api.model
    def get_dept_employee(self):
        """Override: the vendor donut counted archived staff.

        The vendor query has no ``active`` filter and inner-joins
        hr_department, so on this database it reports 52 people against 28
        active, and the 7 with no department vanish rather than showing as a
        slice. Return shape is kept identical so the vendor's d3 pie keeps
        working untouched.
        """
        data = self.xn_headcount_by_department()
        result = [{"label": r["label"], "value": r["value"]} for r in data["rows"]]
        if data["unassigned"]:
            result.append({"label": "No department", "value": data["unassigned"]})
        return result

    @api.model
    def xn_recruitment_pipeline(self):
        """Live applications by stage, in stage order, instead of one total."""
        self._xn_check_manager()
        domain = self._xn_domains()["applicants_open"]
        groups = self.env["hr.applicant"].sudo().read_group(domain, ["id"], ["stage_id"])
        rows = []
        for grp in groups:
            # hr.applicant expands the stage groupby, so empty stages come
            # back too. Four zero-length bars under five applicants is noise,
            # not a funnel.
            if not grp["stage_id_count"]:
                continue
            stage = grp["stage_id"]
            rows.append({
                "id": stage and stage[0] or 0,
                "label": stage and stage[1] or "No stage",
                "value": grp["stage_id_count"],
            })
        sequences = {
            s.id: s.sequence
            for s in self.env["hr.recruitment.stage"].sudo().search([])
        }
        rows.sort(key=lambda r: sequences.get(r["id"], 9999))
        return {"rows": rows, "total": sum(r["value"] for r in rows)}

    @api.model
    def xn_timesheet_utilisation(self, months=6):
        """Project hours logged per month, against calendar capacity.

        Capacity is an estimate: it applies one company calendar to everyone
        rather than each employee's own, which is fine for a trend and not
        fine for billing. When it cannot be computed the client draws hours
        alone rather than a capacity line of zeros.
        """
        self._xn_check_manager()
        today = fields.Date.context_today(self)
        calendar = self.env.company.resource_calendar_id
        headcount = self.env["hr.employee"].sudo().search_count([("active", "=", True)])
        tz = self._xn_tz()

        labels, logged, capacity = [], [], []
        for offset in range(months - 1, -1, -1):
            first = today.replace(day=1) - relativedelta(months=offset)
            last = first + relativedelta(months=1, days=-1)
            groups = self.env["account.analytic.line"].sudo().read_group(
                [
                    ("project_id", "!=", False),
                    ("date", ">=", first),
                    ("date", "<=", last),
                ],
                ["unit_amount"], [],
            )
            hours = (groups and groups[0].get("unit_amount")) or 0.0
            labels.append(first.strftime("%b %Y"))
            logged.append(round(hours, 1))

            month_capacity = 0.0
            if calendar and headcount:
                start = tz.localize(datetime.combine(first, datetime.min.time()))
                end = tz.localize(datetime.combine(last, datetime.max.time()))
                # Narrow catch on purpose: a bare except here would report
                # zero capacity for a real bug and the chart would lie.
                try:
                    month_capacity = calendar.get_work_hours_count(start, end) * headcount
                except (AttributeError, TypeError, ValueError):
                    _logger.warning(
                        "xn_hr_dashboard: could not read capacity from calendar %s",
                        calendar.id, exc_info=True,
                    )
                    month_capacity = 0.0
            capacity.append(round(month_capacity, 1))

        return {
            "labels": labels,
            "logged": logged,
            "capacity": capacity,
            "tracked": any(logged),
            "capacity_known": any(capacity),
        }

    @api.model
    def xn_attendance_trend(self, months=6):
        """Recorded hours and distinct people per month.

        Returned together but charted separately: hours and headcount are
        different units, and putting them on two y-scales in one plot invents
        a correlation the data does not contain.
        """
        self._xn_check_manager()
        today = fields.Date.context_today(self)
        first = today.replace(day=1) - relativedelta(months=months - 1)
        start, end = self._xn_utc_bounds(first, today)
        self.env.cr.execute(
            """
            SELECT to_char(check_in, 'Mon YYYY')     AS label,
                   date_trunc('month', check_in)     AS bucket,
                   COALESCE(SUM(worked_hours), 0)    AS hours,
                   COUNT(DISTINCT employee_id)       AS people
              FROM hr_attendance
             WHERE check_in >= %s AND check_in < %s AND check_out IS NOT NULL
          GROUP BY label, bucket
          ORDER BY bucket
            """,
            (start, end),
        )
        rows = self.env.cr.dictfetchall()
        return {
            "labels": [r["label"] for r in rows],
            "hours": [round(r["hours"], 1) for r in rows],
            "people": [r["people"] for r in rows],
            "tracked": bool(rows),
        }

    @api.model
    def xn_turnover(self, months=12):
        """Joiners, leavers and attrition, in one query.

        Attrition is returned as a single period figure rather than a monthly
        line: with a handful of movements a year, a per-month rate is noise
        with a decimal point on it.
        """
        self._xn_check_manager()
        hire = self._xn_hire_expr()
        exit_expr = self._xn_exit_expr()

        if not exit_expr:
            return {
                "labels": [], "joins": [], "exits": [],
                "total_joins": 0, "total_exits": 0,
                "attrition": 0.0, "exits_tracked": False,
                "exit_fields": [],
            }

        # hire and exit_expr are built from the module-level tuples above and
        # never from anything a caller passes; months is bound as a parameter.
        query = """
            WITH months AS (
                SELECT generate_series(
                    date_trunc('month', CURRENT_DATE) - (INTERVAL '1 month' * %s),
                    date_trunc('month', CURRENT_DATE),
                    INTERVAL '1 month'
                )::date AS m
            )
            SELECT to_char(m, 'Mon YYYY') AS label,
                   m AS bucket,
                   (SELECT count(*) FROM hr_employee e
                     WHERE date_trunc('month', {hire}) = m)      AS joined,
                   (SELECT count(*) FROM hr_employee e
                     WHERE date_trunc('month', {exit}) = m)      AS departed,
                   (SELECT count(*) FROM hr_employee e
                     WHERE {hire} <= (m + INTERVAL '1 month' - INTERVAL '1 day')::date
                       AND ({exit} IS NULL
                            OR {exit} > (m + INTERVAL '1 month' - INTERVAL '1 day')::date)
                   ) AS headcount
              FROM months
          ORDER BY bucket
        """.format(hire=hire, exit=exit_expr)
        self.env.cr.execute(query, (months - 1,))
        rows = self.env.cr.dictfetchall()

        joins = [r["joined"] for r in rows]
        exits = [r["departed"] for r in rows]
        headcounts = [r["headcount"] for r in rows if r["headcount"]]
        avg_headcount = (sum(headcounts) / len(headcounts)) if headcounts else 0

        self.env.cr.execute(
            "SELECT count(*) FROM hr_employee e WHERE {exit} IS NOT NULL".format(
                exit=exit_expr
            )
        )
        exits_tracked = bool(self.env.cr.fetchone()[0])

        return {
            "labels": [r["label"] for r in rows],
            "joins": joins,
            "exits": exits,
            "total_joins": sum(joins),
            "total_exits": sum(exits),
            "attrition": (
                round(sum(exits) / avg_headcount * 100, 1) if avg_headcount else 0.0
            ),
            "exits_tracked": exits_tracked,
            "exit_fields": [c for c in EXIT_COLUMNS if c in self._fields],
        }

    @api.model
    def xn_data_health(self):
        """Which gaps are making the other panels thin."""
        self._xn_check_manager()
        has_joining = "joining_date" in self._fields
        self.env.cr.execute(
            """
            SELECT count(*) FILTER (WHERE active AND birthday IS NULL)      AS no_birthday,
                   count(*) FILTER (WHERE active AND department_id IS NULL) AS no_department,
                   count(*) FILTER (WHERE active AND job_id IS NULL)        AS no_job,
                   count(*) FILTER (WHERE active)                           AS active
              FROM hr_employee
            """
        )
        health = self.env.cr.dictfetchone()

        no_hire_date = 0
        if has_joining:
            self.env.cr.execute(
                "SELECT count(*) FROM hr_employee WHERE joining_date IS NULL"
            )
            no_hire_date = self.env.cr.fetchone()[0]

        exit_expr = self._xn_exit_expr()
        no_exit_date = 0
        if exit_expr:
            self.env.cr.execute(
                "SELECT count(*) FROM hr_employee e "
                "WHERE NOT e.active AND {exit} IS NULL".format(exit=exit_expr)
            )
            no_exit_date = self.env.cr.fetchone()[0]

        health.update({
            "no_hire_date": no_hire_date,
            "archived_without_exit_date": no_exit_date,
        })
        return health

    # ------------------------------------------------------------------
    # "Your team" - full replacement of the vendor's get_upcoming
    # ------------------------------------------------------------------

    @api.model
    def get_upcoming(self):
        """Birthdays, upcoming events and announcements.

        Replaces hrms_dashboard's version rather than extending it, because
        all three of its queries are wrong. The tuple shapes are kept exactly
        so the vendor's OWL templates keep rendering; what changes is:

        * birthdays exclude archived employees, and no longer require a job
          position (an inner join on hr_job hid 6 active employees here);
        * announcements lead with announcement_reason, which the model labels
          "Title", instead of name, which is the sequence code;
        * events left-join their venue instead of requiring one;
        * the announcement query is parameterised rather than interpolated;
        * announcements are scoped to the allowed companies.
        """
        cr = self.env.cr
        lang = self.env.context.get("lang") or "en_US"
        employee = self.env["hr.employee"].search(
            [("user_id", "=", self.env.uid)], limit=1
        )

        cr.execute(
            """
            WITH params AS (
                SELECT to_char(
                           (date_trunc('year', now()) + INTERVAL '1 year'
                            - INTERVAL '1 day')::date, 'DDD')::int AS total_days,
                       to_char(now(), 'DDD')::int                  AS today_doy
            )
            SELECT he.id,
                   he.name,
                   to_char(he.birthday, 'FMMonth DD'),
                   COALESCE(hj.name ->> %(lang)s, hj.name ->> 'en_US', ''),
                   he.birthday,
                   p.total_days,
                   ((to_char(he.birthday, 'DDD')::int - p.today_doy)
                     + p.total_days) %% p.total_days AS dif
              FROM hr_employee he
              CROSS JOIN params p
              LEFT JOIN hr_job hj ON hj.id = he.job_id
             WHERE he.active
               AND he.birthday IS NOT NULL
               AND ((to_char(he.birthday, 'DDD')::int - p.today_doy)
                     + p.total_days) %% p.total_days BETWEEN 0 AND 15
          ORDER BY dif
             LIMIT 20
            """,
            {"lang": lang},
        )
        birthday = cr.fetchall()

        cr.execute(
            """
            SELECT COALESCE(e.name ->> %(lang)s, e.name ->> 'en_US') AS name,
                   e.date_begin,
                   e.date_end,
                   rp.name AS location
              FROM event_event e
              LEFT JOIN res_partner rp ON rp.id = e.address_id
             WHERE e.date_begin >= now()
               AND (e.company_id IS NULL OR e.company_id IN %(companies)s)
          ORDER BY e.date_begin
             LIMIT 10
            """,
            {"lang": lang, "companies": tuple(self.env.companies.ids) or (0,)},
        )
        event = cr.fetchall()

        # One parameterised statement covers all four visibility cases. A null
        # department or job simply makes that branch never match.
        cr.execute(
            """
            SELECT ha.announcement_reason, ha.name, ha.date_start, ha.date_end
              FROM hr_announcement ha
              LEFT JOIN hr_employee_announcements hea ON hea.announcement = ha.id
              LEFT JOIN hr_department_announcements hda ON hda.announcement = ha.id
              LEFT JOIN hr_job_position_announcements hpa ON hpa.announcement = ha.id
             WHERE ha.state = 'approved'
               AND ha.date_start <= now()::date
               AND ha.date_end >= now()::date
               AND (ha.company_id IS NULL OR ha.company_id IN %(companies)s)
               AND (ha.is_announcement = TRUE
                    OR (ha.announcement_type = 'employee'
                        AND hea.employee = %(employee)s)
                    OR (ha.announcement_type = 'department'
                        AND hda.department = %(department)s)
                    OR (ha.announcement_type = 'job_position'
                        AND hpa.job_position = %(job)s))
          GROUP BY ha.id
          ORDER BY ha.date_start DESC
             LIMIT 20
            """,
            {
                "companies": tuple(self.env.companies.ids) or (0,),
                "employee": employee.id or 0,
                "department": employee.department_id.id or 0,
                "job": employee.job_id.id or 0,
            },
        )
        announcement = [
            (row[0], self._xn_announcement_meta(row[1], row[2], row[3]))
            for row in cr.fetchall()
        ]

        return {
            "birthday": birthday,
            "event": event,
            "announcement": announcement,
        }

    @api.model
    def _xn_announcement_meta(self, code, date_start, date_end):
        """Sequence code and validity, for the line under the title."""
        bits = []
        if code:
            bits.append(code)
        if date_start and date_end:
            bits.append("%s to %s" % (
                format(date_start, "%d %b %Y"),
                format(date_end, "%d %b %Y"),
            ))
        return " - ".join(bits)

    # ------------------------------------------------------------------
    # Work anniversaries
    # ------------------------------------------------------------------

    @api.model
    def xn_work_anniversaries(self, days=30):
        """Employees whose joining anniversary falls within the next `days`.

        The vendor dashboard generates exactly one date panel by itself -
        birthdays. Anniversaries are the other date every HR calendar wants and
        the only item on the announcements checklist that cannot reasonably be
        typed by hand, so it is computed here rather than left to someone
        remembering.

        `joining_date` comes from xn_auditree_erp, which this module does not
        depend on. A missing field returns tracked=False so the panel can say
        why it is empty instead of rendering nothing.

        Date arithmetic uses `date + N * interval '1 year'` rather than
        make_date: make_date raises on a 29 February joining date in a non-leap
        year, while the interval form folds it back to the 28th.
        """
        if "joining_date" not in self._fields:
            return {"tracked": False, "window": days, "rows": []}

        lang = self.env.context.get("lang") or "en_US"
        self.env.cr.execute(
            """
            WITH base AS (
                SELECT he.id,
                       he.name,
                       he.joining_date,
                       COALESCE(hj.name ->> %(lang)s, hj.name ->> 'en_US', '') AS job,
                       (he.joining_date
                        + ((EXTRACT(YEAR FROM CURRENT_DATE)
                            - EXTRACT(YEAR FROM he.joining_date))::int
                           * INTERVAL '1 year'))::date AS this_year
                  FROM hr_employee he
                  LEFT JOIN hr_job hj ON hj.id = he.job_id
                 WHERE he.active
                   AND he.joining_date IS NOT NULL
                   AND he.joining_date <= CURRENT_DATE
                   AND (he.company_id IS NULL OR he.company_id IN %(companies)s)
            ),
            upcoming AS (
                SELECT b.id, b.name, b.job, b.joining_date,
                       CASE WHEN b.this_year >= CURRENT_DATE THEN b.this_year
                            ELSE (b.joining_date
                                  + ((EXTRACT(YEAR FROM CURRENT_DATE)
                                      - EXTRACT(YEAR FROM b.joining_date) + 1)::int
                                     * INTERVAL '1 year'))::date
                       END AS next_date
                  FROM base b
            )
            SELECT id,
                   name,
                   job,
                   to_char(next_date, 'FMDD Mon'),
                   (EXTRACT(YEAR FROM next_date)
                    - EXTRACT(YEAR FROM joining_date))::int AS years,
                   (next_date - CURRENT_DATE)::int AS days_away
              FROM upcoming
             WHERE next_date - CURRENT_DATE BETWEEN 0 AND %(days)s
               AND (EXTRACT(YEAR FROM next_date)
                    - EXTRACT(YEAR FROM joining_date))::int >= 1
          ORDER BY days_away, name
             LIMIT 20
            """,
            {
                "lang": lang,
                "companies": tuple(self.env.companies.ids) or (0,),
                "days": days,
            },
        )
        rows = [
            {
                "id": row[0],
                "name": row[1],
                "job": row[2],
                "date": row[3],
                "years": row[4],
                "days_away": row[5],
            }
            for row in self.env.cr.fetchall()
        ]
        return {"tracked": True, "window": days, "rows": rows}

    # ------------------------------------------------------------------
    # Attendance
    # ------------------------------------------------------------------

    @api.model
    def xn_attendance_toggle(self):
        """Check the calling user in or out, and report the resulting state.

        Replaces hrms_dashboard's attendance_manual, which cannot work:

        * it browses hr.employee with request.session.uid, which is a *user*
          id, so it toggles whichever employee happens to share that id with
          the user rather than the caller's own record;
        * it has no @api.model decorator, so call_kw expects a list of ids and
          raises IndexError before any of that runs;
        * it returns a recordset, which does not survive JSON serialisation;
        * it reads request.geoip.city.name, which raises when no GeoIP
          database is installed.

        The employee is resolved strictly by user_id, so a caller can only ever
        toggle their own attendance. sudo() covers the attendance write, not
        the lookup.
        """
        employee = self.sudo().search([("user_id", "=", self.env.uid)], limit=1)
        if not employee:
            return {"ok": False, "reason": "no_employee"}

        # Core accepts no geo information and simply omits those columns. The
        # vendor's geoip dict adds nothing here and raises without a GeoIP db.
        employee._attendance_action_change()

        return {
            "ok": True,
            "checked_in": employee.attendance_state == "checked_in",
        }
