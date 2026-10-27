# -*- coding: utf-8 -*-
import logging

from . import models
from . import controllers

_logger = logging.getLogger(__name__)

# Seeded as the catch-all approver when the module is installed. Matched on
# the user's login or email, case-insensitively; nothing happens if absent.
DEFAULT_APPROVER_EMAIL = 'ghazala.nishath@auditree.com'


def _seed_default_rule(env):
    """Create one rule (any amount -> Nishath) so the flow works on install.

    Rules are configuration, so this only runs when there are none; edit or
    replace it under Purchase > Configuration > Approval Rules.
    """
    Rule = env['xn.purchase.approval.rule']
    if Rule.with_context(active_test=False).search_count([]):
        return
    user = env['res.users'].search([
        '|', ('login', '=ilike', DEFAULT_APPROVER_EMAIL),
        ('email', '=ilike', DEFAULT_APPROVER_EMAIL),
    ], limit=1)
    if not user:
        _logger.info("xn_purchase_approval: no user %s, no default approval "
                     "rule created", DEFAULT_APPROVER_EMAIL)
        return
    Rule.create({
        'name': 'All purchases',
        'min_amount': 0.0,
        'approver_id': user.id,
    })
    _logger.info("xn_purchase_approval: default approval rule created for %s",
                 user.login)


def post_init_hook(env):
    _seed_default_rule(env)
