from datetime import datetime
from functools import wraps
import os

from flask import Flask, jsonify, request, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///shiftease.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app, supports_credentials=True)
db = SQLAlchemy(app)

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_no = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='employee')
    preferred = db.Column(db.Boolean, default=False)  # 管理者だけが見る「いてほしい枠」用

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
    kind = db.Column(db.String(20), nullable=False)  # late / absence
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

@app.post('/api/login')
def login():
    data = request.get_json() or {}
    emp = Employee.query.filter_by(employee_no=str(data.get('employee_no', '')).strip()).first()
    if not emp:
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
    session['employee_id'] = admin.id
    session['role'] = 'admin'
    return jsonify(name=admin.name, role='admin')

@app.post('/api/logout')
def logout():
    session.clear()
    return jsonify(ok=True)

@app.get('/api/shifts')
@login_required
def shifts():
    rows = db.session.query(Shift, Employee).join(Employee, Shift.employee_id == Employee.id).all()
    return jsonify([{'id': s.id, 'date': s.date, 'start': s.start, 'end': s.end, 'employee': e.name} for s, e in rows])

@app.get('/api/requests/me')
@login_required
def my_requests():
    rows = ShiftRequest.query.filter_by(employee_id=session['employee_id']).all()
    return jsonify([{'id': r.id, 'date': r.date, 'start': r.start, 'end': r.end, 'unavailable': r.unavailable, 'message': r.message} for r in rows])

@app.post('/api/requests')
@login_required
def save_request():
    data = request.get_json() or {}
    date = data.get('date')
    if not date:
        return jsonify(error='date required'), 400
    row = ShiftRequest.query.filter_by(employee_id=session['employee_id'], date=date).first()
    if not row:
        row = ShiftRequest(employee_id=session['employee_id'], date=date)
        db.session.add(row)
    row.start = data.get('start')
    row.end = data.get('end')
    row.unavailable = bool(data.get('unavailable'))
    row.message = data.get('message', '')
    db.session.add(ChangeLog(actor_employee_id=session['employee_id'], action='shift_request_updated', detail=f'{date}: {row.start}-{row.end}, unavailable={row.unavailable}'))
    db.session.commit()
    return jsonify(ok=True)

@app.post('/api/attendance-notices')
@login_required
def attendance_notice():
    data = request.get_json() or {}
    kind = data.get('kind')
    if kind not in ('late', 'absence'):
        return jsonify(error='kind must be late or absence'), 400
    db.session.add(AttendanceNotice(employee_id=session['employee_id'], kind=kind, message=data.get('message', '')))
    db.session.commit()
    return jsonify(ok=True)

@app.get('/api/admin/dashboard')
@admin_required
def admin_dashboard():
    employees = Employee.query.filter(Employee.role != 'admin').count()
    requests = ShiftRequest.query.count()
    notices = AttendanceNotice.query.order_by(AttendanceNotice.created_at.desc()).limit(20).all()
    return jsonify(employee_count=employees, request_count=requests, attendance_notices=[{'kind': n.kind, 'message': n.message, 'created_at': n.created_at.isoformat()} for n in notices])

@app.get('/api/admin/change-logs')
@admin_required
def change_logs():
    rows = ChangeLog.query.order_by(ChangeLog.created_at.desc()).limit(100).all()
    return jsonify([{'action': r.action, 'detail': r.detail, 'created_at': r.created_at.isoformat()} for r in rows])

@app.post('/api/admin/shifts')
@admin_required
def admin_save_shift():
    data = request.get_json() or {}
    shift = Shift(employee_id=int(data['employee_id']), date=data['date'], start=data['start'], end=data['end'])
    db.session.add(shift)
    db.session.add(ChangeLog(actor_employee_id=session['employee_id'], action='shift_created', detail=f"employee={shift.employee_id}, {shift.date} {shift.start}-{shift.end}"))
    db.session.commit()
    return jsonify(id=shift.id, ok=True)

@app.get('/api/health')
def health():
    return jsonify(ok=True, service='ShiftEase API')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
