# -*- encoding: utf-8 -*-
"""Referral attribution on the public job pages.

A referral share link looks like /jobs?referral_token=<token> (or the same
parameter on a specific job / apply page). Landing on any of these pages
stores the token in the visitor session; when the application form is
submitted, hr.applicant.website_form_input_filter turns the token into a
referral link (see models/hr_applicant.py).

This controller only registers routes when website_hr_recruitment is installed.
On Community without that module the file is imported but no routes are added.
"""
from odoo import http
from odoo.http import request
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

try:
    from odoo.addons.website_hr_recruitment.controllers.main import WebsiteHrRecruitment as _Base
    _HAS_WEBSITE_RECRUITMENT = True
except ImportError:
    _HAS_WEBSITE_RECRUITMENT = False
    _Base = object


if _HAS_WEBSITE_RECRUITMENT:

    class WebsiteHrRecruitmentReferral(_Base):

        def _capture_referral_token(self, kwargs):
            """Keep the referral token of the incoming share link in the visitor
            session for later attribution."""
            token = kwargs.get('referral_token')
            if token:
                request.session['eh_referral_token'] = token

        def _get_session_referral_employee(self):
            """Referrer of the share link currently in the visitor session, if
            any. Returned sudoed: it is only used to display their name."""
            token = request.session.get('eh_referral_token')
            if not token:
                return request.env['hr.employee']
            return request.env['hr.employee'].sudo().search(
                [('referral_token', '=', token)], limit=1)

        @http.route([
            '/jobs',
            '/jobs/page/<int:page>',
        ], type='http', auth='public', website=True, sitemap=_Base.sitemap_jobs, list_as_website_content=_lt('Jobs'))
        def jobs(self, **kwargs):
            self._capture_referral_token(kwargs)
            return super().jobs(**kwargs)

        @http.route('''/jobs/<model("hr.job"):job>''', type='http', auth='public', website=True, sitemap=True)
        def job(self, job, **kwargs):
            self._capture_referral_token(kwargs)
            return request.render("website_hr_recruitment.detail", {
                'job': job,
                'main_object': job,
                'referral_employee': self._get_session_referral_employee(),
            })

        @http.route('''/jobs/apply/<model("hr.job"):job>''', type='http', auth='public', website=True, sitemap=True)
        def jobs_apply(self, job, **kwargs):
            self._capture_referral_token(kwargs)
            error = {}
            default = {}
            if 'website_hr_recruitment_error' in request.session:
                error = request.session.pop('website_hr_recruitment_error')
                default = request.session.pop('website_hr_recruitment_default')
            return request.render("website_hr_recruitment.apply", {
                'job': job,
                'error': error,
                'default': default,
                'referral_employee': self._get_session_referral_employee(),
            })
