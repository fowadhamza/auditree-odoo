# -*- coding: utf-8 -*-
from odoo import models, fields, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    xn_jl_checklist_ids = fields.One2many(
        'xn.jl.checklist', 'employee_id', string='Joiner/Leaver Checklists',
        groups='hr.group_hr_user')
    xn_jl_checklist_count = fields.Integer(
        compute='_compute_xn_jl_checklist_count', groups='hr.group_hr_user')

    def _compute_xn_jl_checklist_count(self):
        data = self.env['xn.jl.checklist']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        counts = {employee.id: count for employee, count in data}
        for employee in self:
            employee.xn_jl_checklist_count = counts.get(employee.id, 0)

    def _xn_jl_start(self, process):
        self.ensure_one()
        context = {
            'default_employee_id': self.id,
            'default_process': process,
        }
        if process == 'join':
            # Only a future joining date: an existing employee's is their
            # original hire date.
            joining = self._fields.get('joining_date') and self.joining_date
            if joining and joining >= fields.Date.context_today(self):
                context['default_date'] = joining
        return {
            'type': 'ir.actions.act_window',
            'name': _('Start Joining Checklist') if process == 'join'
            else _('Start Exit Checklist'),
            'res_model': 'xn.jl.checklist',
            'view_mode': 'form',
            # The web client needs 'views'; without it the button does nothing.
            'views': [(False, 'form')],
            'target': 'new',
            'context': context,
        }

    def action_xn_jl_start_join(self):
        return self._xn_jl_start('join')

    def action_xn_jl_start_leave(self):
        return self._xn_jl_start('leave')

    def action_xn_jl_view_checklists(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'xn_joiner_leaver.action_xn_jl_checklist')
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'default_employee_id': self.id}
        return action
