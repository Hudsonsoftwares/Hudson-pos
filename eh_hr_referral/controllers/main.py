from odoo import http, fields, _
from odoo.http import request
import json

class ReferralDashboard(http.Controller):

    @http.route('/eh/fix_points', type='http', auth='public', website=True)
    def fix_points(self, **kw):
        applicants = request.env['hr.applicant'].sudo().search([('friend_id', '!=', False)])
        for app in applicants:
            existing = request.env['eh.hr.referral.points'].sudo().search([('applicant_id', '=', app.id)])
            if not existing:
                request.env['eh.hr.referral.points'].sudo().create({
                    'user_id': app.ref_user_id.id,
                    'points': 100,
                    'company_id': app.company_id.id or request.env.company.id,
                    'applicant_id': app.id,
                })
        return "Fixed points"

    @http.route(['/referrals'], type='http', auth="user", website=True)
    def referral_dashboard(self, **kwargs):
        iframe = kwargs.get('iframe')
        
        # We need basic data for the dashboard:
        # User details, total points, to spend points, referrals counts
        employee = request.env['hr.employee'].search([('user_id', '=', request.env.user.id)], limit=1)
        company = request.env.company
        
        alerts = request.env['eh.hr.referral.alert'].search([
            '|', ('date_from', '<=', fields.Date.today()), ('date_from', '=', False),
            '|', ('date_to', '>=', fields.Date.today()), ('date_to', '=', False),
            '|', ('company_id', '=', False), ('company_id', '=', company.id)
        ])
        
        # Calculate Points
        total_points = sum(request.env['eh.hr.referral.points'].sudo().search([('user_id', '=', request.env.user.id)]).mapped('points'))
        spent_points = sum(request.env['eh.hr.referral.reward.log'].sudo().search([('employee_id', '=', employee.id)]).mapped('points')) if employee else 0
        to_spend = total_points - spent_points
        
        # Calculate Level
        levels = request.env['eh.hr.referral.level'].search([], order='points desc')
        current_level_name = '1'
        level_image_id = False
        current_level_points = 0
        for lvl in levels:
            if total_points >= lvl.points:
                current_level_name = lvl.name
                level_image_id = lvl.id
                current_level_points = lvl.points
                break

        # Progress towards the next level (levels are sorted by points desc)
        next_level = levels.filtered(lambda l: l.points > total_points)[-1:]
        if next_level:
            span = next_level.points - current_level_points
            level_progress = int((total_points - current_level_points) * 100 / span) if span else 0
        else:
            level_progress = 100

        # Calculate Referrals
        domain = [('ref_user_id', '=', request.env.user.id)]
        referrals_count = request.env['hr.applicant'].search_count(domain)
        ongoing_count = request.env['hr.applicant'].search_count(domain + [('active', '=', True)])
        
        try:
            successful_applicants = request.env['hr.applicant'].with_context(active_test=False).search(domain + [('stage_id.hired_stage', '=', True)])
        except:
            successful_applicants = request.env['hr.applicant'].with_context(active_test=False).search(domain + [('stage_id.name', 'ilike', 'hired')])

        successful_count = len(successful_applicants)
        ongoing_count = referrals_count - successful_count

        # Check for hired applicants without avatars
        hired_no_avatar = None
        try:
            hired_no_avatar = request.env['hr.applicant'].with_context(active_test=False).search(domain + [('stage_id.hired_stage', '=', True), ('friend_id', '=', False)], limit=1)
        except:
            hired_no_avatar = request.env['hr.applicant'].with_context(active_test=False).search(domain + [('stage_id.name', 'ilike', 'hired'), ('friend_id', '=', False)], limit=1)

        friends = request.env['eh.hr.referral.friend'].sudo().search([])

        # Hired friends stand around the hero, alternating left / right
        team = successful_applicants.filtered('friend_id')[:8]
        team_left = [app.friend_id for app in team[0::2]][::-1]
        team_right = [app.friend_id for app in team[1::2]]

        onboardings = request.env['eh.hr.referral.onboarding'].search([
            '|', ('company_id', '=', False), ('company_id', '=', company.id)
        ], order='sequence, id')
        force_tour = kwargs.get('tour') == '1' or kwargs.get('onboarding') == '1'
        onboarding_completed = request.env.user.eh_referral_onboarding_completed and not force_tour

        values = {
            'iframe': iframe,
            'employee': employee,
            'company': company,
            'alerts': alerts,
            'total_points': total_points,
            'to_spend': to_spend,
            'level': current_level_name,
            'level_image_id': level_image_id,
            'next_level': next_level,
            'level_progress': max(0, min(level_progress, 100)),
            'team_left': team_left,
            'team_right': team_right,
            'referrals_count': referrals_count,
            'ongoing_count': ongoing_count,
            'successful_count': successful_count,
            'successful_applicants': successful_applicants,
            'hired_no_avatar': hired_no_avatar,
            'friends': friends,
            'onboardings': onboardings,
            'onboarding_completed': onboarding_completed,
        }
        
        return request.render("eh_hr_referral.referral_dashboard", values)

    @http.route(['/eh/referral/send_mail'], type='http', auth="user", website=True, methods=['POST'])
    def referral_send_mail(self, **post):
        email_to = post.get('email_to')
        subject = post.get('subject')
        body = post.get('body')
        
        if email_to and subject and body:
            mail_values = {
                'subject': subject,
                'body_html': body.replace('\n', '<br/>'),
                'email_to': email_to,
            }
            request.env['mail.mail'].sudo().create(mail_values).send()
            
        return request.redirect('/referrals?iframe=1')

    @http.route(['/eh/referral/onboarding_skip'], type='jsonrpc', auth="user", website=True)
    def referral_onboarding_skip(self, **post):
        request.env.user.sudo().eh_referral_onboarding_completed = True
        return {'status': 'success'}

    @http.route(['/eh/referral/onboarding_skip_http'], type='http', auth="user", website=True, methods=['POST', 'GET'])
    def referral_onboarding_skip_http(self, **post):
        request.env.user.sudo().eh_referral_onboarding_completed = True
        return json.dumps({'status': 'success'})

    @http.route(['/eh/referral/onboarding_restart'], type='jsonrpc', auth="user", website=True)
    def referral_onboarding_restart(self, **post):
        request.env.user.sudo().eh_referral_onboarding_completed = False
        return {'status': 'success'}

    @http.route(['/eh/referral/choose_avatar'], type='json', auth="user", website=True)
    def referral_choose_avatar(self, applicant_id, friend_id, **post):
        applicant = request.env['hr.applicant'].sudo().browse(int(applicant_id))
        if applicant.exists() and applicant.ref_user_id.id == request.env.user.id:
            applicant.friend_id = int(friend_id)
            
            # Award 100 points
            request.env['eh.hr.referral.points'].sudo().create({
                'user_id': request.env.user.id,
                'points': 100,
                'company_id': request.env.company.id,
                'applicant_id': applicant.id,
            })
            
            return {'status': 'success'}
        return {'status': 'error', 'message': 'Applicant not found or access denied'}
