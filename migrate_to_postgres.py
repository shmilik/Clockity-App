"""
migrate_to_postgres.py
======================
Copies all data from the local SQLite database into a PostgreSQL database.

Usage:
    Set DATABASE_URL to your PostgreSQL connection string, then run:

    Windows PowerShell:
        $env:DATABASE_URL = "postgresql://user:password@host:5432/dbname"
        python migrate_to_postgres.py

    Linux / Mac:
        DATABASE_URL="postgresql://user:password@host:5432/dbname" python migrate_to_postgres.py

The script will:
  1. Create all tables in PostgreSQL (via SQLAlchemy models)
  2. Copy every row from SQLite to PostgreSQL
  3. Reset all PostgreSQL auto-increment sequences so new rows get correct IDs
"""

import os
import sys

# ── Make sure psycopg2 is available ──────────────────────────────────────────
try:
    import psycopg2  # noqa: F401
except ImportError:
    print("ERROR: psycopg2-binary is not installed.")
    print("Run:  pip install psycopg2-binary")
    sys.exit(1)

# ── Validate environment variable ────────────────────────────────────────────
pg_url = os.environ.get('DATABASE_URL', '')
if not pg_url:
    print("ERROR: DATABASE_URL environment variable is not set.")
    print("Example:  $env:DATABASE_URL = 'postgresql://user:pass@host:5432/dbname'")
    sys.exit(1)
if pg_url.startswith('postgres://'):
    pg_url = pg_url.replace('postgres://', 'postgresql://', 1)

# ── Import app and models ─────────────────────────────────────────────────────
# Force SQLite for the source connection before importing app
os.environ.pop('DATABASE_URL', None)
from app import (
    app as flask_app, db,
    Department, Group, PermissionSet, Employee,
    Job, Assignment, Timesheet, PayrollAdjustment,
    JobDeletionLog, JobArchive, FeedbackReport,
    PasswordResetToken, InviteCode
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

SQLITE_URI = 'sqlite:///' + os.path.join(flask_app.instance_path, 'workforce.db')

print(f"\n{'='*60}")
print(f"  Source SQLite : {SQLITE_URI}")
print(f"  Target PG     : {pg_url[:pg_url.rfind('@')+1]}***")
print(f"{'='*60}\n")

# ── Read all data from SQLite ─────────────────────────────────────────────────
print("Reading data from SQLite...")

sqlite_engine = create_engine(SQLITE_URI)

with flask_app.app_context():
    # Temporarily point the app at SQLite to read data
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = SQLITE_URI
    db.engine.dispose()

    def read_all(model):
        with Session(db.engine) as s:
            return s.query(model).all()

    departments      = read_all(Department)
    groups           = read_all(Group)
    permission_sets  = read_all(PermissionSet)
    employees        = read_all(Employee)
    jobs             = read_all(Job)
    assignments      = read_all(Assignment)
    timesheets       = read_all(Timesheet)
    payroll_adjs     = read_all(PayrollAdjustment)
    deletion_logs    = read_all(JobDeletionLog)
    archives         = read_all(JobArchive)
    feedback_reports = read_all(FeedbackReport)
    reset_tokens     = read_all(PasswordResetToken)
    invite_codes     = read_all(InviteCode)

print(f"  Departments    : {len(departments)}")
print(f"  Groups         : {len(groups)}")
print(f"  PermissionSets : {len(permission_sets)}")
print(f"  Employees      : {len(employees)}")
print(f"  Jobs           : {len(jobs)}")
print(f"  Assignments    : {len(assignments)}")
print(f"  Timesheets     : {len(timesheets)}")
print(f"  PayrollAdjs    : {len(payroll_adjs)}")
print(f"  DeletionLogs   : {len(deletion_logs)}")
print(f"  Archives       : {len(archives)}")
print(f"  FeedbackReports: {len(feedback_reports)}")
print(f"  ResetTokens    : {len(reset_tokens)}")
print(f"  InviteCodes    : {len(invite_codes)}")

# ── Connect to PostgreSQL and create schema ───────────────────────────────────
print("\nConnecting to PostgreSQL and creating tables...")

with flask_app.app_context():
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = pg_url
    db.engine.dispose()
    db.create_all()
    print("  Tables created.")

    pg_session = db.session

    def insert_rows(model, rows, label):
        if not rows:
            print(f"  {label}: nothing to migrate")
            return
        for row in rows:
            db.session.merge(row)
        db.session.commit()
        print(f"  {label}: {len(rows)} rows inserted")

    print("\nMigrating data...")
    insert_rows(Department,       departments,      "Department")
    insert_rows(PermissionSet,    permission_sets,  "PermissionSet")
    insert_rows(Group,            groups,           "Group")
    insert_rows(Employee,         employees,        "Employee")
    insert_rows(Job,              jobs,             "Job")
    insert_rows(Assignment,       assignments,      "Assignment")
    insert_rows(Timesheet,        timesheets,       "Timesheet")
    insert_rows(PayrollAdjustment,payroll_adjs,     "PayrollAdjustment")
    insert_rows(JobDeletionLog,   deletion_logs,    "JobDeletionLog")
    insert_rows(JobArchive,       archives,         "JobArchive")
    insert_rows(FeedbackReport,   feedback_reports, "FeedbackReport")
    insert_rows(PasswordResetToken,reset_tokens,    "PasswordResetToken")
    insert_rows(InviteCode,       invite_codes,     "InviteCode")

    # ── Fix sequences so new auto-increment IDs don't collide ────────────────
    print("\nResetting PostgreSQL sequences...")
    sequence_tables = [
        ('department', 'department_id_seq'),
        ('"group"',    'group_id_seq'),
        ('permission_set', 'permission_set_id_seq'),
        ('employee',   'employee_id_seq'),
        ('job',        'job_id_seq'),
        ('assignment', 'assignment_id_seq'),
        ('timesheet',  'timesheet_id_seq'),
        ('payroll_adjustment', 'payroll_adjustment_id_seq'),
        ('job_deletion_log', 'job_deletion_log_id_seq'),
        ('job_archive', 'job_archive_id_seq'),
        ('feedback_report', 'feedback_report_id_seq'),
        ('password_reset_token', 'password_reset_token_id_seq'),
        ('invite_code', 'invite_code_id_seq'),
    ]
    with db.engine.begin() as conn:
        for table, seq in sequence_tables:
            try:
                conn.execute(text(
                    f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {table}), 1))"
                ))
                print(f"  Reset {seq}")
            except Exception as e:
                print(f"  Skipped {seq}: {e}")

print("\n✅  Migration complete! Your PostgreSQL database is ready.")
print("    Set DATABASE_URL on your server and start the app normally.\n")
