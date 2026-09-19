# -*- coding: utf-8 -*-
{
    "name": "Auditree AI Assistant",
    "summary": "Answers employee questions in Discuss using xn_ai_core, with "
               "tools that run as the person asking.",
    "description": """
A first, deliberately small assistant, built to exercise the architecture
rather than to be the finished product.

Why it rides OdooBot
--------------------
mail_bot already owns a direct-message channel between every internal user and
a bot partner, plus the hook (_get_answer) that turns a posted message into a
reply. Reusing it means this module is a hook and two tools instead of a bot
identity, a channel provisioner and a systray entry.

The production assistant should have its own partner and its own name, because
"OdooBot" is not the thing Auditree wants employees talking to. That is a
naming and onboarding exercise, not an architectural one, and it is separate
from proving the tool loop works.

The property this module exists to demonstrate
----------------------------------------------
Tools run as the person asking. There is no sudo() in the tool code, so a tool
that reads hr.leave sees exactly the leave records that user is allowed to
see, enforced by Odoo's own record rules rather than by anything written here.
The model is never told who it is talking to and never decides what it may
read; it only chooses which tool to call.

That is the whole security design, and it is why the tool functions take no
employee identifier -- they resolve to the caller's own employee record and
cannot be pointed at anybody else's.

Known limits
------------
* Replies are generated inside the HTTP request that posted the message. That
  is acceptable for a test with a handful of users and is NOT how this should
  ship: a real deployment generates in a worker and pushes the result over the
  bus, so no HTTP worker is held open for the duration of a model call.
* No conversation history is carried between messages. Each question stands
  alone.
    """,
    "version": "17.0.1.0.0",
    "category": "Human Resources",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": [
        "mail_bot",
        "xn_ai_core",
        "hr_holidays",
    ],
    "data": [],
    "assets": {
        "web.assets_backend": [
            "xn_ai_assistant/static/src/scss/xn_ai_launcher.scss",
            "xn_ai_assistant/static/src/js/xn_ai_launcher.js",
            "xn_ai_assistant/static/src/xml/xn_ai_launcher.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
