# -*- coding: utf-8 -*-
"""Figures behind the asset register dashboard.

Everything the dashboard draws is computed here rather than in the client, so
what is drawn and what is counted cannot drift apart. One call returns the
whole payload: the register is small (low hundreds of rows) and a single round
trip is simpler to reason about than nine.

The register is read in full and aggregated in Python rather than with
read_group. At this size the query cost is irrelevant and the grouping rules
here -- age bands, value concentration, the attention list -- are clearer as
plain code than as nine separate grouped reads.
"""
from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import models, api, fields, _
from odoo.exceptions import AccessError

import logging

_logger = logging.getLogger(__name__)

# Condition keys in the order they should read on screen: best first, so the
# bar always runs from healthy to broken regardless of what the data holds.
CONDITION_ORDER = ['very_good', 'good', 'average', 'bad', 'not_working']

AGE_BANDS = [
    ('0-1y', 0, 1),
    ('1-2y', 1, 2),
    ('2-3y', 2, 3),
    ('3-5y', 3, 5),
    ('5y+', 5, None),
]


class MaintenanceEquipment(models.Model):
    _inherit = 'maintenance.equipment'

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @api.model
    def _xn_dashboard_guard(self):
        """The dashboard aggregates the whole register, including cost.

        Record rules would otherwise let an ordinary internal user see totals
        assembled from equipment they happen to follow, which is a different
        number from the one the register is meant to report and invites the
        reader to treat it as the company total.
        """
        if not self.env.user.has_group(
                'xn_asset_register.group_asset_register_manager'):
            raise AccessError(
                _("The asset dashboard is limited to Asset Register Managers."))

    @api.model
    def _xn_condition_labels(self):
        return dict(
            self._fields['xn_condition']._description_selection(self.env))

    # ------------------------------------------------------------------
    # the payload
    # ------------------------------------------------------------------
    @api.model
    def xn_asset_dashboard_data(self):
        self._xn_dashboard_guard()

        records = self.sudo().search([])
        today = fields.Date.context_today(self)
        labels = self._xn_condition_labels()

        total_value = sum(r.cost or 0.0 for r in records)

        # --- headline -------------------------------------------------
        assigned = records.filtered(lambda r: r.employee_id)
        at_location = records.filtered(
            lambda r: not r.employee_id and r.location)
        unaccounted = records - assigned - at_location
        broken = records.filtered(
            lambda r: r.xn_condition in ('bad', 'not_working'))
        with_leavers = assigned.filtered(lambda r: not r.employee_id.active)

        # --- condition ------------------------------------------------
        by_condition = defaultdict(lambda: {'count': 0, 'value': 0.0})
        for r in records:
            key = r.xn_condition or 'unknown'
            by_condition[key]['count'] += 1
            by_condition[key]['value'] += r.cost or 0.0
        condition = []
        for key in CONDITION_ORDER + ['unknown']:
            if key not in by_condition:
                continue
            condition.append({
                'key': key,
                'label': labels.get(key, _('Not recorded')),
                'count': by_condition[key]['count'],
                'value': round(by_condition[key]['value'], 2),
            })

        # --- category -------------------------------------------------
        by_category = defaultdict(lambda: {'count': 0, 'value': 0.0})
        for r in records:
            name = r.category_id.name or _('Uncategorised')
            by_category[name]['count'] += 1
            by_category[name]['value'] += r.cost or 0.0
        category = sorted(
            ({'label': k, 'count': v['count'], 'value': round(v['value'], 2)}
             for k, v in by_category.items()),
            key=lambda d: (-d['value'], -d['count'], d['label']))

        # --- holders --------------------------------------------------
        by_holder = defaultdict(lambda: {'count': 0, 'value': 0.0,
                                         'active': True, 'id': 0})
        for r in assigned:
            emp = r.employee_id
            entry = by_holder[emp.name or _('Unnamed')]
            entry['count'] += 1
            entry['value'] += r.cost or 0.0
            entry['active'] = emp.active
            entry['id'] = emp.id
        holders = sorted(
            ({'label': k, 'count': v['count'], 'value': round(v['value'], 2),
              'active': v['active'], 'id': v['id']}
             for k, v in by_holder.items()),
            key=lambda d: (-d['count'], -d['value'], d['label']))

        # --- locations ------------------------------------------------
        by_location = defaultdict(lambda: {'count': 0, 'value': 0.0})
        for r in at_location:
            by_location[r.location]['count'] += 1
            by_location[r.location]['value'] += r.cost or 0.0
        locations = sorted(
            ({'label': k, 'count': v['count'], 'value': round(v['value'], 2)}
             for k, v in by_location.items()),
            key=lambda d: -d['count'])

        # --- purchases by year ----------------------------------------
        by_year = defaultdict(lambda: {'count': 0, 'value': 0.0})
        for r in records:
            if not r.effective_date:
                continue
            by_year[r.effective_date.year]['count'] += 1
            by_year[r.effective_date.year]['value'] += r.cost or 0.0
        years = [{'label': str(y), 'count': v['count'],
                  'value': round(v['value'], 2)}
                 for y, v in sorted(by_year.items())]

        # --- age bands ------------------------------------------------
        bands = []
        for label, lo, hi in AGE_BANDS:
            upper = today - relativedelta(years=lo)
            lower = today - relativedelta(years=hi) if hi else date.min
            # lo/up are bound as defaults on purpose: a bare closure over the
            # loop variables would give every band the last band's bounds.
            hit = records.filtered(
                lambda r, lo=lower, up=upper: r.effective_date
                and lo < r.effective_date <= up)
            bands.append({
                'label': label,
                'count': len(hit),
                'value': round(sum(h.cost or 0.0 for h in hit), 2),
            })

        # --- things a person should act on ----------------------------
        attention = [
            {'key': 'not_working', 'label': _('Not working or bad'),
             'count': len(broken)},
            {'key': 'leavers', 'label': _('Held by employees who have left'),
             'count': len(with_leavers)},
            {'key': 'no_condition', 'label': _('Condition not recorded'),
             'count': len(records.filtered(lambda r: not r.xn_condition))},
            {'key': 'no_code', 'label': _('No asset code'),
             'count': len(records.filtered(lambda r: not r.xn_asset_code))},
            {'key': 'unaccounted', 'label': _('Neither assigned nor located'),
             'count': len(unaccounted)},
        ]

        return {
            'currency': self.env.company.currency_id.symbol or '',
            'headline': {
                'total': len(records),
                'total_value': round(total_value, 2),
                'assigned': len(assigned),
                'at_location': len(at_location),
                'broken': len(broken),
                'leavers': len(with_leavers),
            },
            'condition': condition,
            'category': category,
            'holders': holders,
            'locations': locations,
            'years': years,
            'age_bands': bands,
            'attention': [a for a in attention if a['count']],
        }

    # ------------------------------------------------------------------
    # drill-down
    # ------------------------------------------------------------------
    @api.model
    def xn_asset_dashboard_open(self, key, value=None):
        """Open the equipment list filtered to whatever was clicked.

        A figure nobody can click is a figure nobody can check. Every domain
        here mirrors exactly one of the counts above.
        """
        self._xn_dashboard_guard()

        domains = {
            'all': [],
            'assigned': [('employee_id', '!=', False)],
            'at_location': [('employee_id', '=', False),
                            ('location', '!=', False)],
            'not_working': [('xn_condition', 'in', ['bad', 'not_working'])],
            'leavers': [('employee_id.active', '=', False)],
            'no_condition': [('xn_condition', '=', False)],
            'no_code': [('xn_asset_code', '=', False)],
            'unaccounted': [('employee_id', '=', False),
                            ('location', '=', False)],
            'category': [('category_id.name', '=', value)],
            'condition': [('xn_condition', '=', value)],
            'holder': [('employee_id', '=', value)],
            'location': [('location', '=', value)],
            'year': [],
        }
        domain = list(domains.get(key, []))
        if key == 'year' and value:
            domain = [('effective_date', '>=', '%s-01-01' % value),
                      ('effective_date', '<=', '%s-12-31' % value)]
        if key == 'condition' and value == 'unknown':
            domain = [('xn_condition', '=', False)]

        return {
            'type': 'ir.actions.act_window',
            'name': _('Assets'),
            'res_model': 'maintenance.equipment',
            'view_mode': 'tree,form',
            'domain': domain,
            'target': 'current',
            'context': {'search_default_filter': 1},
        }
