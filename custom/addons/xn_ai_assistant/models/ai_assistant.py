# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

import json
import logging
import pytz

from datetime import datetime, time, timedelta

_logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3

SYSTEM_PROMPT = (
    "You are the Auditree ERP assistant. You help employees with questions "
    "about their own HR records and company documents.\n"
    "Use the provided tools to look up facts. Never invent a number or a "
    "document: if a tool does not return the information, say you could not "
    "find it.\n"
    "\n"
    "Formatting rules. Write plain text, never markdown: no asterisks, no "
    "square brackets, no numbered markdown links. The interface renders bare "
    "URLs as clickable links by itself.\n"
    "\n"
    "For a normal answer, use one or two short sentences.\n"
    "\n"
    "When reporting documents found by search, write one line per document "
    "in this shape, and nothing else around it:\n"
    "Document name - where it lives\n"
    "https://the-url\n"
    "\n"
    "List at most three. Say plainly if none matched. Do not describe what a "
    "document contains unless the excerpt says so, and never guess from its "
    "title alone.\n"
    "\n"
    "When you state a leave balance, add that the Time Off app is the "
    "authoritative record.\n"
    "\n"
    "When you cannot answer because no tool covers it, say so in one short "
    "sentence and then name what you can help with, drawn from the list "
    "below. Never leave a refusal as a dead end: a person who is told only "
    "'no' stops asking, while one who is told what else is available usually "
    "tries again."
)


