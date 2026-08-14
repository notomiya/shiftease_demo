from datetime import datetime, timedelta
from functools import wraps
import os

from flask import Flask, jsonify, request, session, Response
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
INDEX_PATH = os.path.join(BASE_DIR, 'index.html')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///shiftease.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = True

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
    __table_args__ = (db.UniqueConstraint('employee_id', 'date', name='uq_request_employee_date'),)


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


class SwapRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, db.ForeignKey('shift.id'), nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    volunteer_id = db.Column(db.Integer, db.ForeignKey('employee.id'))
    message = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='open')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class StaffingRequirement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)
    start = db.Column(db.String(5), nullable=False)
    end = db.Column(db.String(5), nullable=False)
    required_count = db.Column(db.Integer, nullable=False, default=5)
    __table_args__ = (db.UniqueConstraint('date', 'start', 'end', name='uq_staffing_slot'),)


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


def log(action, detail=''):
    db.session.add(ChangeLog(
        actor_employee_id=session.get('employee_id'),
        action=action,
        detail=detail,
    ))


def inject_frontend(html):
    mobile_css = '''
<style>
@media(max-width:700px){
  .card{padding:18px;overflow:hidden}
  label{max-width:100%;overflow-wrap:anywhere}
  #reqUnavailable{flex:0 0 auto!important}
  label:has(#reqUnavailable){display:flex;align-items:flex-start;gap:10px;line-height:1.45}
  .list>div{flex-direction:column;align-items:flex-start}
  .list>div span{max-width:100%;overflow-wrap:anywhere}
}
.swap-card{background:#f8fbf9;border:1px solid #dceae3;border-radius:14px;padding:14px;margin:10px 0}
.swap-card .meta{font-size:12px;color:#6d7872;margin:5px 0 10px}
.swap-card .status-chip{display:inline-block;border-radius:999px;padding:5px 9px;background:#e8f5ef;color:#16845b;font-size:11px;font-weight:800}
.inline-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.inline-actions button{border:0;border-radius:10px;padding:9px 11px;font-weight:800}
.inline-actions .ok{background:#16845b;color:#fff}.inline-actions .sub{background:#edf2ef;color:#17211c}
.scheduler-result{margin-top:14px}.scheduler-result .day{border-top:1px solid #e5ebe7;padding:12px 0}
</style>
'''
    extra_js = r'''
<script>
async function loadSwaps(){
  try{
    const rows=await api('/api/swaps');
    const target=document.getElementById('swap');
    if(!target)return;
    const card=target.querySelector('.card');
    const html=rows.length?rows.map(r=>`<div class="swap-card"><span class="status-chip">${r.status==='open'?'募集中':r.status==='pending'?'店長承認待ち':r.status}</span><h3>${r.date} ${r.start}〜${r.end}</h3><div class="meta">${escapeHtml(r.requester)}さん｜${escapeHtml(r.message||'メッセージなし')}</div>${r.can_volunteer?`<button class="btn" onclick="volunteerSwap(${r.id})">🙋 代われます！</button>`:''}</div>`).join(''):'<p class="muted">現在、交代募集はありません。</p>';
    card.innerHTML='<h2>シフト交代ボード</h2><p class="muted">気軽に募集 → 代われる人が名乗る → 店長承認、の流れです。</p>'+html;
  }catch(e){console.log(e)}
}
async function volunteerSwap(id){try{await api(`/api/swaps/${id}/volunteer`,{method:'POST'});toast('代われます！を送りました 🙋');await loadSwaps()}catch(e){toast(e.message)}}
async function createSwapFromMyShift(){
  try{
    const shifts=await api('/api/shifts');
    const me=document.getElementById('employeeName').textContent;
    const mine=shifts.filter(s=>s.employee===me);
    if(!mine.length)return toast('交代募集できる確定シフトがありません');
    const s=mine[0];
    const message=prompt(`${s.date} ${s.start}〜${s.end} の交代理由・一言（任意）`)||'';
    await api('/api/swaps',{method:'POST',body:JSON.stringify({shift_id:s.id,message})});
    toast('交代募集を出しました！');await loadSwaps();showSec('swap');
  }catch(e){toast(e.message)}
}
const _oldShowSec=showSec;showSec=function(id){_oldShowSec(id);if(id==='swap')loadSwaps()}
async function loadAdminExtras(){
  try{
    const swaps=await api('/api/admin/swaps');
    const reqs=await api('/api/admin/requirements');
    const admin=document.getElementById('admin');if(!admin)return;
    let box=document.getElementById('adminExtras');
    if(!box){box=document.createElement('div');box.id='adminExtras';admin.appendChild(box)}
    box.innerHTML=`<div class="card"><h2>🔄 交代承認</h2>${swaps.length?swaps.map(r=>`<div class="swap-card"><b>${r.date} ${r.start}〜${r.end}</b><div class="meta">${escapeHtml(r.requester)} → ${escapeHtml(r.volunteer||'募集中')}</div>${r.status==='pending'?`<div class="inline-actions"><button class="ok" onclick="approveSwap(${r.id})">承認する</button><button class="sub" onclick="rejectSwap(${r.id})">却下</button></div>`:''}</div>`).join(''):'<p class="muted">承認待ちはありません。</p>'}</div><div class="card"><h2>👥 必要人数</h2><p class="muted">デモでは時間帯ごとの必要人数を登録できます。</p>${reqs.map(r=>`<div class="shift">${r.date} ${r.start}〜${r.end}：<b>${r.required_count}人</b></div>`).join('')}<button class="btn alt" onclick="addRequirement()">＋ 必要人数を追加</button></div><div class="card"><h2>✨ おすすめシフト案</h2><p class="muted">勤務希望・勤務不可・配置優先・公平性・5連勤警告・必要人数を考慮します。</p><button class="btn" onclick="generateScheduleReal()">おすすめ案を作成</button><div id="schedulerResult" class="scheduler-result"></div></div>`;
  }catch(e){console.log(e)}
}
async function approveSwap(id){try{await api(`/api/admin/swaps/${id}/approve`,{method:'POST'});toast('交代を承認し、確定シフトを更新しました ✓');await loadAdmin();await loadAdminExtras()}catch(e){toast(e.message)}}
async function rejectSwap(id){try{await api(`/api/admin/swaps/${id}/reject`,{method:'POST'});toast('交代申請を却下しました');await loadAdminExtras()}catch(e){toast(e.message)}}
async function addRequirement(){
 const date=prompt('日付（例 2026-08-21）','2026-08-21');if(!date)return;
 const start=prompt('開始','11:00')||'11:00';const end=prompt('終了','15:00')||'15:00';const count=Number(prompt('必要人数','8')||8);
 try{await api('/api/admin/requirements',{method:'POST',body:JSON.stringify({date,start,end,required_count:count})});toast('必要人数を保存しました');await loadAdminExtras()}catch(e){toast(e.message)}
}
async function generateScheduleReal(){
 try{const r=await api('/api/admin/generate-schedule',{method:'POST'});const el=document.getElementById('schedulerResult');el.innerHTML=`<div class="warning"><b>自動作成結果</b><p>候補シフト ${r.assignments.length}件 / 警告 ${r.warnings.length}件</p></div>`+r.assignments.map(a=>`<div class="day"><b>${a.date} ${a.start}〜${a.end}</b><br>${a.employees.map(escapeHtml).join('、')}</div>`).join('')+(r.warnings.length?'<h3>⚠️ 要確認</h3>'+r.warnings.map(w=>`<div class="warning">${escapeHtml(w)}</div>`).join(''):'');}catch(e){toast(e.message)}
}
const _oldLoadEmployee=loadEmployee;loadEmployee=async function(){await _oldLoadEmployee();loadSwaps();const home=document.getElementById('home');if(home&&!document.getElementById('swapQuickBtn')){const g=home.querySelector('.grid');if(g){const b=document.createElement('button');b.id='swapQuickBtn';b.className='quick';b.onclick=createSwapFromMyShift;b.innerHTML='📣<b>交代を募集</b><small>自分の確定シフトから</small>';g.appendChild(b)}}}
const _oldLoadAdmin=loadAdmin;loadAdmin=async function(){await _oldLoadAdmin();await loadAdminExtras()}
</script>
'''
    return html.replace('</head>', mobile_css + '</head>').replace('</body>', extra_js + '</body>')


