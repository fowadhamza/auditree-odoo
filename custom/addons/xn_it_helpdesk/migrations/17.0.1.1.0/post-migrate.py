# -*- coding: utf-8 -*-
"""End of the production trial: give everyone "Raise IT Tickets".

The trial installed with only three logins in the group (see
TRIAL_REQUESTER_LOGINS in __init__.py). Going live means every internal
employee except shared/system accounts (xn_auditree_erp's employee_type
'system' - shared mailbox logins like it@) - those are blocked from raising
tickets anyway (see _xn_is_shared_account), so leaving them out of the group
avoids showing them an app they'd get a UserError from using.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        SELECT res_id FROM ir_model_data
        WHERE module = 'xn_it_helpdesk' AND name = 'group_xn_helpdesk_requester'
    """)
    row = cr.fetchone()
    if not row:
        _logger.warning(
            "xn_it_helpdesk: group_xn_helpdesk_requester not found; "
            "skipping the company-wide rollout."
        )
        return
    group_id = row[0]

    cr.execute("""
        INSERT INTO res_groups_users_rel (gid, uid)
        SELECT DISTINCT %s, ru.id
          FROM res_users ru
          JOIN hr_employee he ON he.user_id = ru.id
         WHERE ru.active = true
           AND ru.share = false
           AND COALESCE(he.employee_type, '') != 'system'
           AND NOT EXISTS (
               SELECT 1 FROM res_groups_users_rel r
                WHERE r.gid = %s AND r.uid = ru.id
           )
     RETURNING uid
    """, (group_id, group_id))
    added = cr.fetchall()
    _logger.info(
        "xn_it_helpdesk: granted Raise IT Tickets to %s more user(s) for the company-wide rollout.",
        len(added),
    )
