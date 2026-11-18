# -*- coding: utf-8 -*-
"""Settings kept in ir.config_parameter, with their defaults.

Agent Setup (xn.activity.setup) edits them; everything else reads them
through get_settings() so a missing parameter always falls back to the
documented default.
"""

DEFAULTS = {
    'productive_target': 6.0,        # hours per day
    'idle_minutes': 5,
    'retention_days': 180,           # raw 5-minute slots
    'summary_retention_days': 730,   # daily summaries
    'key_grace_days': 14,
    'digest_to': '',                 # empty = HR Managers' emails
    'alert_to': '',                  # empty = same as the digest
}

MIN_RETENTION_DAYS = 7
AGENT_VERSION = '1.2'


def _num(value, default, cast):
    try:
        return cast(value)
    except (TypeError, ValueError):
        return default


def get_settings(env):
    params = env['ir.config_parameter'].sudo()
    out = {}
    for key, default in DEFAULTS.items():
        raw = params.get_param('xn_activity.%s' % key)
        if isinstance(default, str):
            out[key] = raw or default
        else:
            out[key] = _num(raw, default, type(default)) if raw else default
    out['retention_days'] = max(out['retention_days'], MIN_RETENTION_DAYS)
    out['summary_retention_days'] = max(out['summary_retention_days'],
                                        out['retention_days'])
    return out