@app.get('/')
def frontend():
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()
    return Response(inject_frontend(html), mimetype='text/html')


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
    rows = db.session.query(Shift, Employee).join(Employee, Shift.employee_id == Employee.id).order_by(Shift.date, Shift.start, Employee.name).all()
    return jsonify([{'id':s.id,'employee_id':e.id,'date':s.date,'start':s.start,'end':s.end,'employee':e.name} for s,e in rows])


@app.get('/api/requests/me')
@login_required
def my_requests():
    rows = ShiftRequest.query.filter_by(employee_id=session['employee_id']).order_by(ShiftRequest.date).all()
    return jsonify([{'id':r.id,'date':r.date,'start':r.start,'end':r.end,'unavailable':r.unavailable,'message':r.message,'updated_at':r.updated_at.isoformat() if r.updated_at else None} for r in rows])


@app.post('/api/requests')
@login_required
def save_request():
    data = request.get_json() or {}
    date = str(data.get('date', '')).strip(); unavailable = bool(data.get('unavailable'))
    start = data.get('start') or None; end = data.get('end') or None
    if not date: return jsonify(error='日付を入力してください'), 400
    if not unavailable and (not start or not end): return jsonify(error='勤務希望では開始・終了時刻が必要です'), 400
    if start and end and start >= end: return jsonify(error='終了時刻は開始時刻より後にしてください'), 400
    row = ShiftRequest.query.filter_by(employee_id=session['employee_id'], date=date).first()
    if not row:
        row = ShiftRequest(employee_id=session['employee_id'], date=date); db.session.add(row)
    row.start = None if unavailable else start; row.end = None if unavailable else end
    row.unavailable = unavailable; row.message = str(data.get('message', '')).strip()
    log('shift_request_updated', f'{date}: unavailable={unavailable}, {row.start or "-"}-{row.end or "-"}, message={row.message}')
    db.session.commit(); return jsonify(ok=True, id=row.id)


