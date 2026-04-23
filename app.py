from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, make_response, send_from_directory
import math
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from sqlalchemy import inspect, text
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
import atexit
import csv
import io
import json
import os
import re
import secrets
import shutil

app = Flask(__name__)
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///workforce.db')
# Render/Heroku supply 'postgres://' — SQLAlchemy requires 'postgresql://'
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'jt-9x#Kv!mQ2@rLpZ8nWdYeT6uAsCbG4hF0iXoNjU1yVk7wE3')
# Session security hardening
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
# Trust X-Forwarded-Proto/Host from Nginx so url_for(_external=True) generates https://
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ── Rate limiter (graceful fallback if flask-limiter not installed) ────────────
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(app=app, key_func=get_remote_address, default_limits=[])
except ImportError:
    limiter = None

DEVELOPER_LOGIN_USERNAME = '.Dev'
DEVELOPER_LOGIN_PASSWORD = 'Unicity123'

PERMISSION_KEYS = [
    'can_view_dashboard',
    'can_view_calendar',
    'can_view_jobs',
    'can_view_management',
    'can_view_payroll',
    'can_manage_employees',
    'can_manage_jobs',
    'can_manage_assignments',
    'can_manage_permissions'
]

AUTO_DELETE_JOB_DAYS = 120
_last_auto_purge_run = None
FEEDBACK_SNAPSHOT_PATH = os.path.join(app.root_path, 'feedback_reports_snapshot.json')
EMPLOYEE_SNAPSHOT_PATH = os.path.join(app.root_path, 'employees_snapshot.json')
JOB_SNAPSHOT_PATH = os.path.join(app.root_path, 'jobs_snapshot.json')


def backup_database_on_startup(keep_latest=20):
    # Skip file-based backup when using PostgreSQL
    if not app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        return
    db_path = os.path.join(app.instance_path, 'workforce.db')
    if not os.path.exists(db_path):
        return

    backup_dir = os.path.join(app.instance_path, 'backups')
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_path = os.path.join(backup_dir, f'workforce-{timestamp}.db')

    try:
        shutil.copy2(db_path, backup_path)
    except OSError as error:
        print(f'Warning: could not back up database on startup: {error}')
        return

    backup_files = sorted(
        [
            os.path.join(backup_dir, name)
            for name in os.listdir(backup_dir)
            if name.startswith('workforce-') and name.endswith('.db')
        ],
        key=os.path.getmtime,
        reverse=True
    )

    for old_backup in backup_files[keep_latest:]:
        try:
            os.remove(old_backup)
        except OSError:
            pass


def save_feedback_snapshot():
    reports = FeedbackReport.query.order_by(FeedbackReport.id.asc()).all()
    payload = []

    for report in reports:
        payload.append({
            'report_type': report.report_type,
            'subject': report.subject,
            'details': report.details,
            'submitted_by': report.submitted_by,
            'submitted_at': report.submitted_at.isoformat() if report.submitted_at else None,
            'status': (report.status or 'received'),
            'opened_at': report.opened_at.isoformat() if report.opened_at else None,
            'opened_by': report.opened_by,
            'closed_at': report.closed_at.isoformat() if report.closed_at else None,
            'closed_by': report.closed_by,
            'resolved': bool(report.resolved),
            'resolved_at': report.resolved_at.isoformat() if report.resolved_at else None,
            'reply': report.reply or None
        })

    try:
        with open(FEEDBACK_SNAPSHOT_PATH, 'w', encoding='utf-8') as snapshot_file:
            json.dump(payload, snapshot_file, ensure_ascii=True, indent=2)
    except OSError as error:
        print(f'Warning: could not save feedback snapshot: {error}')


def restore_feedback_from_snapshot_if_needed():
    if not os.path.exists(FEEDBACK_SNAPSHOT_PATH):
        return

    try:
        with open(FEEDBACK_SNAPSHOT_PATH, 'r', encoding='utf-8') as snapshot_file:
            payload = json.load(snapshot_file)
    except (OSError, json.JSONDecodeError) as error:
        print(f'Warning: could not load feedback snapshot: {error}')
        return

    if not isinstance(payload, list):
        return

    restored = 0
    for item in payload:
        if not isinstance(item, dict):
            continue

        report_type = (item.get('report_type') or '').strip()
        subject = (item.get('subject') or '').strip()
        details = (item.get('details') or '').strip()
        if report_type not in ('bug', 'feedback'):
            continue
        if not subject or not details:
            continue

        submitted_at = None
        opened_at = None
        resolved_at = None
        closed_at = None
        submitted_at_raw = item.get('submitted_at')
        opened_at_raw = item.get('opened_at')
        resolved_at_raw = item.get('resolved_at')
        closed_at_raw = item.get('closed_at')
        if submitted_at_raw:
            try:
                submitted_at = datetime.fromisoformat(submitted_at_raw)
            except (TypeError, ValueError):
                submitted_at = datetime.utcnow()
        if opened_at_raw:
            try:
                opened_at = datetime.fromisoformat(opened_at_raw)
            except (TypeError, ValueError):
                opened_at = None
        if resolved_at_raw:
            try:
                resolved_at = datetime.fromisoformat(resolved_at_raw)
            except (TypeError, ValueError):
                resolved_at = None
        if closed_at_raw:
            try:
                closed_at = datetime.fromisoformat(closed_at_raw)
            except (TypeError, ValueError):
                closed_at = None

        status = (item.get('status') or '').strip().lower()
        if status not in {'received', 'open', 'closed'}:
            status = 'closed' if bool(item.get('resolved')) else 'open'

        existing = FeedbackReport.query.filter_by(
            subject=subject[:200],
            submitted_by=(item.get('submitted_by') or None)
        ).first()
        if existing is None:
            report = FeedbackReport(
                report_type=report_type,
                subject=subject[:200],
                details=details[:2000],
                submitted_by=(item.get('submitted_by') or None),
                submitted_at=submitted_at or datetime.utcnow(),
                status=status,
                opened_at=opened_at,
                opened_by=(item.get('opened_by') or None),
                closed_at=closed_at,
                closed_by=(item.get('closed_by') or None),
                resolved=bool(item.get('resolved')),
                resolved_at=resolved_at,
                reply=(item.get('reply') or None)
            )
            db.session.add(report)
            restored += 1

    if restored:
        db.session.commit()


def save_feedback_snapshot_on_exit():
    with app.app_context():
        save_feedback_snapshot()


def save_core_data_snapshots():
    employees = Employee.query.order_by(Employee.id.asc()).all()
    employee_payload = []
    for employee in employees:
        employee_payload.append({
            'id': employee.id,
            'name': employee.name,
            'category': employee.category,
            'phone_number': employee.phone_number,
            'email': employee.email,
            'password_hash': employee.password_hash,
            'group_id': employee.group_id,
            'group_name': employee.group.name if employee.group else None,
            'permission_set_id': employee.permission_set_id,
            'permission_set_name': employee.permission_set.name if employee.permission_set else None
        })

    jobs = Job.query.filter(Job.is_internal.isnot(True)).order_by(Job.id.asc()).all()
    job_payload = []
    for job in jobs:
        job_payload.append({
            'id': job.id,
            'created_at': job.created_at.isoformat() if job.created_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'job_name': job.job_name,
            'job_type': job.job_type,
            'status': job.status,
            'published': bool(job.published),
            'po_number': job.po_number,
            'address': job.address,
            'phone_number': job.phone_number,
            'story': job.story,
            'description': job.description,
            'system_size': job.system_size,
            'cancel_reason': job.cancel_reason,
            'pending_date': job.pending_date.isoformat() if job.pending_date else None,
            'scheduled_date': job.scheduled_date.isoformat() if job.scheduled_date else None
        })

    try:
        with open(EMPLOYEE_SNAPSHOT_PATH, 'w', encoding='utf-8') as employee_file:
            json.dump(employee_payload, employee_file, ensure_ascii=True, indent=2)
        with open(JOB_SNAPSHOT_PATH, 'w', encoding='utf-8') as job_file:
            json.dump(job_payload, job_file, ensure_ascii=True, indent=2)
    except OSError as error:
        print(f'Warning: could not save core data snapshots: {error}')


def restore_core_data_from_snapshots_if_needed():
    def _load_json(path):
        if not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as json_file:
                payload = json.load(json_file)
        except (OSError, json.JSONDecodeError) as error:
            print(f'Warning: could not load snapshot {path}: {error}')
            return []
        return payload if isinstance(payload, list) else []

    employee_payload = _load_json(EMPLOYEE_SNAPSHOT_PATH)
    restored_employee_count = 0
    for item in employee_payload:
        if not isinstance(item, dict):
            continue

        name = (item.get('name') or '').strip()
        if not name:
            continue

        if Employee.query.filter_by(name=name).first() is not None:
            continue

        group = None
        group_name = (item.get('group_name') or '').strip()
        if group_name:
            group = Group.query.filter_by(name=group_name).first()
        if not group and item.get('group_id'):
            group = Group.query.get(item.get('group_id'))

        permission_set = None
        permission_set_name = (item.get('permission_set_name') or '').strip()
        if permission_set_name:
            permission_set = PermissionSet.query.filter_by(name=permission_set_name).first()
        if not permission_set and item.get('permission_set_id'):
            permission_set = PermissionSet.query.get(item.get('permission_set_id'))

        employee = Employee(
            name=name,
            category=item.get('category') or '',
            phone_number=item.get('phone_number') or '',
            email=item.get('email') or '',
            password_hash=item.get('password_hash') or None,
            group_id=group.id if group else None,
            permission_set_id=permission_set.id if permission_set else None
        )
        db.session.add(employee)
        restored_employee_count += 1

    if restored_employee_count:
        db.session.commit()

    job_payload = _load_json(JOB_SNAPSHOT_PATH)
    restored_job_count = 0
    for item in job_payload:
        if not isinstance(item, dict):
            continue

        job_name = (item.get('job_name') or '').strip()
        if not job_name:
            continue

        po_number = item.get('po_number') or None
        created_at_raw = item.get('created_at') or ''
        created_day = created_at_raw[:10] if created_at_raw else ''

        # Deduplicate: match by po_number if present, else by name + creation date
        if po_number:
            existing_job = Job.query.filter_by(po_number=po_number).first()
        elif created_day:
            existing_job = Job.query.filter(
                Job.job_name == job_name,
                db.func.substr(db.cast(Job.created_at, db.String), 1, 10) == created_day
            ).first()
        else:
            existing_job = Job.query.filter_by(job_name=job_name).first()

        if existing_job is not None:
            continue

        created_at = None
        completed_at = None
        pending_date = None
        scheduled_date = None

        completed_at_raw = item.get('completed_at')
        pending_date_raw = item.get('pending_date')
        scheduled_date_raw = item.get('scheduled_date')

        if created_at_raw:
            try:
                created_at = datetime.fromisoformat(created_at_raw)
            except (TypeError, ValueError):
                created_at = datetime.utcnow()
        if completed_at_raw:
            try:
                completed_at = datetime.fromisoformat(completed_at_raw)
            except (TypeError, ValueError):
                completed_at = None
        if pending_date_raw:
            try:
                pending_date = datetime.fromisoformat(pending_date_raw).date()
            except (TypeError, ValueError):
                pending_date = None
        if scheduled_date_raw:
            try:
                scheduled_date = datetime.fromisoformat(scheduled_date_raw).date()
            except (TypeError, ValueError):
                scheduled_date = None

        job = Job(
            created_at=created_at or datetime.utcnow(),
            completed_at=completed_at,
            job_name=job_name,
            job_type=(item.get('job_type') or 'Solar Install'),
            status=(item.get('status') or 'not_started'),
            published=bool(item.get('published')),
            po_number=po_number,
            address=item.get('address') or None,
            phone_number=item.get('phone_number') or None,
            story=item.get('story') or None,
            description=item.get('description') or None,
            system_size=item.get('system_size') or None,
            cancel_reason=item.get('cancel_reason') or None,
            pending_date=pending_date,
            scheduled_date=scheduled_date
        )
        db.session.add(job)
        restored_job_count += 1

    if restored_job_count:
        db.session.commit()


def save_core_data_snapshots_on_exit():
    with app.app_context():
        save_core_data_snapshots()


@app.after_request
def update_snapshots_after_mutation(response):
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        try:
            save_core_data_snapshots()
            save_feedback_snapshot()
        except Exception as error:
            print(f'Warning: snapshot update skipped: {error}')
    return response


def ensure_schema_updates():
    inspector = inspect(db.engine)
    schema_updates = {
        'permission_set': {
            'can_view_payroll': "ALTER TABLE permission_set ADD COLUMN IF NOT EXISTS can_view_payroll BOOLEAN DEFAULT FALSE"
        },
        'group': {
            'color': "ALTER TABLE \"group\" ADD COLUMN IF NOT EXISTS color VARCHAR(7) DEFAULT '#667eea'",
            'permission_set_id': "ALTER TABLE \"group\" ADD COLUMN IF NOT EXISTS permission_set_id INTEGER",
            'city': "ALTER TABLE \"group\" ADD COLUMN IF NOT EXISTS city VARCHAR(100)"
        },
        'employee': {
            'category': "ALTER TABLE employee ADD COLUMN IF NOT EXISTS category VARCHAR(50) DEFAULT 'Installer'",
            'phone_number': "ALTER TABLE employee ADD COLUMN IF NOT EXISTS phone_number VARCHAR(50)",
            'email': "ALTER TABLE employee ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
            'password_hash': "ALTER TABLE employee ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
            'permission_set_id': "ALTER TABLE employee ADD COLUMN IF NOT EXISTS permission_set_id INTEGER",
            'first_login': "ALTER TABLE employee ADD COLUMN IF NOT EXISTS first_login BOOLEAN DEFAULT TRUE"
        },
        'assignment': {
            'crew_id': "ALTER TABLE assignment ADD COLUMN IF NOT EXISTS crew_id INTEGER",
            'day_pay': "ALTER TABLE assignment ADD COLUMN IF NOT EXISTS day_pay BOOLEAN DEFAULT FALSE"
        },
        'job': {
            'created_at': "ALTER TABLE job ADD COLUMN IF NOT EXISTS created_at TIMESTAMP",
            'completed_at': "ALTER TABLE job ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP",
            'po_number': "ALTER TABLE job ADD COLUMN IF NOT EXISTS po_number VARCHAR(100)",
            'address': "ALTER TABLE job ADD COLUMN IF NOT EXISTS address VARCHAR(255)",
            'phone_number': "ALTER TABLE job ADD COLUMN IF NOT EXISTS phone_number VARCHAR(50)",
            'story': "ALTER TABLE job ADD COLUMN IF NOT EXISTS story VARCHAR(255)",
            'description': "ALTER TABLE job ADD COLUMN IF NOT EXISTS description VARCHAR(1000)",
            'system_size': "ALTER TABLE job ADD COLUMN IF NOT EXISTS system_size VARCHAR(100)",
            'cancel_reason': "ALTER TABLE job ADD COLUMN IF NOT EXISTS cancel_reason VARCHAR(500)",
            'pending_date': "ALTER TABLE job ADD COLUMN IF NOT EXISTS pending_date DATE",
            'scheduled_date': "ALTER TABLE job ADD COLUMN IF NOT EXISTS scheduled_date DATE",
            'is_internal': "ALTER TABLE job ADD COLUMN IF NOT EXISTS is_internal BOOLEAN DEFAULT FALSE",
            'permit_number': "ALTER TABLE job ADD COLUMN IF NOT EXISTS permit_number VARCHAR(100)"
        },
        'feedback_report': {
            'resolved_at': "ALTER TABLE feedback_report ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP",
            'status': "ALTER TABLE feedback_report ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'received'",
            'opened_at': "ALTER TABLE feedback_report ADD COLUMN IF NOT EXISTS opened_at TIMESTAMP",
            'opened_by': "ALTER TABLE feedback_report ADD COLUMN IF NOT EXISTS opened_by VARCHAR(255)",
            'closed_at': "ALTER TABLE feedback_report ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP",
            'closed_by': "ALTER TABLE feedback_report ADD COLUMN IF NOT EXISTS closed_by VARCHAR(255)",
            'reply': "ALTER TABLE feedback_report ADD COLUMN IF NOT EXISTS reply TEXT",
            'reply_seen': "ALTER TABLE feedback_report ADD COLUMN IF NOT EXISTS reply_seen BOOLEAN DEFAULT FALSE"
        },
        'timesheet': {
            'employee_name_snapshot': "ALTER TABLE timesheet ADD COLUMN IF NOT EXISTS employee_name_snapshot VARCHAR(100)",
            'employee_email_snapshot': "ALTER TABLE timesheet ADD COLUMN IF NOT EXISTS employee_email_snapshot VARCHAR(255)",
            'employee_phone_snapshot': "ALTER TABLE timesheet ADD COLUMN IF NOT EXISTS employee_phone_snapshot VARCHAR(20)"
        },
        'job_deletion_log': {
            'po_number': "ALTER TABLE job_deletion_log ADD COLUMN IF NOT EXISTS po_number VARCHAR(100)",
            'address': "ALTER TABLE job_deletion_log ADD COLUMN IF NOT EXISTS address VARCHAR(255)",
            'phone_number': "ALTER TABLE job_deletion_log ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20)",
            'story': "ALTER TABLE job_deletion_log ADD COLUMN IF NOT EXISTS story VARCHAR(255)",
            'description': "ALTER TABLE job_deletion_log ADD COLUMN IF NOT EXISTS description VARCHAR(1000)",
            'system_size': "ALTER TABLE job_deletion_log ADD COLUMN IF NOT EXISTS system_size VARCHAR(100)",
            'restored': "ALTER TABLE job_deletion_log ADD COLUMN IF NOT EXISTS restored BOOLEAN DEFAULT FALSE",
            'restored_at': "ALTER TABLE job_deletion_log ADD COLUMN IF NOT EXISTS restored_at TIMESTAMP",
            'restored_job_id': "ALTER TABLE job_deletion_log ADD COLUMN IF NOT EXISTS restored_job_id INTEGER"
        },
        'invite_code': {
            'expires_at': "ALTER TABLE invite_code ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP"
        },
        'time_off_request': {
            'request_type': "ALTER TABLE time_off_request ADD COLUMN IF NOT EXISTS request_type VARCHAR(50) DEFAULT 'Vacation'",
            'reason': "ALTER TABLE time_off_request ADD COLUMN IF NOT EXISTS reason VARCHAR(500)",
            'reviewed_by': "ALTER TABLE time_off_request ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR(100)",
            'reviewed_at': "ALTER TABLE time_off_request ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP",
            'response_note': "ALTER TABLE time_off_request ADD COLUMN IF NOT EXISTS response_note VARCHAR(500)",
            'seen_by_employee': "ALTER TABLE time_off_request ADD COLUMN IF NOT EXISTS seen_by_employee BOOLEAN DEFAULT TRUE"
        }
    }

    with db.engine.begin() as connection:
        for table_name, columns in schema_updates.items():
            if table_name not in inspector.get_table_names():
                continue

            for column_name, alter_sql in columns.items():
                connection.execute(text(alter_sql))

        connection.execute(text("UPDATE \"group\" SET color = '#667eea' WHERE color IS NULL OR color = ''"))
        connection.execute(text("UPDATE employee SET category = 'Installer' WHERE category IS NULL OR category = ''"))
        connection.execute(text("UPDATE job SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
        connection.execute(text("UPDATE feedback_report SET status = 'closed' WHERE (status IS NULL OR status = '') AND resolved = true"))
        connection.execute(text("UPDATE feedback_report SET status = 'open' WHERE (status IS NULL OR status = '') AND (resolved = false OR resolved IS NULL)"))
        connection.execute(text("UPDATE feedback_report SET closed_at = resolved_at WHERE closed_at IS NULL AND resolved_at IS NOT NULL"))

        # Widen phone_number columns that were originally VARCHAR(20)
        for tbl in ('job', 'employee', 'timesheet', 'job_deletion_log'):
            if tbl in inspector.get_table_names():
                try:
                    connection.execute(text(f'ALTER TABLE {tbl} ALTER COLUMN phone_number TYPE VARCHAR(50)'))
                except Exception:
                    pass  # already wide enough or column doesn't exist

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    groups = db.relationship('Group', backref='department', lazy=True, cascade='all, delete-orphan')

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), default='#667eea')
    city = db.Column(db.String(100))
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    permission_set_id = db.Column(db.Integer, db.ForeignKey('permission_set.id'))
    employees = db.relationship('Employee', backref='group', lazy=True, cascade='all, delete-orphan')

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), default='Installer')
    phone_number = db.Column(db.String(20))
    email = db.Column(db.String(255))
    password_hash = db.Column(db.String(255))
    session_token = db.Column(db.String(64), nullable=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'))
    permission_set_id = db.Column(db.Integer, db.ForeignKey('permission_set.id'))
    assignments = db.relationship('Assignment', backref='employee', lazy=True, cascade='all, delete-orphan')
    timesheets = db.relationship('Timesheet', backref='employee', lazy=True, cascade='all, delete-orphan')

    # Track if this is the employee's first login (for onboarding walkthrough)
    first_login = db.Column(db.Boolean, default=True)


class PermissionSet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    can_view_dashboard = db.Column(db.Boolean, default=True)
    can_view_calendar = db.Column(db.Boolean, default=True)
    can_view_jobs = db.Column(db.Boolean, default=True)
    can_view_management = db.Column(db.Boolean, default=False)
    can_view_payroll = db.Column(db.Boolean, default=False)
    can_manage_employees = db.Column(db.Boolean, default=False)
    can_manage_jobs = db.Column(db.Boolean, default=False)
    can_manage_assignments = db.Column(db.Boolean, default=False)
    can_manage_permissions = db.Column(db.Boolean, default=False)

    employees = db.relationship('Employee', backref='permission_set', lazy=True)
    groups = db.relationship('Group', backref='permission_set', lazy=True)

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    job_name = db.Column(db.String(100), nullable=False)
    job_type = db.Column(db.String(50), default='Solar Install')  # Solar Install, Service, Roof Leak
    status = db.Column(db.String(50), default='not_started')  # not_started, in_progress, completed
    published = db.Column(db.Boolean, default=False)  # False = draft, True = published
    po_number = db.Column(db.String(100))
    address = db.Column(db.String(255))
    phone_number = db.Column(db.String(50))
    story = db.Column(db.String(255))
    description = db.Column(db.String(1000))
    system_size = db.Column(db.String(100))
    cancel_reason = db.Column(db.String(500))
    permit_number = db.Column(db.String(100))
    pending_date = db.Column(db.Date)
    scheduled_date = db.Column(db.Date)  # Used for Site Survey jobs
    is_internal = db.Column(db.Boolean, default=False)  # True = hidden system job (General Time, etc.)
    assignments = db.relationship('Assignment', backref='job', lazy=True, cascade='all, delete-orphan')
    timesheets = db.relationship('Timesheet', backref='job', lazy=True, cascade='all, delete-orphan')

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    crew_id = db.Column(db.Integer, db.ForeignKey('group.id'))
    assigned_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    day_pay = db.Column(db.Boolean, default=False)
    crew = db.relationship('Group', foreign_keys=[crew_id])

class Timesheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    clock_in = db.Column(db.DateTime, default=datetime.now)
    clock_out = db.Column(db.DateTime)
    employee_name_snapshot = db.Column(db.String(100))
    employee_email_snapshot = db.Column(db.String(255))
    employee_phone_snapshot = db.Column(db.String(20))


class PayrollAdjustment(db.Model):
    """Manual hour/kW adjustment layered on top of computed timesheet data."""
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    hours_adjustment = db.Column(db.Float, default=0.0)
    kw_adjustment = db.Column(db.Float, default=0.0)
    note = db.Column(db.String(200))
    employee = db.relationship('Employee', backref='payroll_adjustments')


class JobDeletionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer)
    job_name = db.Column(db.String(100), nullable=False)
    job_type = db.Column(db.String(50))
    po_number = db.Column(db.String(100))
    address = db.Column(db.String(255))
    phone_number = db.Column(db.String(20))
    story = db.Column(db.String(255))
    description = db.Column(db.String(1000))
    system_size = db.Column(db.String(100))
    deleted_by = db.Column(db.String(255), nullable=False, default='Unknown')
    deleted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    restored = db.Column(db.Boolean, default=False)
    restored_at = db.Column(db.DateTime)
    restored_job_id = db.Column(db.Integer)


class JobArchive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_type = db.Column(db.String(50))
    assigned_employee = db.Column(db.String(255))
    scheduled_date = db.Column(db.Date)
    completed_date = db.Column(db.Date)
    archived_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class TimeOffRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    employee_name = db.Column(db.String(100), nullable=False)  # snapshot
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    request_type = db.Column(db.String(50), nullable=False, default='Vacation')  # Vacation/Sick/Personal/Bereavement/Medical
    reason = db.Column(db.String(500))
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending/approved/denied/cancelled
    requested_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reviewed_by = db.Column(db.String(100))
    reviewed_at = db.Column(db.DateTime)
    response_note = db.Column(db.String(500))
    seen_by_employee = db.Column(db.Boolean, default=True, nullable=False)  # False when a new decision is made
    employee = db.relationship('Employee', backref='time_off_requests')


class FeedbackReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(20), nullable=False)  # 'bug' or 'feedback'
    subject = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, nullable=False)
    submitted_by = db.Column(db.String(255))
    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default='received')
    opened_at = db.Column(db.DateTime, nullable=True)
    opened_by = db.Column(db.String(255), nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    closed_by = db.Column(db.String(255), nullable=True)
    resolved = db.Column(db.Boolean, default=False)
    resolved_at = db.Column(db.DateTime, nullable=True)
    reply = db.Column(db.Text, nullable=True)
    reply_seen = db.Column(db.Boolean, default=False, nullable=False, server_default='0')


class PasswordResetToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    employee = db.relationship('Employee', backref='reset_tokens')


class InviteCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(12), unique=True, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    used = db.Column(db.Boolean, default=False)
    used_by_name = db.Column(db.String(100))
    used_at = db.Column(db.DateTime)
    created_by = db.relationship('Employee', backref='invite_codes')


class AuditLog(db.Model):
    """Immutable record of significant events (login, approvals, role changes, etc.)."""
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    actor = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    target = db.Column(db.String(255))
    detail = db.Column(db.String(500))
    ip_address = db.Column(db.String(45))


def add_service_employees():
    """Idempotent: adds service tech employees if they don't already exist (matched by email)."""
    service_employees = [
        {"name": "Ryan Murdock",         "email": "ryanm1419@yahoo.com",        "phone_number": "(727) 645-7666"},
        {"name": "Michael Anderson Jr.", "email": "maj37@yahoo.com",             "phone_number": "(727) 678-8641"},
        {"name": "Eric Pierce",          "email": "ericrpierce85@icloud.com",    "phone_number": "(727) 851-8460"},
        {"name": "Antonio Roque",        "email": "aroque813@gmail.com",         "phone_number": "(813) 679-9370"},
        {"name": "Alexis Jimenez",       "email": "alexjimnzd1219@yahoo.com",    "phone_number": "(813) 410-5606"},
        {"name": "Bill Tomlin",          "email": "ttomlin003@gmail.com",        "phone_number": "(813) 847-5837"},
    ]
    added = 0
    for emp in service_employees:
        if not Employee.query.filter_by(email=emp["email"]).first():
            db.session.add(Employee(
                name=emp["name"],
                email=emp["email"],
                phone_number=emp["phone_number"],
                category="Service",
            ))
            added += 1
    if added:
        db.session.commit()
        print(f"[startup] Added {added} service employee(s).")


def has_role(employee, role_name):
    roles = [(r or '').strip() for r in (employee.category or '').split(',')]
    return role_name in roles


def is_manager_or_admin(employee):
    """Returns True if the employee has manager/admin authority over time-off requests."""
    if session.get('developer_user'):
        return True
    if not employee:
        return False
    roles = {(r or '').strip().lower() for r in (employee.category or '').split(',') if (r or '').strip()}
    if roles & {'manager', 'admin', 'management', 'developer', 'development'}:
        return True
    ps = resolve_effective_permission_set(employee)
    if ps and (ps.can_manage_employees or ps.can_manage_permissions or ps.can_view_management):
        return True
    return False


def is_assignable_employee(employee):
    """Returns True if the employee can be assigned to jobs.
    IT, Operations, Office, Development, and Support employees are excluded
    unless they also have Service or Electrician.
    """
    excluded = {'IT', 'Operations', 'Office', 'Development', 'Support'}
    override = {'Service', 'Electrician'}
    roles = {(r or '').strip() for r in (employee.category or '').split(',')}
    if roles & override:
        return True
    if roles & excluded:
        return False
    return True


def normalize_phone_password(value):
    """Return digits-only phone text for password fallback checks."""
    return re.sub(r'\D', '', (value or '').strip())


def _audit(actor, action, target=None, detail=None):
    """Write an immutable audit log entry. Silently ignores errors so it never breaks a request."""
    try:
        ip = request.remote_addr if request else None
        log = AuditLog(actor=actor, action=action, target=target, detail=detail, ip_address=ip)
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _can_grant_payroll(employee):
    """Only admins and developers may grant/revoke the View Payroll permission."""
    if session.get('developer_user'):
        return True
    if not employee:
        return False
    roles = {(r or '').strip().lower() for r in (employee.category or '').split(',') if (r or '').strip()}
    return bool(roles & {'admin', 'developer', 'development'})


def extract_permission_values(form_data):
    return {
        key: bool(form_data.get(key))
        for key in PERMISSION_KEYS
    }


def resolve_effective_permission_set(employee):
    if not employee:
        return None
    if employee.permission_set:
        return employee.permission_set
    if employee.group and employee.group.permission_set:
        return employee.group.permission_set
    return None


def is_field_employee(employee):
    if not employee:
        return False
    field_tokens = {
        'installer', 'electrician', 'site surveyor', 'inspection tech',
        'inspections tech', 'inspections', 'crew lead', 'service'
    }
    roles = {(r or '').strip().lower() for r in (employee.category or '').split(',') if (r or '').strip()}
    return bool(roles & field_tokens)


def is_field_limited_user():
    if session.get('developer_user'):
        return False
    employee = get_logged_in_employee()
    return bool(employee and is_field_employee(employee))


# ---------------------------------------------------------------------------
# Effective-identity helpers
# When a developer is in "view-as" mode these return the overridden identity
# so that ALL route-level permission checks enforce the target's restrictions.
# ---------------------------------------------------------------------------

def _view_as_is_active():
    """True if any view-as override is currently in the session."""
    return bool(session.get('view_as_employee_id') or session.get('view_as_permission_set_id'))


def effective_is_dev_session():
    """Returns True for the developer login session ONLY when no view-as is active.
    Use this instead of session.get('developer_user') in permission guards."""
    if _view_as_is_active():
        return False
    return bool(session.get('developer_user'))


def get_effective_employee():
    """Returns the employee whose identity should be used for permission checks.
    When a developer is viewing-as an employee, returns that employee.
    Otherwise behaves identically to get_logged_in_employee()."""
    real_employee = get_logged_in_employee()
    is_dev = session.get('developer_user') or is_developer_employee(real_employee)
    if is_dev and session.get('view_as_employee_id'):
        override = Employee.query.get(session['view_as_employee_id'])
        if override:
            return override
    return real_employee


def get_effective_permission_set():
    """Returns the PermissionSet that should govern the current request.
    Respects the view-as permission-set override if active."""
    emp = get_effective_employee()
    base = resolve_effective_permission_set(emp)
    real_employee = get_logged_in_employee()
    is_dev = session.get('developer_user') or is_developer_employee(real_employee)
    if is_dev and session.get('view_as_permission_set_id') and not session.get('view_as_employee_id'):
        override = PermissionSet.query.get(session['view_as_permission_set_id'])
        if override:
            return override
    return base


def effective_is_field_limited():
    """Like is_field_limited_user() but respects view-as."""
    if session.get('developer_user'):
        return False
    emp = get_effective_employee()
    if not emp or not is_field_employee(emp):
        return False
    # If the employee has any management permission, don't restrict them
    ps = get_effective_permission_set()
    if ps and (ps.can_manage_jobs or ps.can_manage_employees or
               ps.can_manage_assignments or ps.can_view_management or
               ps.can_manage_permissions):
        return False
    return True


def can_view_management_tab(employee, ignore_dev_session=False):
    if not ignore_dev_session and effective_is_dev_session():
        return True
    if not employee:
        return False
    roles = {(r or '').strip().lower() for r in (employee.category or '').split(',') if (r or '').strip()}
    if roles & {'manager', 'admin', 'management', 'developer', 'development'}:
        return True
    permission_set = get_effective_permission_set() if employee is get_effective_employee() else resolve_effective_permission_set(employee)
    if permission_set and (permission_set.can_view_management or permission_set.can_manage_permissions or
                           permission_set.can_manage_employees or permission_set.can_manage_jobs):
        return True
    return False


def can_view_payroll_tab(employee, ignore_dev_session=False):
    if not ignore_dev_session and effective_is_dev_session():
        return True
    if not employee:
        return False
    permission_set = get_effective_permission_set() if employee is get_effective_employee() else resolve_effective_permission_set(employee)
    if permission_set and permission_set.can_view_payroll:
        return True
    return False


def can_edit_timesheets(employee, ignore_dev_session=False):
    if not ignore_dev_session and effective_is_dev_session():
        return True
    if not employee:
        return False

    roles = {(r or '').strip().lower() for r in (employee.category or '').split(',') if (r or '').strip()}
    if 'manager' in roles:
        return True

    permission_set = get_effective_permission_set() if employee is get_effective_employee() else resolve_effective_permission_set(employee)
    if permission_set and permission_set.can_manage_assignments:
        return True

    return False


def can_view_archive(employee, ignore_dev_session=False):
    if not ignore_dev_session and effective_is_dev_session():
        return True
    if not employee:
        return False

    roles = {(r or '').strip().lower() for r in (employee.category or '').split(',') if (r or '').strip()}
    allowed_roles = {'management', 'manager', 'admin', 'support', 'developer'}
    if roles & allowed_roles:
        return True

    permission_set = get_effective_permission_set() if employee is get_effective_employee() else resolve_effective_permission_set(employee)
    if permission_set and (permission_set.can_view_management or permission_set.can_manage_permissions):
        return True

    return False


def can_view_backend(employee):
    """Back End tab access: developers and support only (never admins/managers)."""
    if session.get('developer_user'):
        return True
    if not employee:
        return False
    roles = {(r or '').strip().lower() for r in (employee.category or '').split(',') if (r or '').strip()}
    if roles & {'developer', 'development', 'support'}:
        return True
    return False


def is_developer_employee(employee):
    """Returns True if this employee is categorised as a Developer."""
    if not employee:
        return False
    roles = {(r or '').strip().lower() for r in (employee.category or '').split(',') if (r or '').strip()}
    return bool(roles & {'developer', 'development'})


def get_view_as_overrides():
    """Return (employee_override, permission_set_override) from the view-as session keys.
    Only honoured when the real logged-in user is a developer employee or dev session."""
    real_employee = get_logged_in_employee()
    is_dev = session.get('developer_user') or is_developer_employee(real_employee)
    if not is_dev:
        return None, None

    emp_id = session.get('view_as_employee_id')
    ps_id = session.get('view_as_permission_set_id')

    emp_override = Employee.query.get(emp_id) if emp_id else None
    ps_override = PermissionSet.query.get(ps_id) if ps_id else None
    return emp_override, ps_override


def normalize_system_size(value):
    if not value:
        return ''
    cleaned = value.strip()
    if cleaned.lower().endswith('kw'):
        cleaned = cleaned[:-2].strip()
    return cleaned


def parse_kw_value(system_size):
    """Parse numeric kW from free-form system size text."""
    normalized = normalize_system_size(system_size)
    if not normalized:
        return 0.0

    match = re.search(r'\d+(?:\.\d+)?', normalized.replace(',', ''))
    if not match:
        return 0.0

    try:
        return float(match.group(0))
    except ValueError:
        return 0.0


def _build_payroll_data(week_start):
    """Per-employee payroll summary: hours from timesheets + kW from install assignments, Mon-Sun."""
    week_end = week_start + timedelta(days=6)
    days = [
        {'key': (week_start + timedelta(days=i)).isoformat(),
         'label': (week_start + timedelta(days=i)).strftime('%a %m/%d')}
        for i in range(7)
    ]
    day_keys = {d['key'] for d in days}

    all_emps = Employee.query.order_by(Employee.name).all()
    _ts_start = datetime(week_start.year, week_start.month, week_start.day)
    _ts_end   = datetime(week_end.year, week_end.month, week_end.day) + timedelta(days=1)
    week_ts   = Timesheet.query.filter(
        Timesheet.clock_in >= _ts_start,
        Timesheet.clock_in <  _ts_end
    ).all()
    # Build job_type lookup to determine service hours without N+1 queries
    _ts_job_ids = {ts.job_id for ts in week_ts if ts.job_id}
    _job_type_map = {}
    if _ts_job_ids:
        for _j in Job.query.filter(Job.id.in_(_ts_job_ids)).with_entities(Job.id, Job.job_type).all():
            _job_type_map[_j.id] = (_j.job_type or '').strip().lower()
    week_assigns = (
        Assignment.query
        .join(Job)
        .filter(
            Assignment.assigned_date >= week_start,
            Assignment.assigned_date <= week_end,
            Job.status != 'canceled'
        )
        .all()
    )

    def _role_order(emp):
        roles = {(r or '').strip().lower() for r in (emp.category or '').split(',') if (r or '').strip()}
        if 'crew lead' in roles:
            return 0
        if 'electrician' in roles:
            return 1
        return 2

    emp_map = {
        emp.id: {
            'id':          emp.id,
            'name':        emp.name or '',
            'group':       emp.group.name if emp.group else '—',
            'group_color': (emp.group.color or '#667eea') if emp.group else '#667eea',
            'department':  (emp.group.department.name
                            if emp.group and emp.group.department else '—'),
            'is_field':    is_field_employee(emp),
            'role_order':  _role_order(emp),
            'daily_hours': {d['key']: 0.0 for d in days},
            'daily_kw':    {d['key']: 0.0 for d in days},
            'daily_day_pay':   {d['key']: 0 for d in days},
            'daily_service_hours': {d['key']: 0.0 for d in days},
            'daily_adj_hours': {d['key']: 0.0 for d in days},
            'daily_adj_kw':    {d['key']: 0.0 for d in days},
            'total_hours': 0.0,
            'total_service_hours': 0.0,
            'total_kw':    0.0,
            'total_day_pay_days': 0,
        }
        for emp in all_emps
    }

    for ts in week_ts:
        if ts.clock_out is None:
            continue
        bucket = emp_map.get(ts.employee_id)
        if not bucket:
            continue
        day_key = ts.clock_in.date().isoformat()
        if day_key not in day_keys:
            continue
        h = (ts.clock_out - ts.clock_in).total_seconds() / 3600.0
        bucket['daily_hours'][day_key] = round(bucket['daily_hours'][day_key] + h, 2)
        bucket['total_hours']          = round(bucket['total_hours'] + h, 2)
        if 'service' in _job_type_map.get(ts.job_id, ''):
            bucket['daily_service_hours'][day_key] = round(bucket['daily_service_hours'][day_key] + h, 2)
            bucket['total_service_hours']          = round(bucket['total_service_hours'] + h, 2)

    seen_kw = set()
    seen_day_pay = set()
    for assign in week_assigns:
        if not assign.job or not assign.assigned_date:
            continue
        if 'install' not in (assign.job.job_type or '').strip().lower():
            continue
        day_key = assign.assigned_date.isoformat()
        bucket = emp_map.get(assign.employee_id)
        if not bucket:
            continue
        po = (assign.job.po_number or '').strip()
        job_key = po if po else str(assign.job.id)

        if assign.day_pay:
            # Day Pay: count once per employee per job per day
            dp_key = (assign.employee_id, job_key, day_key)
            if dp_key in seen_day_pay:
                continue
            seen_day_pay.add(dp_key)
            if day_key in bucket['daily_day_pay']:
                bucket['daily_day_pay'][day_key] += 1
                bucket['total_day_pay_days'] += 1
        else:
            kw = parse_kw_value(assign.job.system_size)
            if kw <= 0:
                continue
            # Dedup per employee: use PO number as job identity when available
            dk = (assign.employee_id, job_key)
            if dk in seen_kw:
                continue
            seen_kw.add(dk)
            bucket['daily_kw'][day_key] = round(bucket['daily_kw'][day_key] + kw, 2)
            bucket['total_kw']          = round(bucket['total_kw'] + kw, 2)

    # Apply manual adjustments
    week_adjs = PayrollAdjustment.query.filter(
        PayrollAdjustment.date >= week_start,
        PayrollAdjustment.date <= week_end
    ).all()
    for adj in week_adjs:
        bucket = emp_map.get(adj.employee_id)
        if not bucket:
            continue
        day_key = adj.date.isoformat()
        if day_key not in day_keys:
            continue
        bucket['daily_adj_hours'][day_key] = round(adj.hours_adjustment or 0.0, 2)
        bucket['daily_adj_kw'][day_key]    = round(adj.kw_adjustment or 0.0, 2)
        bucket['daily_hours'][day_key]     = round(bucket['daily_hours'][day_key] + (adj.hours_adjustment or 0.0), 2)
        bucket['daily_kw'][day_key]        = round(bucket['daily_kw'][day_key]    + (adj.kw_adjustment    or 0.0), 2)
        bucket['total_hours']              = round(bucket['total_hours'] + (adj.hours_adjustment or 0.0), 2)
        bucket['total_kw']                 = round(bucket['total_kw']    + (adj.kw_adjustment    or 0.0), 2)

    def _crew_sort_key(e):
        m = re.search(r'(\d+)', e['group'])
        if m:
            return (0, int(m.group(1)), e['role_order'], e['name'].lower())
        return (1, 0, e['role_order'], e['name'].lower())

    sorted_emps = sorted(emp_map.values(), key=_crew_sort_key)
    return {
        'week_start': week_start.isoformat(),
        'week_end':   week_end.isoformat(),
        'week_label': week_start.strftime('%b %d') + ' – ' + week_end.strftime('%b %d, %Y'),
        'days':       days,
        'employees':  sorted_emps,
    }


def is_ajax_request():
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.is_json
    )


def delete_route_response(success_message, payload=None):
    payload = payload or {}
    if is_ajax_request():
        return jsonify({'ok': True, 'message': success_message, **payload})
    flash(success_message, 'success')
    return redirect(url_for('index'))


def get_logged_in_employee():
    employee_id = session.get('employee_user_id')
    if not employee_id:
        return None
    return Employee.query.get(employee_id)


def get_feedback_actor_name():
    employee = get_logged_in_employee()
    if employee:
        return (employee.name or '').strip()
    if session.get('developer_user'):
        return 'Developer'
    return ''


def can_access_feedback_ticket_board(employee=None):
    if employee is None:
        employee = get_logged_in_employee()
    return can_view_backend(employee)


def can_manage_feedback_ticket(report, allow_submitter_close=False):
    employee = get_logged_in_employee()
    actor = get_feedback_actor_name()

    if can_access_feedback_ticket_board(employee):
        return True

    if allow_submitter_close and actor and report and (report.submitted_by or '').strip() == actor:
        return True

    return False


def is_authenticated_session():
    if session.get('developer_user'):
        return True
    employee_id = session.get('employee_user_id')
    if not employee_id:
        return False
    emp = db.session.get(Employee, employee_id)
    if emp is None:
        session.pop('employee_user_id', None)
        session.pop('employee_user_name', None)
        session.pop('session_token', None)
        return False
    # Enforce single-session: reject if the token doesn't match what's in the DB
    stored_token = emp.session_token
    session_token = session.get('session_token')
    if not stored_token or stored_token != session_token:
        session.clear()
        return False
    return True


@app.context_processor
def inject_auth_employee():
    real_employee = get_logged_in_employee()
    is_dev_session = session.get('developer_user')
    is_real_dev = is_dev_session or is_developer_employee(real_employee)

    # View-as overrides (only for devs)
    emp_override, ps_override = get_view_as_overrides()
    view_as_active = bool(emp_override or ps_override)

    # Effective auth_employee for UI rendering
    if emp_override:
        auth_employee = emp_override
        effective_permission_set = resolve_effective_permission_set(emp_override)
    else:
        auth_employee = real_employee
        effective_permission_set = resolve_effective_permission_set(real_employee)

    # When viewing as a permission set only (no employee override), layer it on top
    if ps_override and not emp_override:
        effective_permission_set = ps_override

    auth_name = auth_employee.name if auth_employee else session.get('developer_user_name', '')
    auth_role = 'Developer' if is_dev_session else 'Employee'

    # When view-as is active, bypass dev-session so the view accurately reflects the target
    if view_as_active:
        _can_edit_ts = can_edit_timesheets(auth_employee, ignore_dev_session=True)
        _can_view_arch = can_view_archive(auth_employee, ignore_dev_session=True)
        _can_view_mgmt = can_view_management_tab(auth_employee, ignore_dev_session=True)
        _can_view_payroll = can_view_payroll_tab(auth_employee, ignore_dev_session=True)
        # For permission-set-only override, also check the overridden set directly
        if ps_override and not emp_override:
            if ps_override.can_manage_assignments:
                _can_edit_ts = True
            if ps_override.can_view_management or ps_override.can_manage_permissions:
                _can_view_arch = True
                _can_view_mgmt = True
            if ps_override.can_view_payroll:
                _can_view_payroll = True
    else:
        _can_edit_ts = can_edit_timesheets(auth_employee)
        _can_view_arch = can_view_archive(auth_employee) or bool(is_dev_session)
        _can_view_mgmt = can_view_management_tab(auth_employee) or bool(is_dev_session)
        _can_view_payroll = can_view_payroll_tab(auth_employee) or bool(is_dev_session)

    # Time-off notification counts
    _time_off_unseen_count = 0
    _time_off_pending_count = 0
    _my_time_off_requests = []
    _pending_time_off_requests = []
    if real_employee:
        _my_time_off_requests = (
            TimeOffRequest.query
            .filter_by(employee_id=real_employee.id)
            .order_by(TimeOffRequest.requested_at.desc())
            .limit(50)
            .all()
        )
        _time_off_unseen_count = sum(1 for r in _my_time_off_requests if not r.seen_by_employee)
    if is_dev_session or (real_employee and is_manager_or_admin(real_employee)):
        _pending_time_off_requests = (
            TimeOffRequest.query
            .filter_by(status='pending')
            .order_by(TimeOffRequest.requested_at.asc())
            .all()
        )
        _time_off_pending_count = len(_pending_time_off_requests)

    # Approved time-off blocks for calendar conflict display (all employees, next 180 days)
    _today = datetime.utcnow().date()
    _approved_time_off = (
        TimeOffRequest.query
        .filter_by(status='approved')
        .filter(TimeOffRequest.end_date >= _today)
        .order_by(TimeOffRequest.start_date)
        .all()
    ) if (is_dev_session or (real_employee and is_manager_or_admin(real_employee))) else []

    return {
        'auth_employee': auth_employee,
        'auth_name': auth_name,
        'auth_role': auth_role,
        'auth_permission_set': effective_permission_set,
        'auth_can_edit_timesheets': _can_edit_ts,
        'auth_can_view_archive': _can_view_arch,
        'auth_can_view_management': _can_view_mgmt,
        'auth_can_view_payroll': _can_view_payroll,
        'auth_can_grant_payroll': _can_grant_payroll(real_employee),
        # Back End tab: always uses real identity, never suppressed
        'auth_can_view_backend': can_view_backend(real_employee) or bool(is_dev_session),
        # View-as state exposed to templates
        'view_as_active': view_as_active,
        'view_as_employee': emp_override,
        'view_as_permission_set': ps_override,
        'real_employee': real_employee,
        'is_real_developer': is_real_dev,
        # Time-off
        'time_off_unseen_count': _time_off_unseen_count,
        'time_off_pending_count': _time_off_pending_count,
        'my_time_off_requests': _my_time_off_requests,
        'pending_time_off_requests': _pending_time_off_requests,
        'approved_time_off': _approved_time_off,
        'auth_is_manager': is_manager_or_admin(real_employee) or bool(is_dev_session),
    }


@app.before_request
def require_employee_login():
    public_endpoints = {'login', 'logout', 'static', 'forgot_password', 'reset_password', 'register', 'verify_invite'}

    if request.path.startswith('/socket.io'):
        return None

    if request.endpoint in public_endpoints:
        return None

    if is_authenticated_session():
        if effective_is_field_limited():
            allowed_field_endpoints = {
                'index',
                'get_assignments_api',
                'clock_in',
                'clock_out',
                'handle_connect',
                'handle_disconnect',
                'dev_view_as_exit',
            }
            if request.endpoint not in allowed_field_endpoints:
                if request.path.startswith('/api/') or is_ajax_request():
                    return jsonify({'ok': False, 'message': 'Not allowed for field user profile.'}), 403
                flash('Your account can only access your published schedule and clock actions.', 'warning')
                return redirect(url_for('index'))
        return None

    if request.path.startswith('/api/') or is_ajax_request():
        return jsonify({'ok': False, 'message': 'Authentication required.'}), 401

    return redirect(url_for('login', next=request.path))


@app.route('/login', methods=['GET', 'POST'])
def login():
    # Rate limit: 20 login attempts per minute per IP
    if limiter:
        try:
            limiter.limit('20 per minute')(lambda: None)()
        except Exception:
            return jsonify({'error': 'Too many login attempts. Please wait a minute.'}), 429

    if is_authenticated_session():
        return redirect(url_for('index'))

    if request.method == 'POST':
        login_id_raw = (request.form.get('email') or '').strip()
        login_id = login_id_raw.lower()
        password = request.form.get('password') or ''

        remember_me = request.form.get('remember_me') == '1'

        if not login_id_raw or not password:
            flash('Username/email and password are required.', 'danger')
            return render_template('login.html')

        if login_id_raw == DEVELOPER_LOGIN_USERNAME and password == DEVELOPER_LOGIN_PASSWORD:
            session['developer_user'] = True
            session['developer_user_name'] = DEVELOPER_LOGIN_USERNAME
            if remember_me:
                session.permanent = True
                app.permanent_session_lifetime = timedelta(days=30)
            flash('Welcome, Developer.', 'success')
            next_url = request.args.get('next') or request.form.get('next') or url_for('index')
            if not next_url.startswith('/'):
                next_url = url_for('index')
            return redirect(next_url)

        employee = Employee.query.filter(db.func.lower(Employee.email) == login_id).first()
        if not employee:
            flash('Invalid email or password.', 'danger')
            return render_template('login.html')

        if employee.password_hash:
            # Try exact password first; also try digits-only so any phone formatting works
            is_valid = check_password_hash(employee.password_hash, password)
            if not is_valid:
                normalized = normalize_phone_password(password)
                if normalized:
                    is_valid = check_password_hash(employee.password_hash, normalized)
        else:
            # No password set — default is the phone number (digits only, formatting ignored)
            normalized_password = normalize_phone_password(password)
            normalized_phone = normalize_phone_password(employee.phone_number)
            is_valid = bool(
                employee.phone_number and normalized_password and normalized_password == normalized_phone
            )
            if is_valid:
                # Always hash the digits-only form so any formatting works on future logins
                employee.password_hash = generate_password_hash(normalized_phone)
                db.session.commit()

        if not is_valid:
            _audit(login_id_raw, 'login_failed', detail='Bad password')
            flash('Invalid email or password.', 'danger')
            return render_template('login.html')

        session['employee_user_id'] = employee.id
        session['employee_user_name'] = employee.name
        # Invalidate any previous session by issuing a new token
        token = secrets.token_hex(32)
        employee.session_token = token

        # Onboarding walkthrough: if first_login is True and not field user, set session flag and mark as not first_login
        show_walkthrough = False
        if getattr(employee, 'first_login', None) is not None and employee.first_login:
            # Only show for office employees (not field)
            if not (hasattr(employee, 'category') and employee.category and employee.category.lower() == 'field'):
                session['show_walkthrough'] = True
                show_walkthrough = True
            employee.first_login = False
        db.session.commit()
        session['session_token'] = token
        if remember_me:
            session.permanent = True
            app.permanent_session_lifetime = timedelta(days=30)
        _audit(employee.name, 'login', detail='remember_me=' + str(remember_me))
        flash(f'Welcome, {employee.name}.', 'success')

        next_url = request.args.get('next') or request.form.get('next') or url_for('index')
        if not next_url.startswith('/'):
            next_url = url_for('index')
        return redirect(next_url)

    return render_template('login.html')


