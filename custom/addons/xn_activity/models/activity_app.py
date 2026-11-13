# -*- coding: utf-8 -*-
import re

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

CATEGORIES = [
    ('productive', 'Productive'),
    ('neutral', 'Neutral'),
    ('unproductive', 'Unproductive'),
    ('unclassified', 'Unclassified'),
]

_APP_NAME_RE = re.compile(r'[^a-z0-9._-]')


def clean_app_name(raw):
    """Process name as the agent sends it -> the key stored in Odoo."""
    name = _APP_NAME_RE.sub('', (raw or '').strip().lower())
    if name.endswith('.exe'):
        name = name[:-4]
    return name[:64] or 'unknown'


class XnActivityApp(models.Model):
    _name = 'xn.activity.app'
    _description = 'Activity App'
    _order = 'category, display_label, name'
    _rec_name = 'display_label'

    name = fields.Char(string='Process Name', required=True, index=True,
                       help="Process name without .exe, lower case, as the "
                            "agent reports it (e.g. excel, chrome).")
    friendly_name = fields.Char()
    display_label = fields.Char(compute='_compute_display_label', store=True)
    category = fields.Selection(CATEGORIES, required=True,
                                default='unclassified', index=True)
    rule_ids = fields.One2many('xn.activity.app.rule', 'app_id',
                               string='Department Overrides')
    idle_as_active = fields.Boolean(
        string='Count Idle as Active',
        help="Time with this app in front but no keyboard or mouse input "
             "counts as active, not idle: meetings, reading long documents. "
             "Applies to past days too.")

    _sql_constraints = [
        ('name_uniq', 'UNIQUE(name)', 'This process name already exists.'),
    ]

    @api.depends('name', 'friendly_name')
    def _compute_display_label(self):
        for app in self:
            app.display_label = app.friendly_name or app.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name'):
                vals['name'] = clean_app_name(vals['name'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('name'):
            vals['name'] = clean_app_name(vals['name'])
        old = {app.id: (app.category, app.idle_as_active) for app in self}
        res = super().write(vals)
        if 'category' in vals or 'idle_as_active' in vals:
            changed = self.filtered(
                lambda a: old.get(a.id) != (a.category, a.idle_as_active))
            if changed:
                self.env['xn.activity.day']._xn_recompute_for_apps(changed)
        return res

    @api.model
    def _xn_get_or_create(self, names):
        """Map raw process names -> app ids, creating Unclassified apps."""
        clean = {raw: clean_app_name(raw) for raw in names}
        wanted = set(clean.values())
        apps = self.sudo().search([('name', 'in', list(wanted))])
        by_name = {a.name: a.id for a in apps}
        missing = wanted - set(by_name)
        if missing:
            new = self.sudo().create([{'name': n} for n in sorted(missing)])
            by_name.update({a.name: a.id for a in new})
        return {raw: by_name[c] for raw, c in clean.items()}


class XnActivityAppRule(models.Model):
    _name = 'xn.activity.app.rule'
    _description = 'Activity App Department Override'
    _order = 'app_id, department_id'

    app_id = fields.Many2one('xn.activity.app', required=True,
                             ondelete='cascade', index=True)
    department_id = fields.Many2one('hr.department', required=True,
                                    ondelete='cascade')
    category = fields.Selection(CATEGORIES, required=True)

    _sql_constraints = [
        ('app_department_uniq', 'UNIQUE(app_id, department_id)',
         'This app already has an override for this department.'),
    ]

    @api.constrains('category')
    def _check_category(self):
        if any(r.category == 'unclassified' for r in self):
            raise ValidationError(_("An override must pick a category."))

    def _xn_touch(self):
        Day = self.env['xn.activity.day']
        for rule in self:
            Day._xn_recompute_for_apps(rule.app_id, rule.department_id)

    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)
        rules._xn_touch()
        return rules

    def write(self, vals):
        before = [(r.app_id, r.department_id) for r in self]
        res = super().write(vals)
        Day = self.env['xn.activity.day']
        for app, dept in before:
            Day._xn_recompute_for_apps(app, dept)
        self._xn_touch()
        return res

    def unlink(self):
        before = [(r.app_id, r.department_id) for r in self]
        res = super().unlink()
        Day = self.env['xn.activity.day']
        for app, dept in before:
            Day._xn_recompute_for_apps(app, dept)
        return res
