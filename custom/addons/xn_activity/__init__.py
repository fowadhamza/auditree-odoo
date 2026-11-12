# -*- coding: utf-8 -*-
import secrets

from . import models
from . import controllers


def post_init_hook(env):
    """Create the API key on first install. Agent Setup shows and rotates it."""
    params = env['ir.config_parameter'].sudo()
    if not params.get_param('xn_activity.api_key'):
        params.set_param('xn_activity.api_key', secrets.token_urlsafe(32))