@app.post('/api/attendance-notices')
@login_required
def attendance_notice():
    data = request.get_json() or {}; kind = data.get('kind')
    if kind not in ('late','absence'): return jsonify(error='kind must be late or absence'),400
    notice=AttendanceNotice(employee_id=session['employee_id'],kind=kind,message=str(data.get('message','')).strip())
    db.session.add(notice); log(f'attendance_{kind}', notice.message); db.session.commit()
    return jsonify(ok=True,id=notice.id)


@app.get('/api/swaps')
@login_required
def swaps():
    rows = SwapRequest.query.order_by(SwapRequest.created_at.desc()).all(); out=[]
    for r in rows:
        s=db.session.get(Shift,r.shift_id); requester=db.session.get(Employee,r.requester_id); volunteer=db.session.get(Employee,r.volunteer_id) if r.volunteer_id else None
        if not s: continue
        out.append({'id':r.id,'shift_id':s.id,'date':s.date,'start':s.start,'end':s.end,'requester':requester.name,'volunteer':volunteer.name if volunteer else None,'message':r.message,'status':r.status,'can_volunteer':r.status=='open' and r.requester_id!=session['employee_id']})
    return jsonify(out)


@app.post('/api/swaps')
@login_required
def create_swap():
    data=request.get_json() or {}; s=db.session.get(Shift,int(data.get('shift_id',0) or 0))
    if not s or s.employee_id!=session['employee_id']: return jsonify(error='自分の確定シフトを選んでください'),400
    exists=SwapRequest.query.filter_by(shift_id=s.id).filter(SwapRequest.status.in_(['open','pending'])).first()
    if exists:return jsonify(error='このシフトはすでに交代募集中です'),400
    r=SwapRequest(shift_id=s.id,requester_id=session['employee_id'],message=str(data.get('message','')).strip(),status='open');db.session.add(r);log('swap_created',f'shift={s.id}');db.session.commit();return jsonify(ok=True,id=r.id)


