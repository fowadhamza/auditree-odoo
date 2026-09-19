# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

import json
import logging

_logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3

SYSTEM_PROMPT = (
    "You are the Auditree ERP assistant. You help employees with questions "
    "about their own HR records.\n"
    "Use the provided tools to look up facts. Never invent a number: if a "
    "tool does not return the information, say you could not find it.\n"
    "Keep answers to one or two short sentences. Do not use markdown.\n"
    "When you state a leave balance, add that the Time Off app is the "
    "authoritative record."
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
                    "description": "The current user's remaining leave, broken "
                                   "down by leave type, for the current year.",
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

        year_start = fields.Date.context_today(self).replace(month=1, day=1)

        allocations = self.env['hr.leave.allocation'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
        ])
        taken = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('request_date_from', '>=', year_start),
        ])

        balances = {}
        for allocation in allocations:
            name = allocation.holiday_status_id.name
            balances.setdefault(name, {"allocated": 0.0, "taken": 0.0})
            balances[name]["allocated"] += allocation.number_of_days or 0.0
        for leave in taken:
            name = leave.holiday_status_id.name
            balances.setdefault(name, {"allocated": 0.0, "taken": 0.0})
            balances[name]["taken"] += leave.number_of_days or 0.0

        if not balances:
            return {"note": "No leave allocations or approved leave found "
                            "for this employee."}

        return {
            "employee": employee.name,
            "leave_types": [
                {
                    "type": name,
                    "allocated_days": round(values["allocated"], 2),
                    "taken_days": round(values["taken"], 2),
                    "remaining_days": round(
                        values["allocated"] - values["taken"], 2),
                }
                for name, values in sorted(balances.items())
            ],
        }

    @api.model
    def _run_tool(self, name, arguments):
        """Dispatch one tool call. Unknown names are reported, not raised.

        A model asking for a tool that does not exist is a normal thing to
        handle, not an exception: telling it so lets it correct itself on the
        next round, whereas raising would lose the whole conversation.
        """
        handler = getattr(self, 'tool_' + name, None)
        if handler is None or name not in [
                schema["function"]["name"] for schema in self._tool_schemas()]:
            return {"error": "No such tool: %s" % name}
        try:
            return handler()
        except Exception as exc:  # noqa: BLE001
            _logger.exception("xn_ai_assistant: tool %s failed", name)
            # Deliberately not the exception text: it can name records and
            # models the asker has no business knowing exist.
            return {"error": "That lookup could not be completed."}

    # ------------------------------------------------------------------
    # The loop
    # ------------------------------------------------------------------

    @api.model
    def answer(self, question):
        """Answer `question` as the current user. Returns plain text."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
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
                return (result.get('content') or '').strip()

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
        return _("Sorry, I could not work that one out.")
