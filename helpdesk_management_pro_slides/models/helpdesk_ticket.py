# -*- coding: utf-8 -*-
from odoo import fields, models

class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.management.ticket'

    slide_id = fields.Many2one('slide.slide', string='eLearning Slide/Lesson', help='Link this ticket to an eLearning slide or lesson')
    course_id = fields.Many2one('slide.channel', string='eLearning Course', help='Link this ticket to an eLearning course')
    use_website_helpdesk_elearning = fields.Boolean(related='team_id.use_website_helpdesk_elearning')
    team_course_ids = fields.Many2many(related='team_id.website_slide_channel_ids', string='Team Courses')

