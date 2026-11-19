# -*- coding: utf-8 -*-
import base64
import secrets
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import file_open

from .activity_settings import (DEFAULTS, MIN_RETENTION_DAYS, AGENT_VERSION,
                                MAX_SPEED_TESTS_PER_HOUR, get_settings)

P = 'xn_activity.%s'


def build_installer(env):
    """install.ps1 with the agent, server URL, key and threshold embedded."""
    s = get_settings(env)
    params = env['ir.config_parameter'].sudo()
    url = (params.get_param(P % 'server_url')
           or params.get_param('web.base.url') or '').rstrip('/')
    key = params.get_param(P % 'api_key') or ''
    if not url.lower().startswith('https://'):
        raise UserError(_("The server URL must start with https:// before an "
                          "installer can be built (now: %s).", url or '-'))
    if not key:
        raise UserError(_("No API key yet. Generate one in Agent Setup."))
    with file_open('xn_activity/data/agent/agent.ps1', 'r') as f:
        agent = f.read()
    agent = (agent
             .replace('__SERVER_URL__', url)
             .replace('__API_KEY__', key)
             .replace('__IDLE_SECONDS__', str(int(s['idle_minutes']) * 60))
             .replace('__AGENT_VERSION__', AGENT_VERSION))
    with file_open('xn_activity/data/agent/install.ps1', 'r') as f:
        installer = f.read()
    b64 = base64.b64encode(agent.encode('utf-8')).decode('ascii')
    installer = (installer
                 .replace('__AGENT_VERSION__', AGENT_VERSION)
                 .replace('__AGENT_B64__', b64))
    # Windows PowerShell 5.1 reads a BOM-less file as ANSI; the content is
    # ASCII, so CRLF line endings are all it needs.
    return installer.replace('\r\n', '\n').replace('\n', '\r\n').encode('ascii')


def can_download_installer(user):
    """HR Managers (Agent Setup) and the IT Agent Installer role."""
    return (user.has_group('hr.group_hr_manager')
            or user.has_group('xn_activity.group_xn_activity_installer'))


class XnActivityInstaller(models.TransientModel):
    """Download-only screen for IT: no settings, no key changes."""
    _name = 'xn.activity.installer'
    _description = 'Activity Agent Installer Download'

    agent_version = fields.Char(readonly=True,
                                default=lambda self: AGENT_VERSION)

    def action_download(self):
        self.ensure_one()
        if not can_download_installer(self.env.user):
            raise UserError(_("Only an HR Manager or an Agent Installer can "
                              "download the installer."))
        build_installer(self.env)   # raise here, not in the download tab
        return {'type': 'ir.actions.act_url',
                'url': '/xn_activity/installer', 'target': 'self'}


