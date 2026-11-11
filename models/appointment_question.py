# pyrefly: ignore [missing-import]
from odoo import models, fields, api

class AppointmentQuestion(models.Model):
    _name = 'appointment.question'
    _description = 'Appointment Question'
    _order = 'sequence, id'

    sequence = fields.Integer('Sequence', default=10)
    name = fields.Char('Question', required=True, translate=True)
    appointment_type_id = fields.Many2one('appointment.type', string='Appointment Type', required=True, ondelete='cascade')
    
    question_type = fields.Selection([
        ('char', 'Single line text'),
        ('text', 'Multi-line text'),
        ('phone', 'Phone Number'),
        ('select', 'Dropdown (one answer)'),
        ('radio', 'Radio (one answer)'),
        ('checkbox', 'Checkboxes (multiple answers)'),
    ], string='Question Type', required=True, default='char')
    
    is_required = fields.Boolean('Mandatory Answer', default=False)
    is_reusable = fields.Boolean('Is Reusable', default=False)
    default_question = fields.Boolean('Default question', default=False)
    placeholder = fields.Char('Placeholder', help="Displayed when the field is empty")
    extra_comments = fields.Text('Extra comments')
    answer_ids = fields.One2many('appointment.question.answer', 'question_id', string='Answers')
    
    appointment_usage_count = fields.Integer('Usage Count', compute='_compute_appointment_usage_count')

    @api.depends('answer_ids')
    def _compute_appointment_usage_count(self):
        for question in self:
            question.appointment_usage_count = 0
            
        if self.ids:
            answer_data = self.env['appointment.answer']._read_group(
                [('question_id', 'in', self.ids)],
                ['question_id'],
                ['__count']
            )
            mapped_data = {q.id: count for q, count in answer_data}
            for question in self:
                question.appointment_usage_count = mapped_data.get(question.id, 0)

    def action_view_answers(self):
        self.ensure_one()
        return {
            'name': 'Answer Breakdown',
            'type': 'ir.actions.act_window',
            'res_model': 'appointment.answer',
            'view_mode': 'list',
            'domain': [('question_id', '=', self.id)],
            'context': {
                'default_question_id': self.id,
                'search_default_question_id': self.id,
                'search_default_appointment_type_id': self.appointment_type_id.id,
            },
        }

class AppointmentQuestionAnswer(models.Model):
    _name = 'appointment.question.answer'
    _description = 'Appointment Question Answer'
    _order = 'sequence, id'

    sequence = fields.Integer('Sequence', default=10)
    name = fields.Char('Answer', required=True, translate=True)
    question_id = fields.Many2one('appointment.question', ondelete='cascade', required=True)