@app.post('/api/swaps/<int:swap_id>/volunteer')
@login_required
def volunteer_swap(swap_id):
    r=db.session.get(SwapRequest,swap_id)
    if not r or r.status!='open':return jsonify(error='この募集は受付中ではありません'),400
    if r.requester_id==session['employee_id']:return jsonify(error='自分の募集には応募できません'),400
    s=db.session.get(Shift,r.shift_id)
    conflict=Shift.query.filter_by(employee_id=session['employee_id'],date=s.date).filter(Shift.start < s.end, Shift.end > s.start).first()
    unavailable=ShiftRequest.query.filter_by(employee_id=session['employee_id'],date=s.date,unavailable=True).first()
    if conflict:return jsonify(error='その時間は別のシフトがあります'),400
    if unavailable:return jsonify(error='その日は勤務不可として提出されています'),400
    r.volunteer_id=session['employee_id'];r.status='pending';log('swap_volunteered',f'swap={r.id}');db.session.commit();return jsonify(ok=True)


@app.get('/api/admin/dashboard')
@admin_required
def admin_dashboard():
    employees=Employee.query.filter(Employee.role!='admin').count(); submitted={x[0] for x in db.session.query(ShiftRequest.employee_id).distinct().all()}
    notices=db.session.query(AttendanceNotice,Employee).join(Employee,AttendanceNotice.employee_id==Employee.id).order_by(AttendanceNotice.created_at.desc()).limit(20).all()
    return jsonify(employee_count=employees,submitted_count=len(submitted),attendance_notice_count=AttendanceNotice.query.count(),attendance_notices=[{'id':n.id,'employee':e.name,'kind':n.kind,'message':n.message,'created_at':n.created_at.isoformat()} for n,e in notices])


@app.get('/api/admin/employees')
@admin_required
def admin_employees():
    rows=Employee.query.filter(Employee.role!='admin').order_by(Employee.name).all();return jsonify([{'id':e.id,'employee_no':e.employee_no,'name':e.name,'preferred':e.preferred} for e in rows])


@app.get('/api/admin/requests')
@admin_required
def admin_requests():
    rows=db.session.query(ShiftRequest,Employee).join(Employee,ShiftRequest.employee_id==Employee.id).order_by(ShiftRequest.date,Employee.name).all()
    return jsonify([{'id':r.id,'employee_id':e.id,'employee':e.name,'date':r.date,'start':r.start,'end':r.end,'unavailable':r.unavailable,'message':r.message,'updated_at':r.updated_at.isoformat() if r.updated_at else None} for r,e in rows])


@app.get('/api/admin/swaps')
@admin_required
def admin_swaps():
    rows=SwapRequest.query.order_by(SwapRequest.created_at.desc()).all();out=[]
    for r in rows:
        s=db.session.get(Shift,r.shift_id);req=db.session.get(Employee,r.requester_id);vol=db.session.get(Employee,r.volunteer_id) if r.volunteer_id else None
        if s:out.append({'id':r.id,'date':s.date,'start':s.start,'end':s.end,'requester':req.name,'volunteer':vol.name if vol else None,'status':r.status,'message':r.message})
    return jsonify(out)


@app.post('/api/admin/swaps/<int:swap_id>/approve')
@admin_required
def approve_swap(swap_id):
    r=db.session.get(SwapRequest,swap_id)
    if not r or r.status!='pending' or not r.volunteer_id:return jsonify(error='承認待ちの申請ではありません'),400
    s=db.session.get(Shift,r.shift_id);old=s.employee_id;s.employee_id=r.volunteer_id;r.status='approved';log('swap_approved',f'shift={s.id}, {old}->{s.employee_id}');db.session.commit();return jsonify(ok=True)


@app.post('/api/admin/swaps/<int:swap_id>/reject')
@admin_required
def reject_swap(swap_id):
    r=db.session.get(SwapRequest,swap_id)
    if not r:return jsonify(error='申請が見つかりません'),404
    r.status='rejected';log('swap_rejected',f'swap={r.id}');db.session.commit();return jsonify(ok=True)


@app.get('/api/admin/requirements')
@admin_required
def get_requirements():
    rows=StaffingRequirement.query.order_by(StaffingRequirement.date,StaffingRequirement.start).all();return jsonify([{'id':r.id,'date':r.date,'start':r.start,'end':r.end,'required_count':r.required_count} for r in rows])


