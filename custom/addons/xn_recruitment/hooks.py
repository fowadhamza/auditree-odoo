# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# Stages in HR's order, matched to existing stages by name (case-insensitive,
# any alias) before anything is created, so a database that already has
# "Round 1" keeps it. (name, aliases, hiring step, hired stage)
STAGES = [
    ('New', ['new', 'new cv', 'new applicant'], False, False),
    ('Cold Call Shortlist', ['cold call shortlist', 'cold call'], 'cold_call', False),
    ('HR Initial Call', ['hr initial call', 'initial qualification'], 'hr_call', False),
    ('Round 1', ['round 1', 'first interview'], 'round1', False),
    ('Round 2', ['round 2', 'second interview'], 'round2', False),
    ('Final Round', ['final round', 'final interview'], 'final', False),
    ('Decision Making', ['decision making', 'decision making round'], 'decision', False),
    ('Selected', ['selected', 'contract proposal', 'offer'], 'offer', False),
    ('Joined', ['joined', 'contract signed', 'hired'], 'joined', True),
]

# Interview panels from HR's answers: first names, matched to internal users.
PANEL_INTERVIEWERS = {
    'xn_recruitment.panel_technical_round1': ['Usama'],
    'xn_recruitment.panel_technical_round2': ['Keerthana'],
    'xn_recruitment.panel_technical_final': ['Athif'],
    'xn_recruitment.panel_technical_decision': ['Faraz'],
    'xn_recruitment.panel_non_technical_round1': ['Ayesha'],
    'xn_recruitment.panel_non_technical_round2': ['Nishath'],
    'xn_recruitment.panel_non_technical_final': ['Sharook', 'Fowad'],
    'xn_recruitment.panel_non_technical_decision': ['Sharook', 'Fowad'],
}

# Copied on every interviewer handover email besides hr@ (first names, internal users).
HANDOVER_CC_NAMES = ['Nishath']

# Channels HR uses. Existing sources with the same name are reused
# (utm.source names are unique).
SOURCES = [
    'LinkedIn', 'Naukri', 'Indeed', 'OLX', 'Recruitment Agency', 'Employee Referral',
    'Direct Application (Email)', 'Company Website', 'Own Search (CV database / LinkedIn)',
]

# The agencies HR works with actively; fee terms are set per agency later.
AGENCIES = ['AJ Recruitment Services', 'Vikash Consultancy']

STOCK_REFUSE_REASONS = ['hr_recruitment.refuse_reason_%d' % index for index in range(1, 9)]


def post_init_hook(env):
    _setup_stages(env)
    _setup_panels(env)
    _setup_handover_cc(env)
    _setup_jobs(env)
    _setup_sources_and_agencies(env)
    _setup_refuse_reasons(env)
    _backfill_applicants(env)


def _setup_stages(env):
    """Map existing stages to hiring steps, create the missing ones, reorder.

    Stages that match nothing are left alone but moved after HR's stages;
    archive them by hand once no candidate sits in them.
    """
    Stage = env['hr.recruitment.stage']
    existing = Stage.search([])
    by_name = {}
    for stage in existing:
        by_name.setdefault((stage.name or '').strip().lower(), stage)
    used = Stage.browse()
    for sequence, (name, aliases, step, hired) in enumerate(STAGES, start=1):
        stage = next((by_name[alias] for alias in aliases
                      if alias in by_name and by_name[alias] not in used), Stage.browse())
        vals = {'sequence': sequence, 'xn_round': step}
        if hired:
            vals['hired_stage'] = True
        if stage:
            stage.write(vals)
        else:
            stage = Stage.create(dict(vals, name=name, fold=hired))
        used |= stage
    for offset, stage in enumerate((existing - used).sorted('sequence'), start=1):
        stage.sequence = 100 + offset
    if existing - used:
        _logger.info("xn_recruitment: stages left unmapped (archive when empty): %s",
                     ', '.join((existing - used).mapped('name')))