class AiAssistant(models.AbstractModel):
    """Tool loop for the Discuss assistant.

    Every method whose name appears in TOOLS is called with the environment of
    the user who asked the question. None of them take an employee identifier,
    and none of them use sudo(): a tool can only ever reach the caller's own
    records, and Odoo's record rules -- not this file -- are what enforce it.
    """

    _name = 'ai.assistant'
    _description = 'AI Assistant'

    # ------------------------------------------------------------------
    # Tool definitions handed to the model
    # ------------------------------------------------------------------

    @api.model
    def _tool_schemas(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_my_profile",
                    "description": "The current user's own employee record: "
                                   "name, job title, department and manager.",
                    "parameters": {"type": "object", "properties": {},
                                   "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_my_leave_balance",
                    "description": "The current user's currently available "
                                   "leave, broken down by leave type. Remaining "
                                   "days already account for approved and "
                                   "pending requests.",
                    "parameters": {"type": "object", "properties": {},
                                   "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_my_assets",
                    "description": "Company equipment currently assigned to "
                                   "the current user: laptops, monitors, "
                                   "headsets and so on, with asset code and "
                                   "recorded condition.",
                    "parameters": {"type": "object", "properties": {},
                                   "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_my_document_expiry",
                    "description": "Expiry dates of the current user's "
                                   "identity documents (passport, visa, work "
                                   "permit, ID), with days remaining. Use for "
                                   "questions about documents expiring or "
                                   "needing renewal.",
                    "parameters": {"type": "object", "properties": {},
                                   "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_my_attendance_summary",
                    "description": "The current user's hours worked this week "
                                   "and whether they are currently checked in "
                                   "or out.",
                    "parameters": {"type": "object", "properties": {},
                                   "required": []},
                },
            },
        ]

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    @api.model
    def _my_employee(self):
        """The caller's own employee record, or an empty recordset.

        Not sudo(): if the user cannot read their own employee record this
        returns nothing and the tool reports that, which is the correct
        outcome. Widening access here would be the bug.
        """
        return self.env['hr.employee'].search(
            [('user_id', '=', self.env.user.id)], limit=1)

    @api.model
    def tool_get_my_profile(self):
        employee = self._my_employee()
        if not employee:
            return {"error": "No employee record is linked to this user."}
        return {
            "name": employee.name,
            "job_title": employee.job_title or None,
            "department": employee.department_id.name or None,
            "manager": employee.parent_id.name or None,
        }

    @api.model
    def tool_get_my_leave_balance(self):
        employee = self._my_employee()
        if not employee:
            return {"error": "No employee record is linked to this user."}

        # Read Odoo's own figures rather than recomputing them. The Time Off
        # dashboard reads exactly these fields, so the two agree by
        # construction instead of by coincidence.
        #
        # This replaces hand-rolled arithmetic that reported roughly five
        # times the real balance: it summed allocations over all time while
        # filtering leave taken to the current year, so expired allocations
        # were counted and the days already spent against them were not. It
        # also ignored allocation validity windows and accruals entirely.
        #
        # virtual_remaining_leaves, not remaining_leaves: the virtual figure
        # also subtracts submitted-but-unapproved requests, which is what
        # someone means when they ask how much leave they have left. Without
        # it the tool invites people to double-book days they have already
        # requested.
        leave_types = self.env['hr.leave.type'].with_context(
            employee_id=employee.id).search([])

        rows = [
            {
                "type": leave_type.name,
                "allocated_days": round(leave_type.max_leaves, 2),
                "taken_days": round(leave_type.leaves_taken, 2),
                "remaining_days": round(
                    leave_type.virtual_remaining_leaves, 2),
            }
            for leave_type in leave_types
            if leave_type.max_leaves or leave_type.leaves_taken
        ]

        if not rows:
            return {"note": "No leave allocations or approved leave found "
                            "for this employee."}

        return {
            "employee": employee.name,
            "leave_types": sorted(rows, key=lambda row: row["type"]),
        }

    @api.model
    def tool_get_my_assets(self):
        """Equipment booked out to the caller.

        Readable without sudo: maintenance.equipment grants access to records
        the user follows, and Odoo subscribes the owner when an item is
        assigned, so an employee can see their own kit and nobody else's.
        """
        employee = self._my_employee()
        if not employee:
            return {"error": "No employee record is linked to this user."}

        equipment = self.env['maintenance.equipment'].search(
            [('employee_id', '=', employee.id)])
        if not equipment:
            return {"note": "No company equipment is currently assigned to "
                            "you."}

        conditions = dict(
            self.env['maintenance.equipment']._fields['xn_condition'].selection)

        return {
            "employee": employee.name,
            "equipment": [
                {
                    "item": item.name,
                    "asset_code": item.xn_asset_code or None,
                    "serial_number": item.serial_no or None,
                    "category": item.category_id.name or None,
                    "condition": conditions.get(item.xn_condition),
                    "assigned_on": str(item.assign_date)
                    if item.assign_date else None,
                }
                for item in equipment
            ],
        }

    @api.model
    def tool_get_my_document_expiry(self):
        """Identity-document expiry dates for the caller.

        The core hr fields (visa, passport, permit, ID) carry
        groups="hr.group_hr_user", so an ordinary employee gets an AccessError
        reading them off hr.employee. They are however on res.users'
        self-readable whitelist, so the caller can read them about themselves
        there. That is the whole reason this reads from two records rather
        than one, and it is what keeps the no-sudo rule intact.

        work_permit_expiration_date is deliberately omitted: it is restricted
        on hr.employee and not exposed on res.users, so it cannot be read
        without widening access.
        """
        employee = self._my_employee()
        if not employee:
            return {"error": "No employee record is linked to this user."}

        user = self.env.user
        today = fields.Date.context_today(self)

        # (label, expiry date, reference number)
        candidates = [
            ("Passport", employee.passport_expiry_date, user.passport_id),
            ("Visa", user.visa_expire, user.visa_no),
            ("Identification", employee.id_expiry_date,
             user.identification_id),
            ("Work permit", None, user.permit_no),
        ]

        documents = []
        for label, expiry, number in candidates:
            if not expiry and not number:
                continue
            entry = {"document": label, "number": number or None,
                     "expires_on": None, "days_remaining": None,
                     "status": "no expiry date recorded"}
            if expiry:
                days = (expiry - today).days
                entry["expires_on"] = str(expiry)
                entry["days_remaining"] = days
                entry["status"] = (
                    "expired" if days < 0
                    else "expires within 30 days" if days <= 30
                    else "expires within 90 days" if days <= 90
                    else "valid")
            documents.append(entry)

        if not documents:
            return {"note": "No identity documents are recorded against your "
                            "employee record. Nothing is stored, so nothing "
                            "can be checked - ask HR to add your passport, "
                            "visa or permit details."}

        return {"employee": employee.name, "documents": documents}

    @api.model
    def tool_get_my_attendance_summary(self):
        """Hours booked this week, and whether the caller is checked in.

        Hours are summed from the caller's own hr.attendance records rather
        than read off hr.employee.hours_today, which carries a groups= on the
        field and is therefore unreadable for an ordinary employee. Attendance
        records themselves are visible to their owner by record rule, so this
        works for everybody without sudo.
        """
        employee = self._my_employee()
        if not employee:
            return {"error": "No employee record is linked to this user."}

        today = fields.Date.context_today(self)
        week_start = today - timedelta(days=today.weekday())

        # check_in is stored in UTC, week_start is a date in the user's own
        # timezone. Converting the boundary rather than comparing naively is
        # what stops Monday morning's hours landing in the previous week.
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        start_utc = tz.localize(
            datetime.combine(week_start, time.min)
        ).astimezone(pytz.UTC).replace(tzinfo=None)

        attendances = self.env['hr.attendance'].search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', fields.Datetime.to_string(start_utc)),
        ])

        # worked_hours is only populated once an entry is checked out, so an
        # open session contributes nothing to the total. Reporting it
        # separately is honest; folding an estimate into the total is not.
        hours = sum(attendances.mapped('worked_hours'))
        checked_in = employee.attendance_state == 'checked_in'

        last_check_in = None
        if checked_in and employee.last_attendance_id.check_in:
            last_check_in = fields.Datetime.context_timestamp(
                self, employee.last_attendance_id.check_in
            ).strftime('%Y-%m-%d %H:%M')

        return {
            "employee": employee.name,
            "week_starting": str(week_start),
            "hours_this_week": round(hours, 2),
            "completed_sessions": len(attendances.filtered('check_out')),
            "currently": "checked in" if checked_in else "checked out",
            "checked_in_since": last_check_in,
            "note": "Hours cover completed sessions only; an open session is "
                    "not counted until you check out."
            if checked_in else None,
        }

    @api.model
    def _run_tool(self, name, arguments):
        """Dispatch one tool call. Unknown names are reported, not raised.

        A model asking for a tool that does not exist is a normal thing to
        handle, not an exception: telling it so lets it correct itself on the
        next round, whereas raising would lose the whole conversation.

        Arguments are filtered against the schema before being passed. The
        model can emit whatever keys it likes, and handing them straight to a
        Python call as **kwargs turns a hallucinated argument name into a
        TypeError -- or, worse, lets a future tool be driven by a parameter
        its schema never advertised.
        """
        schema = next(
            (s for s in self._tool_schemas()
             if s["function"]["name"] == name), None)
        handler = getattr(self, 'tool_' + name, None)
        if schema is None or handler is None:
            return {"error": "No such tool: %s" % name}

        allowed = ((schema["function"].get("parameters") or {})
                   .get("properties") or {})
        kwargs = {key: value for key, value in (arguments or {}).items()
                  if key in allowed}

        try:
            return handler(**kwargs)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("xn_ai_assistant: tool %s failed", name)
            # Deliberately not the exception text: it can name records and
            # models the asker has no business knowing exist.
            return {"error": "That lookup could not be completed."}

    # ------------------------------------------------------------------
    # The loop
    # ------------------------------------------------------------------

    @api.model
    def _system_prompt(self):
        """The static prompt plus a capability list built from the tools.

        Generated rather than written out, so a module that adds a tool also
        updates what the assistant says it can do. A hand-maintained list
        drifts the first time somebody adds a tool and forgets the prompt,
        and the failure is invisible: the assistant simply denies being able
        to do something it can.
        """
        capabilities = "\n".join(
            "- %s" % schema["function"].get("description", "").strip()
            for schema in self._tool_schemas()
            if schema.get("function", {}).get("description"))
        if not capabilities:
            return SYSTEM_PROMPT
        return "%s\n\nWhat you can help with:\n%s" % (
            SYSTEM_PROMPT, capabilities)

    @api.model
    def answer(self, question, history=None):
        """Answer `question` as the current user.

        :param history: prior turns as [{"role", "content"}], oldest first.
            Supplied by the caller rather than stored here, because where a
            conversation lives is a decision for the front end: the launcher
            keeps it in the session, and the Discuss bot has no history at
            all.
        :return: {"text": str, "log_id": int or None}

        Returns a dict rather than a string so the caller can attach feedback
        to the exact call that produced the answer. Without the log id there
        is no way to tell which of a day's requests a thumbs-down refers to.
        """
        messages = [{"role": "system", "content": self._system_prompt()}]
        for turn in (history or []):
            # Only the two roles a conversation is made of. Anything else in
            # the stored history is ignored rather than trusted, so a stray
            # or crafted entry cannot become a system instruction.
            if turn.get('role') in ('user', 'assistant') and turn.get('content'):
                messages.append({"role": turn['role'],
                                 "content": turn['content']})
        messages.append({"role": "user", "content": question})
        service = self.env['ai.service']

        for _round in range(MAX_TOOL_ROUNDS):
            result = service.call(
                messages=messages,
                purpose='hr_assistant',
                tools=self._tool_schemas(),
                max_tokens=500,
            )
            tool_calls = result.get('tool_calls') or []
            if not tool_calls:
                return {"text": (result.get('content') or '').strip(),
                        "log_id": result.get('log_id')}

            messages.append({
                "role": "assistant",
                "content": result.get('content') or None,
                "tool_calls": tool_calls,
            })
            for call in tool_calls:
                function = call.get('function') or {}
                try:
                    arguments = json.loads(function.get('arguments') or '{}')
                except ValueError:
                    arguments = {}
                output = self._run_tool(function.get('name'), arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get('id'),
                    "content": json.dumps(output),
                })

        _logger.warning(
            "xn_ai_assistant: gave up after %d tool rounds for user %s",
            MAX_TOOL_ROUNDS, self.env.user.login)
        return {"text": _("Sorry, I could not work that one out."),
                "log_id": None}
