# -*- coding: utf-8 -*-
import base64
import hmac
import json
import logging
import os
import re
from datetime import datetime, timedelta

from odoo import http, tools
from odoo.http import request

_logger = logging.getLogger(__name__)

TOKEN_PARAM = 'xn_recruitment_bridge.api_token'

# A CV, not an arbitrary upload. Anything executable or script-like is refused
# outright rather than stored and left for someone to click on later.
ALLOWED_CV_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.odt', '.rtf', '.txt', '.png', '.jpg', '.jpeg',
}
MAX_CV_BYTES = 10 * 1024 * 1024
MAX_FIELD_CHARS = 256
MAX_LETTER_CHARS = 20000

# Matches core's own recent-application window in
# website_hr_recruitment/controllers/main.py.
DUPLICATE_WINDOW_DAYS = 90


def _json_response(payload, status=200):
    """Return a JSON body from a type='http' route.

    These routes are type='http' rather than type='json' on purpose: Odoo's
    JSON transport expects a JSON-RPC envelope and cannot carry a file upload,
    and the WordPress end needs to post multipart/form-data for the CV.
    """
    return request.make_response(
        json.dumps(payload),
        headers=[
            ('Content-Type', 'application/json'),
            ('Cache-Control', 'no-store'),
        ],
        status=status,
    )


def _token_is_valid():
    """Constant-time check of the shared secret.

    Fails closed: an unset or blank parameter rejects every request. The
    alternative -- treating "no token configured" as "no authentication
    required" -- would leave the endpoint open on any database where the
    post-init hook did not run.
    """
    expected = request.env['ir.config_parameter'].sudo().get_param(TOKEN_PARAM)
    if not expected:
        _logger.error(
            "Recruitment bridge called but %s is not set; refusing. "
            "Set the parameter before pointing WordPress at this endpoint.",
            TOKEN_PARAM,
        )
        return False
    supplied = request.httprequest.headers.get('X-Auditree-Token') or ''
    return hmac.compare_digest(supplied, expected)


def _clean_text(value, limit=MAX_FIELD_CHARS):
    """Collapse whitespace and cap length on a single-line form value."""
    if not value:
        return ''
    return re.sub(r'\s+', ' ', str(value)).strip()[:limit]


def _safe_filename(filename):
    """Reduce an uploaded filename to a harmless basename.

    The name is attacker-supplied. Path separators are stripped so it cannot
    describe a location, and the result is capped so it fits ir.attachment.
    """
    base = os.path.basename((filename or '').replace('\\', '/')).strip()
    base = re.sub(r'[^A-Za-z0-9._ -]', '_', base)
    return (base or 'cv')[:120]


