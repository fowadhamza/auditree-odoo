# -*- coding: utf-8 -*-
import base64
import io

import xlsxwriter

from odoo import models, fields


class ForecastExportWizard(models.TransientModel):
    _name = 'forecast.export.wizard'
    _description = 'Forecast Excel Export'

    file_data = fields.Binary(readonly=True)
    file_name = fields.Char(readonly=True)

    def action_generate(self):
        self.ensure_one()
        config = self.env['forecast.config'].get_config()
        lines = self.env['forecast.monthly.line'].search([], order='month, line_type')
        cash_months = self.env['forecast.cash.flow.month'].search([], order='month')
        line_type_labels = dict(lines._fields['line_type'].selection) if lines \
            else dict(self.env['forecast.monthly.line']._fields['line_type'].selection)

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        bold = workbook.add_format({'bold': True})
        money_fmt = workbook.add_format({'num_format': '#,##0'})

        info_sheet = workbook.add_worksheet('Info')
        info_sheet.write(0, 0, 'Forecast window', bold)
        info_sheet.write(0, 1, '%s to %s' % (config.window_start, config.window_end))
        info_sheet.write(1, 0, 'Exported at', bold)
        info_sheet.write(1, 1, str(fields.Datetime.now()))
        info_sheet.write(2, 0, 'Last recalculated', bold)
        info_sheet.write(2, 1, str(config.last_recomputed or 'never - run Recalculate first'))

        pl_sheet = workbook.add_worksheet('P&L')
        headers = ['Month', 'Type', 'Category', 'Employee', 'Client', 'Direction', 'Amount']
        for col, header in enumerate(headers):
            pl_sheet.write(0, col, header, bold)
        row = 1
        for line in lines:
            pl_sheet.write(row, 0, line.month.strftime('%b-%y'))
            pl_sheet.write(row, 1, line_type_labels.get(line.line_type))
            pl_sheet.write(row, 2, line.category or '')
            pl_sheet.write(row, 3, line.employee_id.name or '')
            pl_sheet.write(row, 4, line.client_id.name or '')
            pl_sheet.write(row, 5, line.direction)
            pl_sheet.write_number(row, 6, line.amount, money_fmt)
            row += 1

        cf_sheet = workbook.add_worksheet('Cash Flow')
        cf_headers = ['Month', 'Opening', 'Inflow', 'Outflow', 'Net Change', 'Closing']
        for col, header in enumerate(cf_headers):
            cf_sheet.write(0, col, header, bold)
        row = 1
        for cm in cash_months:
            cf_sheet.write(row, 0, cm.month.strftime('%b-%y'))
            cf_sheet.write_number(row, 1, cm.opening_balance, money_fmt)
            cf_sheet.write_number(row, 2, cm.total_inflow, money_fmt)
            cf_sheet.write_number(row, 3, cm.total_outflow, money_fmt)
            cf_sheet.write_number(row, 4, cm.net_change, money_fmt)
            cf_sheet.write_number(row, 5, cm.closing_balance, money_fmt)
            row += 1

        workbook.close()
        output.seek(0)

        self.file_data = base64.b64encode(output.read())
        self.file_name = 'Forecast_%s_to_%s.xlsx' % (config.window_start, config.window_end)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'forecast.export.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
