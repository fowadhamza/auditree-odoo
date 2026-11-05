# -*- coding: utf-8 -*-
import logging

from markupsafe import Markup, escape

from odoo import models, fields, _
from odoo.tools import format_date

_logger = logging.getLogger(__name__)


class ProjectTask(models.Model):
    _inherit = 'project.task'

    xn_jl_ticket_id = fields.Many2one(
        'helpdesk.ticket', string='IT Ticket', copy=False, readonly=True)

    def _xn_jl_after_create(self):
        res = super()._xn_jl_after_create()
        for task in self.filtered('xn_jl_step_id.xn_raise_ticket'):
            task._xn_jl_raise_ticket()
        return res

    def _xn_jl_ticket_vals(self):
        self.ensure_one()
        checklist = self.xn_jl_checklist_id
        employee = checklist.employee_id
        when = format_date(self.env, checklist.date)
        if checklist.process == 'join':
            name = _("New joiner: %(name)s - laptop, company ID and accounts "
                     "(joining %(date)s)", name=employee.name, date=when)
            intro = _("Please prepare the laptop and create the company ID, "
                      "Microsoft 365 and Odoo accounts for this joiner.")
        else:
            name = _("Leaver: %(name)s - disable access and recover assets "
                     "(last working day %(date)s)", name=employee.name, date=when)
            if checklist.exit_type == 'immediate':
                intro = _("Immediate termination: disable all access today and "
                          "start the asset return.")
            else:
                intro = _("Please disable all access at close of office hours on "
                          "the last working day and start the asset return.")
        rows = [
            (_('Employee'), employee.name),
            (_('Job title'), employee.job_title or employee.job_id.name or '-'),
            (_('Department'), employee.department_id.name or '-'),
            (_('Reporting manager'), employee.parent_id.name or '-'),
            (_('Joining date') if checklist.process == 'join'
             else _('Last working day'), when),
        ]
        body = Markup('<p>%s</p><ul>%s</ul>') % (
            intro,
            Markup('').join(Markup('<li><b>%s:</b> %s</li>') % (label, value)
                            for label, value in rows))
        hr = self.env['xn.jl.role']._xn_user('hr') or self.env.user
        category = self.env.ref('xn_it_helpdesk.category_access_request',
                                raise_if_not_found=False)
        return {
            'name': name,
            'description': body,
            'partner_id': hr.partner_id.id,
            'partner_name': hr.name,
            'partner_email': hr.email,
            'category_id': category.id if category else False,
            'priority': '2' if checklist.exit_type == 'immediate' else '1',
        }

    def _xn_jl_raise_ticket(self):
        """Raise the IT ticket for this step and mark the step done."""
        self.ensure_one()
        ticket = self.env['helpdesk.ticket'].sudo().create(self._xn_jl_ticket_vals())
        self.sudo().write({'xn_jl_ticket_id': ticket.id})
        link = Markup('<a href="#" data-oe-model="helpdesk.ticket" data-oe-id="%s">%s</a>') % (
            ticket.id, ticket.number or ticket.name)
        note = escape(_("IT ticket raised: %s")) % link
        self.sudo().message_post(body=note, message_type='comment',
                                 subtype_xmlid='mail.mt_note')
        self.xn_jl_checklist_id.sudo().message_post(
            body=note, message_type='comment', subtype_xmlid='mail.mt_note')
        self.sudo().write({'state': '1_done'})
        _logger.info("xn_joiner_leaver_helpdesk: ticket %s raised for task %s",
                     ticket.id, self.id)
