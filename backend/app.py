from datetime import datetime
from functools import wraps
import os

from flask import Flask, jsonify, request, session, send_from_directory
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///shiftease.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'

db = SQLAlchemy(app)


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_no = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='employee')
    preferred = db.Column(db.Boolean, default=False)


class ShiftRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    start = db.Column(db.String(5))
    end = db.Column(db.String(5))
    unavailable = db.Column(db.Boolean, default=False)
    message = db.Column(db.Text, default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    start = db.Column(db.String(5), nullable=False)
    end = db.Column(db.String(5), nullable=False)


class AttendanceNotice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ChangeLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor_employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    action = db.Column(db.String(100), nullable=False)
    detail = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def login_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if not session.get('employee_id'):
            return jsonify(error='login required'), 401
        return fn(*args, **kwargs)
    return inner


def admin_required(fn):
    @wraps(fn)
    def inner(*args, **kwargs):
        if session.get('role') != 'admin':
            return jsonify(error='admin required'), 403
        return fn(*args, **kwargs)
    return inner


@app.get('/')
def frontend():
    return send_from_directory(BASE_DIR, 'index.html')


@app.post('/api/login')
def login():
    data = request.get_json() or {}
    emp = Employee.query.filter_by(employee_no=str(data.get('employee_no', '')).strip()).first()
    if not emp or emp.role == 'admin':
        return jsonify(error='従業員番号が見つかりません'), 404
    session['employee_id'] = emp.id
    session['role'] = emp.role
    return jsonify(id=emp.id, employee_no=emp.employee_no, name=emp.name, role=emp.role)


@app.post('/api/admin/login')
def admin_login():
    data = request.get_json() or {}
    if str(data.get('pin', '')) != os.environ.get('ADMIN_PIN', '1234'):
        return jsonify(error='PINが違います'), 401
    admin = Employee.query.filter_by(role='admin').first()
    if not admin:
        return jsonify(error='管理者が登録されていません'), 500
    session['employee_id'] = admin.id
    session['role'] = 'admin'
    return jsonify(id=admin.id, name=admin.name, role='admin')


@app.get('/api/me')
@login_required
def me():
    emp = db.session.get(Employee, session['employee_id'])
    return jsonify(id=emp.id, employee_no=emp.employee_no, name=emp.name, role=emp.role)


@app.post('/api/logout')
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get('/api/shifts')
@login_required
def shifts():
    rows = (
        db.session.query(Shift, Employee)
        .join(Employee, Shift.employee_id == Employee.id)
        .order_by(Shift.date, Shift.start, Employee.name)
        .all()
    )
    return jsonify([
        {
            'id': s.id,
            'employee_id': e.id,
            'date': s.date,
            'start': s.start,
            'end': s.end,
            'employee': e.name,
        }
        for s, e in rows
    ])


@app.get('/api/requests/me')
@login_required
def my_requests():
    rows = ShiftRequest.query.filter_by(employee_id=session['employee_id']).order_by(ShiftRequest.date).all()
    return jsonify([
        {
            'id': r.id,
            'date': r.date,
            'start': r.start,
            'end': r.end,
            'unavailable': r.unavailable,
            'message': r.message,
            'updated_at': r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ])


@app.post('/api/requests')
@login_required
def save_request():
    data = request.get_json() or {}
    date = str(data.get('date', '')).strip()
    unavailable = bool(data.get('unavailable'))
    start = data.get('start') or None
    end = data.get('end') or None

    if not date:
        return jsonify(error='日付を入力してください'), 400
    if not unavailable and (not start or not end):
        return jsonify(error='勤務希望では開始・終了時刻が必要です'), 400
    if start and end and start >= end:
        return jsonify(error='終了時刻は開始時刻より後にしてください'), 400

    row = ShiftRequest.query.filter_by(employee_id=session['employee_id'], date=date).first()
    if not row:
        row = ShiftRequest(employee_id=session['employee_id'], date=date)
        db.session.add(row)

    row.start = None if unavailable else start
    row.end = None if unavailable else end
    row.unavailable = unavailable
    row.message = str(data.get('message', '')).strip()

    detail = f'{date}: unavailable={unavailable}, {row.start or "-"}-{row.end or "-"}'
    if row.message:
        detail += f', message={row.message}'
    db.session.add(ChangeLog(
        actor_employee_id=session['employee_id'],
        action='shift_request_updated',
        detail=detail,
    ))
    db.session.commit()
    return jsonify(ok=True, id=row.id)


@app.post('/api/attendance-notices')
@login_required
def attendance_notice():
    data = request.get_json() or {}
    kind = data.get('kind')
    if kind not in ('late', 'absence'):
        return jsonify(error='kind must be late or absence'), 400
    notice = AttendanceNotice(
        employee_id=session['employee_id'],
        kind=kind,
        message=str(data.get('message', '')).strip(),
    )
    db.session.add(notice)
    db.session.add(ChangeLog(
        actor_employee_id=session['employee_id'],
        action=f'attendance_{kind}',
        detail=notice.message,
    ))
    db.session.commit()
    return jsonify(ok=True, id=notice.id)


@app.get('/api/admin/dashboard')
@admin_required
def admin_dashboard():
    employees = Employee.query.filter(Employee.role != 'admin').count()
    submitted_employee_ids = {
        row.employee_id for row in db.session.query(ShiftRequest.employee_id).distinct().all()
    }
    notices = (
        db.session.query(AttendanceNotice, Employee)
        .join(Employee, AttendanceNotice.employee_id == Employee.id)
        .order_by(AttendanceNotice.created_at.desc())
        .limit(20)
        .all()
    )
    return jsonify(
        employee_count=employees,
        submitted_count=len(submitted_employee_ids),
        attendance_notice_count=AttendanceNotice.query.count(),
        attendance_notices=[
            {
                'id': n.id,
                'employee': e.name,
                'kind': n.kind,
                'message': n.message,
                'created_at': n.created_at.isoformat(),
            }
            for n, e in notices
        ],
    )


@app.get('/api/admin/employees')
@admin_required
def admin_employees():
    rows = Employee.query.filter(Employee.role != 'admin').order_by(Employee.name).all()
    return jsonify([
        {
            'id': e.id,
            'employee_no': e.employee_no,
            'name': e.name,
            'preferred': e.preferred,
        }
        for e in rows
    ])


@app.get('/api/admin/requests')
@admin_required
def admin_requests():
    rows = (
        db.session.query(ShiftRequest, Employee)
        .join(Employee, ShiftRequest.employee_id == Employee.id)
        .order_by(ShiftRequest.date, Employee.name)
        .all()
    )
    return jsonify([
        {
            'id': r.id,
            'employee_id': e.id,
            'employee': e.name,
            'date': r.date,
            'start': r.start,
            'end': r.end,
            'unavailable': r.unavailable,
            'message': r.message,
            'updated_at': r.updated_at.isoformat() if r.updated_at else None,
        }
        for r, e in rows
    ])


@app.get('/api/admin/change-logs')
@admin_required
def change_logs():
    rows = ChangeLog.query.order_by(ChangeLog.created_at.desc()).limit(100).all()
    return jsonify([
        {
            'action': r.action,
            'detail': r.detail,
            'created_at': r.created_at.isoformat(),
        }
        for r in rows
    ])


@app.post('/api/admin/shifts')
@admin_required
def admin_save_shift():
    data = request.get_json() or {}
    required = ('employee_id', 'date', 'start', 'end')
    if any(data.get(k) in (None, '') for k in required):
        return jsonify(error='employee_id, date, start, end are required'), 400
    if data['start'] >= data['end']:
        return jsonify(error='終了時刻は開始時刻より後にしてください'), 400

    shift = Shift(
        employee_id=int(data['employee_id']),
        date=data['date'],
        start=data['start'],
        end=data['end'],
    )
    db.session.add(shift)
    db.session.add(ChangeLog(
        actor_employee_id=session['employee_id'],
        action='shift_created',
        detail=f'employee={shift.employee_id}, {shift.date} {shift.start}-{shift.end}',
    ))
    db.session.commit()
    return jsonify(id=shift.id, ok=True)


@app.get('/api/health')
def health():
    return jsonify(ok=True, service='ShiftEase API')


with app.app_context():
    db.create_all()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
