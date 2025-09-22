from odoo import models, fields, api, exceptions

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    approval_line_ids = fields.One2many('purchase.order.approval.line', 'order_id', string='Approval Lines', readonly=True)

    def button_confirm(self):
        self.ensure_one()
 
        if self.approval_line_ids and any(line.status in ('pending', 'current') for line in self.approval_line_ids):
            self.message_post(body="This order is already waiting for approval. Please use the approval buttons in the 'Approval Details' tab.")
            return self._get_refresh_action()

        required_levels = self.env['purchase.approval.level'].search([
            ('minimum_amount', '<=', self.amount_total),
            '|',
            ('maximum_amount', '>=', self.amount_total),
            ('maximum_amount', '=', 0)
        ], order='sequence asc')

        if required_levels:
            self.write({'state': 'to approve'})
            self._create_approval_lines(required_levels)
            self._check_approval_status()
            self.message_post(body="This order requires approval. The approval process has been initiated.")
        else:
            self.message_post(body="No approval required for this order. Order confirmed.")
            super(PurchaseOrder, self).button_confirm()
        
        return self._get_refresh_action()

    def _create_approval_lines(self, levels):
        self.approval_line_ids.unlink()
        line_vals = []
        for level in levels:
            line_vals.append((0, 0, {
                'level_id': level.id,
                'order_id': self.id,
            }))
        self.write({'approval_line_ids': line_vals})

    def _check_approval_status(self):
        self.ensure_one()
        current_line = self.approval_line_ids.filtered(lambda l: l.status == 'current')
        if current_line:
            return

        pending_lines = self.approval_line_ids.filtered(lambda l: l.status == 'pending')
        if pending_lines:
            pending_lines[0].status = 'current'
            
            activity_type_id = self.env.ref('mail.mail_activity_data_todo').id
            for user in pending_lines[0].user_ids:
                self.activity_schedule(
                    activity_type_id=activity_type_id,
                    summary=f"Approval required for Purchase Order {self.name}",
                    user_id=user.id,
                    date_deadline=fields.Date.today(),
                    note=f"Please approve Purchase Order {self.name} for {self.amount_total} {self.currency_id.symbol}."
                )
        else:
            super(PurchaseOrder, self).button_confirm()

    def _get_refresh_action(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def button_approve(self, force=False):
        self.ensure_one()
        if self.state == 'to approve':
            all_approved = all(line.status == 'approved' for line in self.approval_line_ids)
            if not all_approved:
                raise exceptions.UserError("Please complete all approvals in the 'Approval Details' tab first before approving the order.")
        
        return super(PurchaseOrder, self).button_approve(force=force)
