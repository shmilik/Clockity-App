"""
direct_migrate.py
=================
Copies all data from SQLite to PostgreSQL using raw sqlite3 + psycopg2.
No Flask-SQLAlchemy involved — avoids engine-caching bugs.

Usage (on the server):
    DATABASE_URL=postgresql://jobuser:Clockity2026@localhost/jobtracker \
        .venv/bin/python3 direct_migrate.py
"""

import os
import sys
import sqlite3

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2-binary not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
SQLITE_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'workforce.db')
PG_URL = os.environ.get('DATABASE_URL', '')

if not PG_URL:
    print("ERROR: DATABASE_URL environment variable is not set.")
    sys.exit(1)

print(f"\n{'='*60}")
print(f"  Source: {SQLITE_PATH}")
print(f"  Target: {PG_URL[:PG_URL.rfind('@')+1]}***")
print(f"{'='*60}\n")

# ── Connect ───────────────────────────────────────────────────────────────────
sqlite_conn = sqlite3.connect(SQLITE_PATH)
sqlite_conn.row_factory = sqlite3.Row
sc = sqlite_conn.cursor()

pg_conn = psycopg2.connect(PG_URL)
pg_conn.autocommit = False
pc = pg_conn.cursor()

# ── Helpers ───────────────────────────────────────────────────────────────────
def sqlite_tables():
    sc.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return {row[0] for row in sc.fetchall()}

def sqlite_columns(table):
    sc.execute(f"PRAGMA table_info(\"{table}\")")
    return [row[1] for row in sc.fetchall()]

def pg_table_exists(table):
    pc.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
        (table,)
    )
    return pc.fetchone() is not None

def truncate_all():
    """Truncate every table that exists in PG, in correct FK order (cascade handles the rest)."""
    tables = [
        'audit_log', 'invite_code', 'password_reset_token', 'feedback_report',
        'time_off_request', 'job_archive', 'job_deletion_log',
        'payroll_adjustment', 'timesheet', 'assignment', 'job',
        'employee', '"group"', 'permission_set', 'department',
    ]
    for t in tables:
        bare = t.strip('"')
        if pg_table_exists(bare):
            pc.execute(f'TRUNCATE TABLE {t} CASCADE')
    pg_conn.commit()
    print("  All tables truncated.\n")

def pg_bool_columns(pg_table):
    """Return set of column names that are boolean in PostgreSQL."""
    bare = pg_table.strip('"')
    pc.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND data_type='boolean'
    """, (bare,))
    return {row[0] for row in pc.fetchall()}

def pg_int_columns(pg_table):
    """Return set of column names that are integer in PostgreSQL."""
    bare = pg_table.strip('"')
    pc.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        AND data_type IN ('integer','bigint','smallint')
    """, (bare,))
    return {row[0] for row in pc.fetchall()}

def copy_table(sqlite_table, pg_table=None):
    """Copy every row from sqlite_table into pg_table (defaults to same name)."""
    if pg_table is None:
        pg_table = sqlite_table

    existing_tables = sqlite_tables()
    if sqlite_table not in existing_tables:
        print(f"  {sqlite_table}: not in SQLite (skipping)")
        return

    bare_pg = pg_table.strip('"')
    if not pg_table_exists(bare_pg):
        print(f"  {pg_table}: not in PostgreSQL (skipping)")
        return

    cols = sqlite_columns(sqlite_table)
    if not cols:
        print(f"  {sqlite_table}: no columns (skipping)")
        return

    bool_cols = pg_bool_columns(pg_table)
    int_cols  = pg_int_columns(pg_table)

    sc.execute(f'SELECT * FROM "{sqlite_table}"')
    rows = sc.fetchall()

    if not rows:
        print(f"  {sqlite_table}: 0 rows")
        return

    col_list = ', '.join(f'"{c}"' for c in cols)
    placeholders = ', '.join(['%s'] * len(cols))
    sql = f'INSERT INTO {pg_table} ({col_list}) VALUES ({placeholders})'

    def coerce(col, val):
        if col in bool_cols:
            if val is None:
                return None
            return bool(int(val))
        if col in int_cols:
            if val == '' or val is None:
                return None
            return int(val)
        return val

    inserted = 0
    skipped = 0
    for row in rows:
        try:
            coerced = tuple(coerce(cols[i], row[i]) for i in range(len(cols)))
            pc.execute(sql, coerced)
            pg_conn.commit()
            inserted += 1
        except Exception as e:
            pg_conn.rollback()
            skipped += 1
            print(f"    Skipped row (id={row[0]}): {e}")
    print(f"  {sqlite_table}: {inserted} rows inserted" + (f", {skipped} skipped" if skipped else ""))

def reset_sequences():
    """Set each sequence to the current MAX(id) so new rows don't conflict."""
    pairs = [
        ('department',            'department_id_seq'),
        ('permission_set',        'permission_set_id_seq'),
        ('"group"',               'group_id_seq'),
        ('employee',              'employee_id_seq'),
        ('job',                   'job_id_seq'),
        ('assignment',            'assignment_id_seq'),
        ('timesheet',             'timesheet_id_seq'),
        ('payroll_adjustment',    'payroll_adjustment_id_seq'),
        ('job_deletion_log',      'job_deletion_log_id_seq'),
        ('job_archive',           'job_archive_id_seq'),
        ('time_off_request',      'time_off_request_id_seq'),
        ('feedback_report',       'feedback_report_id_seq'),
        ('password_reset_token',  'password_reset_token_id_seq'),
        ('invite_code',           'invite_code_id_seq'),
        ('audit_log',             'audit_log_id_seq'),
    ]
    for table, seq in pairs:
        bare = table.strip('"')
        if not pg_table_exists(bare):
            continue
        try:
            pc.execute(f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {table}), 1))")
            pg_conn.commit()
            print(f"  Reset {seq}")
        except Exception as e:
            pg_conn.rollback()
            print(f"  Skipped {seq}: {e}")

# ── Run ───────────────────────────────────────────────────────────────────────
print("Truncating PostgreSQL tables...")
truncate_all()

print("Copying data...")
# Order matters — parents before children
copy_table('department')
copy_table('permission_set')
copy_table('group', '"group"')   # group is a reserved word in PG
copy_table('employee')
copy_table('job')
copy_table('assignment')
copy_table('timesheet')
copy_table('payroll_adjustment')
copy_table('job_deletion_log')
copy_table('job_archive')
copy_table('time_off_request')
copy_table('feedback_report')
copy_table('password_reset_token')
copy_table('invite_code')
copy_table('audit_log')

print("\nResetting sequences...")
reset_sequences()

sqlite_conn.close()
pg_conn.close()

print("\n✅  Migration complete! PostgreSQL is now populated from SQLite.\n")
