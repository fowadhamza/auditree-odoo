# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo.tools.translate import _
from datetime import datetime, timedelta, date, time
from dateutil.relativedelta import relativedelta
from odoo import tools, api
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo import api, fields, models, _
import logging
from odoo.osv import  osv
from odoo import SUPERUSER_ID
from odoo.exceptions import UserError, ValidationError

from datetime import datetime
from datetime import timedelta

class crm_lead(models.Model):
    """ CRM Lead Case """
    _inherit = "crm.lead"


    
class crm_task_wizard(models.TransientModel):
    _name = 'crm.project.wizard'
    _description = "CRM project Wizard"
    
    
    def get_name(self):
        ctx = dict(self._context or {})
        active_id = ctx.get('active_id')
        crm_brw = self.env['crm.lead'].browse(active_id)
        name = crm_brw.name
        return name
    
    
    name = fields.Char('Project Name',default = get_name)



    def create_service(self):
        ctx = dict(self._context or {})
        active_id = ctx.get('active_id')
        crm_brw = self.env['crm.lead'].browse(active_id)

        vals = {'name': self.name,
                'lead_id': crm_brw.id or False
                }
        self.env['project.project'].create(vals)
        
class ProjectProject(models.Model):
    _inherit='project.project'
    
    lead_id =  fields.Many2one('crm.lead', 'Opportunity')

class ProjectTask(models.Model):
    _inherit='project.task'


    billing_type=fields.Selection([('no_billing','No Billing'),('billing_amt','Billing Amount')],string="Billing Type",default='no_billing')
    task_lines=fields.One2many('service.task.line','task_id',string="Task LInes")
    bill_amt=fields.Float(string="Total",compute='_compute_total')
    billed_amt=fields.Float(string="Billed Amount",compute='compute_billed_amt')
    due_amount=fields.Float(string="Due Amount",compute='_compute_due_amt')

    employee_ids=fields.Many2many('hr.employee',compute='_compute_employees')

    @api.depends('task_lines','task_lines.employee_id')
    def _compute_employees(self):
        for rec in self:
            if rec.task_lines:
                rec.employee_ids=rec.task_lines.mapped('employee_id')
            else:
                rec.employee_ids=False

    @api.depends('bill_amt','billed_amt')
    def _compute_due_amt(self):
        for rec in self:
            rec.due_amount=rec.bill_amt-rec.billed_amt

    @api.depends('task_lines')
    def _compute_total(self):
        for rec in self:
            rec.bill_amt=sum(rec.task_lines.mapped('total_amt'))


    def create_invoice(self):
        if  self.billed_amt>self.due_amount:
            raise UserError("Already Billed The Task")
        else:
            line_items=[]
            for line in self.task_lines:
                vals={
                    'product_id':line.product_id.id,
                    'task_line_id':line.id,
                    'quantity':line.tot_hrs,
                    'price_unit':line.price_unit,

                }
                line_items.append((0,0,vals))
            inv_vals={
                'partner_id':self.project_id.lead_id.partner_id.id,
                'task_id':self.id,
                'move_type':'out_invoice',
                'invoice_line_ids':line_items,

            }
            invoice=self.env['account.move'].sudo().create(inv_vals)


    def compute_inv_count(self):
        inv_obj = self.env['account.move']
        self.inv_count = inv_obj.search_count([('task_id', 'in', [a.id for a in self])])

    inv_count = fields.Integer(compute='compute_inv_count', string='Invoices')

    def compute_billed_amt(self):
        for rec in self:
            rec.billed_amt= sum((self.env['account.move'].search([('task_id', 'in', [a.id for a in self]),('state','=','posted')])).mapped('amount_total'))


class TaskLInes(models.Model):
    _name='service.task.line'

    task_id=fields.Many2one('project.task',string="Task")
    employee_id=fields.Many2one('hr.employee',string="Employee")
    activity_type=fields.Many2one('mail.activity.type',string="Activity ype")
    product_id=fields.Many2one('product.product',string="Service")
    price_unit=fields.Float(string="Service Charge")
    scheduled_date=fields.Date(string="Scheduled Date")
    start=fields.Datetime(string="Start",default=lambda self: fields.datetime.now())
    end=fields.Datetime(string="End",default=lambda self: fields.datetime.now())
    #tot_hrs=fields.Float(string="Duration(hrs)",compute='_compute_duration')
    tot_hrs=fields.Float(string="Duration(hrs)",)


    status=fields.Selection([('closed','Closed'),('pending','Pending'),('in+progress','In Progress'),('on_hold','On Hold'),('cancelled','Cancelled')],string="Status")
    approval_status=fields.Selection([('approved','Approved'),('rejected','Rejected'),('need_info','Need Information')],string="Approval Status")
    total_amt=fields.Float(string="Total",compute='_compute_total')
    tax_ids=fields.Many2many('account.tax',string="Taxes")

    @api.depends('tot_hrs','price_unit')
    def _compute_total(self):
        for rec in self:
            rec.total_amt=rec.price_unit*rec.tot_hrs

    def _get_duration(self, start, stop):
        """ Get the duration value between the 2 given dates. """
        if not start or not stop:
            return 0
        duration = (stop - start).total_seconds() / 3600
        return round(duration, 2)

    #@api.depends('start', 'end')
    @api.onchange('start', 'end')
    def _compute_duration(self):
        for event in self:
            if self.start>self.end:
                raise UserError("End date must greater than or equal to start date")
            today = datetime.today().date()
            ten_days_before = today - timedelta(days=10)
            res_user = self.env['res.users'].browse(self._uid)
            if self.start.date()<ten_days_before and not res_user.has_group('bi_crm_task.group_service_task_manager'):
                raise UserError("Start date not allow to enter past 10 days.Only Allowed to Service Task line Manager ")
            if self.end.date() < ten_days_before and not res_user.has_group('bi_crm_task.group_service_task_manager'):
                raise UserError("End date not allow to enter past 10 days .Only Allowed to Service Task line Manager")


            #event.tot_hrs = self._get_duration(event.start, event.end)

    @api.onchange('product_id')
    def oncahnge_product_id(self):
        for rec in self:
            rec.price_unit=rec.product_id.list_price