@app.route('/logout')
def logout():
    # Clear the session token in DB so the account can't be used from other tabs
    employee_id = session.get('employee_user_id')
    actor = session.get('employee_user_name') or session.get('developer_user_name') or 'unknown'
    if employee_id:
        emp = db.session.get(Employee, employee_id)
        if emp:
            emp.session_token = None
            db.session.commit()
    _audit(actor, 'logout')
    session.pop('employee_user_id', None)
    session.pop('employee_user_name', None)
    session.pop('session_token', None)
    session.pop('developer_user', None)
    session.pop('developer_user_name', None)
    session.pop('view_as_employee_id', None)
    session.pop('view_as_permission_set_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


def _can_manage_invites(employee):
    """True if employee can generate/delete invite codes (admin, manager, dev)."""
    if not employee:
        return False
    roles = {(r or '').strip().lower() for r in (employee.category or '').split(',')}
    if roles & {'manager', 'developer', 'development', 'admin', 'support'}:
        return True
    pset = resolve_effective_permission_set(employee)
    return bool(pset and pset.can_manage_employees)


def _generate_invite_code():
    """Return a unique 4+4 uppercase alphanumeric invite code, e.g. AB3X-7YK2."""
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    while True:
        part1 = ''.join(secrets.choice(alphabet) for _ in range(4))
        part2 = ''.join(secrets.choice(alphabet) for _ in range(4))
        code = f'{part1}-{part2}'
        if not InviteCode.query.filter_by(code=code).first():
            return code


@app.route('/invite/generate', methods=['POST'])
def generate_invite_code():
    if not is_authenticated_session():
        return jsonify({'error': 'unauthorized'}), 401
    actor = get_logged_in_employee()
    is_dev = bool(session.get('developer_user')) or is_developer_employee(actor)
    if not is_dev and not _can_manage_invites(actor):
        return jsonify({'error': 'forbidden'}), 403
    code = _generate_invite_code()
    invite = InviteCode(
        code=code,
        created_by_id=actor.id if actor else None,
        expires_at=datetime.utcnow() + timedelta(minutes=5)
    )
    db.session.add(invite)
    db.session.commit()
    # Build invite link using the real network IP so coworkers on other devices can use it
    # Build invite link — use the public domain/host so the link works from any device
    invite_link = url_for('verify_invite', code=code, _external=True)
    return jsonify({'code': code, 'id': invite.id, 'expires_in': 300, 'link': invite_link})


@app.route('/invite/<int:invite_id>/delete', methods=['POST'])
def delete_invite_code(invite_id):
    if not is_authenticated_session():
        return jsonify({'error': 'unauthorized'}), 401
    actor = get_logged_in_employee()
    is_dev = bool(session.get('developer_user')) or is_developer_employee(actor)
    if not is_dev and not _can_manage_invites(actor):
        return jsonify({'error': 'forbidden'}), 403
    invite = InviteCode.query.get(invite_id)
    if invite and not invite.used:
        db.session.delete(invite)
        db.session.commit()
    return jsonify({'success': True})


@app.route('/verify-invite', methods=['GET', 'POST'])
def verify_invite():
    """Code gate — user must enter a valid, unexpired invite code before seeing the register form."""
    if request.method == 'POST':
        code_raw = (request.form.get('invite_code') or '').strip().upper()
        if not code_raw:
            return render_template('verify_invite.html', error='Please enter an invite code.')
        invite = InviteCode.query.filter_by(code=code_raw, used=False).first()
        now = datetime.utcnow()
        if not invite:
            return render_template('verify_invite.html', error='Invalid or already-used invite code.')
        if invite.expires_at and invite.expires_at < now:
            return render_template('verify_invite.html', error='That code has expired. Ask your manager for a new one.')
        # Store verified code in session so /register can trust it
        session['verified_invite_code'] = code_raw
        return redirect(url_for('register'))
    # GET — clear any stale verified code
    session.pop('verified_invite_code', None)
    resp = make_response(render_template('verify_invite.html', error=None))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/register', methods=['GET', 'POST'])
def register():
    # Registration requires a code pre-verified via /verify-invite (stored in session)
    verified_code = session.get('verified_invite_code', '').strip().upper()
    if not verified_code:
        return redirect(url_for('verify_invite'))

    if request.method == 'POST':
        full_name = (request.form.get('full_name') or '').strip()
        email_raw = (request.form.get('email') or '').strip()
        phone_number = (request.form.get('phone_number') or '').strip()
        role = (request.form.get('role') or '').strip()
        password = (request.form.get('password') or '').strip()
        confirm = (request.form.get('confirm_password') or '').strip()

        # Re-fetch the invite using the session-stored code (not from form — user can't tamper)
        invite = InviteCode.query.filter_by(code=verified_code, used=False).first()

        errors = []
        if not invite:
            session.pop('verified_invite_code', None)
            flash('Your invite code is no longer valid. Please ask for a new one.', 'danger')
            return redirect(url_for('verify_invite'))
        if not full_name:
            errors.append('Full name is required.')
        if not email_raw:
            errors.append('Email is required.')
        if not phone_number:
            errors.append('Phone number is required.')
        if role not in ('Office', 'Field'):
            errors.append('Please select a role.')
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')

        if not errors:
            existing = Employee.query.filter(db.func.lower(Employee.email) == email_raw.lower()).first()
            if existing:
                errors.append('An account with that email already exists.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('register.html',
                                   full_name=full_name, email=email_raw,
                                   phone_number=phone_number, role=role)

        standard_ps = PermissionSet.query.filter_by(name='Standard').first() if role == 'Office' else None

        new_employee = Employee(
            name=full_name,
            email=email_raw,
            phone_number=phone_number,
            password_hash=generate_password_hash(password),
            category=role,
            permission_set_id=standard_ps.id if standard_ps else None
        )
        db.session.add(new_employee)


        # Delete invite code after use (one-time use, no log)
        db.session.delete(invite)
        db.session.commit()
        session.pop('verified_invite_code', None)
        flash(f'Account created for {full_name}. You can now sign in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', full_name='', email='', phone_number='', role='')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if is_authenticated_session():
        return redirect(url_for('index'))

    reset_url = None
    if request.method == 'POST':
        email_raw = (request.form.get('email') or '').strip()
        if not email_raw:
            flash('Please enter your email address.', 'danger')
            return render_template('reset_password.html', step='request', reset_url=None)

        employee = Employee.query.filter(db.func.lower(Employee.email) == email_raw.lower()).first()
        # Always show a success-like page to avoid email enumeration
        if employee:
            # Invalidate any existing unused tokens for this employee
            PasswordResetToken.query.filter_by(employee_id=employee.id, used=False).delete()
            token = secrets.token_hex(32)
            expires_at = datetime.utcnow() + timedelta(hours=2)
            prt = PasswordResetToken(employee_id=employee.id, token=token, expires_at=expires_at)
            db.session.add(prt)
            db.session.commit()
            reset_url = url_for('reset_password', token=token, _external=True)

        return render_template('reset_password.html', step='link_shown',
                               reset_url=reset_url, email=email_raw)

    return render_template('reset_password.html', step='request', reset_url=None)


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if is_authenticated_session():
        return redirect(url_for('index'))

    prt = PasswordResetToken.query.filter_by(token=token, used=False).first()
    if not prt or prt.expires_at < datetime.utcnow():
        flash('This password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = (request.form.get('new_password') or '').strip()
        confirm_password = (request.form.get('confirm_password') or '').strip()

        if not new_password or len(new_password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('reset_password.html', step='set_password', token=token)

        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', step='set_password', token=token)

        employee = prt.employee
        employee.password_hash = generate_password_hash(new_password)
        prt.used = True
        db.session.commit()

        flash('Your password has been updated. You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html', step='set_password', token=token)


@app.route('/change-password', methods=['POST'])
def change_password():
    """Allow any logged-in employee to change their own password."""
    employee = get_logged_in_employee()
    if not employee:
        return jsonify({'success': False, 'message': 'Not logged in.'}), 403

    current_pw = (request.form.get('current_password') or '').strip()
    new_pw = (request.form.get('new_password') or '').strip()
    confirm_pw = (request.form.get('confirm_password') or '').strip()

    if not check_password_hash(employee.password_hash or '', current_pw):
        return jsonify({'success': False, 'message': 'Current password is incorrect.'}), 400

    if len(new_pw) < 6:
        return jsonify({'success': False, 'message': 'New password must be at least 6 characters.'}), 400

    if new_pw != confirm_pw:
        return jsonify({'success': False, 'message': 'New passwords do not match.'}), 400

    employee.password_hash = generate_password_hash(new_pw)
    PasswordResetToken.query.filter_by(employee_id=employee.id, used=False).delete()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Password updated successfully.'})


@app.route('/employee/<int:id>/set-password', methods=['POST'])
def admin_set_employee_password(id):
    current_employee = get_effective_employee()
    is_admin = effective_is_dev_session() or (
        current_employee and 'manager' in {
            (r or '').strip().lower()
            for r in (current_employee.category or '').split(',')
        }
    )
    if not is_admin:
        pset = resolve_effective_permission_set(current_employee)
        if not (pset and pset.can_manage_employees):
            flash('You do not have permission to reset passwords.', 'danger')
            return redirect(url_for('index'))

    employee = Employee.query.get(id)
    if not employee:
        flash('Employee not found.', 'danger')
        return redirect(url_for('index'))

    new_password = (request.form.get('new_password') or '').strip()
    if not new_password or len(new_password) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('index'))

    employee.password_hash = generate_password_hash(new_password)
    # Invalidate any outstanding reset tokens for this employee
    PasswordResetToken.query.filter_by(employee_id=employee.id, used=False).delete()
    db.session.commit()
    flash(f'Password for {employee.name} has been updated.', 'success')
    return redirect(url_for('index'))


def parse_employee_categories(form_data):
    categories = [c.strip() for c in form_data.getlist('category') if (c or '').strip()]
    custom_raw = (form_data.get('category_custom') or '').strip()
    if custom_raw:
        custom_categories = [c.strip() for c in custom_raw.split(',') if c.strip()]
        categories.extend(custom_categories)

    # Preserve order while removing duplicates.
    seen = set()
    unique_categories = []
    for c in categories:
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_categories.append(c)
    return unique_categories


def get_calendar_section_for_employee(employee):
    roles = {(r or '').strip().lower() for r in (employee.category or '').split(',') if (r or '').strip()}

    bottom_roles = {'office', 'support', 'development'}
    if roles & bottom_roles:
        return {
            'title': 'Office / Support / Development',
            'is_crew': False,
            'color': ''
        }

    if employee.group:
        return {
            'title': employee.group.name,
            'is_crew': True,
            'color': employee.group.color or '#1f2f4f'
        }

    if 'crew lead' in roles:
        title = 'Crew Lead'
    elif 'installer' in roles or 'electrician' in roles:
        title = 'Installer'
    elif 'service' in roles:
        title = 'Service'
    elif 'site surveyor' in roles or 'inspection tech' in roles or 'inspections' in roles or 'inspections tech' in roles:
        title = 'Site Surveyor / Inspections'
    else:
        title = 'Other'

    return {
        'title': title,
        'is_crew': False,
        'color': ''
    }


JOB_TYPE_COLOR_MAP = {
    'install': '#1f8a4c',
    'reinstall': '#2f9e44',
    'uninstall': '#b45309',
    'red tag': '#c21833',
    'service': '#0c8599',
    'mpu': '#364fc7',
    'inspection': '#ff1493',
    'inspections': '#ff1493',
    'site survey': '#39ff14',
    'site surveys': '#39ff14',
    'roof leak': '#71e6c8',
    'roof leaks': '#71e6c8',
    'funding': '#f2b705',
    'unspecified': '#475569'
}


def get_job_type_color(job_type):
    normalized = (job_type or '').strip().lower() or 'unspecified'
    return JOB_TYPE_COLOR_MAP.get(normalized, '#5b6b8a')


def crew_sort_key(group):
    name = (group.name or '').strip()
    match = re.search(r'(\d+)', name)
    if match:
        # Numeric crews first, lowest number first (Crew 1, Crew 2, ...)
        return (0, int(match.group(1)), name.lower())
    return (1, 0, name.lower())


def is_multi_employee_job_type(job_type):
    return (job_type or '').strip().lower() in {'install', 'solar install', 'reinstall', 'uninstall'}


def is_crew_eligible_job_type(job_type):
    return is_multi_employee_job_type(job_type)


def should_assign_full_crew(job, employee):
    return (
        bool(job)
        and bool(employee)
        and is_crew_eligible_job_type(job.job_type)
        and has_role(employee, 'Crew Lead')
        and bool(employee.group)
        and bool(employee.group.employees)
    )


def expand_job_assignments_for_crew_leads(job, slot_map):
    """For install-like jobs, expand crew-lead assignments into full crew assignments.

    Returns a list of crew names that were expanded.
    """
    expanded_crews = []
    for (assigned_date, start_time, end_time), slot_assignments in slot_map.items():
        crew_lead_assignment = next(
            (assign for assign in slot_assignments if should_assign_full_crew(job, assign.employee)),
            None
        )
        if not crew_lead_assignment:
            continue

        crew = crew_lead_assignment.employee.group
        if not crew:
            continue

        # Replace the slot with the full crew for this crew lead's crew.
        for assign in slot_assignments:
            db.session.delete(assign)

        for member in crew.employees:
            db.session.add(Assignment(
                employee_id=member.id,
                job_id=job.id,
                crew_id=crew.id,
                assigned_date=assigned_date,
                start_time=start_time,
                end_time=end_time
            ))

        expanded_crews.append(crew.name)

    return expanded_crews


def ensure_default_crews():
    default_crews = [
        ("Crew 1", "#ffe066"),   # Yellow
        ("Crew 2", "#a259e6"),   # Purple
        ("Crew 3", "#3b82f6"),   # Blue
        ("Crew 4", "#f472b6"),   # Pink
        ("Crew 5", "#22c55e")    # Green
    ]

    crews_department = Department.query.filter_by(name="Current Crews").first()
    if not crews_department:
        crews_department = Department(name="Current Crews")
        db.session.add(crews_department)
        db.session.flush()

    existing_crews = {group.name: group for group in Group.query.filter_by(department_id=crews_department.id).all()}
    for crew_name, crew_color in default_crews:
        if crew_name not in existing_crews:
            db.session.add(Group(name=crew_name, color=crew_color, department_id=crews_department.id))

    db.session.commit()


def ensure_default_permission_sets():
    admin = PermissionSet.query.filter_by(name='Admin').first()
    if not admin:
        admin = PermissionSet(
            name='Admin',
            can_view_dashboard=True,
            can_view_calendar=True,
            can_view_jobs=True,
            can_view_management=True,
            can_manage_employees=True,
            can_manage_jobs=True,
            can_manage_assignments=True,
            can_manage_permissions=True
        )
        db.session.add(admin)

    standard = PermissionSet.query.filter_by(name='Standard').first()
    if not standard:
        standard = PermissionSet(name='Standard')
        db.session.add(standard)
    standard.can_view_dashboard = True
    standard.can_view_calendar = True
    standard.can_view_jobs = True
    standard.can_view_management = False
    standard.can_manage_employees = False
    standard.can_manage_jobs = True
    standard.can_manage_assignments = True
    standard.can_manage_permissions = False

    manager = PermissionSet.query.filter_by(name='Manager').first()
    if not manager:
        manager = PermissionSet(name='Manager')
        db.session.add(manager)
    manager.can_view_dashboard = True
    manager.can_view_calendar = True
    manager.can_view_jobs = True
    manager.can_view_management = True
    manager.can_manage_employees = True
    manager.can_manage_jobs = True
    manager.can_manage_assignments = True
    manager.can_manage_permissions = False

    db.session.commit()


def get_or_create_default_clock_job():
    default_job = Job.query.filter_by(job_name='General Time', job_type='Support').first()
    if default_job:
        if not default_job.is_internal:
            default_job.is_internal = True
            db.session.commit()
        return default_job
    default_job = Job(job_name='General Time', job_type='Support', status='not_started', published=False, is_internal=True)
    db.session.add(default_job)
    db.session.commit()
    return default_job


def get_or_create_generic_install_job():
    job = Job.query.filter_by(job_name='Install (General)', job_type='Solar Install').first()
    if job:
        if not job.is_internal:
            job.is_internal = True
            db.session.commit()
        return job
    job = Job(job_name='Install (General)', job_type='Solar Install', status='not_started', published=False, is_internal=True)
    db.session.add(job)
    db.session.commit()
    return job


def get_or_create_generic_service_job():
    job = Job.query.filter_by(job_name='Service (General)', job_type='Service').first()
    if job:
        if not job.is_internal:
            job.is_internal = True
            db.session.commit()
        return job
    job = Job(job_name='Service (General)', job_type='Service', status='not_started', published=False, is_internal=True)
    db.session.add(job)
    db.session.commit()
    return job


def run_stale_job_cleanup(force=False):
    """Archive jobs older than AUTO_DELETE_JOB_DAYS with compact historical fields.

    To avoid extra overhead, this runs at most once per hour unless force=True.
    """
    global _last_auto_purge_run
    now_utc = datetime.utcnow()
    if not force and _last_auto_purge_run and (now_utc - _last_auto_purge_run) < timedelta(hours=1):
        return 0

    cutoff = now_utc - timedelta(days=AUTO_DELETE_JOB_DAYS)
    stale_jobs = Job.query.filter(
        Job.created_at < cutoff,
        Job.job_name != 'General Time'
    ).all()
    if not stale_jobs:
        _last_auto_purge_run = now_utc
        return 0

    for job in stale_jobs:
        db.session.add(build_job_archive_entry(job))
        db.session.delete(job)

    db.session.commit()
    _last_auto_purge_run = now_utc
    return len(stale_jobs)


def build_job_archive_entry(job):
    assigned_employee_names = sorted({
        (a.employee.name or '').strip()
        for a in (job.assignments or [])
        if a.employee and (a.employee.name or '').strip()
    })
    assigned_employee = ', '.join(assigned_employee_names) if assigned_employee_names else 'Unassigned'

    assignment_dates = [a.assigned_date for a in (job.assignments or []) if a.assigned_date]
    scheduled_date = min(assignment_dates) if assignment_dates else (job.scheduled_date or job.pending_date)
    completed_date = job.completed_at.date() if job.completed_at else None

    return JobArchive(
        job_type=job.job_type or 'Unspecified',
        assigned_employee=assigned_employee,
        scheduled_date=scheduled_date,
        completed_date=completed_date
    )

def broadcast_job_update(job_id, action, job_data=None):
    """Broadcast job update to all connected clients."""
    try:
        socketio.emit('job_updated', {
            'job_id': job_id,
            'action': action,  # 'published', 'unpublished', 'assigned', 'started', 'completed', 'canceled', 'deleted'
            'job_data': job_data
        }, to=None, skip_sid=None)
    except Exception as e:
        print(f"Error broadcasting update: {e}")

# ── PWA support routes ────────────────────────────────────────────────────────
@app.route('/manifest.json')
def pwa_manifest():
    response = make_response(send_from_directory('Static', 'manifest.json'))
    response.headers['Content-Type'] = 'application/manifest+json'
    return response

@app.route('/sw.js')
def pwa_service_worker():
    response = make_response(send_from_directory('Static', 'sw.js'))
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/')
def index():
    run_stale_job_cleanup()
    current_employee = get_effective_employee()
    is_field_limited_view = effective_is_field_limited()
    is_field_user = is_field_employee(current_employee) if current_employee else False
    archive_visible = can_view_archive(current_employee) or bool(session.get('developer_user'))

    if is_field_limited_view and current_employee:
        employees = [current_employee]
        service_first_employees = [current_employee] if is_assignable_employee(current_employee) else []
        assignments = (
            Assignment.query
            .join(Job)
            .filter(Assignment.employee_id == current_employee.id)
            .filter(Job.published.is_(True))
            .filter(Job.status != 'canceled')
            .all()
        )
        jobs = sorted(
            {assign.job for assign in assignments if assign.job and not assign.job.is_internal},
            key=lambda j: (j.job_name or '').lower()
        )
        published_jobs = list(jobs)
        pending_jobs = []
        departments = []
    else:
        employees = Employee.query.order_by(Employee.name).all()
        service_first_employees = sorted(
            [e for e in employees if is_assignable_employee(e)],
            key=lambda e: (0 if has_role(e, 'Service') else 1, (e.name or '').lower())
        )
        jobs = Job.query.filter(Job.is_internal.isnot(True)).all()
        published_jobs = Job.query.filter_by(published=True).filter(Job.is_internal.isnot(True)).all()
        pending_jobs = Job.query.filter_by(published=False, pending_date=None).filter(Job.is_internal.isnot(True)).all()
        assignments = Assignment.query.all()
        departments = Department.query.all()
    for dept in departments:
        dept.groups.sort(key=crew_sort_key)

    # Build Field category: employees whose roles include field-oriented positions
    _field_role_tokens = {
        'installer', 'electrician', 'site surveyor', 'inspection tech',
        'inspections tech', 'inspections', 'crew lead', 'service'
    }
    def _is_field_employee(emp):
        cats = [c.strip().lower() for c in (emp.category or '').split(',')]
        return any(c in _field_role_tokens for c in cats)
    field_employees = sorted(
        [e for e in employees if _is_field_employee(e)],
        key=lambda e: (e.name or '').lower()
    )
    groups = sorted(Group.query.all(), key=crew_sort_key) if not is_field_limited_view else ([current_employee.group] if current_employee and current_employee.group else [])
    permission_sets = PermissionSet.query.order_by(PermissionSet.name.asc()).all() if not is_field_limited_view else []
    history = Timesheet.query.order_by(Timesheet.clock_in.desc()).limit(100).all()
    my_active_log = None
    my_recent_logs = []
    archive_items = []
    if current_employee:
        my_active_log = (
            Timesheet.query
            .filter_by(employee_id=current_employee.id, clock_out=None)
            .order_by(Timesheet.clock_in.desc())
            .first()
        )
        my_recent_logs = (
            Timesheet.query
            .filter_by(employee_id=current_employee.id)
            .order_by(Timesheet.clock_in.desc())
            .limit(5)
            .all()
        )
    completed_jobs = []
    if archive_visible:
        archive_items = JobArchive.query.order_by(JobArchive.archived_at.desc()).limit(1000).all()
        completed_jobs = Job.query.filter_by(status='completed').order_by(Job.completed_at.desc()).limit(500).all()
    _dashboard_job_types = {'emergency funding','funding','inspection','install','uninstall','reinstall','mpu','red tag','roof leak','site survey','custom shift'}
    dash_job_count = sum(1 for j in jobs if (j.job_type or '').strip().lower() in _dashboard_job_types and j.status not in ('completed', 'canceled'))
    deletion_logs = JobDeletionLog.query.order_by(JobDeletionLog.deleted_at.desc()).limit(100).all() if not is_field_limited_view else []
    # Invite codes — visible only to those who can manage them
    can_manage_invites = _can_manage_invites(current_employee) or bool(session.get('developer_user'))
    now = datetime.utcnow()
    invite_codes = InviteCode.query.filter(
        (InviteCode.expires_at == None) | (InviteCode.expires_at > now)
    ).order_by(InviteCode.created_at.desc()).limit(100).all() if can_manage_invites else []
    open_feedback_reports = []
    resolved_feedback_reports = []
    my_feedback_reports = []
    is_dev_or_support = False
    if can_view_backend(current_employee) or bool(session.get('developer_user')):
        _real = get_logged_in_employee()
        if session.get('developer_user'):
            is_dev_or_support = True
        elif _real:
            _be_roles = {(r or '').strip().lower() for r in (_real.category or '').split(',') if (r or '').strip()}
            is_dev_or_support = bool(_be_roles & {'developer', 'development', 'support'})
        open_feedback_reports = FeedbackReport.query.filter(FeedbackReport.status.in_(['received', 'open'])).order_by(FeedbackReport.submitted_at.desc()).limit(500).all()
        resolved_feedback_reports = FeedbackReport.query.filter_by(status='closed').order_by(FeedbackReport.closed_at.desc()).limit(500).all() if is_dev_or_support else []
    # Tickets submitted by the current employee (for the reply notification view)
    unread_reply_count = 0
    if current_employee:
        my_feedback_reports = FeedbackReport.query.filter_by(
            submitted_by=current_employee.name
        ).order_by(FeedbackReport.submitted_at.desc()).limit(50).all()
        unread_reply_count = sum(1 for r in my_feedback_reports if r.reply and r.status == 'closed' and not r.reply_seen)
    today_date = datetime.now().date()

    # Build a Monday-Saturday crew schedule for the current week.
    week_start = today_date - timedelta(days=today_date.weekday())
    week_dates = [week_start + timedelta(days=offset) for offset in range(6)]
    week_days = [{
        'key': day.isoformat(),
        'label': day.strftime('%a %m/%d')
    } for day in week_dates]
    week_day_keys = {d['key'] for d in week_days}

    # Full Mon-Sun blocks for the Field Schedule tab
    field_week_days = [{'key': (week_start + timedelta(days=i)).isoformat(),
                        'label': (week_start + timedelta(days=i)).strftime('%a %m/%d')} for i in range(7)]
    next_week_start_date = week_start + timedelta(days=7)
    field_next_week_days = [{'key': (next_week_start_date + timedelta(days=i)).isoformat(),
                             'label': (next_week_start_date + timedelta(days=i)).strftime('%a %m/%d')} for i in range(7)]
    field_next_week_end_key = (next_week_start_date + timedelta(days=6)).isoformat()

    # Field Schedule tab: dedicated query — always published, non-canceled, for the
    # current_employee directly (independent of is_field_limited_view so it always
    # matches what Calendar would show for that employee).
    field_schedule_assignments = []
    field_schedule_roster = []
    if current_employee:
        field_schedule_assignments = (
            Assignment.query.join(Job)
            .filter(
                Assignment.employee_id == current_employee.id,
                Job.published.is_(True),
                Job.status != 'canceled'
            )
            .order_by(Assignment.assigned_date)
            .all()
        )
        if field_schedule_assignments:
            _fs_job_ids = {a.job_id for a in field_schedule_assignments}
            field_schedule_roster = (
                Assignment.query.join(Job)
                .filter(
                    Assignment.job_id.in_(_fs_job_ids),
                    Job.published.is_(True),
                    Job.status != 'canceled'
                )
                .all()
            )

    crew_rows_by_id = {}
    for group in sorted(groups, key=lambda g: ((g.department.name if g.department else ''), g.name)):
        crew_rows_by_id[group.id] = {
            'crew': group,
            'days': {d['key']: [] for d in week_days},
            '_seen': {d['key']: set() for d in week_days}
        }

    for assign in assignments:
        day_key = assign.assigned_date.isoformat()
        if day_key not in week_day_keys:
            continue

        crew = assign.crew or assign.employee.group
        if not crew:
            continue

        if crew.id not in crew_rows_by_id:
            crew_rows_by_id[crew.id] = {
                'crew': crew,
                'days': {d['key']: [] for d in week_days},
                '_seen': {d['key']: set() for d in week_days}
            }

        row = crew_rows_by_id[crew.id]
        dedupe_key = (assign.job_id, assign.start_time, assign.end_time)
        if dedupe_key in row['_seen'][day_key]:
            continue

        row['_seen'][day_key].add(dedupe_key)
        row['days'][day_key].append({
            'job_id': assign.job.id,
            'job_name': assign.job.job_name,
            'status': assign.job.status,
            'crew_id': assign.crew_id,
            'assigned_date': day_key,
            'can_drag': bool(assign.crew_id),
            'start_time': assign.start_time.strftime('%H:%M') if assign.start_time else '',
            'end_time': assign.end_time.strftime('%H:%M') if assign.end_time else ''
        })

    crew_week_schedule = []
    for row in crew_rows_by_id.values():
        day_has_jobs = any(row['days'][d['key']] for d in week_days)
        if day_has_jobs:
            crew_week_schedule.append({
                'crew': row['crew'],
                'days': row['days']
            })

    crew_week_schedule.sort(key=lambda r: crew_sort_key(r['crew']))

    # Install kW summary: Crew 1-5 totals plus per-employee weekly payroll view.
    allowed_kw_crews = {'crew 1', 'crew 2', 'crew 3', 'crew 4', 'crew 5'}
    crew_kw_map = {
        f'crew-{group.id}': {
            'entity_name': group.name,
            'entity_color': group.color or '#667eea',
            'sort_group': crew_sort_key(group),
            'sort_name': (group.name or '').lower(),
            'total_kw': 0.0,
            'daily_map': {},
            'week_member_map': {}
        }
        for group in groups
        if (group.name or '').strip().lower() in allowed_kw_crews
    }
    seen_crew_job_dates = set()
    seen_member_job_dates = set()

    for assign in assignments:
        if not assign.job or assign.job.status == 'canceled' or not assign.assigned_date:
            continue

        job_type_norm = (assign.job.job_type or '').strip().lower()
        if 'install' not in job_type_norm:
            continue

        crew = assign.crew or assign.employee.group
        if not crew:
            continue

        entity_key = f'crew-{crew.id}'
        if entity_key not in crew_kw_map:
            continue

        kw_value = parse_kw_value(assign.job.system_size)
        if kw_value <= 0:
            continue

        day_key = assign.assigned_date.isoformat()

        dedupe_key = (entity_key, day_key, assign.job.id)
        if dedupe_key in seen_crew_job_dates:
            continue
        seen_crew_job_dates.add(dedupe_key)

        crew_bucket = crew_kw_map[entity_key]
        crew_bucket['total_kw'] += kw_value

        day_bucket = crew_bucket['daily_map'].setdefault(day_key, {
            'date': assign.assigned_date,
            'date_label': assign.assigned_date.strftime('%a %m/%d/%Y'),
            'total_kw': 0.0,
            'jobs': []
        })
        day_bucket['total_kw'] += kw_value
        day_bucket['jobs'].append({
            'job_name': assign.job.job_name,
            'kw': kw_value
        })

        # Weekly payroll view: kW by employee/day (Mon-Sat current week).
        if day_key in week_day_keys:
            member_dedupe_key = (entity_key, assign.employee_id, day_key, assign.job.id)
            if member_dedupe_key in seen_member_job_dates:
                continue
            seen_member_job_dates.add(member_dedupe_key)

            member_bucket = crew_bucket['week_member_map'].setdefault(assign.employee_id, {
                'employee_name': assign.employee.name,
                'day_kw': {d['key']: 0.0 for d in week_days},
                'week_total_kw': 0.0
            })
            member_bucket['day_kw'][day_key] += kw_value
            member_bucket['week_total_kw'] += kw_value

    crew_kw_summary = []
    for bucket in crew_kw_map.values():
        daily_rows = sorted(bucket['daily_map'].values(), key=lambda d: d['date'], reverse=True)
        for day in daily_rows:
            day['jobs'].sort(key=lambda j: (j['job_name'] or '').lower())

        week_members = sorted(
            bucket['week_member_map'].values(),
            key=lambda m: (m['employee_name'] or '').lower()
        )
        for member in week_members:
            member['week_total_kw'] = round(member['week_total_kw'], 2)

        crew_kw_summary.append({
            'entity_name': bucket['entity_name'],
            'entity_color': bucket['entity_color'],
            'total_kw': round(bucket['total_kw'], 2),
            'daily': daily_rows,
            'week_members': week_members,
            'sort_group': bucket['sort_group'],
            'sort_name': bucket['sort_name']
        })

    crew_kw_summary.sort(key=lambda row: (row['sort_group'], row['sort_name']))

    # Build an employee-by-date schedule window for the Calendar tab.
    requested_schedule_start = (request.args.get('schedule_start') or '').strip()
    try:
        _anchor = datetime.strptime(requested_schedule_start, '%Y-%m-%d').date() if requested_schedule_start else today_date
    except ValueError:
        _anchor = today_date
    # Snap to Monday of the week containing the anchor date (weekday(): Mon=0, Sun=6)
    employee_window_start = _anchor - timedelta(days=_anchor.weekday())

    employee_window_dates = [employee_window_start + timedelta(days=offset) for offset in range(14)]
    employee_schedule_days = [{
        'key': day.isoformat(),
        'label': day.strftime('%a %m/%d')
    } for day in employee_window_dates]
    employee_day_keys = {d['key'] for d in employee_schedule_days}

    employee_schedule_rows_by_id = {
        emp.id: {
            'employee': emp,
            'days': {d['key']: [] for d in employee_schedule_days}
        }
        for emp in sorted(employees, key=lambda e: (e.name or '').lower())
    }

    for assign in assignments:
        if assign.job.status == 'canceled':
            continue

        day_key = assign.assigned_date.isoformat()
        if day_key not in employee_day_keys:
            continue

        row = employee_schedule_rows_by_id.get(assign.employee_id)
        if not row:
            continue

        crew = assign.crew or assign.employee.group
        crew_name = crew.name if crew else 'Unassigned Crew'
        crew_color = crew.color if crew and crew.color else '#667eea'
        crew_members = [m.name for m in (crew.employees if crew else []) if m and m.name]
        crew_lead = next((m.name for m in (crew.employees if crew else []) if has_role(m, 'Crew Lead')), '')
        electrician = next((m.name for m in (crew.employees if crew else []) if has_role(m, 'Electrician')), '')
        job_type_color = get_job_type_color(assign.job.job_type)
        chip_color = crew_color if assign.crew_id else job_type_color
        job_type_norm = (assign.job.job_type or '').strip().lower()
        is_install_like = 'install' in job_type_norm
        chip_title = assign.job.job_name if is_install_like else (assign.job.job_type or assign.job.job_name)

        row['days'][day_key].append({
            'assignment_id': assign.id,
            'job_id': assign.job.id,
            'job_name': assign.job.job_name,
            'chip_title': chip_title,
            'job_type': assign.job.job_type,
            'published': assign.job.published,
            'status': assign.job.status,
            'start_time': assign.start_time.strftime('%H:%M') if assign.start_time else '',
            'end_time': assign.end_time.strftime('%H:%M') if assign.end_time else '',
            'assigned_date': day_key,
            'po_number': assign.job.po_number or '',
            'address': assign.job.address or '',
            'phone_number': assign.job.phone_number or '',
            'story': assign.job.story or '',
            'description': assign.job.description or '',
            'system_size': assign.job.system_size or '',
            'day_pay': bool(assign.day_pay),
            'crew_id': crew.id if crew else '',
            'crew_name': crew_name,
            'crew_color': crew_color,
            'chip_color': chip_color,
            'crew_lead': crew_lead,
            'electrician': electrician,
            'crew_members': crew_members,
            'display_employee': row['employee'].name or ''
        })

    employee_schedule_rows = list(employee_schedule_rows_by_id.values())
    employee_schedule_rows.sort(key=lambda r: (r['employee'].name or '').lower())

    # Group rows by crew first. If an employee is assigned to a crew,
    # they are listed under that crew once. Only non-crew employees are
    # grouped by role hierarchy.
    role_hierarchy = [
        ('Crew Lead', ['Crew Lead']),
        ('Installer', ['Installer', 'Electrician']),
        ('Service', ['Service']),
        ('Site Surveyor / Inspections', ['Site Surveyor', 'Inspection Tech', 'Inspections', 'Inspections Tech'])
    ]

    def employee_role_tokens(employee):
        return {(r or '').strip().lower() for r in (employee.category or '').split(',') if (r or '').strip()}

    crew_rows = {}
    section_rows = {title: [] for title, _aliases in role_hierarchy}
    section_rows['Other'] = []
    section_rows['Office / Support / Development'] = []
    bottom_role_tokens = {'office', 'support', 'development'}

    for row in employee_schedule_rows:
        tokens = employee_role_tokens(row['employee'])
        if tokens & bottom_role_tokens:
            section_rows['Office / Support / Development'].append(row)
            continue

        crew = row['employee'].group
        if crew:
            bucket = crew_rows.setdefault(crew.id, {
                'crew': crew,
                'rows': []
            })
            bucket['rows'].append(row)
            continue

        assigned_section = None
        for section_title, aliases in role_hierarchy:
            if any(alias.lower() in tokens for alias in aliases):
                assigned_section = section_title
                break

        if not assigned_section:
            assigned_section = 'Other'

        section_rows[assigned_section].append(row)

    employee_schedule_sections = []
    def crew_member_sort_key(row):
        emp = row['employee']
        if has_role(emp, 'Crew Lead'):
            rank = 0
        elif has_role(emp, 'Electrician'):
            rank = 1
        else:
            rank = 2
        return (rank, (emp.name or '').lower())

    for bucket in sorted(crew_rows.values(), key=lambda b: crew_sort_key(b['crew'])):
        bucket['rows'].sort(key=crew_member_sort_key)
        employee_schedule_sections.append({
            'title': bucket['crew'].name,
            'rows': bucket['rows'],
            'is_crew': True,
            'color': bucket['crew'].color or '#1f2f4f'
        })

    for section_title, _aliases in role_hierarchy:
        rows = section_rows.get(section_title, [])
        if rows:
            rows.sort(key=lambda r: (r['employee'].name or '').lower())
            employee_schedule_sections.append({
                'title': section_title,
                'rows': rows,
                'is_crew': False,
                'color': None
            })

    if section_rows.get('Other'):
        section_rows['Other'].sort(key=lambda r: (r['employee'].name or '').lower())
        employee_schedule_sections.append({
            'title': 'Other',
            'rows': section_rows['Other'],
            'is_crew': False,
            'color': None
        })

    if section_rows.get('Office / Support / Development'):
        section_rows['Office / Support / Development'].sort(key=lambda r: (r['employee'].name or '').lower())
        employee_schedule_sections.append({
            'title': 'Office / Support / Development',
            'rows': section_rows['Office / Support / Development'],
            'is_crew': False,
            'color': None
        })

    employee_window_prev = (employee_window_start - timedelta(days=14)).isoformat()
    employee_window_next = (employee_window_start + timedelta(days=14)).isoformat()
    employee_window_today = today_date.isoformat()
    employee_window_end = (employee_window_start + timedelta(days=13)).isoformat()

    tentative_jobs = [
        job for job in jobs
        if len(job.assignments) == 0 and not job.pending_date and job.status != 'canceled'
    ]
    tentative_jobs_by_type_map = {}
    for job in tentative_jobs:
        job_type_label = (job.job_type or '').strip() or 'Unspecified'
        if job_type_label not in tentative_jobs_by_type_map:
            tentative_jobs_by_type_map[job_type_label] = []
        tentative_jobs_by_type_map[job_type_label].append(job)

    tentative_jobs_by_type = [
        {
            'job_type': job_type,
            'jobs': sorted(grouped_jobs, key=lambda j: (j.job_name or '').lower()),
            'color': get_job_type_color(job_type)
        }
        for job_type, grouped_jobs in sorted(
            tentative_jobs_by_type_map.items(),
            key=lambda item: (item[0] or '').lower()
        )
    ]

    # Calendar search index: one row per job with earliest known scheduled date.
    search_by_job = {}
    for assign in assignments:
        if not assign.job or assign.job.status == 'canceled' or not assign.assigned_date:
            continue
        existing = search_by_job.get(assign.job_id)
        date_key = assign.assigned_date.isoformat()
        if not existing or date_key < existing['d']:
            search_by_job[assign.job_id] = {
                'id': assign.job_id,
                'n': assign.job.job_name or '',
                't': assign.job.job_type or '',
                'd': date_key,
            }

    for job in jobs:
        if job.status == 'canceled' or not job.scheduled_date:
            continue
        existing = search_by_job.get(job.id)
        date_key = job.scheduled_date.isoformat()
        if not existing or date_key < existing['d']:
            search_by_job[job.id] = {
                'id': job.id,
                'n': job.job_name or '',
                't': job.job_type or '',
                'd': date_key,
            }

    calendar_search_index = sorted(search_by_job.values(), key=lambda row: row['d'])

    # Payroll weekly summary
    _payroll_week_start = today_date - timedelta(days=today_date.weekday())
    payroll_data = _build_payroll_data(_payroll_week_start)

    # Manager at-a-glance stats
    _real_emp = get_logged_in_employee()
    _mgr_stats = {}
    if is_manager_or_admin(_real_emp) or session.get('developer_user'):
        _today_staffed = set()
        _today_jobs_set = set()
        for a in assignments:
            if a.assigned_date == today_date and a.job and a.job.status != 'canceled':
                _today_staffed.add(a.employee_id)
                _today_jobs_set.add(a.job_id)
        # Approved time-off starting in next 7 days
        _near_tor = TimeOffRequest.query.filter(
            TimeOffRequest.status == 'approved',
            TimeOffRequest.start_date >= today_date,
            TimeOffRequest.start_date <= today_date + timedelta(days=7)
        ).order_by(TimeOffRequest.start_date).all()
        # Jobs needing attention: not cancelled, no assignments, no pending_date
        _needs_assign = sum(
            1 for j in jobs
            if j.status not in ('canceled', 'completed') and not j.assignments and not j.pending_date
        )
        _mgr_stats = {
            'today_staff_count': len(_today_staffed),
            'today_job_count': len(_today_jobs_set),
            'upcoming_tor': _near_tor,
            'needs_assignment': _needs_assign,
        }

    # Build crew_city_map + crew_address_map: derive city/full-address from most relevant active job per crew
    def _extract_city(addr):
        if not addr:
            return None
        parts = [p.strip() for p in addr.split(',')]
        return parts[1] if len(parts) >= 2 else (parts[0] if parts else None)

    _crew_city_candidates  = {}  # group_id -> list of (assigned_date, city, full_address)
    for _a in assignments:
        if not _a.crew_id or not _a.job or _a.job.status in ('canceled', 'completed'):
            continue
        _city = _extract_city(_a.job.address)
        if not _city:
            continue
        _full_addr = (_a.job.address or '').strip()
        _crew_city_candidates.setdefault(_a.crew_id, []).append((_a.assigned_date, _city, _full_addr))

    crew_city_map    = {}
    crew_address_map = {}  # group_id -> full job address for map geocoding
    for _gid, _candidates in _crew_city_candidates.items():
        _future = [(d, c, a) for d, c, a in _candidates if d >= today_date]
        _past   = [(d, c, a) for d, c, a in _candidates if d < today_date]
        _chosen = min(_future, key=lambda x: x[0]) if _future else (max(_past, key=lambda x: x[0]) if _past else None)
        if _chosen:
            crew_city_map[_gid]    = _chosen[1]
            crew_address_map[_gid] = _chosen[2]

    return render_template('index.html', employees=employees, service_first_employees=service_first_employees, jobs=jobs, published_jobs=published_jobs,
                         pending_jobs=pending_jobs, assignments=assignments,
                         departments=departments, groups=groups, history=history,
                         my_active_log=my_active_log, my_recent_logs=my_recent_logs,
                         generic_install_job_id=get_or_create_generic_install_job().id,
                         generic_service_job_id=get_or_create_generic_service_job().id,
                         archive_items=archive_items,
                         completed_jobs=completed_jobs,
                         open_feedback_reports=open_feedback_reports,
                         resolved_feedback_reports=resolved_feedback_reports,
                         my_feedback_reports=my_feedback_reports,
                         unread_reply_count=unread_reply_count,
                         is_dev_or_support=is_dev_or_support,
                         permission_sets=permission_sets,
                         deletion_logs=deletion_logs,
                         crew_kw_summary=crew_kw_summary,
                         is_field_limited_view=is_field_limited_view,
                         is_field_user=is_field_user,
                         dash_job_count=dash_job_count,
                         field_employees=field_employees,
                         today_date=today_date, week_days=week_days,
                         field_week_days=field_week_days,
                         field_next_week_days=field_next_week_days,
                         field_next_week_end_key=field_next_week_end_key,
                         field_schedule_assignments=field_schedule_assignments,
                         field_schedule_roster=field_schedule_roster,
                         crew_week_schedule=crew_week_schedule,
                         employee_schedule_days=employee_schedule_days,
                         employee_schedule_rows=employee_schedule_rows,
                         employee_schedule_sections=employee_schedule_sections,
                         employee_window_start=employee_window_start,
                         employee_window_end=employee_window_end,
                         employee_window_prev=employee_window_prev,
                         employee_window_next=employee_window_next,
                         employee_window_today=employee_window_today,
                         tentative_jobs_total=len(tentative_jobs),
                         tentative_jobs_by_type=tentative_jobs_by_type,
                         calendar_search_index=calendar_search_index,
                         payroll_data=payroll_data,
                         invite_codes=invite_codes,
                         mgr_stats=_mgr_stats,
                         _can_manage_invites=can_manage_invites,
                         crew_city_map=crew_city_map,
                         crew_address_map=crew_address_map)

# ── Payroll API ─────────────────────────────────────────────────────────────

@app.route('/api/my-hours')
def my_hours_api():
    if not is_authenticated_session():
        return jsonify({'error': 'unauthorized'}), 401
    emp = get_logged_in_employee()
    if not emp:
        return jsonify({'error': 'no employee'}), 403

    week_str = (request.args.get('week') or '').strip()
    try:
        requested = datetime.strptime(week_str, '%Y-%m-%d').date()
        week_start = requested - timedelta(days=requested.weekday())
    except ValueError:
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())

    week_end = week_start + timedelta(days=6)
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    assigns = (
        Assignment.query.join(Job)
        .filter(
            Assignment.employee_id == emp.id,
            Assignment.assigned_date >= week_start,
            Assignment.assigned_date <= week_end,
            Job.status != 'canceled'
        )
        .order_by(Assignment.assigned_date, Assignment.start_time)
        .all()
    )

    rows = []
    total_hours = 0.0
    seen = set()
    for a in assigns:
        dedupe = (a.job_id, a.assigned_date, a.start_time, a.end_time)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        hours = None
        if a.start_time and a.end_time:
            start_m = a.start_time.hour * 60 + a.start_time.minute
            end_m = a.end_time.hour * 60 + a.end_time.minute
            h = round((end_m - start_m) / 60, 2)
            if h > 0:
                hours = h
                total_hours += h
        rows.append({
            '_sort': (a.assigned_date, a.start_time or datetime.min.time()),
            'day_name': day_names[a.assigned_date.weekday()],
            'date': a.assigned_date.strftime('%m/%d/%Y'),
            'job_name': a.job.job_name if a.job else '—',
            'start_time': a.start_time.strftime('%I:%M %p') if a.start_time else None,
            'end_time': a.end_time.strftime('%I:%M %p') if a.end_time else None,
            'hours': hours,
        })

    # Also include clock-in/out timesheet entries (used by office employees)
    week_start_dt = datetime.combine(week_start, datetime.min.time())
    week_end_dt = datetime.combine(week_end + timedelta(days=1), datetime.min.time())
    timesheets = (
        Timesheet.query
        .filter(
            Timesheet.employee_id == emp.id,
            Timesheet.clock_in >= week_start_dt,
            Timesheet.clock_in < week_end_dt,
            Timesheet.clock_out.isnot(None)
        )
        .order_by(Timesheet.clock_in)
        .all()
    )
    for ts in timesheets:
        h = round((ts.clock_out - ts.clock_in).total_seconds() / 3600, 2)
        if h <= 0:
            continue
        total_hours += h
        day_date = ts.clock_in.date()
        rows.append({
            '_sort': (day_date, ts.clock_in.time()),
            'day_name': day_names[day_date.weekday()],
            'date': day_date.strftime('%m/%d/%Y'),
            'job_name': ts.job.job_name if ts.job else '—',
            'start_time': ts.clock_in.strftime('%I:%M %p'),
            'end_time': ts.clock_out.strftime('%I:%M %p'),
            'hours': h,
        })

    rows.sort(key=lambda r: r['_sort'])
    for r in rows:
        del r['_sort']

    return jsonify({'rows': rows, 'total_hours': round(total_hours, 2)})

@app.route('/api/payroll-week')
def payroll_week_api():
    if not is_authenticated_session():
        return jsonify({'error': 'unauthorized'}), 401
    week_start_str = (request.args.get('week_start') or '').strip()
    try:
        requested = datetime.strptime(week_start_str, '%Y-%m-%d').date()
        week_start = requested - timedelta(days=requested.weekday())
    except ValueError:
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
    return jsonify(_build_payroll_data(week_start))


@app.route('/payroll/export')
def payroll_export():
    if not is_authenticated_session():
        return redirect(url_for('login'))
    week_start_str = (request.args.get('week_start') or '').strip()
    try:
        requested = datetime.strptime(week_start_str, '%Y-%m-%d').date()
        week_start = requested - timedelta(days=requested.weekday())
    except ValueError:
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
    data = _build_payroll_data(week_start)
    group_filter = (request.args.get('group') or 'all').strip().lower()

    buf = io.StringIO()
    writer = csv.writer(buf)
    header = ['Employee', 'Department', 'Crew']
    for d in data['days']:
        if group_filter == 'office':
            header.append(d['label'] + ' Hours')
        else:
            header += [d['label'] + ' Hours', d['label'] + ' kW']
    header.append('Total Hours')
    if group_filter != 'office':
        header.append('Total kW')
    writer.writerow(header)

    for emp in data['employees']:
        if group_filter == 'field' and not emp['is_field']:
            continue
        if group_filter == 'office' and emp['is_field']:
            continue
        row = [emp['name'], emp['department'], emp['group']]
        for d in data['days']:
            h  = emp['daily_hours'][d['key']]
            kw = emp['daily_kw'][d['key']]
            if group_filter == 'office':
                row.append(round(h, 2) if h > 0 else '')
            else:
                row.append(round(h,  2) if h  > 0 else '')
                row.append(round(kw, 2) if kw > 0 else '')
        row.append(round(emp['total_hours'], 2) if emp['total_hours'] > 0 else '')
        if group_filter != 'office':
            row.append(round(emp['total_kw'], 2) if emp['total_kw'] > 0 else '')
        writer.writerow(row)

    buf.seek(0)
    filename = f"payroll_{data['week_start']}_to_{data['week_end']}.csv"
    from flask import Response as FlaskResponse
    return FlaskResponse(
        buf.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


# ── Payroll Editing API ──────────────────────────────────────────────────────

def _payroll_edit_authorized():
    """Anyone who can view the payroll tab may also edit it."""
    if not is_authenticated_session():
        return False
    emp = get_effective_employee()
    return can_view_payroll_tab(emp)

@app.route('/api/payroll-day-detail')
def payroll_day_detail():
    if not _payroll_edit_authorized():
        return jsonify({'error': 'unauthorized'}), 403
    try:
        emp_id  = int(request.args.get('employee_id', 0))
        day_str = request.args.get('date', '')
        day     = datetime.strptime(day_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid params'}), 400

    emp = Employee.query.get(emp_id)
    if not emp:
        return jsonify({'error': 'employee not found'}), 404

    day_start = datetime(day.year, day.month, day.day)
    day_end   = day_start + timedelta(days=1)
    entries = Timesheet.query.filter(
        Timesheet.employee_id == emp_id,
        Timesheet.clock_in >= day_start,
        Timesheet.clock_in <  day_end
    ).order_by(Timesheet.clock_in).all()

    adj = PayrollAdjustment.query.filter_by(employee_id=emp_id, date=day).first()

    jobs = Job.query.order_by(Job.job_name).all()

    return jsonify({
        'employee_id':   emp_id,
        'employee_name': emp.name or '',
        'date':          day_str,
        'timesheets': [
            {
                'id':        ts.id,
                'job_id':    ts.job_id,
                'job_name':  ts.job.job_name if ts.job else '—',
                'clock_in':  ts.clock_in.strftime('%Y-%m-%dT%H:%M') if ts.clock_in else '',
                'clock_out': ts.clock_out.strftime('%Y-%m-%dT%H:%M') if ts.clock_out else '',
                'hours':     round((ts.clock_out - ts.clock_in).total_seconds() / 3600.0, 2)
                             if ts.clock_in and ts.clock_out else None,
            }
            for ts in entries
        ],
        'adjustment': {
            'hours': adj.hours_adjustment if adj else 0.0,
            'kw':    adj.kw_adjustment    if adj else 0.0,
            'note':  adj.note             if adj else '',
        },
        'jobs': [{'id': j.id, 'name': j.job_name} for j in jobs],
    })


@app.route('/api/payroll-timesheet-save', methods=['POST'])
def payroll_timesheet_save():
    if not _payroll_edit_authorized():
        return jsonify({'error': 'unauthorized'}), 403
    data = request.get_json(force=True) or {}
    ts_id     = data.get('id')
    emp_id    = data.get('employee_id')
    job_id    = data.get('job_id')
    ci_raw    = (data.get('clock_in') or '').strip()
    co_raw    = (data.get('clock_out') or '').strip()

    if not ci_raw:
        return jsonify({'error': 'clock_in required'}), 400
    try:
        ci = datetime.strptime(ci_raw, '%Y-%m-%dT%H:%M')
    except ValueError:
        return jsonify({'error': 'invalid clock_in'}), 400
    co = None
    if co_raw:
        try:
            co = datetime.strptime(co_raw, '%Y-%m-%dT%H:%M')
        except ValueError:
            return jsonify({'error': 'invalid clock_out'}), 400
    if co and co < ci:
        return jsonify({'error': 'clock_out before clock_in'}), 400

    if ts_id:
        ts = Timesheet.query.get(int(ts_id))
        if not ts:
            return jsonify({'error': 'not found'}), 404
        ts.clock_in  = ci
        ts.clock_out = co
        if job_id and str(job_id).isdigit() and Job.query.get(int(job_id)):
            ts.job_id = int(job_id)
    else:
        if not emp_id or not job_id:
            return jsonify({'error': 'employee_id and job_id required for new entry'}), 400
        emp = Employee.query.get(int(emp_id))
        if not emp:
            return jsonify({'error': 'employee not found'}), 404
        if not Job.query.get(int(job_id)):
            return jsonify({'error': 'job not found'}), 404
        ts = Timesheet(
            employee_id=int(emp_id),
            job_id=int(job_id),
            clock_in=ci,
            clock_out=co,
            employee_name_snapshot=emp.name,
            employee_email_snapshot=emp.email,
            employee_phone_snapshot=emp.phone_number,
        )
        db.session.add(ts)

    db.session.commit()
    return jsonify({'ok': True, 'id': ts.id})


@app.route('/api/payroll-timesheet-delete/<int:ts_id>', methods=['POST'])
def payroll_timesheet_delete(ts_id):
    if not _payroll_edit_authorized():
        return jsonify({'error': 'unauthorized'}), 403
    ts = Timesheet.query.get(ts_id)
    if not ts:
        return jsonify({'error': 'not found'}), 404
    db.session.delete(ts)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/api/payroll-adjustment-save', methods=['POST'])
def payroll_adjustment_save():
    if not _payroll_edit_authorized():
        return jsonify({'error': 'unauthorized'}), 403
    data = request.get_json(force=True) or {}
    try:
        emp_id  = int(data.get('employee_id', 0))
        day     = datetime.strptime(data.get('date', ''), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid params'}), 400

    try:
        hours_adj = float(data.get('hours', 0) or 0)
        kw_adj    = float(data.get('kw', 0) or 0)
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid numbers'}), 400

    note = (data.get('note') or '').strip()[:200]

    adj = PayrollAdjustment.query.filter_by(employee_id=emp_id, date=day).first()
    if hours_adj == 0 and kw_adj == 0 and not note:
        if adj:
            db.session.delete(adj)
            db.session.commit()
        return jsonify({'ok': True, 'deleted': True})

    if not adj:
        if not Employee.query.get(emp_id):
            return jsonify({'error': 'employee not found'}), 404
        adj = PayrollAdjustment(employee_id=emp_id, date=day)
        db.session.add(adj)
    adj.hours_adjustment = hours_adj
    adj.kw_adjustment    = kw_adj
    adj.note             = note or None
    db.session.commit()
    return jsonify({'ok': True})


# Department Management
@app.route('/department/add', methods=['POST'])
def add_department():
    dept_name = request.form.get('department_name')
    if dept_name:
        new_dept = Department(name=dept_name)
        db.session.add(new_dept)
        db.session.commit()
        flash(f'Department {dept_name} added successfully', 'success')
    return redirect(url_for('index'))

@app.route('/department/<int:id>/delete')
def delete_department(id):
    department = Department.query.get(id)
    if department:
        department_name = department.name
        db.session.delete(department)
        db.session.commit()
        return delete_route_response('Department deleted', {
            'deleted_type': 'department',
            'deleted_id': id,
            'deleted_name': department_name
        })
    if is_ajax_request():
        return jsonify({'ok': False, 'message': 'Department not found'}), 404
    return redirect(url_for('index'))

# Group Management
@app.route('/group/add', methods=['POST'])
def add_group():
    group_name = request.form.get('group_name')
    dept_id = request.form.get('department_id')
    group_color = request.form.get('group_color') or '#667eea'
    group_city = (request.form.get('group_city') or '').strip() or None
    if group_name and dept_id:
        new_group = Group(name=group_name, department_id=dept_id, color=group_color, city=group_city)
        db.session.add(new_group)
        db.session.commit()
        flash(f'Group {group_name} added successfully', 'success')
    return redirect(url_for('index'))

@app.route('/group/<int:id>/delete')
def delete_group(id):
    group = Group.query.get(id)
    if group:
        group_name = group.name
        db.session.delete(group)
        db.session.commit()
        return delete_route_response('Group deleted', {
            'deleted_type': 'group',
            'deleted_id': id,
            'deleted_name': group_name
        })
    if is_ajax_request():
        return jsonify({'ok': False, 'message': 'Group not found'}), 404
    return redirect(url_for('index'))


@app.route('/group/<int:id>/update', methods=['POST'])
def update_group(id):
    group = Group.query.get(id)
    if not group:
        flash('Crew not found.', 'danger')
        return redirect(url_for('index'))

    group_name = request.form.get('group_name')
    department_id = request.form.get('department_id')
    group_color = request.form.get('group_color') or '#667eea'

    if not group_name or not department_id:
        flash('Crew name and department are required.', 'danger')
        return redirect(url_for('index'))

    group_city = (request.form.get('group_city') or '').strip() or None
    group.name = group_name
    group.department_id = department_id
    group.color = group_color
    group.city = group_city
    db.session.commit()
    flash(f'Crew {group_name} updated successfully', 'success')
    return redirect(url_for('index'))


@app.route('/permissions/set/add', methods=['POST'])
def add_permission_set():
    set_name = (request.form.get('set_name') or '').strip()
    if not set_name:
        flash('Permission set name is required.', 'danger')
        return redirect(url_for('index'))

    existing = PermissionSet.query.filter(db.func.lower(PermissionSet.name) == set_name.lower()).first()
    if existing:
        flash('A permission set with that name already exists.', 'danger')
        return redirect(url_for('index'))

    values = extract_permission_values(request.form)
    if not _can_grant_payroll(get_effective_employee()):
        values.pop('can_view_payroll', None)
    permission_set = PermissionSet(name=set_name, **values)
    db.session.add(permission_set)
    db.session.commit()
    flash(f'Permission set "{set_name}" created.', 'success')
    return redirect(url_for('index'))


@app.route('/permissions/set/<int:id>/update', methods=['POST'])
def update_permission_set(id):
    permission_set = PermissionSet.query.get(id)
    if not permission_set:
        flash('Permission set not found.', 'danger')
        return redirect(url_for('index'))

    set_name = (request.form.get('set_name') or '').strip()
    if not set_name:
        flash('Permission set name is required.', 'danger')
        return redirect(url_for('index'))

    name_conflict = PermissionSet.query.filter(
        db.func.lower(PermissionSet.name) == set_name.lower(),
        PermissionSet.id != permission_set.id
    ).first()
    if name_conflict:
        flash('Another permission set already uses that name.', 'danger')
        return redirect(url_for('index'))

    permission_set.name = set_name
    values = extract_permission_values(request.form)
    if not _can_grant_payroll(get_effective_employee()):
        values.pop('can_view_payroll', None)
    for key, enabled in values.items():
        setattr(permission_set, key, enabled)

    db.session.commit()
    flash(f'Permission set "{set_name}" updated.', 'success')
    return redirect(url_for('index'))


@app.route('/permissions/apply/group', methods=['POST'])
def apply_permission_set_to_group():
    group_id = request.form.get('group_id')
    permission_set_id = request.form.get('permission_set_id')

    group = Group.query.get(group_id) if group_id else None
    if not group:
        if is_ajax_request():
            return jsonify({'ok': False, 'message': 'Crew/group not found.'}), 404
        flash('Crew/group not found.', 'danger')
        return redirect(url_for('index'))

    permission_set = PermissionSet.query.get(permission_set_id) if permission_set_id else None
    group.permission_set_id = permission_set.id if permission_set else None
    db.session.commit()

    if permission_set:
        message = f'Applied permission set "{permission_set.name}" to group "{group.name}".'
        if is_ajax_request():
            return jsonify({'ok': True, 'message': message, 'group_id': group.id, 'permission_set_id': permission_set.id})
        flash(message, 'success')
    else:
        message = f'Cleared group-level permission set for "{group.name}".'
        if is_ajax_request():
            return jsonify({'ok': True, 'message': message, 'group_id': group.id, 'permission_set_id': ''})
        flash(message, 'info')
    return redirect(url_for('index'))


@app.route('/permissions/apply/employee', methods=['POST'])
def apply_permission_set_to_employee():
    employee_id = request.form.get('employee_id')
    permission_set_id = request.form.get('permission_set_id')

    employee = Employee.query.get(employee_id) if employee_id else None
    if not employee:
        flash('Employee not found.', 'danger')
        return redirect(url_for('index'))

    permission_set = PermissionSet.query.get(permission_set_id) if permission_set_id else None
    employee.permission_set_id = permission_set.id if permission_set else None
    db.session.commit()

    if permission_set:
        flash(f'Applied permission set "{permission_set.name}" to employee "{employee.name}".', 'success')
    else:
        flash(f'Cleared employee override permission set for "{employee.name}".', 'info')
    return redirect(url_for('index'))

# Employee Management
@app.route('/employee/add', methods=['POST'])
def add_employee():
    name = request.form.get('employee_name')
    group_id = request.form.get('group_id')
    categories = parse_employee_categories(request.form)
    category = ', '.join(categories) if categories else ''
    phone_number = request.form.get('phone_number', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    if not name:
        if is_ajax_request():
            return jsonify({'ok': False, 'message': 'Employee name is required.'}), 400
        flash('Employee name is required.', 'danger')
        return redirect(url_for('index'))
    if not category:
        if is_ajax_request():
            return jsonify({'ok': False, 'message': 'At least one position is required.'}), 400
        flash('At least one position is required.', 'danger')
        return redirect(url_for('index'))
    if not phone_number:
        if is_ajax_request():
            return jsonify({'ok': False, 'message': 'Phone number is required.'}), 400
        flash('Phone number is required.', 'danger')
        return redirect(url_for('index'))
    if not email:
        if is_ajax_request():
            return jsonify({'ok': False, 'message': 'Email is required.'}), 400
        flash('Email is required.', 'danger')
        return redirect(url_for('index'))
    email_in_use = Employee.query.filter(db.func.lower(Employee.email) == email.lower()).first()
    if email_in_use:
        if is_ajax_request():
            return jsonify({'ok': False, 'message': 'Email is already used by another employee.'}), 400
        flash('Email is already used by another employee.', 'danger')
        return redirect(url_for('index'))
    if not password:
        if is_ajax_request():
            return jsonify({'ok': False, 'message': 'Password is required.'}), 400
        flash('Password is required.', 'danger')
        return redirect(url_for('index'))
    new_employee = Employee(
        name=name,
        category=category,
        phone_number=phone_number,
        email=email,
        password_hash=generate_password_hash(password),
        group_id=group_id if group_id else None
    )
    db.session.add(new_employee)
    db.session.commit()
    if is_ajax_request():
        section_info = get_calendar_section_for_employee(new_employee)
        return jsonify({
            'ok': True,
            'message': f'Employee {name} added successfully',
            'employee': {
                'id': new_employee.id,
                'name': new_employee.name,
                'category': new_employee.category or '',
                'group_name': new_employee.group.name if new_employee.group else '',
                'calendar_section_title': section_info['title'],
                'calendar_section_is_crew': section_info['is_crew'],
                'calendar_section_color': section_info['color']
            }
        })
    flash(f'Employee {name} added successfully', 'success')
    return redirect(url_for('index'))

@app.route('/employee/<int:id>/delete')
def delete_employee(id):
    employee = Employee.query.get(id)
    if employee:
        employee_name = employee.name
        db.session.delete(employee)
        db.session.commit()
        return delete_route_response('Employee deleted', {
            'deleted_type': 'employee',
            'deleted_id': id,
            'deleted_name': employee_name
        })
    if is_ajax_request():
        return jsonify({'ok': False, 'message': 'Employee not found'}), 404
    return redirect(url_for('index'))


@app.route('/employee/test/cleanup', methods=['POST'])
def cleanup_test_employees():
    current_employee = get_effective_employee()
    is_admin = effective_is_dev_session() or (
        current_employee and 'manager' in {
            (r or '').strip().lower()
            for r in (current_employee.category or '').split(',')
        }
    )
    if not is_admin:
        pset = resolve_effective_permission_set(current_employee)
        if not (pset and pset.can_manage_employees):
            flash('You do not have permission to clean up test employees.', 'danger')
            return redirect(url_for('index', tab='management'))

    test_employees = Employee.query.filter(Employee.name.like('TestEmployee (%)')).all()
    if not test_employees:
        flash('No TestEmployee records were found.', 'info')
        return redirect(url_for('index', tab='management'))

    deleted_count = len(test_employees)
    for employee in test_employees:
        db.session.delete(employee)
    db.session.commit()

    flash(f'Deleted {deleted_count} TestEmployee records.', 'success')
    return redirect(url_for('index', tab='management'))

@app.route('/employee/<int:id>/update', methods=['POST'])
def update_employee(id):
    employee = Employee.query.get(id)
    def _fail(message, status=400):
        if is_ajax_request():
            return jsonify({'ok': False, 'message': message}), status
        flash(message, 'danger')
        return redirect(url_for('index'))

    if not employee:
        return _fail('Employee not found.', 404)

    employee_name = request.form.get('employee_name')
    categories = parse_employee_categories(request.form)
    category = ', '.join(categories) if categories else ''
    group_id = request.form.get('group_id')
    permission_set_id = (request.form.get('permission_set_id') or '').strip()
    phone_number = request.form.get('phone_number', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()

    if not employee_name:
        return _fail('Employee name is required.')

    if not category:
        return _fail('At least one position is required.')
    if not phone_number:
        return _fail('Phone number is required.')
    if not email:
        return _fail('Email is required.')

    email_in_use = Employee.query.filter(
        db.func.lower(Employee.email) == email.lower(),
        Employee.id != employee.id
    ).first()
    if email_in_use:
        return _fail('Email is already used by another employee.')

    employee.name = employee_name
    employee.category = category
    employee.phone_number = phone_number
    employee.email = email
    if password:
        employee.password_hash = generate_password_hash(password)
    employee.group_id = group_id if group_id else None
    if permission_set_id:
        permission_set = PermissionSet.query.get(permission_set_id)
        if not permission_set:
            return _fail('Selected permission set was not found.')
        employee.permission_set_id = permission_set.id
    else:
        employee.permission_set_id = None
    db.session.commit()
    if is_ajax_request():
        return jsonify({
            'ok': True,
            'message': f'Employee {employee.name} updated successfully',
            'employee': {
                'id': employee.id,
                'name': employee.name,
                'permission_set_id': employee.permission_set_id or ''
            }
        })
    flash(f'Employee {employee.name} updated successfully', 'success')
    return redirect(url_for('index'))

# Job Management
@app.route('/job/add', methods=['POST'])
def add_job():
    job_name = request.form.get('job_name')
    job_type = request.form.get('job_type', 'Install')
    po_number = request.form.get('po_number')
    address = request.form.get('address')
    phone_number = request.form.get('phone_number')
    story = request.form.get('story')
    description = request.form.get('description') or ''
    system_size = normalize_system_size(request.form.get('system_size'))
    scheduled_date_raw = request.form.get('scheduled_date', '').strip()
    pending_date_raw = request.form.get('pending_date', '').strip()
    permit_number = (request.form.get('permit_number') or '').strip()

    if len(description) > 1000:
        if is_ajax_request():
            return jsonify({'ok': False, 'message': 'Job details cannot exceed 1000 characters.'}), 400
        flash('Job details cannot exceed 1000 characters.', 'danger')
        return redirect(url_for('index'))

    if job_type == 'Install' and not system_size:
        if is_ajax_request():
            return jsonify({'ok': False, 'message': 'System size is required for Install jobs.'}), 400
        flash('System size is required for Install jobs.', 'danger')
        return redirect(url_for('index'))

    if job_type == 'Inspection' and not permit_number:
        if is_ajax_request():
            return jsonify({'ok': False, 'message': 'Permit Number is required for Inspection jobs.'}), 400
        flash('Permit Number is required for Inspection jobs.', 'danger')
        return redirect(url_for('index'))

    # For Custom Shift, skip all required field checks
    if job_type == 'Custom Shift':
        job_name = job_name or 'Custom Shift'
        po_number = po_number or ''
        address = address or ''
        phone_number = phone_number or ''
        story = story or ''
        description = description or ''
        system_size = system_size or ''

    scheduled_date = None
    if job_type and 'site survey' in job_type.lower():
        if not scheduled_date_raw:
            if is_ajax_request():
                return jsonify({'ok': False, 'message': 'Survey date is required for Site Survey jobs.'}), 400
            flash('Survey date is required for Site Survey jobs.', 'danger')
            return redirect(url_for('index'))
        try:
            scheduled_date = datetime.strptime(scheduled_date_raw, '%Y-%m-%d').date()
        except ValueError:
            if is_ajax_request():
                return jsonify({'ok': False, 'message': 'Invalid survey date format.'}), 400
            flash('Invalid survey date format.', 'danger')
            return redirect(url_for('index'))

    # Parse optional pending_date (places job on the calendar without crew/publish)
    pending_date = None
    if pending_date_raw:
        try:
            pending_date = datetime.strptime(pending_date_raw, '%Y-%m-%d').date()
        except ValueError:
            pass  # Ignore bad date — job still saves without a date
    # calendarSlotAddJobModal passes the slot date as scheduled_date for non-survey jobs
    if not pending_date and scheduled_date_raw and not (job_type and 'site survey' in job_type.lower()):
        try:
            pending_date = datetime.strptime(scheduled_date_raw, '%Y-%m-%d').date()
        except ValueError:
            pass

    # For Custom Shift, allow job_name to be blank
    if job_type == 'Custom Shift' or job_name:
        ps = get_effective_permission_set()
        _emp = get_effective_employee()
        try:
            new_job = Job(
                job_name=job_name or 'Custom Shift',
                job_type=job_type,
                po_number=po_number,
                address=address,
                phone_number=phone_number,
                story=story,
                description=description,
                system_size=system_size or None,
                permit_number=permit_number or None,
                scheduled_date=scheduled_date,
                pending_date=pending_date,
                published=False
            )
            db.session.add(new_job)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            import traceback
            err_detail = traceback.format_exc()
            app.logger.error(f'add_job DB error: {err_detail}')
            if is_ajax_request():
                return jsonify({'ok': False, 'message': f'Database error: {str(e)}'}), 500
            flash('Failed to save job. Please try again.', 'danger')
            return redirect(url_for('index'))
        if is_ajax_request():
            return jsonify({
                'ok': True,
                'message': f'Job {job_name or "Custom Shift"} ({job_type}) added successfully',
                'job_id': new_job.id,
                'job_name': new_job.job_name,
                'job_type': new_job.job_type,
                'pending_date': pending_date.isoformat() if pending_date else None
            })
        flash(f'Job {job_name or "Custom Shift"} ({job_type}) added successfully', 'success')
    elif is_ajax_request():
        return jsonify({'ok': False, 'message': 'Job name is required.'}), 400
    return redirect(url_for('index'))


@app.route('/job/<int:id>/update', methods=['POST'])
def update_job(id):
    job = Job.query.get(id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('index'))

    job_name = (request.form.get('job_name') or '').strip()
    job_type = request.form.get('job_type', 'Install')
    po_number = request.form.get('po_number')
    address = request.form.get('address')
    phone_number = request.form.get('phone_number')
    story = request.form.get('story')
    description = request.form.get('description') or ''
    system_size = normalize_system_size(request.form.get('system_size'))
    scheduled_date_raw = request.form.get('scheduled_date', '').strip()
    permit_number = (request.form.get('permit_number') or '').strip()


    # For Custom Shift, allow job_name to be blank
    if job_type != 'Custom Shift' and not job_name:
        flash('Job name is required.', 'danger')
        return redirect(url_for('index'))

    if len(description) > 1000:
        flash('Job details cannot exceed 1000 characters.', 'danger')
        return redirect(url_for('index'))


    if job_type == 'Install' and not system_size:
        flash('System size is required for Install jobs.', 'danger')
        return redirect(url_for('index'))

    if job_type == 'Inspection' and not permit_number:
        flash('Permit Number is required for Inspection jobs.', 'danger')
        return redirect(url_for('index'))

    # For Custom Shift, skip all required field checks
    if job_type == 'Custom Shift':
        job_name = job_name or 'Custom Shift'
        po_number = po_number or ''
        address = address or ''
        phone_number = phone_number or ''
        story = story or ''
        description = description or ''
        system_size = system_size or ''

    scheduled_date = None
    if job_type and 'site survey' in job_type.lower():
        if not scheduled_date_raw:
            flash('Survey date is required for Site Survey jobs.', 'danger')
            return redirect(url_for('index'))
        try:
            scheduled_date = datetime.strptime(scheduled_date_raw, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid survey date format.', 'danger')
            return redirect(url_for('index'))

    job.job_name = job_name
    job.job_type = job_type
    job.po_number = po_number
    job.address = address
    job.phone_number = phone_number
    job.story = story
    job.description = description
    job.system_size = system_size or None
    job.permit_number = permit_number or None
    job.scheduled_date = scheduled_date
    db.session.commit()
    if is_ajax_request():
        return jsonify({
            'ok': True,
            'job_id': job.id,
            'job_name': job.job_name,
            'job_type': job.job_type,
            'system_size': job.system_size or '',
            'status': job.status,
        })
    flash(f'Job {job.job_name} updated successfully', 'success')
    return redirect(url_for('index'))

@app.route('/job/<int:id>/delete')
def delete_job(id):
    job = Job.query.get(id)
    if job:
        job_id = job.id
        job_name = job.job_name
        actor_name = None
        if effective_is_dev_session():
            actor_name = session.get('developer_user_name') or 'Developer'
        else:
            current_employee = get_effective_employee()
            if current_employee and current_employee.name:
                actor_name = current_employee.name

        deleted_by = (
            actor_name
            or request.form.get('deleted_by')
            or request.args.get('deleted_by')
            or request.headers.get('X-Forwarded-User')
            or request.headers.get('X-User')
            or request.remote_addr
            or 'Unknown'
        )
        db.session.add(JobDeletionLog(
            job_id=job.id,
            job_name=job.job_name or 'Unnamed Job',
            job_type=job.job_type or 'Unspecified',
            po_number=job.po_number,
            address=job.address,
            phone_number=job.phone_number,
            story=job.story,
            description=job.description,
            system_size=job.system_size,
            deleted_by=(deleted_by or 'Unknown').strip() or 'Unknown'
        ))
        db.session.add(build_job_archive_entry(job))
        db.session.delete(job)
        db.session.commit()
        broadcast_job_update(job_id, 'deleted', {'job_name': job_name})
        return delete_route_response('Job deleted', {
            'deleted_type': 'job',
            'deleted_id': id,
            'deleted_name': job_name
        })
    if is_ajax_request():
        return jsonify({'ok': False, 'message': 'Job not found'}), 404
    return redirect(url_for('index'))


@app.route('/deleted-job/<int:log_id>/restore', methods=['POST'])
def restore_deleted_job(log_id):
    log = JobDeletionLog.query.get(log_id)
    if not log:
        flash('Deleted job record not found.', 'danger')
        return redirect(url_for('index'))

    if log.restored:
        flash('This deleted job has already been restored.', 'warning')
        return redirect(url_for('index'))

    job_name = (request.form.get('job_name') or '').strip()
    job_type = (request.form.get('job_type') or '').strip() or 'Unspecified'
    po_number = (request.form.get('po_number') or '').strip()
    address = (request.form.get('address') or '').strip()
    phone_number = (request.form.get('phone_number') or '').strip()
    story = (request.form.get('story') or '').strip()
    description = (request.form.get('description') or '').strip()
    system_size = normalize_system_size(request.form.get('system_size'))

    if not job_name:
        flash('Job name is required to restore a deleted job.', 'danger')
        return redirect(url_for('index'))

    if len(description) > 1000:
        flash('Job details cannot exceed 1000 characters.', 'danger')
        return redirect(url_for('index'))

    restored_job = Job(
        job_name=job_name,
        job_type=job_type,
        status='not_started',
        published=False,
        pending_date=None,
        scheduled_date=None,
        po_number=po_number or None,
        address=address or None,
        phone_number=phone_number or None,
        story=story or None,
        description=description or None,
        system_size=system_size or None,
        cancel_reason=None
    )
    db.session.add(restored_job)
    db.session.flush()

    log.restored = True
    log.restored_at = datetime.utcnow()
    log.restored_job_id = restored_job.id
    db.session.commit()
    flash(f'Job {job_name or "Custom Shift"} restored successfully', 'success')
    return redirect(url_for('index'))

@app.route('/job/<int:id>/status/<status>')
def update_job_status(id, status):
    job = Job.query.get(id)
    if job and status in ['not_started', 'in_progress', 'completed']:
        job.status = status
        job.completed_at = datetime.utcnow() if status == 'completed' else None
        if status == 'completed':
            job.published = False
        if status != 'canceled':
            job.cancel_reason = None
        db.session.commit()
        action_map = {'not_started': 'started', 'in_progress': 'started', 'completed': 'completed'}
        broadcast_job_update(job.id, action_map.get(status, status), {'status': status})
        flash(f'Job status updated to {status}', 'success')
    return redirect(url_for('index'))


@app.route('/job/<int:id>/cancel', methods=['POST'])
def cancel_job(id):
    job = Job.query.get(id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('index'))

    cancel_reason = (request.form.get('cancel_reason') or '').strip()
    if not cancel_reason:
        flash('Cancellation reason is required.', 'danger')
        return redirect(url_for('index'))

    job.status = 'canceled'
    job.cancel_reason = cancel_reason
    db.session.commit()
    broadcast_job_update(job.id, 'canceled', {'status': 'canceled', 'reason': cancel_reason})
    flash(f'Job "{job.job_name}" was marked as canceled.', 'warning')
    return redirect(url_for('index'))


@app.route('/job/<int:id>/reopen', methods=['GET', 'POST'])
def reopen_job(id):
    job = Job.query.get(id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('index'))

    reopen_date_raw = (request.form.get('reopen_date') or request.args.get('reopen_date') or '').strip()
    reopen_date = None
    if reopen_date_raw:
        try:
            reopen_date = datetime.strptime(reopen_date_raw, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date selected for reopen.', 'danger')
            return redirect(url_for('index'))

    # Reopening should reset status and optionally place the job onto a scheduled date.
    Assignment.query.filter_by(job_id=job.id).delete(synchronize_session=False)
    job.status = 'not_started'
    job.cancel_reason = None
    job.published = False
    job.pending_date = reopen_date
    db.session.commit()

    broadcast_job_update(job.id, 'reopened', {
        'status': 'not_started',
        'published': False,
        'pending_date': reopen_date.isoformat() if reopen_date else None
    })

    if reopen_date:
        flash(f'Job "{job.job_name}" was reopened and moved to Scheduled for {reopen_date.strftime("%m/%d/%Y")}.', 'success')
    else:
        flash(f'Job "{job.job_name}" was reopened and moved to Unscheduled.', 'success')
    return redirect(url_for('index'))

# ---------------------------------------------------------------------------
@app.route('/job/<int:id>/publish')
def publish_job(id):
    job = Job.query.get(id)
    if job:
        # Build slot_map: {(assigned_date, start_time, end_time): [Assignment, ...]}
        slot_map = {}
        for assign in Assignment.query.filter_by(job_id=job.id).all():
            key = (assign.assigned_date, assign.start_time, assign.end_time)
            slot_map.setdefault(key, []).append(assign)
        expanded_crews = expand_job_assignments_for_crew_leads(job, slot_map)
        job.published = True
        db.session.commit()
        broadcast_job_update(job.id, 'published', {'published': True})
        if expanded_crews:
            crew_list = ', '.join(sorted(set(expanded_crews)))
            flash(f'Job "{job.job_name}" published and expanded to full crew assignment for {crew_list}.', 'success')
        else:
            flash(f'Job "{job.job_name}" published and ready for scheduling', 'success')
    return redirect(url_for('index'))

@app.route('/job/<int:id>/unpublish')
def unpublish_job(id):
    job = Job.query.get(id)
    if job:
        # Build slot_map: {(assigned_date, start_time, end_time): [Assignment, ...]}
        slot_map = {}
        for assign in Assignment.query.filter_by(job_id=job.id).all():
            key = (assign.assigned_date, assign.start_time, assign.end_time)
            slot_map.setdefault(key, []).append(assign)
        expanded_crews = expand_job_assignments_for_crew_leads(job, slot_map)
        job.published = False
        db.session.commit()
        broadcast_job_update(job.id, 'unpublished', {'published': False})
        if expanded_crews:
            crew_list = ', '.join(sorted(set(expanded_crews)))
            flash(f'Job "{job.job_name}" unpublished for the full crew assignment: {crew_list}.', 'info')
        else:
            flash(f'Job "{job.job_name}" unpublished (back to draft)', 'info')
    return redirect(url_for('index'))

# Assignment Management
@app.route('/assign', methods=['POST'])
def assign_employee():
    employee_ids = request.form.getlist('employee_ids')
    if not employee_ids:
        single_employee_id = request.form.get('employee_id')
        if single_employee_id:
            employee_ids = [single_employee_id]

    job_id = request.form.get('job_id')
    assigned_date_raw = request.form.get('assigned_date')
    start_time_raw = request.form.get('start_time')
    end_time_raw = request.form.get('end_time')

    if not job_id:
        flash('Job is required.', 'danger')
        return redirect(url_for('index'))

    job = Job.query.get(job_id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('index'))

    # Allow saving assignment intent without a date. Date can be selected later.
    if not assigned_date_raw:
        job.published = False
        job.pending_date = None
        db.session.commit()
        broadcast_job_update(job.id, 'unpublished', {'published': False})
        flash('Job saved without a date. Select a date later to schedule it.', 'info')
        return redirect(url_for('index'))

    if not employee_ids:
        flash('Team member(s) are required when assigning with a date.', 'danger')
        return redirect(url_for('index'))

    if len(employee_ids) > 4:
        flash('You can assign at most 4 individual team members to a job.', 'danger')
        return redirect(url_for('index'))

    if len(employee_ids) > 1 and not is_multi_employee_job_type(job.job_type):
        flash('Only Install, Reinstall, and Uninstall jobs can be assigned to multiple employees. All other jobs must be assigned to one employee only.', 'danger')
        return redirect(url_for('index'))

    selected_employees = Employee.query.filter(Employee.id.in_(employee_ids)).all()
    if len(selected_employees) != len(set(employee_ids)):
        flash('One or more selected employees were not found.', 'danger')
        return redirect(url_for('index'))

    blocked = [emp.name for emp in selected_employees if not is_assignable_employee(emp)]
    if blocked:
        flash(f'The following employees cannot be assigned to jobs: {", ".join(blocked)}.', 'danger')
        return redirect(url_for('index'))

    if job.job_type.strip().lower() == 'mpu':
        non_electricians = [emp.name for emp in selected_employees if not has_role(emp, 'Electrician')]
        if non_electricians:
            flash(f'MPU jobs can only be assigned to Electricians: {", ".join(non_electricians)} do not have the Electrician role.', 'danger')
            return redirect(url_for('index'))

    if job.job_type.strip().lower() == 'site survey':
        non_surveyors = [emp.name for emp in selected_employees if not has_role(emp, 'Site Surveyor')]
        if non_surveyors:
            flash(f'Site Survey jobs can only be assigned to Site Surveyors: {", ".join(non_surveyors)} do not have the Site Surveyor role.', 'danger')
            return redirect(url_for('index'))

    if job.job_type.strip().lower() == 'inspection':
        non_inspection_techs = [emp.name for emp in selected_employees if not has_role(emp, 'Inspections Tech')]
        if non_inspection_techs:
            flash(f'Inspection jobs can only be assigned to Inspections Techs: {", ".join(non_inspection_techs)} do not have the Inspections Tech role.', 'danger')
            return redirect(url_for('index'))

    assigned_date = datetime.strptime(assigned_date_raw, '%Y-%m-%d').date()
    start_time = datetime.strptime(start_time_raw, '%H:%M').time() if start_time_raw else None
    end_time = datetime.strptime(end_time_raw, '%H:%M').time() if end_time_raw else None

    auto_assigned_crew = None
    if len(selected_employees) == 1 and should_assign_full_crew(job, selected_employees[0]):
        auto_assigned_crew = selected_employees[0].group
        for member in auto_assigned_crew.employees:
            new_assignment = Assignment(
                employee_id=member.id,
                job_id=job_id,
                crew_id=auto_assigned_crew.id,
                assigned_date=assigned_date,
                start_time=start_time,
                end_time=end_time
            )
            db.session.add(new_assignment)
    else:
        for employee in selected_employees:
            new_assignment = Assignment(
                employee_id=employee.id,
                job_id=job_id,
                assigned_date=assigned_date,
                start_time=start_time,
                end_time=end_time
            )
            db.session.add(new_assignment)

    job.published = False
    job.pending_date = None

    db.session.commit()
    if auto_assigned_crew:
        broadcast_job_update(int(job_id), 'assigned', {'assigned_to': 'crew', 'crew': auto_assigned_crew.name})
        flash(f'Crew "{auto_assigned_crew.name}" assigned automatically because the selected team member is a Crew Lead.', 'success')
    else:
        broadcast_job_update(int(job_id), 'assigned', {'assigned_to': 'employee'})
        flash(f'Assignment created for {len(selected_employees)} team member(s).', 'success')
    return redirect(url_for('index'))


@app.route('/assign/crew', methods=['POST'])
def assign_crew():
    crew_id = request.form.get('crew_id')
    job_id = request.form.get('job_id')
    assigned_date_raw = request.form.get('assigned_date')
    start_time_raw = request.form.get('start_time')
    end_time_raw = request.form.get('end_time')

    if not job_id:
        flash('Job is required.', 'danger')
        return redirect(url_for('index'))

    job = Job.query.get(job_id)
    if not job:
        flash('Job not found.', 'danger')
        return redirect(url_for('index'))

    if not is_crew_eligible_job_type(job.job_type):
        flash('Only Install, Reinstall, and Uninstall jobs can be assigned to crews.', 'warning')
        return redirect(url_for('index'))

    # Allow saving job assignment intent without a date. Date can be selected later.
    if not assigned_date_raw:
        job.published = False
        job.pending_date = None
        db.session.commit()
        broadcast_job_update(job.id, 'unpublished', {'published': False})
        flash('Job saved without a date. Select a date later to schedule it.', 'info')
        return redirect(url_for('index'))

    # Allow scheduling unpublished jobs without selecting a crew.
    if not crew_id:
        assigned_date = datetime.strptime(assigned_date_raw, '%Y-%m-%d').date()
        job.pending_date = assigned_date
        job.published = False
        db.session.commit()
        broadcast_job_update(job.id, 'unpublished', {'published': False, 'pending_date': assigned_date.isoformat()})
        flash('Job scheduled as pending without a crew assignment.', 'info')
        return redirect(url_for('index'))

    crew = Group.query.get(crew_id)
    if not crew:
        flash('Crew not found.', 'danger')
        return redirect(url_for('index'))

    crew_members = crew.employees
    if not crew_members:
        flash('This crew has no employees yet. Add employees to this crew first.', 'danger')
        return redirect(url_for('index'))

    assigned_date = datetime.strptime(assigned_date_raw, '%Y-%m-%d').date()
    start_time = datetime.strptime(start_time_raw, '%H:%M').time() if start_time_raw else None
    end_time = datetime.strptime(end_time_raw, '%H:%M').time() if end_time_raw else None

    for member in crew_members:
        new_assignment = Assignment(
            employee_id=member.id,
            job_id=job_id,
            crew_id=crew.id,
            assigned_date=assigned_date,
            start_time=start_time,
            end_time=end_time
        )
        db.session.add(new_assignment)

    # Crew assignment should not auto-publish.
    job.published = False
    job.pending_date = None

    db.session.commit()
    broadcast_job_update(int(job_id), 'assigned', {'assigned_to': 'crew', 'crew': crew.name})
    flash(f'Crew "{crew.name}" assigned to job for {len(crew_members)} team member(s).', 'success')
    return redirect(url_for('index'))

@app.route('/assignment/<int:id>/delete')
def delete_assignment(id):
    assignment = Assignment.query.get(id)
    if assignment:
        assignment_id = assignment.id
        db.session.delete(assignment)
        db.session.commit()
        return delete_route_response('Assignment deleted', {
            'deleted_type': 'assignment',
            'deleted_id': assignment_id
        })
    if is_ajax_request():
        return jsonify({'ok': False, 'message': 'Assignment not found'}), 404
    return redirect(url_for('index'))

# Timesheet Operations
@app.route('/clock_in', methods=['POST'])
def clock_in():
    current_employee = get_effective_employee()
    selected_employee_id = request.form.get('employee_id')
    selected_job_id = (request.form.get('job_id') or '').strip()

    # Geofence: Only allow field employees to clock in within 0.5 miles of 4515 George Rd Tampa, FL 33634
    # 4515 George Rd, Tampa, FL 33634: 27.994991, -82.543160
    GEOFENCE_LAT = 27.994991
    GEOFENCE_LON = -82.543160
    GEOFENCE_RADIUS_MILES = 0.5

    def haversine(lat1, lon1, lat2, lon2):
        R = 3958.8  # Earth radius in miles
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c



    # Enforce shift assignment for installers and service techs
    if current_employee:
        roles = {(r or '').strip().lower() for r in (current_employee.category or '').split(',') if (r or '').strip()}
        if 'installer' in roles or 'service' in roles or 'service tech' in roles or 'service technician' in roles:
            # Installer geofence
            if 'installer' in roles:
                lat = request.form.get('latitude')
                lon = request.form.get('longitude')
                try:
                    lat = float(lat)
                    lon = float(lon)
                except (TypeError, ValueError):
                    flash('Location required to clock in. Please enable location services.', 'danger')
                    return redirect(url_for('index'))
                dist = haversine(lat, lon, GEOFENCE_LAT, GEOFENCE_LON)
                if dist > GEOFENCE_RADIUS_MILES:
                    flash('You must be within 0.5 miles of 4515 George Rd, Tampa, FL to clock in.', 'danger')
                    return redirect(url_for('index'))
                if str(current_employee.id) != str(selected_employee_id):
                    flash('You can only clock in as yourself.', 'danger')
                    return redirect(url_for('index'))

            # Both installer and service tech must have an assigned shift for today
            today = datetime.now().date()
            today_assigns = (
                Assignment.query.join(Job)
                .filter(
                    Assignment.employee_id == current_employee.id,
                    Assignment.assigned_date == today,
                    Job.published.is_(True),
                    Job.status != 'canceled'
                )
                .all()
            )
            if not today_assigns:
                flash("You don't have a shift scheduled for today.", 'danger')
                return redirect(url_for('index'))

            today_job_ids = {str(a.job_id) for a in today_assigns}
            if selected_job_id not in today_job_ids:
                flash('You can only clock in to your assigned job for today.', 'danger')
                return redirect(url_for('index'))

    if not selected_job_id:
        selected_job_id = str(get_or_create_default_clock_job().id)

    # Snapshot employee contact info at clock-in time
    clocking_emp = Employee.query.get(int(selected_employee_id)) if selected_employee_id else None
    new_log = Timesheet(
        employee_id=selected_employee_id,
        job_id=selected_job_id,
        employee_name_snapshot=clocking_emp.name if clocking_emp else None,
        employee_email_snapshot=clocking_emp.email if clocking_emp else None,
        employee_phone_snapshot=clocking_emp.phone_number if clocking_emp else None,
        # Optionally, you could store lat/lon in the log for auditing
        # clock_in_lat=lat, clock_in_lon=lon
    )
    db.session.add(new_log)
    db.session.commit()

    # Auto-mark job as in_progress when first employee clocks in
    if selected_job_id:
        clocked_job = Job.query.get(int(selected_job_id))
        if clocked_job and clocked_job.status == 'not_started':
            clocked_job.status = 'in_progress'
            db.session.commit()
            broadcast_job_update(clocked_job.id, 'status_changed', {'status': 'in_progress'})

    flash('Clocked in successfully', 'success')
    return redirect(url_for('index'))

@app.route('/clock_out/<int:id>')
def clock_out(id):
    log = Timesheet.query.get(id)
    if log:
        current_employee = get_effective_employee()
        # Only allow clocking out your own logs
        if effective_is_field_limited() and current_employee and log.employee_id != current_employee.id:
            flash('You can only clock out your own time logs.', 'danger')
            return redirect(url_for('index'))

        # Require notes for service techs
        roles = {(r or '').strip().lower() for r in (current_employee.category or '').split(',') if (r or '').strip()}
        if 'service' in roles or 'service tech' in roles or 'service technician' in roles:
            notes = request.form.get('service_notes', '').strip()
            if not notes:
                flash('You must leave notes before clocking out.', 'danger')
                return redirect(url_for('index'))
            # Update job description with notes
            job = Job.query.get(log.job_id)
            if job:
                if job.description:
                    job.description += f"\nService Tech Notes ({datetime.now().strftime('%Y-%m-%d %H:%M')}): {notes}"
                else:
                    job.description = f"Service Tech Notes ({datetime.now().strftime('%Y-%m-%d %H:%M')}): {notes}"
                db.session.add(job)

        log.clock_out = datetime.now()
        db.session.commit()
        flash('Clocked out successfully', 'success')
    return redirect(url_for('index'))


@app.route('/timesheet/<int:id>/update', methods=['POST'])
def update_timesheet(id):
    current_employee = get_effective_employee()
    if not can_edit_timesheets(current_employee):
        flash('Only managers can edit timesheets.', 'danger')
        return redirect(url_for('index'))

    log = Timesheet.query.get(id)
    if not log:
        flash('Time log not found.', 'danger')
        return redirect(url_for('index'))

    clock_in_raw = (request.form.get('clock_in') or '').strip()
    clock_out_raw = (request.form.get('clock_out') or '').strip()

    if not clock_in_raw:
        flash('Clock in time is required.', 'danger')
        return redirect(url_for('index'))

    try:
        clock_in_dt = datetime.strptime(clock_in_raw, '%Y-%m-%dT%H:%M')
    except ValueError:
        flash('Invalid clock in date/time.', 'danger')
        return redirect(url_for('index'))

    clock_out_dt = None
    if clock_out_raw:
        try:
            clock_out_dt = datetime.strptime(clock_out_raw, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Invalid clock out date/time.', 'danger')
            return redirect(url_for('index'))

    if clock_out_dt and clock_out_dt < clock_in_dt:
        flash('Clock out cannot be earlier than clock in.', 'danger')
        return redirect(url_for('index'))

    log.clock_in = clock_in_dt
    log.clock_out = clock_out_dt

    # Managers may also reassign employee / job
    new_employee_id = request.form.get('employee_id')
    new_job_id = request.form.get('job_id')
    if new_employee_id and new_employee_id.isdigit():
        emp = Employee.query.get(int(new_employee_id))
        if emp:
            log.employee_id = emp.id
            log.employee_name_snapshot = emp.name
            log.employee_email_snapshot = emp.email
            log.employee_phone_snapshot = emp.phone_number
    if new_job_id and new_job_id.isdigit():
        if Job.query.get(int(new_job_id)):
            log.job_id = int(new_job_id)

    db.session.commit()
    flash('Time log updated.', 'success')
    return redirect(url_for('index'))


@app.route('/timesheet/<int:id>/delete', methods=['POST'])
def delete_timesheet(id):
    current_employee = get_effective_employee()
    if not can_edit_timesheets(current_employee):
        flash('Only managers can delete time logs.', 'danger')
        return redirect(url_for('index'))
    log = Timesheet.query.get(id)
    if log:
        db.session.delete(log)
        db.session.commit()
        flash('Time log deleted.', 'success')
    return redirect(url_for('index'))

# API for Calendar
@app.route('/api/assignments')
def get_assignments_api():
    from flask import jsonify

    current_employee = get_effective_employee()
    if effective_is_field_limited() and current_employee:
        assignments = (
            Assignment.query
            .join(Job)
            .filter(Assignment.employee_id == current_employee.id)
            .filter(Job.published.is_(True))
            .filter(Job.status != 'canceled')
            .all()
        )
    else:
        assignments = Assignment.query.all()
    events = []
    crew_event_map = {}

    for assign in assignments:
        start_time = assign.start_time.strftime('%H:%M') if assign.start_time else '09:00'
        end_time = assign.end_time.strftime('%H:%M') if assign.end_time else '17:00'
        assigned_crew = assign.crew or assign.employee.group
        crew_color = assigned_crew.color if assigned_crew and assigned_crew.color else '#667eea'
        job_type_color = get_job_type_color(assign.job.job_type)
        crew_name = assigned_crew.name if assigned_crew else 'UnAssigned'
        unpublished_class = ['event-unpublished'] if not assign.job.published else []
        role = assign.employee.category or 'Installer'

        # Determine emoji based on job type
        if assign.job.job_type in ('Solar Install', 'Install', 'Reinstall'):
            job_type_emoji = '☀️'
        elif assign.job.job_type == 'Service':
            job_type_emoji = '🔨'
        else:
            job_type_emoji = '💧'

        if assign.crew_id:
            event_key = f"{assign.crew_id}-{assign.job_id}-{assign.assigned_date}-{start_time}-{end_time}"
            if event_key not in crew_event_map:
                crew_event_map[event_key] = {
                    'title': f"{job_type_emoji} {assign.job.job_name} ({crew_name})",
                    'start': f"{assign.assigned_date}T{start_time}",
                    'end': f"{assign.assigned_date}T{end_time}",
                    'backgroundColor': crew_color,
                    'borderColor': crew_color,
                    'classNames': unpublished_class,
                    'extendedProps': {
                        'crewId': assign.crew_id,
                        'assignedDate': assign.assigned_date.isoformat(),
                        'jobId': assign.job.id,
                        'jobName': assign.job.job_name,
                        'jobType': assign.job.job_type,
                        'systemSize': assign.job.system_size or '',
                        'employee': 'Crew Assignment',
                        'crewName': crew_name,
                        'crewColor': crew_color,
                        'status': assign.job.status,
                        'published': assign.job.published,
                        'poNumber': assign.job.po_number or 'N/A',
                        'address': assign.job.address or 'N/A',
                        'phoneNumber': assign.job.phone_number or 'N/A',
                        'story': assign.job.story or 'N/A',
                        'description': assign.job.description or 'No description',
                        'startTime': start_time,
                        'endTime': end_time,
                        'crewLead': 'Not assigned',
                        'electrician': 'Not assigned',
                        'crewMembers': []
                    }
                }

            crew_event_map[event_key]['extendedProps']['crewMembers'].append(f"{assign.employee.name} ({role})")
            if role == 'Crew Lead':
                crew_event_map[event_key]['extendedProps']['crewLead'] = assign.employee.name
            if role == 'Electrician':
                crew_event_map[event_key]['extendedProps']['electrician'] = assign.employee.name
        else:
            events.append({
                'id': f"assignment-{assign.id}",
                'title': f"{job_type_emoji} {assign.job.job_name}",
                'start': f"{assign.assigned_date}T{start_time}",
                'end': f"{assign.assigned_date}T{end_time}",
                # No crew assignment: keep job-type color on calendar.
                'backgroundColor': job_type_color,
                'borderColor': job_type_color,
                'classNames': unpublished_class,
                'extendedProps': {
                    'assignmentId': assign.id,
                    'assignedDate': assign.assigned_date.isoformat(),
                    'crewId': assign.employee.group.id if assign.employee.group else None,
                    'jobId': assign.job.id,
                    'jobName': assign.job.job_name,
                    'jobType': assign.job.job_type,
                    'systemSize': assign.job.system_size or '',
                    'dayPay': bool(assign.day_pay),
                    'employee': assign.employee.name,
                    'crewName': crew_name,
                    'crewColor': crew_color,
                    'status': assign.job.status,
                    'published': assign.job.published,
                    'poNumber': assign.job.po_number or 'N/A',
                    'address': assign.job.address or 'N/A',
                    'phoneNumber': assign.job.phone_number or 'N/A',
                    'story': assign.job.story or 'N/A',
                    'description': assign.job.description or 'No description',
                    'startTime': start_time,
                    'endTime': end_time,
                    'crewLead': 'N/A',
                    'electrician': 'N/A',
                    'crewMembers': [f"{assign.employee.name} ({role})"]
                }
            })

    events.extend(crew_event_map.values())

    # Show pending date holds for jobs that were dropped onto a day but not crew-assigned yet.
    held_job_ids = {assign.job_id for assign in assignments}
    held_jobs = Job.query.filter(Job.pending_date.isnot(None)).all()
    for job in held_jobs:
        if job.id in held_job_ids:
            continue

        hold_class_names = [] if job.published else ['event-unpublished']
        hold_icon = '🟢' if job.published else '🟡'
        job_type_color = get_job_type_color(job.job_type)

        events.append({
            'id': f"pending-{job.id}",
            'title': f"{hold_icon} {job.job_name} (UnAssigned)",
            'start': job.pending_date.isoformat(),
            'allDay': True,
            'backgroundColor': job_type_color,
            'borderColor': job_type_color,
            'textColor': '#111827',
            'classNames': hold_class_names,
            'extendedProps': {
                'jobId': job.id,
                'jobName': job.job_name,
                'jobType': job.job_type,
                'systemSize': job.system_size or '',
                'employee': 'Pending',
                'crewName': 'UnAssigned',
                'crewColor': job_type_color,
                'status': job.status,
                'published': job.published,
                'poNumber': job.po_number or 'N/A',
                'address': job.address or 'N/A',
                'phoneNumber': job.phone_number or 'N/A',
                'story': job.story or 'N/A',
                'description': job.description or 'No description',
                'startTime': '',
                'endTime': '',
                'crewLead': 'Not assigned',
                'electrician': 'Not assigned',
                'crewMembers': [],
                'isPendingHold': True
            }
        })

    return jsonify(events)


@app.route('/api/grid-assign', methods=['POST'])
def grid_assign():
    """Assign a job to an employee on a specific date from the employee-schedule grid."""
    from flask import jsonify
    try:
        data = request.json or {}
        job_id = int(data.get('job_id'))
        employee_id = int(data.get('employee_id'))
        target_date_raw = data.get('target_date', '')
        source_assignment_id = data.get('source_assignment_id')  # set when moving an existing chip
        copy_mode = bool(data.get('copy_mode'))

        if not job_id or not employee_id or not target_date_raw:
            return jsonify({'success': False, 'message': 'job_id, employee_id, and target_date are required.'}), 400

        target_date = datetime.strptime(target_date_raw, '%Y-%m-%d').date()

        job = Job.query.get(job_id)
        if not job:
            return jsonify({'success': False, 'message': 'Job not found.'}), 404

        employee = Employee.query.get(employee_id)
        if not employee:
            return jsonify({'success': False, 'message': 'Employee not found.'}), 404

        if not is_assignable_employee(employee):
            return jsonify({'success': False, 'message': f'{employee.name} cannot be assigned to jobs.'}), 400

        # If moving an existing assignment, delete the old assignment first.
        # For crew-assigned slots, only dragging the Crew Lead should move the whole crew;
        # dragging any other crew member should only move that individual assignment.
        if source_assignment_id and not copy_mode:
            old = Assignment.query.get(int(source_assignment_id))
            if old:
                move_entire_crew_slot = bool(old.crew_id and has_role(old.employee, 'Crew Lead'))
                if move_entire_crew_slot:
                    Assignment.query.filter_by(
                        job_id=old.job_id,
                        crew_id=old.crew_id,
                        assigned_date=old.assigned_date,
                        start_time=old.start_time,
                        end_time=old.end_time
                    ).delete(synchronize_session=False)
                else:
                    db.session.delete(old)

        # In copy mode, create a new independent Job record cloned from the original
        # so that deleting the copy does not affect the original job.
        if copy_mode:
            target_job = Job(
                job_name=job.job_name,
                job_type=job.job_type,
                status='not_started',
                published=job.published,
                po_number=job.po_number,
                address=job.address,
                phone_number=job.phone_number,
                story=job.story,
                description=job.description,
                system_size=job.system_size,
                cancel_reason=None,
                permit_number=job.permit_number,
                is_internal=job.is_internal,
                pending_date=target_date,
                scheduled_date=job.scheduled_date,
            )
            db.session.add(target_job)
            db.session.flush()  # get target_job.id before creating assignments
        else:
            target_job = job

        if should_assign_full_crew(target_job, employee):
            crew = employee.group
            for member in crew.employees:
                db.session.add(Assignment(
                    employee_id=member.id,
                    job_id=target_job.id,
                    crew_id=crew.id,
                    assigned_date=target_date,
                    start_time=None,
                    end_time=None
                ))
            success_message = (
                f'Crew "{crew.name}" copied to {job.job_name} on {target_date_raw}.'
                if copy_mode else
                f'Crew "{crew.name}" assigned to {job.job_name} on {target_date_raw}.'
            )
        else:
            new_assignment = Assignment(
                employee_id=employee_id,
                job_id=target_job.id,
                assigned_date=target_date,
                start_time=None,
                end_time=None
            )
            db.session.add(new_assignment)
            success_message = (
                f'{job.job_name} copied to {employee.name} on {target_date_raw}.'
                if copy_mode else
                f'{employee.name} assigned to {job.job_name} on {target_date_raw}.'
            )

        # Update the target job's pending_date so it appears on that date
        if not copy_mode:
            target_job.pending_date = target_date

        db.session.commit()
        return jsonify({'success': True, 'message': success_message})
    except Exception as exc:
        db.session.rollback()
        
        return jsonify({'success': False, 'message': str(exc)}), 400


@app.route('/api/move-assignment', methods=['POST'])
def move_assignment():
    from flask import jsonify

    try:
        data = request.json or {}
        assignment_id = int(data.get('assignment_id'))
        target_date = datetime.strptime(data.get('target_date'), '%Y-%m-%d').date()

        assignment = Assignment.query.get(assignment_id)
        if not assignment:
            return jsonify({'success': False, 'message': 'Assignment not found.'}), 404

        assignment.assigned_date = target_date
        db.session.commit()
        return jsonify({'success': True, 'message': 'Assignment moved successfully.'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400


@app.route('/api/move-pending-hold', methods=['POST'])
def move_pending_hold():
    from flask import jsonify

    try:
        data = request.json or {}
        job_id = int(data.get('job_id'))
        target_date = datetime.strptime(data.get('target_date'), '%Y-%m-%d').date()

        job = Job.query.get(job_id)
        if not job:
            return jsonify({'success': False, 'message': 'Job not found.'}), 404

        job.pending_date = target_date
        job.published = False
        db.session.commit()
        return jsonify({'success': True, 'message': 'Pending hold moved successfully.'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400


@app.route('/api/remove-assignment', methods=['POST'])
def remove_assignment():
    from flask import jsonify

    try:
        data = request.json or {}
        assignment_id = data.get('assignment_id')
        if not assignment_id:
            return jsonify({'success': False, 'message': 'Assignment ID required.'}), 400

        assignment = Assignment.query.get(int(assignment_id))
        if not assignment:
            return jsonify({'success': False, 'message': 'Assignment not found.'}), 404

        db.session.delete(assignment)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Assignment removed successfully.'})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(exc)}), 400


@app.route('/api/assignment/<int:assign_id>/toggle-day-pay', methods=['POST'])
def toggle_day_pay(assign_id):
    if not is_authenticated_session():
        return jsonify({'ok': False, 'message': 'Unauthorized'}), 403
    assign = Assignment.query.get(assign_id)
    if not assign:
        return jsonify({'ok': False, 'message': 'Assignment not found'}), 404
    assign.day_pay = not bool(assign.day_pay)
    db.session.commit()
    return jsonify({'ok': True, 'day_pay': assign.day_pay})


@app.route('/api/return-to-pending', methods=['POST'])
def return_to_pending():

    try:
        data = request.json or {}
        job_id = int(data.get('job_id'))

        job = Job.query.get(job_id)
        if not job:
            return jsonify({'success': False, 'message': 'Job not found.'}), 404

        Assignment.query.filter_by(job_id=job_id).delete(synchronize_session=False)
        job.pending_date = None
        job.published = False
        db.session.commit()
        return jsonify({'success': True, 'message': 'Job returned to pending list.'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400


@app.route('/api/reassign-job-crew', methods=['POST'])
def reassign_job_crew():
    from flask import jsonify

    try:
        data = request.json or {}
        job_id = int(data.get('job_id'))
        target_crew_id = int(data.get('target_crew_id'))
        target_assigned_date = datetime.strptime(data.get('assigned_date'), '%Y-%m-%d').date()
        original_assigned_date_raw = (data.get('original_assigned_date') or data.get('assigned_date') or '').strip()
        original_assigned_date = datetime.strptime(original_assigned_date_raw, '%Y-%m-%d').date()

        job = Job.query.get(job_id)
        if not job:
            return jsonify({'success': False, 'message': 'Job not found.'}), 404
        allowed_job_types = {'install', 'uninstall', 'reinstall'}
        if (job.job_type or '').strip().lower() not in allowed_job_types:
            return jsonify({'success': False, 'message': 'Crew assignment is only allowed for Install, Uninstall, or Reinstall jobs.'}), 400

        start_time_raw = data.get('start_time') or ''
        end_time_raw = data.get('end_time') or ''
        start_time_obj = datetime.strptime(start_time_raw, '%H:%M').time() if start_time_raw else None
        end_time_obj = datetime.strptime(end_time_raw, '%H:%M').time() if end_time_raw else None

        target_crew = Group.query.get(target_crew_id)
        if not target_crew:
            return jsonify({'success': False, 'message': 'Target crew not found.'}), 404
        if not target_crew.employees:
            return jsonify({'success': False, 'message': 'Target crew has no employees.'}), 400

        def find_slot_assignments(source_date):
            query = Assignment.query.filter_by(
                job_id=job_id,
                assigned_date=source_date
            )
            if start_time_obj is not None:
                query = query.filter_by(start_time=start_time_obj)
            if end_time_obj is not None:
                query = query.filter_by(end_time=end_time_obj)
            rows = query.all()

            # Legacy rows can have NULL start/end times while the calendar UI sends
            # default values (09:00/17:00). Retry date-only lookup.
            if not rows:
                rows = Assignment.query.filter_by(
                    job_id=job_id,
                    assigned_date=source_date
                ).all()
            return rows

        slot_assignments = find_slot_assignments(original_assigned_date)

        # If the client date is shifted by timezone serialization, try adjacent days.
        if not slot_assignments:
            slot_assignments = find_slot_assignments(original_assigned_date - timedelta(days=1))
        if not slot_assignments:
            slot_assignments = find_slot_assignments(original_assigned_date + timedelta(days=1))

        # If nothing was found (timezone drift, legacy data, or pending-hold case),
        # continue by applying the crew assignment to the selected target slot.

        for assign in slot_assignments:
            db.session.delete(assign)

        # Ensure target slot is replaced cleanly (avoid duplicate members on retries).
        target_slot_query = Assignment.query.filter_by(
            job_id=job_id,
            assigned_date=target_assigned_date
        )
        if start_time_obj is not None:
            target_slot_query = target_slot_query.filter_by(start_time=start_time_obj)
        if end_time_obj is not None:
            target_slot_query = target_slot_query.filter_by(end_time=end_time_obj)
        for existing in target_slot_query.all():
            db.session.delete(existing)

        for member in target_crew.employees:
            db.session.add(Assignment(
                employee_id=member.id,
                job_id=job_id,
                crew_id=target_crew.id,
                assigned_date=target_assigned_date,
                start_time=start_time_obj,
                end_time=end_time_obj
            ))

        if job:
            job.published = False
            job.pending_date = None

        db.session.commit()
        return jsonify({'success': True, 'message': 'Job reassigned to selected crew.'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400

@app.route('/api/schedule-day', methods=['POST'])
def schedule_day():
    from flask import jsonify
    selected_date = request.json.get('date')
    employees = Employee.query.all()
    published_jobs = Job.query.filter_by(published=True).all()
    
    return jsonify({
        'date': selected_date,
        'employees': [{'id': e.id, 'name': e.name} for e in employees],
        'jobs': [{'id': j.id, 'name': j.job_name} for j in published_jobs]
    })


@app.route('/api/move-crew-job', methods=['POST'])
def move_crew_job():
    from flask import jsonify

    try:
        data = request.json or {}
        job_id = int(data.get('job_id'))
        source_crew_id = int(data.get('source_crew_id'))
        target_crew_id = int(data.get('target_crew_id'))
        source_date = datetime.strptime(data.get('source_date'), '%Y-%m-%d').date()
        target_date = datetime.strptime(data.get('target_date'), '%Y-%m-%d').date()

        start_time_raw = data.get('start_time') or ''
        end_time_raw = data.get('end_time') or ''
        start_time_obj = datetime.strptime(start_time_raw, '%H:%M').time() if start_time_raw else None
        end_time_obj = datetime.strptime(end_time_raw, '%H:%M').time() if end_time_raw else None

        source_assignments = Assignment.query.filter_by(
            crew_id=source_crew_id,
            job_id=job_id,
            assigned_date=source_date,
            start_time=start_time_obj,
            end_time=end_time_obj
        ).all()
        if not source_assignments:
            return jsonify({'success': False, 'message': 'Source crew assignment block was not found.'}), 404

        target_crew = Group.query.get(target_crew_id)
        if not target_crew:
            return jsonify({'success': False, 'message': 'Target crew not found.'}), 404

        if not target_crew.employees:
            return jsonify({'success': False, 'message': 'Target crew has no employees.'}), 400

        for assign in source_assignments:
            db.session.delete(assign)

        for member in target_crew.employees:
            db.session.add(Assignment(
                employee_id=member.id,
                job_id=job_id,
                crew_id=target_crew.id,
                assigned_date=target_date,
                start_time=start_time_obj,
                end_time=end_time_obj
            ))

        db.session.commit()
        return jsonify({'success': True, 'message': 'Crew job moved successfully.'})
    except Exception as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400

@app.route('/api/drag-schedule', methods=['POST'])
def drag_schedule():
    from flask import jsonify
    try:
        data = request.json or {}
        employee_id = data.get('employee_id')
        job_id = data.get('job_id')
        assigned_date = data.get('assigned_date')
        start_time = data.get('start_time') or '09:00'
        end_time = data.get('end_time') or '17:00'

        if not job_id or not assigned_date:
            return jsonify({'success': False, 'message': 'Job and date are required.'}), 400
        
        # Parse date and times
        from datetime import datetime as dt
        assigned_date = dt.strptime(assigned_date, '%Y-%m-%d').date()
        start_time_obj = dt.strptime(start_time, '%H:%M').time()
        end_time_obj = dt.strptime(end_time, '%H:%M').time()
        
        job = Job.query.get(job_id)
        if not job:
            return jsonify({'success': False, 'message': 'Job not found.'}), 404

        if employee_id:
            new_assignment = Assignment(
                employee_id=employee_id,
                job_id=job_id,
                assigned_date=assigned_date,
                start_time=start_time_obj,
                end_time=end_time_obj
            )
            db.session.add(new_assignment)

        # A date drop keeps the job in pending until a crew is assigned.
        job.published = False
        job.pending_date = assigned_date

        db.session.commit()

        if employee_id:
            return jsonify({'success': True, 'message': 'Assignment created. Job remains pending until crew assignment.'})
        return jsonify({'success': True, 'message': 'Job placed on calendar as pending. Assign a crew to publish it.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/job-search')
def job_search_api():
    from flask import jsonify
    q = (request.args.get('q') or '').strip()
    if len(q) < 1:
        return jsonify([])

    results = []
    seen_jobs = set()

    # Search assignments — gives us actual scheduled dates
    assignments = (Assignment.query
                   .join(Job)
                   .filter(Job.job_name.ilike(f'%{q}%'))
                   .order_by(Assignment.assigned_date)
                   .all())
    for assign in assignments:
        if assign.job_id not in seen_jobs and assign.assigned_date:
            seen_jobs.add(assign.job_id)
            results.append({
                'job_id': assign.job_id,
                'job_name': assign.job.job_name,
                'job_type': assign.job.job_type or '',
                'date': assign.assigned_date.isoformat(),
                'date_display': assign.assigned_date.strftime('%m/%d/%Y'),
            })

    # Also include jobs with a scheduled_date but no assignments yet
    jobs_with_dates = (Job.query
                       .filter(Job.job_name.ilike(f'%{q}%'))
                       .filter(Job.scheduled_date.isnot(None))
                       .all())
    for job in jobs_with_dates:
        if job.id not in seen_jobs:
            seen_jobs.add(job.id)
            results.append({
                'job_id': job.id,
                'job_name': job.job_name,
                'job_type': job.job_type or '',
                'date': job.scheduled_date.isoformat(),
                'date_display': job.scheduled_date.strftime('%m/%d/%Y'),
            })

    results.sort(key=lambda x: x['date'])
    return jsonify(results[:10])


@app.route('/job-search-jump', methods=['GET'])
def job_search_jump():
    query = (request.args.get('job_query') or '').strip()
    if not query:
        return redirect(url_for('index'))

    assign = (Assignment.query
              .join(Job)
              .filter(Job.status != 'canceled')
              .filter(Job.job_name.ilike(f'%{query}%'))
              .order_by(Assignment.assigned_date.asc())
              .first())
    if assign and assign.assigned_date:
        return redirect(url_for('index', schedule_start=assign.assigned_date.isoformat()))

    job = (Job.query
           .filter(Job.status != 'canceled')
           .filter(Job.scheduled_date.isnot(None))
           .filter(Job.job_name.ilike(f'%{query}%'))
           .order_by(Job.scheduled_date.asc())
           .first())
    if job and job.scheduled_date:
        return redirect(url_for('index', schedule_start=job.scheduled_date.isoformat()))

    flash('No scheduled job found for that search.', 'warning')
    return redirect(url_for('index'))


@app.route('/feedback/submit', methods=['POST'])
def submit_feedback():
    report_type = (request.form.get('report_type') or '').strip()
    subject = (request.form.get('subject') or '').strip()
    details = (request.form.get('details') or '').strip()

    if report_type not in ('bug', 'feedback'):
        return jsonify({'success': False, 'message': 'Invalid report type.'}), 400
    if not subject or len(subject) > 200:
        return jsonify({'success': False, 'message': 'Subject is required (max 200 chars).'}), 400
    if not details or len(details) > 2000:
        return jsonify({'success': False, 'message': 'Details are required (max 2000 chars).'}), 400

    emp = get_logged_in_employee()
    submitted_by = None
    if emp:
        submitted_by = emp.name
    elif session.get('developer_user'):
        submitted_by = session.get('developer_user')

    report = FeedbackReport(
        report_type=report_type,
        subject=subject,
        details=details,
        submitted_by=submitted_by,
        status='received',
        opened_at=None,
        opened_by=None,
        closed_at=None,
        closed_by=None,
        resolved=False,
        resolved_at=None
    )
    db.session.add(report)
    db.session.commit()
    save_feedback_snapshot()
    return jsonify({'success': True, 'message': 'Thank you! Your report has been submitted.'})


@app.route('/feedback/<int:id>/open', methods=['POST'])
def open_feedback(id):
    report = FeedbackReport.query.get(id)
    if not report:
        return jsonify({'success': False, 'message': 'Report not found.'}), 404
    if not can_access_feedback_ticket_board():
        return jsonify({'success': False, 'message': 'Not authorised.'}), 403

    if (report.status or '').strip().lower() == 'received':
        actor = get_feedback_actor_name() or 'System'
        report.status = 'open'
        report.opened_at = datetime.utcnow()
        report.opened_by = actor
        report.resolved = False
        report.resolved_at = None
        db.session.commit()
        save_feedback_snapshot()

    return jsonify({'success': True, 'status': report.status or 'open'})


@app.route('/feedback/<int:id>/resolve', methods=['POST'])
def resolve_feedback(id):
    report = FeedbackReport.query.get(id)
    if not report:
        return jsonify({'success': False, 'message': 'Report not found.'}), 404

    if not can_manage_feedback_ticket(report, allow_submitter_close=True):
        return jsonify({'success': False, 'message': 'Not authorised.'}), 403

    actor = get_feedback_actor_name() or 'System'
    now = datetime.utcnow()

    reply_text = ''
    if request.is_json:
        reply_text = (request.json.get('reply') or '').strip()
    else:
        reply_text = (request.form.get('reply') or '').strip()
    report.status = 'closed'
    report.closed_at = now
    report.closed_by = actor
    report.resolved = True
    report.resolved_at = now
    if reply_text:
        report.reply = reply_text
        report.reply_seen = False
    db.session.commit()
    save_feedback_snapshot()
    return jsonify({
        'success': True,
        'status': 'closed',
        'resolved': True,
        'reply': report.reply or '',
        'closed_at': report.closed_at.strftime('%m/%d/%Y %I:%M %p') if report.closed_at else '',
        'closed_by': report.closed_by or '',
        'resolved_at': report.resolved_at.strftime('%m/%d/%Y %I:%M %p') if report.resolved_at else ''
    })


@app.route('/feedback/mark-replies-seen', methods=['POST'])
def mark_feedback_replies_seen():
    emp = get_logged_in_employee()
    if not emp:
        return jsonify({'success': False}), 403
    FeedbackReport.query.filter_by(
        submitted_by=emp.name,
        status='closed'
    ).filter(FeedbackReport.reply.isnot(None)).update({'reply_seen': True})
    db.session.commit()
    return jsonify({'success': True})


@app.route('/feedback/<int:id>/reopen', methods=['POST'])
def reopen_feedback(id):
    report = FeedbackReport.query.get(id)
    if not report:
        return jsonify({'success': False, 'message': 'Report not found.'}), 404

    if not can_access_feedback_ticket_board():
        return jsonify({'success': False, 'message': 'Not authorised.'}), 403

    actor = get_feedback_actor_name() or 'System'
    report.status = 'open'
    report.opened_at = datetime.utcnow()
    report.opened_by = actor
    report.closed_at = None
    report.closed_by = None
    report.resolved = False
    report.resolved_at = None
    db.session.commit()
    save_feedback_snapshot()
    return jsonify({'success': True, 'status': 'open', 'resolved': False})


@app.route('/feedback/<int:id>/delete', methods=['POST'])
def delete_feedback(id):
    real_employee = get_logged_in_employee()
    is_dev_or_support = False
    if session.get('developer_user'):
        is_dev_or_support = True
    elif real_employee:
        _roles = {(r or '').strip().lower() for r in (real_employee.category or '').split(',') if (r or '').strip()}
        is_dev_or_support = bool(_roles & {'developer', 'development', 'support'})
    if not is_dev_or_support:
        return jsonify({'success': False, 'message': 'Not authorised.'}), 403
    report = FeedbackReport.query.get(id)
    if not report:
        return jsonify({'success': False, 'message': 'Report not found.'}), 404
    db.session.delete(report)
    db.session.commit()
    save_feedback_snapshot()
    return jsonify({'success': True})


# ── Time Off Requests ───────────────────────────────────────────────────────

TIME_OFF_TYPES = ['Vacation', 'Sick', 'Personal', 'Bereavement', 'Medical']


def _business_days(start, end):
    """Count weekdays (Mon-Fri) between start and end inclusive."""
    count = 0
    current = start
    while current <= end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


def _tor_conflicts(employee_id, start_date, end_date, exclude_id=None):
    """Return list of conflicting approved/pending TimeOffRequests for the employee."""
    q = TimeOffRequest.query.filter(
        TimeOffRequest.employee_id == employee_id,
        TimeOffRequest.status.in_(['pending', 'approved']),
        TimeOffRequest.start_date <= end_date,
        TimeOffRequest.end_date >= start_date
    )
    if exclude_id:
        q = q.filter(TimeOffRequest.id != exclude_id)
    return q.all()


@app.route('/time-off/request', methods=['POST'])
def time_off_request():
    emp = get_logged_in_employee()
    if not emp:
        return jsonify({'success': False, 'message': 'Not logged in.'}), 401

    start_str = (request.form.get('start_date') or '').strip()
    end_str = (request.form.get('end_date') or '').strip()
    reason = (request.form.get('reason') or '').strip()[:500]
    request_type = (request.form.get('request_type') or 'Vacation').strip()
    if request_type not in TIME_OFF_TYPES:
        request_type = 'Vacation'

    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date format.'}), 400

    today = datetime.utcnow().date()
    if start_date < today:
        return jsonify({'success': False, 'message': 'Cannot request time off for past dates.'}), 400

    if end_date < start_date:
        return jsonify({'success': False, 'message': 'End date must be on or after start date.'}), 400

    # Overlap guard
    overlapping = _tor_conflicts(emp.id, start_date, end_date)
    if overlapping:
        return jsonify({'success': False, 'message': 'You already have a pending or approved request that overlaps those dates.'}), 400

    # Duplicate submission guard (same employee, same dates, within 10 seconds)
    cutoff = datetime.utcnow() - timedelta(seconds=10)
    dup = TimeOffRequest.query.filter_by(
        employee_id=emp.id, start_date=start_date, end_date=end_date
    ).filter(TimeOffRequest.requested_at >= cutoff).first()
    if dup:
        return jsonify({'success': False, 'message': 'Duplicate submission — request already received.'}), 400

    tor = TimeOffRequest(
        employee_id=emp.id,
        employee_name=emp.name,
        start_date=start_date,
        end_date=end_date,
        request_type=request_type,
        reason=reason or None,
        status='pending',
        requested_at=datetime.utcnow(),
        seen_by_employee=True
    )
    db.session.add(tor)
    db.session.commit()

    # SocketIO: push new pending count to all connected managers
    pending_count = TimeOffRequest.query.filter_by(status='pending').count()
    socketio.emit('time_off_pending_update', {'count': pending_count})

    bdays = _business_days(start_date, end_date)
    return jsonify({'success': True, 'message': f'Time off request submitted ({bdays} business day{"s" if bdays != 1 else ""}).'})


@app.route('/time-off/<int:tor_id>/review', methods=['POST'])
def time_off_review(tor_id):
    emp = get_logged_in_employee()
    if not emp and not session.get('developer_user'):
        return jsonify({'success': False, 'message': 'Not logged in.'}), 401

    if not is_manager_or_admin(emp):
        return jsonify({'success': False, 'message': 'Manager access required.'}), 403

    tor = TimeOffRequest.query.get(tor_id)
    if not tor:
        return jsonify({'success': False, 'message': 'Request not found.'}), 404

    if tor.status != 'pending':
        return jsonify({'success': False, 'message': 'Request has already been reviewed.'}), 400

    decision = (request.form.get('decision') or '').strip().lower()
    if decision not in ('approved', 'denied'):
        return jsonify({'success': False, 'message': 'Decision must be approved or denied.'}), 400

    note = (request.form.get('note') or '').strip()[:500]
    reviewer_name = emp.name if emp else session.get('developer_user_name', 'Manager')

    tor.status = decision
    tor.reviewed_by = reviewer_name
    tor.reviewed_at = datetime.utcnow()
    tor.response_note = note or None
    tor.seen_by_employee = False  # Employee hasn't seen the decision yet
    db.session.commit()

    _audit(
        reviewer_name, f'time_off_{decision}',
        target=tor.employee_name,
        detail=f'Dates: {tor.start_date} – {tor.end_date}' + (f' | Note: {note}' if note else '')
    )

    # SocketIO: broadcast updated pending count
    pending_count = TimeOffRequest.query.filter_by(status='pending').count()
    socketio.emit('time_off_pending_update', {'count': pending_count})

    return jsonify({'success': True, 'message': f'Request {decision}.'})


@app.route('/time-off/<int:tor_id>/change-decision', methods=['POST'])
def time_off_change_decision(tor_id):
    """Allow managers to revoke or change the decision on an already-reviewed request."""
    emp = get_logged_in_employee()
    if not emp and not session.get('developer_user'):
        return jsonify({'success': False, 'message': 'Not logged in.'}), 401

    if not is_manager_or_admin(emp):
        return jsonify({'success': False, 'message': 'Manager access required.'}), 403

    tor = TimeOffRequest.query.get(tor_id)
    if not tor:
        return jsonify({'success': False, 'message': 'Request not found.'}), 404

    new_status = (request.form.get('status') or '').strip().lower()
    if new_status not in ('approved', 'denied', 'pending'):
        return jsonify({'success': False, 'message': 'Status must be approved, denied, or pending.'}), 400

    note = (request.form.get('note') or '').strip()[:500]
    reviewer_name = emp.name if emp else session.get('developer_user_name', 'Manager')

    old_status = tor.status
    tor.status = new_status
    tor.reviewed_by = reviewer_name
    tor.reviewed_at = datetime.utcnow()
    tor.response_note = note or tor.response_note
    tor.seen_by_employee = False
    db.session.commit()

    _audit(
        reviewer_name, f'time_off_changed',
        target=tor.employee_name,
        detail=f'{old_status} → {new_status} | Dates: {tor.start_date} – {tor.end_date}' + (f' | Note: {note}' if note else '')
    )

    pending_count = TimeOffRequest.query.filter_by(status='pending').count()
    socketio.emit('time_off_pending_update', {'count': pending_count})

    return jsonify({'success': True, 'message': f'Request changed to {new_status}.', 'new_status': new_status})


@app.route('/time-off/<int:tor_id>/cancel', methods=['POST'])
def time_off_cancel(tor_id):
    emp = get_logged_in_employee()
    if not emp:
        return jsonify({'success': False, 'message': 'Not logged in.'}), 401

    tor = TimeOffRequest.query.get(tor_id)
    if not tor:
        return jsonify({'success': False, 'message': 'Request not found.'}), 404

    if tor.employee_id != emp.id:
        return jsonify({'success': False, 'message': 'Not your request.'}), 403

    if tor.status not in ('pending',):
        return jsonify({'success': False, 'message': 'Only pending requests can be cancelled.'}), 400

    tor.status = 'cancelled'
    db.session.commit()

    pending_count = TimeOffRequest.query.filter_by(status='pending').count()
    socketio.emit('time_off_pending_update', {'count': pending_count})

    return jsonify({'success': True, 'message': 'Request cancelled.'})


@app.route('/time-off/mark-seen', methods=['POST'])
def time_off_mark_seen():
    emp = get_logged_in_employee()
    if not emp:
        return jsonify({'success': False, 'message': 'Not logged in.'}), 401

    TimeOffRequest.query.filter_by(employee_id=emp.id, seen_by_employee=False).update({'seen_by_employee': True})
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/time-off/conflicts')
def time_off_conflicts_api():
    """Return assignment conflicts for a given employee + date range (for manager view)."""
    emp = get_logged_in_employee()
    if not emp and not session.get('developer_user'):
        return jsonify({'error': 'unauthorized'}), 401

    emp_id_raw = (request.args.get('employee_id') or '').strip()
    start_str = (request.args.get('start_date') or '').strip()
    end_str = (request.args.get('end_date') or '').strip()

    if not emp_id_raw.isdigit() or not start_str or not end_str:
        return jsonify({'conflicts': []})

    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'conflicts': []})

    target_employee_id = int(emp_id_raw)
    # Only managers can check other employees
    if target_employee_id != (emp.id if emp else -1) and not is_manager_or_admin(emp):
        return jsonify({'conflicts': []})

    conflicting_assignments = (
        Assignment.query
        .join(Job)
        .filter(
            Assignment.employee_id == target_employee_id,
            Assignment.assigned_date >= start_date,
            Assignment.assigned_date <= end_date,
            Job.published.is_(True),
            Job.status != 'canceled'
        )
        .all()
    )

    conflicts = []
    seen = set()
    for a in conflicting_assignments:
        key = (a.assigned_date, a.job_id)
        if key in seen:
            continue
        seen.add(key)
        conflicts.append({
            'date': a.assigned_date.isoformat(),
            'job_name': a.job.job_name if a.job else '?',
            'job_type': a.job.job_type if a.job else '',
        })

    conflicts.sort(key=lambda x: x['date'])
    return jsonify({'conflicts': conflicts})


@app.route('/api/time-off/approved-log')
def time_off_approved_log_api():
    """Return all approved time-off requests, for manager view."""
    emp = get_logged_in_employee()
    if not emp and not session.get('developer_user'):
        return jsonify({'error': 'unauthorized'}), 401
    if not is_manager_or_admin(emp):
        return jsonify({'error': 'forbidden'}), 403

    records = (
        TimeOffRequest.query
        .filter_by(status='approved')
        .order_by(TimeOffRequest.start_date.desc())
        .limit(500)
        .all()
    )
    result = []
    for r in records:
        result.append({
            'id': r.id,
            'employee_name': r.employee_name,
            'request_type': r.request_type or 'Vacation',
            'start_date': r.start_date.isoformat(),
            'end_date': r.end_date.isoformat(),
            'business_days': _business_days(r.start_date, r.end_date),
            'reason': r.reason or '',
            'reviewed_by': r.reviewed_by or '',
            'reviewed_at': r.reviewed_at.strftime('%b %d, %Y') if r.reviewed_at else '',
            'response_note': r.response_note or '',
        })
    return jsonify({'log': result})


@app.route('/api/time-off/history')
def time_off_history_api():
    """Return all reviewed (approved/denied) time-off requests, for manager view."""
    emp = get_logged_in_employee()
    if not emp and not session.get('developer_user'):
        return jsonify({'error': 'unauthorized'}), 401
    if not is_manager_or_admin(emp):
        return jsonify({'error': 'forbidden'}), 403

    days = 90
    since = (datetime.utcnow() - timedelta(days=days)).date()
    records = (
        TimeOffRequest.query
        .filter(TimeOffRequest.status.in_(['approved', 'denied']),
                TimeOffRequest.start_date >= since)
        .order_by(TimeOffRequest.reviewed_at.desc())
        .limit(200)
        .all()
    )
    result = []
    for r in records:
        result.append({
            'id': r.id,
            'employee_name': r.employee_name,
            'request_type': r.request_type or 'Vacation',
            'start_date': r.start_date.isoformat(),
            'end_date': r.end_date.isoformat(),
            'business_days': _business_days(r.start_date, r.end_date),
            'reason': r.reason or '',
            'status': r.status,
            'reviewed_by': r.reviewed_by or '',
            'reviewed_at': r.reviewed_at.strftime('%b %d, %Y') if r.reviewed_at else '',
            'response_note': r.response_note or '',
        })
    return jsonify({'history': result})


# ── Overtime hours API ──────────────────────────────────────────────────────────
@app.route('/api/employee/<int:emp_id>/week-hours')
def employee_week_hours(emp_id):
    """Return total scheduled hours for an employee in a given week (Mon–Sun)."""
    if not is_authenticated_session():
        return jsonify({'error': 'unauthorized'}), 401

    week_start_str = (request.args.get('week_start') or '').strip()
    try:
        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
        week_start = week_start - timedelta(days=week_start.weekday())  # snap to Monday
    except ValueError:
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    assignments = Assignment.query.filter(
        Assignment.employee_id == emp_id,
        Assignment.assigned_date >= week_start,
        Assignment.assigned_date <= week_end,
    ).all()

    total_hours = 0.0
    for a in assignments:
        if a.start_time and a.end_time:
            start_dt = datetime.combine(a.assigned_date, a.start_time)
            end_dt   = datetime.combine(a.assigned_date, a.end_time)
            diff = (end_dt - start_dt).total_seconds() / 3600
            if diff > 0:
                total_hours += diff
        else:
            total_hours += 8.0  # assume 8h for all-day shifts

    warning = total_hours > 40
    return jsonify({'hours': round(total_hours, 2), 'limit': 40, 'warning': warning,
                    'week_start': week_start.isoformat(), 'week_end': week_end.isoformat()})


# ── When I Work CSV Import ──────────────────────────────────────────────────────
import csv as _csv
import io as _io
import re as _re

def _wiw_parse_csv(file_bytes):
    """Parse a When I Work export — either XLSX or CSV.

    Handles two formats:
    1. Wide/pivot format: date columns as headers (e.g. 'Apr 6, 2026'), one row per
       employee+position, hours per day as cell values.
    2. Row-per-shift format: columns include 'Date', 'Start Time', 'End Time'.

    Always returns a list of flat shift dicts with keys:
        emp_name, date_raw, start_raw, end_raw, job_hint
    """
    # Detect XLSX by PK magic bytes
    is_xlsx = file_bytes[:2] == b'PK'

    if is_xlsx:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        rows_raw = list(ws.iter_rows(values_only=True))
        if not rows_raw:
            return []
        # First non-empty row is the header
        header = [str(c).strip() if c is not None else '' for c in rows_raw[0]]
        raw_rows = []
        for row in rows_raw[1:]:
            norm = {header[i]: (str(row[i]).strip() if row[i] is not None else '')
                    for i in range(len(header))}
            if any(v for v in norm.values()):
                raw_rows.append(norm)
        fieldnames = header
    else:
        text = file_bytes.decode('utf-8-sig', errors='replace')
        reader = csv.DictReader(io.StringIO(text, newline=''))
        raw_rows = []
        fieldnames = []
        for row in reader:
            if not fieldnames:
                fieldnames = [k for k in row.keys() if k is not None]
            norm = {k.strip(): (v or '').strip() for k, v in row.items() if k is not None}
            if any(v for v in norm.values()):
                raw_rows.append(norm)

    if not raw_rows:
        return []

    # Detect date columns — headers that parse as a date (e.g. "Apr 6, 2026")
    date_col_map = {}  # header -> date object
    for col in fieldnames:
        col_stripped = col.strip()
        if not col_stripped:
            continue
        for fmt in ('%b %d, %Y', '%B %d, %Y', '%m/%d/%Y', '%Y-%m-%d'):
            try:
                date_col_map[col_stripped] = datetime.strptime(col_stripped, fmt).date()
                break
            except ValueError:
                pass

    shifts = []
    if date_col_map:
        # Wide/pivot format
        for row in raw_rows:
            first = row.get('First Name') or row.get('first name') or ''
            last  = row.get('Last Name')  or row.get('last name')  or ''
            emp_name = (first + ' ' + last).strip()
            if not emp_name:
                emp_name = row.get('User') or row.get('user') or row.get('Employee') or ''
            position = row.get('Position') or row.get('position') or ''
            site     = row.get('Site') or row.get('site') or row.get('Location') or ''
            job_hint = position or site

            for col, parsed_date in date_col_map.items():
                hours_str = row.get(col) or '0'
                try:
                    hours = float(str(hours_str).replace(',', ''))
                except ValueError:
                    hours = 0.0
                if hours <= 0:
                    continue
                shifts.append({
                    'emp_name': emp_name,
                    'date_raw': parsed_date.strftime('%Y-%m-%d'),
                    'start_raw': '',
                    'end_raw':   '',
                    'job_hint':  job_hint,
                })
    else:
        # Row-per-shift format
        for row in raw_rows:
            first = row.get('First Name') or row.get('first name') or row.get('firstname') or ''
            last  = row.get('Last Name')  or row.get('last name')  or row.get('lastname')  or ''
            emp_name = (first + ' ' + last).strip()
            if not emp_name:
                emp_name = row.get('User') or row.get('user') or row.get('Name') or row.get('name') or ''
            date_raw  = row.get('Date') or row.get('date') or ''
            start_raw = row.get('Start Time') or row.get('start time') or row.get('Start') or ''
            end_raw   = row.get('End Time')   or row.get('end time')   or row.get('End')   or ''
            notes     = row.get('Notes') or row.get('notes') or ''
            location  = row.get('Location') or row.get('location') or row.get('Position') or row.get('position') or ''
            job_hint  = notes or location
            if not emp_name and not date_raw:
                continue
            shifts.append({
                'emp_name': emp_name,
                'date_raw': date_raw,
                'start_raw': start_raw,
                'end_raw':   end_raw,
                'job_hint':  job_hint,
            })

    return shifts

def _wiw_extract_row(shift):
    """Unpack a shift dict produced by _wiw_parse_csv."""
    return (
        shift.get('emp_name', ''),
        shift.get('date_raw', ''),
        shift.get('start_raw', ''),
        shift.get('end_raw', ''),
        shift.get('job_hint', ''),
    )

def _parse_wiw_date(date_raw):
    """Try multiple date formats WiW might use. Returns date or None."""
    import re
    date_raw = date_raw.strip()
    # Remove day-of-week prefix like "Mon ", "Mon, ", "Monday ", "Monday, "
    date_raw = re.sub(r'^[A-Za-z]+,?\s+', '', date_raw)
    for fmt in ('%b %d, %Y', '%B %d, %Y', '%m/%d/%Y', '%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(date_raw, fmt).date()
        except ValueError:
            pass
    return None

def _parse_wiw_time(time_raw):
    """Parse a time string like '7:00 AM', '07:00', '7:00:00'. Returns time or None."""
    time_raw = time_raw.strip()
    for fmt in ('%I:%M %p', '%I:%M%p', '%H:%M', '%H:%M:%S', '%I:%M:%S %p'):
        try:
            return datetime.strptime(time_raw.upper(), fmt.upper()).time()
        except ValueError:
            pass
    return None

def _match_employee(name, all_employees):
    """Case-insensitive full-name match against Employee list."""
    name_lower = name.lower().strip()
    for emp in all_employees:
        if emp.name.lower().strip() == name_lower:
            return emp
    # Partial: last name only
    for emp in all_employees:
        parts = emp.name.lower().split()
        if parts and parts[-1] == name_lower.split()[-1] if name_lower else False:
            return emp
    return None

def _match_job(hint, all_jobs):
    """Find best-matching active job by searching hint against name, po_number, address."""
    if not hint:
        return None
    hint_l = hint.lower()
    candidates = []
    for j in all_jobs:
        score = 0
        if j.job_name and j.job_name.lower() in hint_l: score += 3
        if hint_l in (j.job_name or '').lower(): score += 3
        if j.po_number and j.po_number.lower() in hint_l: score += 2
        if j.address and j.address.lower() in hint_l: score += 2
        if j.address and any(part in (j.address or '').lower() for part in hint_l.split() if len(part) > 3): score += 1
        if score > 0:
            candidates.append((score, j))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


@app.route('/import/wheniwork/preview', methods=['POST'])
def wiw_import_preview():
    emp = get_logged_in_employee()
    if not is_authenticated_session():
        return jsonify({'error': 'unauthorized'}), 401
    if not is_manager_or_admin(emp):
        return jsonify({'error': 'forbidden'}), 403
    if 'file' not in request.files or not request.files['file'].filename:
        return jsonify({'error': 'No file uploaded'}), 400

    file_bytes = request.files['file'].read()
    try:
        rows = _wiw_parse_csv(file_bytes)
    except Exception as e:
        return jsonify({'error': f'Could not parse CSV: {e}'}), 400

    if not rows:
        raw_text = file_bytes.decode('utf-8-sig', errors='replace')
        first_lines = raw_text.splitlines()[:8]
        print("=== WiW DEBUG: 0 shifts parsed ===")
        for l in first_lines:
            print(repr(l))
        print("===================================")
        return jsonify({
            'preview': [], 'all_jobs': [], 'all_employees': [],
            'debug_total_rows': 0,
            'debug_raw_lines': first_lines
        })

    all_employees = Employee.query.all()
    active_jobs   = Job.query.filter(Job.status != 'cancelled').all()

    preview = []
    for i, shift in enumerate(rows):
        emp_name, date_raw, start_raw, end_raw, job_hint = _wiw_extract_row(shift)
        parsed_date  = _parse_wiw_date(date_raw)
        parsed_start = _parse_wiw_time(start_raw)
        parsed_end   = _parse_wiw_time(end_raw)
        matched_emp  = _match_employee(emp_name, all_employees)
        matched_job  = _match_job(job_hint, active_jobs)
        preview.append({
            'row': i,
            'wiw_employee':  emp_name,
            'wiw_date':      date_raw,
            'wiw_start':     start_raw,
            'wiw_end':       end_raw,
            'wiw_notes':     job_hint,
            'date_parsed':   parsed_date.isoformat() if parsed_date else None,
            'start_parsed':  parsed_start.strftime('%H:%M') if parsed_start else None,
            'end_parsed':    parsed_end.strftime('%H:%M') if parsed_end else None,
            'matched_emp_id':   matched_emp.id   if matched_emp else None,
            'matched_emp_name': matched_emp.name if matched_emp else None,
            'matched_job_id':   matched_job.id   if matched_job else None,
            'matched_job_name': matched_job.job_name if matched_job else None,
        })

    all_jobs_list = [{'id': j.id, 'label': f"{j.job_name} — {j.address or 'No address'}"} for j in active_jobs]
    all_emp_list  = [{'id': e.id, 'name': e.name} for e in all_employees]
    return jsonify({'preview': preview, 'all_jobs': all_jobs_list, 'all_employees': all_emp_list,
                    'debug_total_rows': len(rows)})


@app.route('/import/wheniwork/commit', methods=['POST'])
def wiw_import_commit():
    emp = get_logged_in_employee()
    if not is_authenticated_session():
        return jsonify({'error': 'unauthorized'}), 401
    if not is_manager_or_admin(emp):
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json(force=True) or {}
    rows = data.get('rows', [])

    created = 0
    skipped = 0
    errors  = []
    for r in rows:
        emp_id  = r.get('emp_id')
        job_id  = r.get('job_id')
        date_s  = r.get('date')
        start_s = r.get('start')
        end_s   = r.get('end')
        if not (emp_id and job_id and date_s):
            skipped += 1
            continue
        try:
            assigned_date = date.fromisoformat(date_s)
            start_time  = datetime.strptime(start_s, '%H:%M').time() if start_s else None
            end_time    = datetime.strptime(end_s,   '%H:%M').time() if end_s   else None
        except Exception:
            errors.append(f"Bad date/time for row emp={emp_id} job={job_id}")
            skipped += 1
            continue
        # Skip if assignment already exists for this employee+job+date
        exists = Assignment.query.filter_by(
            employee_id=emp_id, job_id=job_id, assigned_date=assigned_date
        ).first()
        if exists:
            skipped += 1
            continue
        a = Assignment(employee_id=emp_id, job_id=job_id,
                       assigned_date=assigned_date, start_time=start_time, end_time=end_time)
        db.session.add(a)
        created += 1

    try:
        db.session.commit()
        _audit(emp.name, 'wiw_import', detail=f'created={created} skipped={skipped}')
        socketio.emit('schedule_update', {'msg': 'WiW import completed'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

    return jsonify({'created': created, 'skipped': skipped, 'errors': errors})


# ── Time-off CSV export ─────────────────────────────────────────────────────────
@app.route('/export/time-off')
def export_time_off_csv():
    emp = get_logged_in_employee()
    if not is_authenticated_session():
        return redirect(url_for('login'))
    if not is_manager_or_admin(emp):
        return jsonify({'error': 'Manager access required.'}), 403

    status_filter = (request.args.get('status') or 'all').strip().lower()

    query = TimeOffRequest.query
    if status_filter != 'all':
        query = query.filter(TimeOffRequest.status == status_filter)
    records = query.order_by(TimeOffRequest.requested_at.desc()).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Employee', 'Type', 'Start', 'End', 'Business Days', 'Status', 'Reason', 'Requested At', 'Reviewed By', 'Reviewed At', 'Response Note'])
    for r in records:
        bd = _business_days(r.start_date, r.end_date)
        writer.writerow([
            r.employee_name,
            r.request_type or 'Vacation',
            r.start_date.isoformat(),
            r.end_date.isoformat(),
            bd,
            r.status,
            r.reason or '',
            r.requested_at.strftime('%Y-%m-%d %H:%M') if r.requested_at else '',
            r.reviewed_by or '',
            r.reviewed_at.strftime('%Y-%m-%d %H:%M') if r.reviewed_at else '',
            r.response_note or '',
        ])

    response = make_response(buf.getvalue())
    fname = f'time-off-{status_filter}-{datetime.now().strftime("%Y%m%d")}.csv'
    response.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    _audit(emp.name if emp else 'dev', 'export_time_off_csv', detail=f'status={status_filter}')
    return response


# ── Schedule CSV export ─────────────────────────────────────────────────────────
@app.route('/export/schedule')
def export_schedule_csv():
    if not is_authenticated_session():
        return redirect(url_for('login'))

    week_start_str = (request.args.get('week_start') or '').strip()
    try:
        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
        week_start = week_start - timedelta(days=week_start.weekday())
    except ValueError:
        today = datetime.now().date()
        week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    assignments = (
        Assignment.query
        .join(Employee)
        .join(Job)
        .filter(
            Assignment.assigned_date >= week_start,
            Assignment.assigned_date <= week_end,
        )
        .order_by(Assignment.assigned_date, Employee.name)
        .all()
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Date', 'Employee', 'Category', 'Job', 'Job Type', 'Start Time', 'End Time', 'Status', 'Published'])
    for a in assignments:
        writer.writerow([
            a.assigned_date.isoformat(),
            a.employee.name if a.employee else '',
            a.employee.category if a.employee else '',
            a.job.job_name if a.job else '',
            a.job.job_type if a.job else '',
            a.start_time.strftime('%H:%M') if a.start_time else '',
            a.end_time.strftime('%H:%M') if a.end_time else '',
            a.job.status if a.job else '',
            'Yes' if (a.job and a.job.published) else 'No',
        ])

    emp = get_logged_in_employee()
    response = make_response(buf.getvalue())
    fname = f'schedule-{week_start.isoformat()}.csv'
    response.headers['Content-Disposition'] = f'attachment; filename="{fname}"'
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    _audit(emp.name if emp else 'dev', 'export_schedule_csv', detail=f'week={week_start.isoformat()}')
    return response


# ── Audit log viewer (manager/dev only) ────────────────────────────────────────
@app.route('/api/audit-log')
def audit_log_api():
    emp = get_logged_in_employee()
    if not is_authenticated_session():
        return jsonify({'error': 'unauthorized'}), 401
    if not is_manager_or_admin(emp):
        return jsonify({'error': 'forbidden'}), 403

    limit = min(int(request.args.get('limit') or 200), 500)
    actor_filter = (request.args.get('actor') or '').strip()
    action_filter = (request.args.get('action') or '').strip()

    query = AuditLog.query
    if actor_filter:
        query = query.filter(AuditLog.actor.ilike(f'%{actor_filter}%'))
    if action_filter:
        query = query.filter(AuditLog.action.ilike(f'%{action_filter}%'))
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

    return jsonify({'logs': [{
        'id': l.id,
        'timestamp': l.timestamp.strftime('%Y-%m-%d %H:%M:%S') if l.timestamp else '',
        'actor': l.actor,
        'action': l.action,
        'target': l.target or '',
        'detail': l.detail or '',
        'ip_address': l.ip_address or '',
    } for l in logs]})


@app.route('/dev/view-as', methods=['POST'])
def dev_view_as():
    real_employee = get_logged_in_employee()
    if not (session.get('developer_user') or is_developer_employee(real_employee)):
        return jsonify({'success': False, 'message': 'Not authorised.'}), 403

    mode = (request.form.get('mode') or request.json.get('mode', '') if request.is_json else request.form.get('mode') or '').strip()
    target_id_raw = (request.form.get('target_id') or (request.json.get('target_id') if request.is_json else None) or '').strip()

    session.pop('view_as_employee_id', None)
    session.pop('view_as_permission_set_id', None)

    if mode == 'employee' and target_id_raw.isdigit():
        emp = Employee.query.get(int(target_id_raw))
        if not emp:
            return jsonify({'success': False, 'message': 'Employee not found.'}), 404
        session['view_as_employee_id'] = emp.id
        return jsonify({'success': True, 'message': f'Now viewing as {emp.name}.'})
    elif mode == 'permission_set' and target_id_raw.isdigit():
        ps = PermissionSet.query.get(int(target_id_raw))
        if not ps:
            return jsonify({'success': False, 'message': 'Permission set not found.'}), 404
        session['view_as_permission_set_id'] = ps.id
        return jsonify({'success': True, 'message': f'Now viewing with permissions: {ps.name}.'})
    else:
        return jsonify({'success': False, 'message': 'Invalid mode or target.'}), 400


@app.route('/dev/view-as/exit', methods=['POST', 'GET'])
def dev_view_as_exit():
    session.pop('view_as_employee_id', None)
    session.pop('view_as_permission_set_id', None)
    if is_ajax_request():
        return jsonify({'success': True})
    return redirect(url_for('index', tab='backend'))


# WebSocket handlers for real-time updates
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')


# ── Custom error pages ─────────────────────────────────────────────────────────
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(429)
def rate_limit_exceeded(e):
    if request.path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': 'Too many requests. Please slow down.'}), 429
    return render_template('429.html'), 429


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

# Ensure schema + service employees exist regardless of how the app is launched
# (flask run does not execute the if __name__ == '__main__' block)
try:
    with app.app_context():
        db.create_all()
        ensure_schema_updates()
        add_service_employees()
except Exception as _startup_err:
    print(f'Warning: startup init skipped: {_startup_err}')

if __name__ == '__main__':
    with app.app_context():
        backup_database_on_startup()
        db.create_all()
        ensure_schema_updates()
        ensure_default_crews()
        ensure_default_permission_sets()
        restore_feedback_from_snapshot_if_needed()
        restore_core_data_from_snapshots_if_needed()
        add_service_employees()
        # Seed data if empty
        if not Employee.query.first() and not Job.query.first():
            # Create core departments if missing
            dept_it = Department.query.filter_by(name="IT").first()
            if not dept_it:
                dept_it = Department(name="IT")
                db.session.add(dept_it)

            dept_ops = Department.query.filter_by(name="Operations").first()
            if not dept_ops:
                dept_ops = Department(name="Operations")
                db.session.add(dept_ops)

            db.session.flush()

            # Create groups within departments if missing
            group_dev = Group.query.filter_by(name="Development", department_id=dept_it.id).first()
            if not group_dev:
                group_dev = Group(name="Development", department_id=dept_it.id, color='#3b82f6')
                db.session.add(group_dev)

            group_support = Group.query.filter_by(name="Support", department_id=dept_it.id).first()
            if not group_support:
                group_support = Group(name="Support", department_id=dept_it.id, color='#22c55e')
                db.session.add(group_support)

            group_field = Group.query.filter_by(name="Field Operations", department_id=dept_ops.id).first()
            if not group_field:
                group_field = Group(name="Field Operations", department_id=dept_ops.id, color='#f97316')
                db.session.add(group_field)

            db.session.flush()

            # Create employees
            emp1 = Employee(name="Staff Member A", category="Office", group_id=group_dev.id)
            emp2 = Employee(name="Staff Member B", category="Installer", group_id=group_field.id)
            emp3 = Employee(name="Staff Member C", category="Service", group_id=group_support.id)
            db.session.add_all([emp1, emp2, emp3])

            # Create jobs
            job1 = Job(job_name="Project Site 101", job_type="Solar Install", status="not_started")
            job2 = Job(job_name="Project Site 102", job_type="Service", status="in_progress")
            db.session.add_all([job1, job2])

            db.session.commit()
            save_feedback_snapshot()
            save_core_data_snapshots()
    atexit.register(save_feedback_snapshot_on_exit)
    atexit.register(save_core_data_snapshots_on_exit)
    app.run(host='0.0.0.0', port=5000, debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')

# Move walkthrough flag route here so app is defined
@app.route('/clear_walkthrough_flag', methods=['POST'])
def clear_walkthrough_flag():
    session.pop('show_walkthrough', None)
    return '', 204