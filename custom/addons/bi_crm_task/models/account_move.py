# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

from odoo.tools.translate import _
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from odoo import tools, api
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo import api, fields, models, _
import logging
from odoo.osv import  osv
from odoo import SUPERUSER_ID



class AccountMOve(models.Model):
    _inherit = "account.move"

    task_id=fields.Many2one('project.task',string="Task")


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    task_line_id=fields.Many2one('service.task.line',string="Service task line")