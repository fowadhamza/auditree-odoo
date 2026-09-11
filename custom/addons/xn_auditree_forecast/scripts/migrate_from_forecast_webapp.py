# -*- coding: utf-8 -*-
"""One-off data migration from the standalone Auditree Forecast web app
(Next.js/Prisma/Postgres) into this Odoo module.

Usage (from auditreelive-server/, with Odoo stopped so the DB isn't locked):

    export FORECAST_SOURCE_DATABASE_URL="<the DATABASE_URL value from forecast-webapp/.env>"
    python3 odoo-bin shell --config=/home/fowadhamza/Projects/Auditree/local-dev.conf \\
        -d AUDITREE_LIVE_NEW \\
        < /home/fowadhamza/Projects/Auditree/custom/addons/xn_auditree_forecast/scripts/migrate_from_forecast_webapp.py

Never hardcode the source DSN in this file - it must only ever come from the
FORECAST_SOURCE_DATABASE_URL environment variable, set by hand in your shell,
so the credential never gets committed to git.

Set FORECAST_MIGRATION_WIPE_FIRST=1 to delete any existing forecast.* records
before importing (useful to re-run this cleanly during testing).

Not migrated: CustomField (no equivalent model in this module yet).
"""
import os

import psycopg2
import psycopg2.extras

FORECAST_MODELS_TO_WIPE = [
    'forecast.monthly.line',
    'forecast.cash.flow.month',
    'forecast.revenue.override',
    'forecast.revenue.assignment',
    'forecast.salary.plan',
    'forecast.expense.line',
    'forecast.cash.movement',
    'forecast.financial.adjustment',
    'forecast.employee',
    'forecast.client',
]


def val_or_false(value):
    return value if value is not None else False


def as_date(value):
    if value is None:
        return False
    return value.date() if hasattr(value, 'date') else value


SYSTEM_CA_BUNDLE = '/etc/ssl/certs/ca-certificates.crt'


def get_source_connection():
    dsn = os.environ.get('FORECAST_SOURCE_DATABASE_URL')
    if not dsn:
        raise SystemExit(
            "Set FORECAST_SOURCE_DATABASE_URL to the forecast-webapp DATABASE_URL "
            "before running this script.")
    # Neon's DSN uses sslmode=verify-full, which needs a trusted CA bundle;
    # libpq's default ~/.postgresql/root.crt usually doesn't exist, so point it
    # at the system bundle instead of weakening the SSL verification mode.
    kwargs = {}
    if os.path.exists(SYSTEM_CA_BUNDLE):
        kwargs['sslrootcert'] = SYSTEM_CA_BUNDLE
    return psycopg2.connect(dsn, **kwargs)


def fetch_all(cr, table):
    cr.execute('SELECT * FROM "%s"' % table)
    return cr.fetchall()


def get_or_activate_currency(env, code):
    Currency = env['res.currency'].with_context(active_test=False)
    currency = Currency.search([('name', '=', code)], limit=1)
    if currency and not currency.active:
        currency.active = True
    return currency


