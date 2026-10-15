# -*- coding: utf-8 -*-
from odoo import models, fields, tools

from .helpdesk_ticket_stage import XN_STATES


class XnHelpdeskTicketReport(models.Model):
    """Ticket ageing and resolution time, one row per active ticket.

    A SQL view rather than stored fields because age depends on now(): it is
    recomputed on every read, so the report never goes stale. Like every
    _auto = False model here, a change to the SELECT only reaches the database
    on -u xn_it_helpdesk.
    """
    _name = 'xn.helpdesk.ticket.report'
    _description = 'IT Helpdesk Ticket Analysis'
    _auto = False
    _rec_name = 'number'
    _order = 'create_date desc'

    ticket_id = fields.Many2one('helpdesk.ticket', string='Ticket', readonly=True)
    number = fields.Char(string='Ticket No.', readonly=True)
    name = fields.Char(string='Subject', readonly=True)
    create_date = fields.Datetime(string='Submitted On', readonly=True)
    resolved_date = fields.Datetime(string='Resolved On', readonly=True)
    closed_date = fields.Datetime(string='Closed On', readonly=True)
    stage_id = fields.Many2one('helpdesk.ticket.stage', string='Status', readonly=True)
    state = fields.Selection(XN_STATES, string='IT Status', readonly=True)
    is_open = fields.Boolean(string='Open', readonly=True)
    category_id = fields.Many2one('helpdesk.ticket.category', string='Category', readonly=True)
    priority = fields.Selection(
        [('0', 'Low'), ('1', 'Medium'), ('2', 'High'), ('3', 'Critical')],
        string='Priority', readonly=True)
    user_id = fields.Many2one('res.users', string='Assigned To', readonly=True)
    team_id = fields.Many2one('helpdesk.ticket.team', string='Team', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    employee_code = fields.Char(string='Employee ID', readonly=True)
    department_id = fields.Many2one('hr.department', string='Department', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    reopen_count = fields.Integer(string='Times Reopened', readonly=True)
    age_days = fields.Float(
        string='Age (Days)', readonly=True, group_operator='avg',
        help="Days from submission to resolution, or to now if still open.")
    resolution_hours = fields.Float(
        string='Resolution Time (Hours)', readonly=True, group_operator='avg',
        help="Hours from submission to resolution. Empty while open.")
    age_bucket = fields.Selection(
        [
            ('a', '0-1 days'),
            ('b', '2-3 days'),
            ('c', '4-7 days'),
            ('d', '8-14 days'),
            ('e', '15-30 days'),
            ('f', 'Over 30 days'),
        ],
        string='Age Bracket', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW xn_helpdesk_ticket_report AS (
                SELECT
                    t.id,
                    t.id AS ticket_id,
                    t.number,
                    t.name,
                    t.create_date,
                    t.xn_resolved_date AS resolved_date,
                    t.xn_closed_date AS closed_date,
                    t.stage_id,
                    s.xn_state AS state,
                    (s.xn_state IS NULL OR s.xn_state NOT IN ('resolved', 'closed')) AS is_open,
                    t.category_id,
                    t.priority,
                    t.user_id,
                    t.team_id,
                    t.xn_employee_id AS employee_id,
                    t.xn_employee_code AS employee_code,
                    t.xn_department_id AS department_id,
                    t.company_id,
                    t.xn_reopen_count AS reopen_count,
                    a.age_days,
                    CASE WHEN t.xn_resolved_date IS NOT NULL
                         THEN EXTRACT(EPOCH FROM (t.xn_resolved_date - t.create_date)) / 3600.0
                    END AS resolution_hours,
                    CASE
                        WHEN a.age_days < 2 THEN 'a'
                        WHEN a.age_days < 4 THEN 'b'
                        WHEN a.age_days < 8 THEN 'c'
                        WHEN a.age_days < 15 THEN 'd'
                        WHEN a.age_days <= 30 THEN 'e'
                        ELSE 'f'
                    END AS age_bucket
                FROM helpdesk_ticket t
                LEFT JOIN helpdesk_ticket_stage s ON s.id = t.stage_id
                -- Datetimes are stored as naive UTC, so compare with UTC now.
                CROSS JOIN LATERAL (
                    SELECT EXTRACT(EPOCH FROM (
                        COALESCE(t.xn_resolved_date, NOW() AT TIME ZONE 'UTC') - t.create_date
                    )) / 86400.0 AS age_days
                ) a
                WHERE t.active
            )
        """)