class RecruitmentBridge(http.Controller):

    @http.route(
        '/auditree/recruitment/jobs',
        type='http', auth='public', methods=['GET'], csrf=False, sitemap=False,
    )
    def list_jobs(self, **kwargs):
        """Published vacancies, for the WordPress careers page to render.

        Public because it is the same information core already publishes at
        /jobs -- an authenticated feed of public data buys nothing.

        The is_published filter matters more here than it looks. hr.job in
        this database holds 34 records, most of which are employee job titles
        (CEO, CFO, Partner) rather than open vacancies. Listing the table
        unfiltered would advertise a vacancy for every role in the company.
        """
        jobs = request.env['hr.job'].sudo().search([
            ('is_published', '=', True),
            ('active', '=', True),
        ], order='sequence, name')

        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        payload = [{
            'id': job.id,
            'name': job.name,
            'department': job.department_id.name or '',
            'location': job.address_id.city or '',
            'country': job.address_id.country_id.name or '',
            'positions': job.no_of_recruitment,
            'published_date': job.published_date.isoformat() if job.published_date else None,
            'description_html': job.website_description or job.description or '',
            'odoo_url': '%s%s' % (base_url, job.website_url or ''),
        } for job in jobs]

        return _json_response({'status': 'ok', 'count': len(payload), 'jobs': payload})

    @http.route(
        '/auditree/recruitment/ping',
        type='http', auth='public', methods=['GET'], csrf=False, sitemap=False,
    )
    def ping(self, **kwargs):
        """Connectivity and credential check for whoever wires up WordPress.

        Exists so that "can the WordPress host reach Odoo, and is the token
        right?" can be answered in one curl, without filing a test applicant
        that HR then has to delete.
        """
        if not _token_is_valid():
            return _json_response({'status': 'error', 'error': 'unauthorised'}, status=401)
        return _json_response({'status': 'ok', 'odoo': 'reachable'})

    @http.route(
        '/auditree/recruitment/apply',
        type='http', auth='public', methods=['POST'], csrf=False, sitemap=False,
    )
    def apply(self, **post):
        """Create an hr.applicant from a WordPress form submission.

        Expects multipart/form-data with an X-Auditree-Token header:

            job_id      (int, required)   an is_published hr.job
            name        (str, required)   the applicant's name
            email       (str, required)   must normalise to a real address
            phone       (str, optional)
            linkedin    (str, optional)
            letter      (str, optional)   cover letter, plain text
            cv          (file, optional)

        Creation only, and never a stage change: hr.applicant.write in
        xn_auditree_erp sends approval email with force_send=True whenever
        stage_id moves, so an endpoint that could set a stage would also be
        able to make Odoo send mail on demand. The stage is left to core's
        _compute_stage, which picks the first unfolded stage for the job.
        """
        if not _token_is_valid():
            _logger.warning(
                "Rejected recruitment bridge submission from %s: bad or missing token",
                request.httprequest.remote_addr,
            )
            return _json_response({'status': 'error', 'error': 'unauthorised'}, status=401)

        errors = {}

        # -- Job -------------------------------------------------------------
        job = request.env['hr.job']
        try:
            job_id = int(post.get('job_id') or 0)
        except (TypeError, ValueError):
            job_id = 0
        if not job_id:
            errors['job_id'] = 'required'
        else:
            job = request.env['hr.job'].sudo().browse(job_id).exists()
            # An unpublished or archived job is treated as not existing at
            # all. Reporting "this job is closed" would confirm the id to
            # someone enumerating them.
            if not job or not job.active or not job.is_published:
                errors['job_id'] = 'unknown or closed job'

        # -- Applicant --------------------------------------------------------
        partner_name = _clean_text(post.get('name'))
        if not partner_name:
            errors['name'] = 'required'

        email = _clean_text(post.get('email'))
        normalized_email = tools.email_normalize(email) if email else ''
        if not email:
            errors['email'] = 'required'
        elif not normalized_email:
            errors['email'] = 'not a valid email address'

        if errors:
            return _json_response({'status': 'error', 'errors': errors}, status=400)

        # -- CV ----------------------------------------------------------------
        upload = request.httprequest.files.get('cv')
        cv_name, cv_content = None, None
        if upload and upload.filename:
            cv_name = _safe_filename(upload.filename)
            extension = os.path.splitext(cv_name)[1].lower()
            if extension not in ALLOWED_CV_EXTENSIONS:
                return _json_response({
                    'status': 'error',
                    'errors': {'cv': 'file type not accepted: %s' % (extension or 'none')},
                }, status=400)
            cv_content = upload.read()
            if len(cv_content) > MAX_CV_BYTES:
                return _json_response({
                    'status': 'error',
                    'errors': {'cv': 'file larger than %d MB' % (MAX_CV_BYTES // (1024 * 1024))},
                }, status=413)
            if not cv_content:
                cv_name, cv_content = None, None

        # -- Duplicate guard ----------------------------------------------------
        # Without this, a double-clicked submit button or a retrying WordPress
        # plugin files the same person twice and HR interviews a ghost.
        Applicant = request.env['hr.applicant'].sudo()
        since = datetime.now() - timedelta(days=DUPLICATE_WINDOW_DAYS)
        existing = Applicant.search([
            ('email_normalized', '=', normalized_email),
            ('job_id', '=', job.id),
            ('create_date', '>=', since),
        ], limit=1)
        if existing:
            _logger.info(
                "Recruitment bridge: duplicate application for job %s from %s, ignored",
                job.id, normalized_email,
            )
            return _json_response({
                'status': 'duplicate',
                'applicant_id': existing.id,
                'message': 'An application for this job from this address already exists.',
            })

        # -- Create --------------------------------------------------------------
        source = request.env.ref(
            'xn_recruitment_bridge.utm_source_wordpress', raise_if_not_found=False)
        medium = request.env.ref(
            'utm.utm_medium_website', raise_if_not_found=False)
        values = {
            'name': '%s - %s' % (partner_name, job.name),
            'partner_name': partner_name,
            'email_from': normalized_email,
            'job_id': job.id,
            'department_id': job.department_id.id,
            'company_id': job.company_id.id or request.env.company.id,
            'source_id': source.id if source else False,
            'medium_id': medium.id if medium else False,
        }
        phone = _clean_text(post.get('phone'), limit=32)
        if phone:
            values['partner_phone'] = phone
        linkedin = _clean_text(post.get('linkedin'))
        if linkedin:
            values['linkedin_profile'] = linkedin
        letter = post.get('letter')
        if letter:
            # description is a Html field and this text came off the public
            # internet. plaintext2html escapes it, so a cover letter cannot
            # carry markup into the recruiter's browser.
            values['description'] = tools.plaintext2html(str(letter)[:MAX_LETTER_CHARS])

        applicant = Applicant.create(values)

        if cv_content:
            attachment = request.env['ir.attachment'].sudo().create({
                'name': cv_name,
                'datas': base64.b64encode(cv_content),
                'res_model': 'hr.applicant',
                'res_id': applicant.id,
            })
            # Makes the CV the document shown in the applicant's preview pane,
            # which is where a recruiter expects to find it. Writing only this
            # key keeps the write clear of stage_id and its approval email.
            applicant.write({'message_main_attachment_id': attachment.id})

        _logger.info(
            "Recruitment bridge: created applicant %s for job %s (%s) from %s",
            applicant.id, job.id, job.name, request.httprequest.remote_addr,
        )
        return _json_response({
            'status': 'ok',
            'applicant_id': applicant.id,
            'stage': applicant.stage_id.name or '',
        })