def run(env):
    if os.environ.get('FORECAST_MIGRATION_WIPE_FIRST') == '1':
        print('Wiping existing forecast.* records first...')
        for model in FORECAST_MODELS_TO_WIPE:
            env[model].sudo().search([]).unlink()

    conn = get_source_connection()
    conn.set_session(readonly=True, autocommit=True)
    cr = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    employee_map = {}
    client_map = {}
    revenue_assignment_map = {}

    # -- Employees --------------------------------------------------------
    rows = fetch_all(cr, 'Employee')
    for row in rows:
        rec = env['forecast.employee'].create({
            'name': row['name'],
            'auditree_title': val_or_false(row['auditreeTitle']),
            'client_role': val_or_false(row['clientRole']),
            'employee_type': row['employeeType'],
            'start_date': as_date(row['startDate']),
            'end_date': as_date(row['endDate']),
            'active': row['active'],
        })
        employee_map[row['id']] = rec.id
    print('Employees migrated: %d' % len(rows))

    # -- Clients ------------------------------------------------------------
    rows = fetch_all(cr, 'Client')
    for row in rows:
        rec = env['forecast.client'].create({
            'name': row['name'],
            'category': val_or_false(row['category']),
            'account_owner': val_or_false(row['accountOwner']),
        })
        client_map[row['id']] = rec.id
    print('Clients migrated: %d' % len(rows))

    # -- Revenue assignments --------------------------------------------------
    rows = fetch_all(cr, 'RevenueAssignment')
    for row in rows:
        currency = get_or_activate_currency(env, row['currency'] or 'INR')
        rec = env['forecast.revenue.assignment'].create({
            'employee_id': employee_map[row['employeeId']],
            'client_id': client_map[row['clientId']],
            'bill_rate': row['billRate'],
            'currency_id': currency.id if currency else env.company.currency_id.id,
            'exchange_rate': row['exchangeRate'],
            'allocation_pct': row['allocationPct'],
            'start_month': as_date(row['startMonth']),
            'end_month': as_date(row['endMonth']),
        })
        revenue_assignment_map[row['id']] = rec.id
    print('Revenue assignments migrated: %d' % len(rows))

    # -- Revenue overrides ----------------------------------------------------
    rows = fetch_all(cr, 'RevenueOverride')
    for row in rows:
        env['forecast.revenue.override'].create({
            'revenue_assignment_id': revenue_assignment_map[row['revenueAssignmentId']],
            'month': as_date(row['month']),
            'amount': row['amount'],
            'reason': val_or_false(row['reason']),
        })
    print('Revenue overrides migrated: %d' % len(rows))

    # -- Salary plans -----------------------------------------------------------
    rows = fetch_all(cr, 'SalaryPlan')
    for row in rows:
        env['forecast.salary.plan'].create({
            'employee_id': employee_map[row['employeeId']],
            'fixed_ctc': row['fixedCtc'],
            'variable_ctc': row['variableCtc'],
            'effective_date': as_date(row['effectiveDate']),
            'end_date': as_date(row['endDate']),
            'hike_pct': val_or_false(row['hikePct']),
            'next_review_date': as_date(row['nextReviewDate']),
        })
    print('Salary plans migrated: %d' % len(rows))

    # -- Expense line items -----------------------------------------------------
    rows = fetch_all(cr, 'ExpenseLineItem')
    for row in rows:
        env['forecast.expense.line'].create({
            'name': row['name'],
            'category': val_or_false(row['category']),
            'annual_total': row['annualTotal'],
            'recurrence': row['recurrence'],
            'start_month': as_date(row['startMonth']),
            'end_month': as_date(row['endMonth']),
        })
    print('Expense line items migrated: %d' % len(rows))

    # -- Other cash movements -----------------------------------------------------
    rows = fetch_all(cr, 'OtherCashMovement')
    for row in rows:
        env['forecast.cash.movement'].create({
            'date': as_date(row['date']),
            'movement_type': row['type'],
            'amount': row['amount'],
            'category': val_or_false(row['category']),
            'description': val_or_false(row['description']),
        })
    print('Other cash movements migrated: %d' % len(rows))

    # -- Financial adjustments -----------------------------------------------------
    rows = fetch_all(cr, 'FinancialAdjustment')
    for row in rows:
        env['forecast.financial.adjustment'].create({
            'month': as_date(row['month']),
            'adjustment_type': row['type'],
            'amount': row['amount'],
            'notes': val_or_false(row['notes']),
        })
    print('Financial adjustments migrated: %d' % len(rows))

    # -- Forecast window -----------------------------------------------------------
    cr.execute('SELECT * FROM forecast_window ORDER BY "advancedAt" DESC LIMIT 1')
    window_row = cr.fetchone()
    config = env['forecast.config'].get_config()
    if window_row:
        config.write({
            'window_start': as_date(window_row['startMonth']),
            'window_end': as_date(window_row['endMonth']),
        })
        print('Forecast window set to %s - %s' % (config.window_start, config.window_end))
    else:
        print('No ForecastWindow row found; keeping the default window.')

    cr.close()
    conn.close()

    print('Recalculating monthly lines and cash flow...')
    config.action_recalculate()
    env.cr.commit()
    print('Done.')


run(env)  # noqa: F821 - `env` is injected by `odoo-bin shell`