class XnActivitySetup(models.TransientModel):
    _name = 'xn.activity.setup'
    _description = 'Activity Agent Setup'

    server_url = fields.Char(
        string='Server URL', required=True,
        help="The address laptops send to. Must be https://.")
    api_key = fields.Char(string='API Key', readonly=True)
    old_key_until = fields.Datetime(string='Previous Key Accepted Until',
                                    readonly=True)
    productive_target = fields.Float(string='Daily Productive Target (hours)')
    idle_minutes = fields.Integer(string='Idle Threshold (minutes)')
    retention_days = fields.Integer(string='Keep 5-Minute Data (days)')
    summary_retention_days = fields.Integer(string='Keep Daily Summaries (days)')
    key_grace_days = fields.Integer(
        string='Previous Key Grace Period (days)',
        help="After a new key is generated, laptops on the previous key keep "
             "reporting for this many days.")
    alert_to = fields.Char(
        string='Laptop Alerts To',
        help="Comma-separated emails for the weekday 'laptops not reporting' "
             "alert, e.g. it@auditree.com. Empty uses the digest recipients.")
    digest_to = fields.Char(
        string='Weekly Digest To',
        help="Comma-separated emails. Empty sends to every HR Manager.")
    work_accounts_only = fields.Boolean(
        string='Work Accounts Only',
        help="Store activity only for Windows sign-ins with a Microsoft 365 "
             "work account that matches an employee's work email. Local "
             "Windows accounts and unknown users are dropped and shown as "
             "Rejected Sign-in on Devices. The Windows User Name field on "
             "employees is then not used.")
    speed_test_url = fields.Char(
        string='Speed Test File',
        help="https address of a small file (about 2 MB) the agent downloads "
             "to measure connection speed. Our own bucket by default. "
             "Reaches laptops on their next report.")
    speed_tests_per_hour = fields.Integer(
        string='Speed Tests per Hour',
        help="0 to 4, at random minutes, only while the person is active and "
             "the connection is not metered (phone hotspot, mobile data). 0 "
             "turns the speed test off; connection type and response time "
             "are still recorded.")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        s = get_settings(self.env)
        params = self.env['ir.config_parameter'].sudo()
        res.update({k: s[k] for k in DEFAULTS})
        res['server_url'] = (params.get_param(P % 'server_url')
                             or params.get_param('web.base.url'))
        res['api_key'] = params.get_param(P % 'api_key')
        until = params.get_param(P % 'api_key_old_until')
        res['old_key_until'] = until or False
        return res

    @api.constrains('retention_days', 'idle_minutes', 'productive_target',
                    'server_url', 'speed_test_url', 'speed_tests_per_hour')
    def _check_values(self):
        for rec in self:
            if rec.retention_days < MIN_RETENTION_DAYS:
                raise ValidationError(_("Keep 5-minute data for at least %s "
                                        "days.", MIN_RETENTION_DAYS))
            if rec.summary_retention_days < rec.retention_days:
                raise ValidationError(_("Daily summaries must be kept at "
                                        "least as long as the 5-minute data."))
            if not 1 <= rec.idle_minutes <= 60:
                raise ValidationError(_("Idle threshold: 1 to 60 minutes."))
            if not 0 <= rec.productive_target <= 24:
                raise ValidationError(_("Productive target: 0 to 24 hours."))
            if not (rec.server_url or '').lower().startswith('https://'):
                raise ValidationError(_("The server URL must start with "
                                        "https://."))
            if not 0 <= rec.speed_tests_per_hour <= MAX_SPEED_TESTS_PER_HOUR:
                raise ValidationError(_("Speed tests per hour: 0 to %s.",
                                        MAX_SPEED_TESTS_PER_HOUR))
            if rec.speed_test_url and \
                    not rec.speed_test_url.lower().startswith('https://'):
                raise ValidationError(_("The speed test file must be an "
                                        "https:// address."))

    def _check_manager(self):
        if not self.env.user.has_group('hr.group_hr_manager'):
            raise UserError(_("Only an HR Manager can change Agent Setup."))

    def action_save(self):
        self.ensure_one()
        self._check_manager()
        params = self.env['ir.config_parameter'].sudo()
        old_target = get_settings(self.env)['productive_target']
        params.set_param(P % 'server_url', self.server_url.rstrip('/'))
        for k in DEFAULTS:
            params.set_param(P % k, self[k] if self[k] is not False else '')
        if self.productive_target != old_target:
            self.env['xn.activity.day']._xn_refresh_status()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': _("Saved."),
                           'next': {'type': 'ir.actions.act_window_close'}}}

    def action_download_installer(self):
        self.ensure_one()
        self.action_save()
        build_installer(self.env)   # raise here, not in the download tab
        return {'type': 'ir.actions.act_url',
                'url': '/xn_activity/installer', 'target': 'self'}

    def action_new_key(self):
        """New key now; the previous one keeps working for the grace period."""
        self.ensure_one()
        self._check_manager()
        params = self.env['ir.config_parameter'].sudo()
        current = params.get_param(P % 'api_key')
        grace = get_settings(self.env)['key_grace_days']
        if current:
            params.set_param(P % 'api_key_old', current)
            params.set_param(P % 'api_key_old_until', fields.Datetime.to_string(
                fields.Datetime.now() + timedelta(days=grace)))
        params.set_param(P % 'api_key', secrets.token_urlsafe(32))
        action = self.env['ir.actions.act_window']._for_xml_id(
            'xn_activity.action_xn_activity_setup')
        return action
