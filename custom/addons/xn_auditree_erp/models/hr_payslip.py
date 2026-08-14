from odoo import models, fields,api


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def get_report_values(self):

        payslip_allowances = self.env['hr.payslip.line'].search([
            ('slip_id', '=', self.id),
            ('category_id.code', 'in', ['ALW','BASIC'])
        ])
        payslip_deductions = self.env['hr.payslip.line'].search([
            ('slip_id', '=', self.id),
            ('category_id.code', '=', 'DED')
        ])
        earnings = []
        for line in payslip_allowances:
            allowance_key = line.name
            allowance_amount = "{:.2f}".format(abs(line.total))
            earnings.append({allowance_key: {'amount': allowance_amount}})

        deductions = {}
        for line in payslip_deductions:
            deduction_key = line.name
            deduction_amount = "{:.2f}".format(abs(line.total))
            deductions[deduction_key] = {'amount': deduction_amount}
        report_data = []
        i = 0
        j = 0
        for dic in earnings:
            for key in dic:
                i = i + 1
                deduction = ''
                deduction_amount = ''
                while j < len(list(deductions.keys())):
                    deduction = list(deductions.keys())[j]
                    deduction_amount = deductions.get(list(deductions.keys())[j]).get('amount')
                    j = j + 1
                    break
                report_data.append(
                    {'earnings': key, 'amount': dic[key]['amount'],'deductions': deduction, 'deduction_amount': deduction_amount})
        deduction = ''
        deduction_amount = ''
        while j < len(list(deductions.keys())):
            deduction = list(deductions.keys())[j]
            deduction_amount = deductions.get(list(deductions.keys())[j]).get('amount')
            report_data.append({'earnings': ' ', 'amount': ' ', 'deductions': deduction,'deduction_amount': deduction_amount})
            j = j + 1
        return report_data

    def amount_to_words(self, net):
        return self.company_id.currency_id.amount_to_text(net)







