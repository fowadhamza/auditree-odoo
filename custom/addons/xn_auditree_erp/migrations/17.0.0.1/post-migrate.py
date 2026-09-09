# -*- coding: utf-8 -*-
"""Parent the allowance categories under ALW.

The GROSS and NET salary rules total `categories.BASIC + categories.ALW`, and
Odoo's `_sum_salary_rule_category` rolls a rule's amount up through its
category's parents only. These ten categories were created in the UI with no
parent, so every allowance sitting in one -- House Rent Allowance above all --
was silently dropped from gross and net pay: a March 2025 slip totalling 41.00
in earnings printed a gross and a net of 16.00.

Parenting them under ALW makes the stock rules total correctly. Payslips
already computed keep their old lines; they have to be recomputed by hand
(Compute Sheet), which is deliberate -- this must not silently rewrite slips
that have been paid or posted.
"""
import logging

_logger = logging.getLogger(__name__)

# Listed explicitly rather than picked up as "every category without a parent",
# so the structural categories (BASIC, ALW, GROSS, DED, NET, COMP) cannot be
# swept up by accident.
ALLOWANCE_CATEGORY_CODES = (
    'HRA', 'DA', 'Travel', 'Meal', 'Medical',
    'Other', 'CA', 'PPA', 'LTA', 'Special',
)


def migrate(cr, version):
    """Set parent_id = ALW on the allowance categories that lack a parent."""
    if not version:
        return

    cr.execute("SELECT id FROM hr_salary_rule_category WHERE code = %s", ('ALW',))
    row = cr.fetchone()
    if not row:
        _logger.warning(
            "No salary rule category with code ALW; leaving the allowance "
            "categories unparented."
        )
        return
    alw_id = row[0]

    cr.execute("""
        UPDATE hr_salary_rule_category
           SET parent_id = %s
         WHERE code IN %s
           AND parent_id IS NULL
           AND id != %s
     RETURNING code
    """, (alw_id, ALLOWANCE_CATEGORY_CODES, alw_id))
    updated = [code for (code,) in cr.fetchall()]

    if updated:
        _logger.info(
            "Parented %s salary rule categories under ALW: %s",
            len(updated), ', '.join(sorted(updated)),
        )
    else:
        _logger.info("Allowance categories already parented; nothing to do.")
