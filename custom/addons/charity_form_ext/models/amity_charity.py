# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from datetime import datetime,date, timedelta
from dateutil.relativedelta import relativedelta
import base64
import vobject
from odoo.exceptions import UserError

class AmityCharity(models.Model):
	_name = 'amity.charity'
	_inherit = ['mail.thread', 'mail.activity.mixin']

	name=fields.Char(string="Application No",required=True, tracking=True, copy=False, readonly=True, default=lambda self: _('New'))
	date=fields.Date(string="Date")
	sl_no=fields.Char(string="SL.No")
	applicant_name=fields.Char(string="Name")
	age=fields.Integer(string="Age")
	application_type=fields.Selection([('emergency','Emergency'),('health_care','Health Care'),('home_project','Home Project'),('orphan_care','Orphan Care'),('relief_food','Relief Food Kit'),('help_poor','Help The Poor People')],string="Application Type",required=True)
	house_ame=fields.Char(string="House Name")
	place=fields.Char(string="Place")
	district=fields.Char(string="District")
	zip=fields.Char(string="Pin")
	mobile=fields.Char(string="Mobile")
	phone=fields.Char(string="Phone")
	description=fields.Text(string="Description")
	state=fields.Selection([('draft','Draft'),('confirm','Confirm')],string="Status",default='draft')
	charity_amount=fields.Float(string="Amount")
	partner_id=fields.Many2one('res.partner',string="Customer")
	journal_id=fields.Many2one('account.journal',string="Journal")
	payment_method_id=fields.Many2one('account.payment.method.line',string="Payment Method")
	communication=fields.Char(string="Memo")
	payment_date=fields.Date(string="Payment Date")
	payment_id=fields.Many2one('account.payment',string="Payment")

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			if vals.get('name', _("New")) == _("New"):
				vals['name'] = self.env['ir.sequence'].next_by_code('amity.charity') or _("New")
		return super().create(vals_list)



	def action_confirm(self):
		self.write({'state':'confirm'})

	def action_create_payment(self):
		self.ensure_one()
		if not self.journal_id:
			raise UserError("Journal Required")
		if not self.payment_method_id:
			raise UserError("Payment Method Required")
		payment_vals={'partner_id':self.partner_id.id,
					  'amount':self.charity_amount,
					  'payment_type':'outbound',
					  'journal_id':self.journal_id.id,
					  'payment_method_line_id':self.payment_method_id.id,
					  'ref':self.communication,
					  'date':self.payment_date,
					  'charity_id':self.id,
					  }
		payment=self.env['account.payment'].sudo().create(payment_vals)
		if payment:
			self.payment_id=payment.id


class AccountPayment(models.Model):
	_inherit = 'account.payment'

	charity_id=fields.Many2one('amity.charity',string="Charity")