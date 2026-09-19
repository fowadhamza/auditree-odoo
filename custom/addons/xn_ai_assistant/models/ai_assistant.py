# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

import json
import logging

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
