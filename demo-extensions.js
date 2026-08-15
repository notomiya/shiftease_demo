(()=>{
const ensure=()=>{
  state.reminders=state.reminders||{};
  state.attendanceNotices=state.attendanceNotices||[
    {id:1,employeeId:16,date:'2026-08-16',type:'absence',message:'発熱のため',ack:false,created:'8/15 7:40'}
  ];
  state.notifications=state.notifications||[
    {id:1,title:'シフトが確定しました',body:'8/16〜23分が公開されています',read:false},
    {id:2,title:'次回希望の締切',body:'8/20までに提出してください',read:false}
  ];
  state.swapHistory=state.swapHistory||{};
  save();
};
ensure();

function overlap(a1,a2,b1,b2){return Math.max(a1,b1)<Math.min(a2,b2)}
function h(t){return Number(String(t).slice(0,2))}
function preferenceRate(i){
  const ds=dates.slice(0,8);let total=0,ok=0;
  ds.forEach(dt=>{
    const r=requestFor(i,dt); if(!r)return;
    total++;
    const s=confirmed.find(x=>x.employeeId===i&&x.date===dt);
    if(r.type==='off'){if(!s)ok++;return}
    if(!s)return;
    if(h(s.start)>=h(r.start)&&h(s.end)<=h(r.end))ok++;
  });
  if(!total)return null;
  return Math.round(ok/total*100);
}
window.preferenceRate=preferenceRate;

function reminderText(i){const v=state.reminders[i];return v?`送信済み ${v}`:'未送信'}
window.sendReminder=(i)=>{state.reminders[i]=new Date().toLocaleString('ja-JP',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});state.notifications.push({id:Date.now()+i,title:'シフト希望の提出をお願いします',body:'締切は8/20です',read:false,target:i});save();renderAdminStatus();toast(`${E[i].name}さんへ催促通知を送りました`)};
window.sendAllReminders=()=>{E.forEach((_,i)=>{if(statusById(i)==='未提出')state.reminders[i]=new Date().toLocaleString('ja-JP',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})});save();renderAdminStatus();toast('未提出者へ催促通知を送りました')};

window.approveSwap=(id)=>{
  const x=swaps.find(s=>s.id===id);if(!x||x.status!=='pending')return;
  const shift=confirmed.find(s=>s.id===x.shiftId);if(!shift||x.volunteer==null)return toast('交代情報が不足しています');
  const conflict=confirmed.some(s=>s.employeeId===x.volunteer&&s.date===shift.date&&s.id!==shift.id&&overlap(h(s.start),h(s.end),h(shift.start),h(shift.end)));
  const req=requestFor(x.volunteer,shift.date);
  if(conflict)return toast('立候補者に重複シフトがあります');
  if(req&&req.type==='off')return toast('立候補者はこの日を勤務不可にしています');
  const old=shift.employeeId;shift.employeeId=x.volunteer;x.status='approved';
  state.swapHistory[id]={status:'approved',at:new Date().toLocaleString('ja-JP'),old,new:x.volunteer};
  state.notifications.push({id:Date.now(),title:'シフト交代が承認されました',body:`${E[old].name} → ${E[x.volunteer].name} / ${shift.date} ${shift.start}〜${shift.end}`,read:false});
  save();renderAdminHome();renderAdminCreate();toast('シフト交代を承認し、確定シフトを更新しました');
};
window.rejectSwap=(id)=>{const x=swaps.find(s=>s.id===id);if(!x)return;x.status='rejected';state.swapHistory[id]={status:'rejected',at:new Date().toLocaleString('ja-JP')};save();renderAdminHome();toast('交代申請を却下しました')};

const oldAdminHome=renderAdminHome;
renderAdminHome=function(){oldAdminHome();const root=document.getElementById('admin-home');const pending=swaps.filter(x=>x.status==='pending');const box=document.createElement('div');box.className='card';box.innerHTML=`<div class="sectionHead"><div><h2>シフト交代の承認</h2><div class="muted small">立候補後、店長が確認して確定します</div></div><span class="pill warn">${pending.length}件</span></div>${pending.length?pending.map(x=>{const s=confirmed.find(z=>z.id===x.shiftId);return `<div class="approvalCard"><b>${s.date.slice(5).replace('-','/')} ${s.start}〜${s.end}</b><div class="small muted" style="margin-top:4px">${E[x.requester].name} → ${E[x.volunteer].name}</div><div class="small" style="margin-top:5px">${esc(x.message)}</div><div class="workflowActions"><button class="btn sm" onclick="approveSwap(${x.id})">承認する</button><button class="btn sm ghost" onclick="rejectSwap(${x.id})">却下</button></div></div>`}).join(''):'<div class="okbox">現在、承認待ちはありません。</div>'}`;root.insertBefore(box,root.children[1]||null);
const att=document.createElement('div');att.className='card';att.innerHTML=`<div class="sectionHead"><h2>欠勤・遅刻の記録</h2><span class="pill warn">${state.attendanceNotices.filter(x=>!x.ack).length}件未確認</span></div><div class="list">${state.attendanceNotices.map(n=>`<div class="row issue ${n.ack?'attendanceDone':''}"><div><b>${E[n.employeeId].name}｜${n.type==='late'?'遅刻':'欠勤'}</b><div class="small muted">${n.date} ${n.created}　${esc(n.message||'')}</div></div>${n.ack?'<span class="miniBadge">確認済み</span>':`<button class="btn sm ghost" onclick="ackAttendance(${n.id})">確認済みにする</button>`}</div>`).join('')}</div>`;root.appendChild(att)};
window.ackAttendance=id=>{const n=state.attendanceNotices.find(x=>x.id===id);if(n)n.ack=true;save();renderAdminHome();toast('確認済みにしました')};

