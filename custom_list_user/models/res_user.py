from odoo import models, fields, api

class ResUsers(models.Model):
    _inherit = 'res.users'
    
    sequence_number = fields.Integer(string="No", compute='_compute_sequence_number', store=False)

    @api.depends('name')
    def _compute_sequence_number(self):
        index = 1
        for record in self:
            record.sequence_number = index
            index += 1