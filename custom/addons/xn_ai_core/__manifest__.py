# -*- coding: utf-8 -*-
{
    "name": "Auditree AI Core",
    "summary": "Shared plumbing for AI features: provider adapter, job logging, "
               "spend controls and a kill switch.",
    "description": """
Every outbound AI call in this database goes through this module.

Why a shared core
-----------------
Feature modules (an HR assistant, forecast commentary, document extraction)
all need the same things: somewhere to put the endpoint configuration, a
record of what was sent and what it cost, a ceiling on spend, and a way to
turn the whole thing off without a deployment. Building that once means a
feature module contains only its own logic.

No provider SDK
---------------
Azure OpenAI is a REST endpoint with an api-key header, so this calls it with
`requests`, which Odoo already depends on. Adding `openai` or `azure-ai-*`
would mean a new package in the production venv, and the venv rebuild is the
deploy step that has actually broken this server before. A dict and a POST
avoid that entirely.

Provider adapters
-----------------
`_call_azure` is the only adapter today. The dispatch in `_dispatch` keeps the
shape for a second one, because the provider decision is reversible and should
stay that way -- model names are configuration, not code.

Safety properties this module is responsible for
------------------------------------------------
* Aadhaar and PAN numbers never leave the database. `_redact` masks them on
  every outbound payload as a backstop; tools are separately expected to pass
  named field lists rather than whole records.
* No call is made when the kill switch is off or the monthly token budget is
  exhausted.
* Prompt and response bodies are NOT stored by default. Turning that on makes
  ai.request.log a second copy of personal data under different access rules,
  so it is opt-in and gated on a setting.

What this module deliberately does not do
-----------------------------------------
It does not queue. Batch callers should drive it from `ir.cron`; an
interactive caller (a chat reply) should run it in a worker and push the
result over the bus. Baking one of those in would make the other awkward.
    """,
    "version": "17.0.1.0.0",
    "category": "Technical",
    "author": "Auditree",
    "license": "LGPL-3",
    "depends": [
        "base",
        "base_setup",
    ],
    "data": [
        "security/xn_ai_core_security.xml",
        "security/ir.model.access.csv",
        "views/ai_request_log_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