@app.post('/api/admin/requirements')
@admin_required
def save_requirement():
    d=request.get_json() or {};date=str(d.get('date',''));start=str(d.get('start',''));end=str(d.get('end',''));count=int(d.get('required_count',0) or 0)
    if not date or not start or not end or count<1:return jsonify(error='日付・時間・必要人数を入力してください'),400
    r=StaffingRequirement.query.filter_by(date=date,start=start,end=end).first()
    if not r:r=StaffingRequirement(date=date,start=start,end=end);db.session.add(r)
    r.required_count=count;log('staffing_requirement_updated',f'{date} {start}-{end}: {count}');db.session.commit();return jsonify(ok=True,id=r.id)


def consecutive_warning(employee_id,date_str,assigned_dates):
    d=datetime.strptime(date_str,'%Y-%m-%d').date();days=set(assigned_dates.get(employee_id,set()));days.add(d)
    streak=1;cur=d-timedelta(days=1)
    while cur in days:streak+=1;cur-=timedelta(days=1)
    cur=d+timedelta(days=1)
    while cur in days:streak+=1;cur+=timedelta(days=1)
    return streak>=5


@app.post('/api/admin/generate-schedule')
@admin_required
def generate_schedule():
    requirements=StaffingRequirement.query.order_by(StaffingRequirement.date,StaffingRequirement.start).all()
    if not requirements:
        return jsonify(assignments=[],warnings=['必要人数がまだ登録されていません。まず1枠以上登録してください。'])
    employees=Employee.query.filter(Employee.role!='admin').all();load={e.id:0 for e in employees};assigned_dates={e.id:set() for e in employees};assignments=[];warnings=[]
    for slot in requirements:
        candidates=[]
        for e in employees:
            req=ShiftRequest.query.filter_by(employee_id=e.id,date=slot.date).first()
            if req and req.unavailable:continue
            if req and req.start and req.end and not (req.start<=slot.start and req.end>=slot.end):continue
            score=(100 if e.preferred else 0)-(load[e.id]*10)+(20 if req else 0)
            candidates.append((score,e))
        candidates.sort(key=lambda x:(-x[0],x[1].name));chosen=[]
        for _,e in candidates[:slot.required_count]:
            chosen.append(e.name);load[e.id]+=1
            if consecutive_warning(e.id,slot.date,assigned_dates):warnings.append(f'{slot.date}：{e.name}さんが5連勤以上になる可能性があります。')
            assigned_dates[e.id].add(datetime.strptime(slot.date,'%Y-%m-%d').date())
        if len(chosen)<slot.required_count:warnings.append(f'{slot.date} {slot.start}〜{slot.end}：必要{slot.required_count}人に対して候補{len(chosen)}人です。')
        assignments.append({'date':slot.date,'start':slot.start,'end':slot.end,'required_count':slot.required_count,'employees':chosen})
    return jsonify(assignments=assignments,warnings=warnings)


@app.get('/api/admin/change-logs')
@admin_required
def change_logs():
    rows=ChangeLog.query.order_by(ChangeLog.created_at.desc()).limit(100).all();return jsonify([{'action':r.action,'detail':r.detail,'created_at':r.created_at.isoformat()} for r in rows])


@app.post('/api/admin/shifts')
@admin_required
def admin_save_shift():
    d=request.get_json() or {};required=('employee_id','date','start','end')
    if any(d.get(k) in (None,'') for k in required):return jsonify(error='employee_id, date, start, end are required'),400
    if d['start']>=d['end']:return jsonify(error='終了時刻は開始時刻より後にしてください'),400
    s=Shift(employee_id=int(d['employee_id']),date=d['date'],start=d['start'],end=d['end']);db.session.add(s);log('shift_created',f'employee={s.employee_id}, {s.date} {s.start}-{s.end}');db.session.commit();return jsonify(id=s.id,ok=True)


@app.get('/api/health')
def health():
    return jsonify(ok=True,service='ShiftEase API',version='0.3')


with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=True)
