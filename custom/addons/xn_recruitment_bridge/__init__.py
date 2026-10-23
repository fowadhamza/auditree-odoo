# -*- coding: utf-8 -*-
import logging
import secrets

from . import controllers

_logger = logging.getLogger(__name__)

TOKEN_PARAM = 'xn_recruitment_bridge.api_token'


def post_init_hook(env):
    """Generate the shared secret at install time.

    Shipping a default token in a data file would put the production secret
    in git and make every install of this module share one value. Generating
    it here means the secret exists only in the database it protects.

    An existing value is never overwritten, so re-running -u on the module
    does not silently break a configured WordPress end.
    """
    params = env['ir.config_parameter'].sudo()
    if params.get_param(TOKEN_PARAM):
        _logger.info("xn_recruitment_bridge: API token already set, leaving it alone")
        return
    params.set_param(TOKEN_PARAM, secrets.token_urlsafe(32))
    _logger.info(
        "xn_recruitment_bridge: generated an API token. Read it from Settings > "
        "Technical > System Parameters (%s) and give it to the WordPress end.",
        TOKEN_PARAM,
    )