renderAdminStatus=function(){const root=document.getElementById('admin-status');root.innerHTML=`<div class="card"><div class="sectionHead"><div><h2>希望提出状況</h2><div class="muted small">8/16〜31分・締切8/20</div></div><button class="btn alt" onclick="sendAllReminders()">未提出者へ一括催促</button></div><div class="tableWrap"><table><thead><tr><th>氏名</th><th>状態</th><th>いつもの希望</th><th>最終更新</th><th>催促</th></tr></thead><tbody>${E.map((e,i)=>`<tr><td><b>${e.name}</b><br><span class="muted">${e.no}</span></td><td><span class="pill ${statusById(i)==='未提出'?'warn':statusById(i)==='更新あり'?'blue':''}">${statusById(i)}</span></td><td>${e.usual}</td><td>${updateById(i)}</td><td>${statusById(i)==='未提出'?`<button class="btn sm ${state.reminders[i]?'ghost':'alt'}" onclick="sendReminder(${i})">${state.reminders[i]?'再催促':'催促する'}</button><div class="remindState ${state.reminders[i]?'remindSent':''}">${reminderText(i)}</div>`:'—'}</td></tr>`).join('')}</tbody></table></div></div>`};

renderAdminStaff=function(){const root=document.getElementById('admin-staff');root.innerHTML=`<div class="card"><div class="sectionHead"><div><h2>従業員管理</h2><div class="muted small">自動シフト作成に使う内部条件・希望通り率</div></div><button class="btn alt" onclick="toast('従業員追加フォームは本番実装時に権限付きで接続します')">従業員を追加</button></div><div class="staffgrid">${E.map((e,i)=>{const rate=preferenceRate(i);const cls=rate==null?'':rate<60?'low':rate<80?'mid':'';return `<div class="staff"><h3>${e.name}</h3><div class="small muted">${e.no}・${e.employment}</div><div><span class="tag">${e.skill}</span><span class="tag">${e.priority}</span></div><div class="small" style="margin-top:8px"><b>通常希望</b><br>${e.usual}</div><div class="staffRate"><div class="staffRateHead"><b>希望通り率</b><b>${rate==null?'—':rate+'%'}</b></div>${rate==null?'':`<div class="rateBar ${cls}"><span style="width:${rate}%"></span></div>`}<div class="rateNote">希望提出済みの日について「勤務不可を避けられた／希望時間内に配置された」割合（8/16〜23のデモ計算）</div></div></div>`}).join('')}</div></div>`};

const oldAttendance=openAttendance;
openAttendance=function(){const root=document.getElementById('emp-home');root.insertAdjacentHTML('afterbegin',`<div class="card" id="attendanceForm"><h2>欠勤・遅刻の記録</h2><div class="warning"><b>当日の欠勤・遅刻は、まず店舗へ電話してください。</b><br><span class="small">この画面は連絡内容を記録するためのものです。</span></div><label>種類</label><select id="attType"><option value="late">遅刻</option><option value="absence">欠勤</option></select><label>到着予定 / メッセージ</label><textarea id="attMessage" placeholder="例：10:30ごろ到着予定です"></textarea><button class="btn full" onclick="submitAttendance()">記録する</button></div>`);scrollTo(0,0)};
window.submitAttendance=()=>{state.attendanceNotices.push({id:Date.now(),employeeId:0,date:'2026-08-16',type:attType.value,message:attMessage.value,ack:false,created:new Date().toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit'})});save();document.getElementById('attendanceForm')?.remove();toast('記録しました。店舗への電話連絡も忘れずに。')};

const oldRenderEmployee=renderEmployee;
renderEmployee=function(e){oldRenderEmployee(e);if(e.id===0){const unread=state.notifications.filter(n=>!n.read&&(n.target==null||n.target===0)).length;notifPill.textContent=`通知 ${unread}件`}}

if(!document.getElementById('ext-ready')){const m=document.createElement('meta');m.id='ext-ready';document.head.appendChild(m)}
})();