def _setup_panels(env):
    """Fill the panels with the users HR named; skip names that are ambiguous."""
    Users = env['res.users']
    interviewer_group = env.ref('hr_recruitment.group_hr_recruitment_interviewer')
    for xmlid, first_names in PANEL_INTERVIEWERS.items():
        line = env.ref(xmlid, raise_if_not_found=False)
        if not line:
            continue
        users = Users.browse()
        for first_name in first_names:
            matches = Users.search([('share', '=', False), ('name', '=ilike', first_name + '%')])
            if len(matches) == 1:
                users |= matches
            else:
                _logger.warning("xn_recruitment: %d users match '%s' for %s; set it by hand "
                                "in Interview Panels", len(matches), first_name, xmlid)
        if users:
            line.write({'user_ids': [(4, user.id) for user in users]})
            interviewer_group.write({'users': [(4, user.id) for user in users]})


def _setup_handover_cc(env):
    """Add HANDOVER_CC_NAMES' emails to xn_recruitment.handover_cc; skip ambiguous names."""
    Param = env['ir.config_parameter'].sudo()
    emails = env['hr.applicant']._xn_handover_cc()
    known = {email.lower() for email in emails}
    for first_name in HANDOVER_CC_NAMES:
        matches = env['res.users'].search([('share', '=', False), ('name', '=ilike', first_name + '%')])
        if len(matches) != 1 or not matches.email:
            _logger.warning("xn_recruitment: %d users match '%s' for the handover Cc; add the "
                            "address to xn_recruitment.handover_cc by hand", len(matches), first_name)
            continue
        if matches.email.lower() not in known:
            emails.append(matches.email)
            known.add(matches.email.lower())
    Param.set_param('xn_recruitment.handover_cc', ', '.join(emails))


def _setup_jobs(env):
    """Give every job a panel (audit roles technical, others not) and a start date."""
    technical = env.ref('xn_recruitment.panel_technical', raise_if_not_found=False)
    non_technical = env.ref('xn_recruitment.panel_non_technical', raise_if_not_found=False)
    for job in env['hr.job'].with_context(active_test=False).search([('xn_panel_id', '=', False)]):
        panel = technical if 'audit' in (job.name or '').lower() else non_technical
        if panel:
            job.xn_panel_id = panel
    env.cr.execute("""
        UPDATE hr_job SET xn_opened_on = create_date::date
         WHERE xn_opened_on IS NULL OR xn_opened_on = CURRENT_DATE
    """)


def _setup_sources_and_agencies(env):
    Source = env['utm.source']
    for name in SOURCES:
        if not Source.search([('name', '=ilike', name)], limit=1):
            Source.create({'name': name})
    Partner = env['res.partner']
    for name in AGENCIES:
        agency = Partner.search([('name', '=ilike', name)], limit=1)
        if agency:
            agency.xn_is_recruitment_agency = True
        else:
            Partner.create({'name': name, 'is_company': True, 'xn_is_recruitment_agency': True})


def _setup_refuse_reasons(env):
    """Archive the stock reasons so HR picks from their own list."""
    for xmlid in STOCK_REFUSE_REASONS:
        reason = env.ref(xmlid, raise_if_not_found=False)
        if reason:
            reason.active = False


def _backfill_applicants(env):
    """Furthest step from the current stage, refusal date from the last write."""
    env.flush_all()
    env.cr.execute("""
        UPDATE hr_applicant a
           SET xn_max_round_order = s.xn_round_order
          FROM hr_recruitment_stage s
         WHERE s.id = a.stage_id
           AND s.xn_round_order > COALESCE(a.xn_max_round_order, 0)
    """)
    env.cr.execute("""
        UPDATE hr_applicant SET xn_refused_on = write_date::date
         WHERE refuse_reason_id IS NOT NULL AND xn_refused_on IS NULL
    """)
    env['hr.applicant'].invalidate_model(['xn_max_round_order', 'xn_refused_on'])
