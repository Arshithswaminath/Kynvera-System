(function(){
let PROJECT_ID = null;
let onBackCb = null;
let project = null;
let quotations = [];
let followups = [];
let activities = [];
let contacts = [];
let owners = [];
let summary = {};
let pendingApproveId = null;
let meUser = null;
let canPrepQuotes = false;

function canPrepareQuotations(){
  if(canPrepQuotes) return true;
  if(!meUser) return false;
  if(meUser.role === 'admin') return true;
  const d=(meUser.designation||'').trim().toLowerCase();
  if(d==='business_development') return true;
  return !!(meUser.access_quotations);
}

function gatePrepareOrToast(){
  if(canPrepareQuotations()) return true;
  pdToast('You do not have permission to prepare quotations');
  return false;
}

function esc(t){
  if(t===null||t===undefined)return'';
  const d=document.createElement('div');d.textContent=String(t);return d.innerHTML;
}
function money(n){
  const v=Number(n||0);
  return 'AED '+v.toLocaleString(undefined,{maximumFractionDigits:0});
}
function moneyAed(n){
  const v=Number(n||0);
  return 'AED '+v.toLocaleString(undefined,{maximumFractionDigits:2});
}
/** Date + time in 24h: YYYY-MM-DD HH:mm (local). Treats naive API timestamps as UTC. */
function fmtDateTime24(iso){
  if(!iso) return '—';
  const s=String(iso);
  const d=new Date(/Z$|[+-]\d{2}:?\d{2}$/.test(s)?s:s+'Z');
  if(isNaN(d.getTime())) return '—';
  const p=n=>String(n).padStart(2,'0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function statusSlug(s){return String(s||'active').toLowerCase().replace(/\s+/g,'_').replace(/[^a-z0-9_]/g,'')}
function statusLabel(s){
  const raw=String(s||'active').trim();
  if(!raw) return 'Active';
  return raw.replace(/[_-]+/g,' ').replace(/\b\w/g,c=>c.toUpperCase());
}
function prioritySlug(p){return p==='high'?'high':p==='low'?'low':'med'}
function authHeaders(){
  const token=localStorage.getItem('access_token');
  return {'Content-Type':'application/json','Authorization':'Bearer '+token};
}
async function apiGet(url){
  const r=await fetch(url,{headers:authHeaders()});
  const j=await r.json().catch(()=>({}));
  if(!r.ok||j.success===false) throw new Error(j.error||'Request failed');
  return j.data||j;
}
async function apiPost(url,payload){
  const r=await fetch(url,{method:'POST',headers:authHeaders(),body:JSON.stringify(payload||{})});
  const j=await r.json().catch(()=>({}));
  if(!r.ok||j.success===false) throw new Error(j.error||'Request failed');
  return j.data||j;
}
async function apiPut(url,payload){
  const r=await fetch(url,{method:'PUT',headers:authHeaders(),body:JSON.stringify(payload||{})});
  const j=await r.json().catch(()=>({}));
  if(!r.ok||j.success===false) throw new Error(j.error||'Request failed');
  return j.data||j;
}
async function apiDelete(url){
  const r=await fetch(url,{method:'DELETE',headers:authHeaders()});
  const j=await r.json().catch(()=>({}));
  if(!r.ok||j.success===false) throw new Error(j.error||'Request failed');
  return j.data||j;
}

let _tt;
function pdToast(msg){
  const t=document.getElementById('pd-toast');
  if(!t)return;
  t.textContent=msg;
  t.style.transform='translateY(0)';
  t.style.opacity='1';
  clearTimeout(_tt);
  _tt=setTimeout(()=>{t.style.transform='translateY(70px)';t.style.opacity='0'},2800);
}

function dueMeta(iso){
  if(!iso) return {label:'No due date',cls:'later'};
  const due=new Date(iso);
  if(Number.isNaN(due.getTime())) return {label:String(iso).slice(0,10),cls:'later'};
  const now=new Date();
  const dayMs=24*60*60*1000;
  const a=new Date(now.getFullYear(),now.getMonth(),now.getDate());
  const b=new Date(due.getFullYear(),due.getMonth(),due.getDate());
  const delta=Math.floor((b-a)/dayMs);
  if(delta<0) return {label:`Overdue · ${Math.abs(delta)}d`,cls:'overdue'};
  if(delta===0) return {label:'Today',cls:'today'};
  if(delta===1) return {label:'Tomorrow',cls:'soon'};
  if(delta<=7) return {label:`In ${delta}d`,cls:'soon'};
  return {label:due.toLocaleDateString(),cls:'later'};
}

function kv(rows){
  return rows.map(([k,v,muted])=>`<div class="pd-kv-row"><div class="pd-kv-k">${esc(k)}</div><div class="pd-kv-v${muted?' muted':''}">${v}</div></div>`).join('');
}

function pdShowPanel(name,btn){
  // Leaving quotations, or re-clicking Quotations nav, returns to the list
  if(name!=='quotations' || btn) pdCloseQuote();
  document.querySelectorAll('.pd-panel').forEach(p=>p.classList.toggle('active',p.id===`pd-panel-${name}`));
  document.querySelectorAll('.pd-nav-item').forEach(b=>b.classList.toggle('active',b===btn||b.dataset.panel===name));
  if(btn&&!btn.classList.contains('pd-nav-item')){
    const match=document.querySelector(`.pd-nav-item[data-panel="${name}"]`);
    if(match) match.classList.add('active');
  }
}

function pdShowQuoteEditor(show){
  const list=document.getElementById('pdQuoteListView');
  const editor=document.getElementById('pdQuoteEditor');
  if(list) list.hidden=!!show;
  if(editor) editor.hidden=!show;
}

function renderHero(){
  document.getElementById('pdHeroTitle').textContent=project.name||'Untitled project';
  document.getElementById('pdHeroSub').textContent=project.company||project.co||'—';
  const st=statusSlug(project.status);
  const chips=[
    `<span class="pd-status-badge pd-sb-${esc(st)}">${esc(statusLabel(project.status))}</span>`,
    `<span class="pd-chip">Stage · ${esc(statusLabel(project.stage||'prospecting'))}</span>`,
    `<span class="pd-priority pd-pr-${prioritySlug(project.priority)}">${esc((project.priority||'med').toUpperCase())}</span>`,
    `<span class="pd-chip">Owner · ${esc(project.owner||'Unassigned')}</span>`,
  ];
  document.getElementById('pdHeroChips').innerHTML=chips.join('');
  const promote=document.getElementById('pdPromoteBtn');
  if(promote){
    const won=(project.status||'').toLowerCase()==='won';
    promote.style.display=won?'none':'';
  }
  document.title=`${project.name||'Project'} — Business Development | Kynvera`;
}

function renderOverview(){
  const pct=Math.max(0,Math.min(100,Number(project.progress||0)));
  document.getElementById('pdTileIdentity').innerHTML=kv([
    ['Project',esc(project.name||'—')],
    ['Company',esc(project.company||project.co||'—')],
    ['Owner',esc(project.owner||'Unassigned')],
    ['Created',esc(project.createdAt?new Date(project.createdAt).toLocaleString():'—'),!project.createdAt],
    ['Updated',esc(project.updatedAt?new Date(project.updatedAt).toLocaleString():'—'),!project.updatedAt],
  ]);
  document.getElementById('pdTilePipeline').innerHTML=kv([
    ['Stage',esc(statusLabel(project.stage||'prospecting'))],
    ['Status',`<span class="pd-status-badge pd-sb-${esc(statusSlug(project.status))}">${esc(statusLabel(project.status))}</span>`],
    ['Priority',`<span class="pd-priority pd-pr-${prioritySlug(project.priority)}">${esc((project.priority||'med').toUpperCase())}</span>`],
    ['Progress',`<div class="pd-progress"><div class="pd-progress-label"><span>${pct}%</span></div><div class="pd-progress-bar"><div class="pd-progress-fill" style="width:${pct}%"></div></div></div>`],
  ]);
  document.getElementById('pdTileCommercial').innerHTML=kv([
    ['Deal value',esc(project.value||money(project.valueAmount))],
    ['Next action',esc(project.next||'No action'),!(project.next&&project.next!=='No action')],
    ['Expected close',esc(project.expectedCloseDate||project.nextDate||'—'),!(project.expectedCloseDate||project.nextDate)],
  ]);
  const latestNo=summary.latest_quote_no||'—';
  const latestSt=summary.latest_quote_status?statusLabel(summary.latest_quote_status):'—';
  document.getElementById('pdTileQuotes').innerHTML=kv([
    ['Quote count',String(summary.quote_count||0)],
    ['Quoted total',moneyAed(summary.quoted_total||0)],
    ['Latest quote',esc(latestNo)],
    ['Latest status',esc(latestSt),!summary.latest_quote_status],
  ]);
}

function renderContact(){
  document.getElementById('pdPrimaryContact').innerHTML=kv([
    ['Name',esc(project.primaryContactName||'—'),!project.primaryContactName],
    ['Email',project.primaryContactEmail?`<a href="mailto:${esc(project.primaryContactEmail)}">${esc(project.primaryContactEmail)}</a>`:'—',!project.primaryContactEmail],
    ['Company',esc(project.company||project.co||'—')],
  ]);
  const grid=document.getElementById('pdContactsGrid');
  if(!contacts.length){
    grid.innerHTML='<div class="pd-empty" style="grid-column:1/-1">No other company contacts on file.</div>';
    return;
  }
  grid.innerHTML=contacts.map(c=>`<div class="pd-contact-card">
    <div class="pd-cc-head">
      <div class="pd-cc-top" style="margin-bottom:0"><div class="pd-cc-av">${esc(c.initials||'NA')}</div>
        <div><div class="pd-cc-name">${esc(c.name)}</div><div class="pd-cc-title">${esc(c.title||'Contact')}</div></div>
      </div>
      ${c.id?`<button type="button" class="pd-btn pd-btn-ghost pd-btn-danger" style="min-height:44px;padding:6px 10px;font-size:12px" onclick="pdDeleteContact(${Number(c.id)})">Delete</button>`:''}
    </div>
    <div class="pd-cc-line">${esc(c.email||'No email')}</div>
    <div class="pd-cc-line">${esc(c.phone||'')}</div>
  </div>`).join('');
}

function renderQuotes(){
  const tb=document.getElementById('pdQuotesTbody');
  const countEl=document.getElementById('pdNavQuoteCount');
  if(countEl) countEl.textContent=String(quotations.length);
  const canPrep=canPrepareQuotations();
  document.querySelectorAll('[data-pd-quote-create]').forEach(el=>{
    el.style.display=canPrep?'':'none';
  });
  if(!quotations.length){
    tb.innerHTML=`<tr><td colspan="6" class="pd-empty">${canPrep?'No quotations yet. Create one for this project.':'No quotations yet.'}</td></tr>`;
    return;
  }
  tb.innerHTML=quotations.map(q=>{
    const created=fmtDateTime24(q.created_at);
    const submitted=q.submitted_at?fmtDateTime24(q.submitted_at):null;
    const st=q.status||'draft';
    const editable=canPrep && (st==='draft'||st==='sent'||st==='rejected');
    const cancellable=canPrep && (st==='draft'||st==='sent'||st==='pending_approval'||st==='rejected');
    const pending=st==='pending_approval';
    const approved=st==='approved';
    const hasLpo=!!(q.lpo_url||q.lpo_filename);
    return `<tr>
    <td style="font-weight:700">${esc(q.ref_no||q.quote_no)}</td>
    <td>${esc(q.company_name)}</td>
    <td><span class="pd-status-badge pd-sb-${esc(statusSlug(st))}">${esc(statusLabel(st))}</span></td>
    <td>${moneyAed(q.grand_total)}</td>
    <td class="pd-quote-when">
      <div><span class="pd-quote-when-k">Created</span> ${esc(created)}</div>
      ${submitted?`<div><span class="pd-quote-when-k">Submitted</span> ${esc(submitted)}</div>`:`<div class="muted">Not submitted</div>`}
      ${q.status==='cancelled'&&q.rejection_notes?`<div class="muted">Cancel: ${esc(q.rejection_notes)}</div>`:''}
    </td>
    <td class="actions">
      <button type="button" class="pd-btn pd-btn-ghost" style="min-height:44px;padding:6px 10px;font-size:12px" onclick="pdQuotePdf(${q.id})">PDF</button>
      ${editable?`<button type="button" class="pd-btn pd-btn-ghost" style="min-height:44px;padding:6px 10px;font-size:12px;margin-left:4px" onclick="pdQuoteEdit(${q.id})">Edit</button>`:''}
      ${editable?`<button type="button" class="pd-btn pd-btn-primary" style="min-height:44px;padding:6px 10px;font-size:12px;margin-left:4px" onclick="pdQuoteSubmit(${q.id})">Submit</button>`:''}
      ${pending?`<button type="button" class="pd-btn pd-btn-primary" style="min-height:44px;padding:6px 10px;font-size:12px;margin-left:4px" onclick="pdQuoteApprove(${q.id})">Approve</button>`:''}
      ${pending?`<button type="button" class="pd-btn pd-btn-ghost pd-btn-danger" style="min-height:44px;padding:6px 10px;font-size:12px;margin-left:4px" onclick="pdQuoteReject(${q.id})">Reject</button>`:''}
      ${approved&&!hasLpo?`<button type="button" class="pd-btn pd-btn-ghost" style="min-height:44px;padding:6px 10px;font-size:12px;margin-left:4px" onclick="pdQuoteAttachLpo(${q.id})">Attach LPO</button>`:''}
      ${hasLpo?`<button type="button" class="pd-btn pd-btn-ghost" style="min-height:44px;padding:6px 10px;font-size:12px;margin-left:4px" onclick="pdQuoteDownloadLpo(${q.id})">LPO</button>`:''}
      ${approved&&hasLpo?`<button type="button" class="pd-btn pd-btn-ghost" style="min-height:44px;padding:6px 10px;font-size:12px;margin-left:4px" onclick="pdQuoteAttachLpo(${q.id})">Replace LPO</button>`:''}
      ${cancellable?`<button type="button" class="pd-btn pd-btn-ghost" style="min-height:44px;padding:6px 10px;font-size:12px;margin-left:4px;color:#6b7280" onclick="pdQuoteCancel(${q.id})">Cancel</button>`:''}
    </td>
  </tr>`;
  }).join('');
}

function renderFollowups(){
  const body=document.getElementById('pdFollowupsBody');
  const countEl=document.getElementById('pdNavFuCount');
  if(countEl) countEl.textContent=String(summary.open_followups!=null?summary.open_followups:followups.filter(f=>(f.status||'open')!=='done').length);
  if(!followups.length){
    body.innerHTML='<div class="pd-empty">No follow-ups for this project yet.</div>';
    return;
  }
  body.innerHTML=`<div class="pd-fu-list">${followups.map(f=>{
    const d=dueMeta(f.date);
    const done=(f.status||'open')==='done';
    const btn=done
      ? `<button type="button" class="pd-btn pd-btn-ghost" style="min-height:44px;padding:6px 10px;font-size:12px" onclick="pdSetFollowupStatus(${Number(f.id||0)},'open')">Reopen</button>`
      : `<button type="button" class="pd-btn pd-btn-primary" style="min-height:44px;padding:6px 10px;font-size:12px" onclick="pdSetFollowupStatus(${Number(f.id||0)},'done')">Mark done</button>`;
    return `<div class="pd-fu-item"><div class="pd-fu-ico">${f.icon||'📝'}</div>
      <div><div class="pd-fu-title${done?' done':''}">${esc(f.title)}</div>
      <div class="pd-fu-meta">${esc(f.co||'')} <span class="pd-fu-date ${d.cls}">${esc(d.label)}</span>
      · ${esc(statusLabel(f.status||'open'))}</div></div>
      <div class="pd-fu-actions">${f.id?btn:''}</div></div>`;
  }).join('')}</div>`;
}

function renderActivity(){
  const body=document.getElementById('pdActivityBody');
  if(!activities.length){
    body.innerHTML='<div class="pd-empty">No activity recorded yet.</div>';
    return;
  }
  body.innerHTML=`<div class="pd-act-list">${activities.map(a=>`<div class="pd-act-item">
    <div class="pd-act-ico" style="background:${esc(a.bg||'#fff4ef')}">${a.icon||'📝'}</div>
    <div><div class="pd-act-title">${esc(a.title)}</div>
    <div class="pd-fu-meta">${esc(a.desc||'')}</div>
    <div class="pd-act-meta">${esc(a.time?fmtDateTime24(a.time):'')} ${a.badge?`· ${esc(a.badge)}`:''}</div></div>
  </div>`).join('')}</div>`;
}

function renderNotes(){
  const notes=(project.notes||'').trim();
  document.getElementById('pdNotesBody').textContent=notes||'No notes yet. Use Edit details to add context.';
  if(!notes) document.getElementById('pdNotesBody').classList.add('muted');
  else document.getElementById('pdNotesBody').classList.remove('muted');
}

function populateOwnerSelect(){
  const sel=document.getElementById('pdFldOwnerUser');
  if(!sel) return;
  const cur=sel.value;
  sel.innerHTML='<option value="">Me (default)</option>'+(owners||[]).map(o=>`<option value="${o.id}">${esc(o.name)}</option>`).join('');
  if(cur) sel.value=cur;
}

function renderAll(){
  renderHero();
  renderOverview();
  renderContact();
  renderQuotes();
  renderFollowups();
  renderActivity();
  renderNotes();
  populateOwnerSelect();
}

async function loadProject(){
  const loading=document.getElementById('pdLoading');
  const err=document.getElementById('pdError');
  const ws=document.getElementById('pdWorkspace');
  try{
    const [data, meData] = await Promise.all([
      apiGet(`/api/admin/bd/projects/${PROJECT_ID}`),
      apiGet('/api/auth/me').catch(()=>({})),
    ]);
    meUser = meData.user || meData || meUser;
    canPrepQuotes = !!(data.can_prepare_quotations);
    project=data.project||null;
    if(!project) throw new Error('Project not found');
    quotations=data.quotations||[];
    followups=data.followups||[];
    activities=data.activities||[];
    contacts=data.contacts||[];
    owners=data.owners||[];
    summary=data.summary||{};
    loading.style.display='none';
    err.style.display='none';
    ws.style.display='block';
    renderAll();
  }catch(e){
    loading.style.display='none';
    ws.style.display='none';
    err.style.display='block';
    err.textContent=e.message||'Failed to load project';
  }
}

function pdOpenEdit(){
  if(!project) return;
  document.getElementById('pdFldName').value=project.name||'';
  document.getElementById('pdFldCompany').value=project.company||project.co||'';
  document.getElementById('pdFldValue').value=project.valueAmount!=null?project.valueAmount:0;
  document.getElementById('pdFldStage').value=(project.stage||'prospecting').toLowerCase();
  document.getElementById('pdFldPriority').value=prioritySlug(project.priority);
  document.getElementById('pdFldStatus').value=statusSlug(project.status)||'active';
  document.getElementById('pdFldProgress').value=project.progress!=null?project.progress:0;
  document.getElementById('pdFldNextAction').value=(project.next&&project.next!=='No action')?project.next:'';
  document.getElementById('pdFldOwner').value=project.owner||'';
  document.getElementById('pdFldOwnerUser').value=project.ownerUserId||project.owner_user_id||'';
  document.getElementById('pdFldCloseDate').value=(project.expectedCloseDate||'').slice(0,10);
  document.getElementById('pdFldContactName').value=project.primaryContactName||'';
  document.getElementById('pdFldContactEmail').value=project.primaryContactEmail||'';
  document.getElementById('pdFldNotes').value=project.notes||'';
  document.getElementById('pdEditModal').classList.add('open');
}
function pdCloseEdit(){document.getElementById('pdEditModal').classList.remove('open')}

async function pdSaveProject(){
  const payload={
    name:(document.getElementById('pdFldName').value||'').trim(),
    company:(document.getElementById('pdFldCompany').value||'').trim(),
    value_amount:Number(document.getElementById('pdFldValue').value||0),
    stage:document.getElementById('pdFldStage').value,
    priority:document.getElementById('pdFldPriority').value,
    status:document.getElementById('pdFldStatus').value,
    progress:Number(document.getElementById('pdFldProgress').value||0),
    next_action:(document.getElementById('pdFldNextAction').value||'').trim()||null,
    owner:(document.getElementById('pdFldOwner').value||'').trim()||null,
    owner_user_id:document.getElementById('pdFldOwnerUser').value||null,
    expected_close_date:document.getElementById('pdFldCloseDate').value||null,
    primary_contact_name:(document.getElementById('pdFldContactName').value||'').trim()||null,
    primary_contact_email:(document.getElementById('pdFldContactEmail').value||'').trim()||null,
    notes:(document.getElementById('pdFldNotes').value||'').trim()||null,
  };
  if(!payload.name||!payload.company){pdToast('Project name and company are required');return;}
  const btn=document.getElementById('pdEditSaveBtn');
  if(btn){btn.disabled=true;btn.textContent='Saving…';}
  try{
    await apiPut(`/api/admin/bd/projects/${PROJECT_ID}`,payload);
    pdCloseEdit();
    pdToast('Project updated');
    await loadProject();
  }catch(e){pdToast(e.message||'Save failed');}
  finally{if(btn){btn.disabled=false;btn.textContent='Save Changes';}}
}

const QT_DEFAULTS={
  intro:'With reference to our discussion, we are pleased to quote for the following:',
  notes:'VAT excluded in the quote.\nPrices may change at any time; new prices apply unless the client confirms and the advance payment is received.',
  exclusions:'Any civil work is excluded and remains the client\'s scope.\nAny additional requirement or variation will be quoted separately.',
  terms:'Validity : 10 Days\nDelivery : as per stock availability at the time of approval and advance payment clearance\nPayment : 50% advance, 50% after completion\nPlease confirm your acceptance to enable us to proceed, assuring you of our best services at all times.',
  signoffLabel:'Thanks & Regards',
  sigName:'Business Development',
  sigEmail:'',
  sigPhone:'',
};

function pdQuoteCollectItems(){
  const rows=[...document.querySelectorAll('#pdQuoteItemsBody tr')];
  return rows.map(tr=>{
    const desc=(tr.querySelector('[data-q-desc]')?.value||'').trim();
    const qty=Number(tr.querySelector('[data-q-qty]')?.value||0);
    const price=Number(tr.querySelector('[data-q-price]')?.value||0);
    return {description:desc,quantity:qty||1,unit:'',unit_price:price};
  }).filter(it=>it.description);
}

function pdQuoteRefreshTotals(){
  const items=pdQuoteCollectItems();
  const sub=items.reduce((s,it)=>s+(Number(it.quantity)||0)*(Number(it.unit_price)||0),0);
  const disc=Number(document.getElementById('pdQuoteDiscount')?.value||0);
  const net=Math.max(sub-disc,0);
  const el=document.getElementById('pdQuoteTotalsPreview');
  if(el) el.textContent=`Total: AED ${sub.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})} · After discount: AED ${net.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})}+VAT`;
  [...document.querySelectorAll('#pdQuoteItemsBody tr')].forEach((tr,i)=>{
    const n=tr.querySelector('[data-q-n]');
    if(n) n.textContent=String(i+1);
    const qty=Number(tr.querySelector('[data-q-qty]')?.value||0);
    const price=Number(tr.querySelector('[data-q-price]')?.value||0);
    const tot=tr.querySelector('[data-q-total]');
    if(tot) tot.textContent=(qty*price).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
  });
}

function pdQuoteAddRow(item){
  const body=document.getElementById('pdQuoteItemsBody');
  if(!body) return;
  const tr=document.createElement('tr');
  const desc=esc(item&&item.description||'');
  const qty=item&&item.quantity!=null?item.quantity:1;
  const price=item&&item.unit_price!=null?item.unit_price:0;
  tr.innerHTML=`<td data-q-n></td>
    <td><input data-q-desc type="text" value="${desc}" placeholder="Description"></td>
    <td><input data-q-qty type="number" min="0" step="any" value="${qty}"></td>
    <td><input data-q-price type="number" min="0" step="0.01" value="${price}"></td>
    <td data-q-total style="text-align:right;font-weight:600">0.00</td>
    <td><button type="button" class="pd-btn pd-btn-ghost" style="min-height:30px;padding:2px 8px;font-size:11px" data-q-del>✕</button></td>`;
  body.appendChild(tr);
  tr.querySelectorAll('input').forEach(inp=>inp.addEventListener('input',pdQuoteRefreshTotals));
  tr.querySelector('[data-q-del]').addEventListener('click',()=>{tr.remove();pdQuoteRefreshTotals();});
  pdQuoteRefreshTotals();
}

function pdQuoteFillDefaults(q){
  const set=(id,v)=>{const el=document.getElementById(id);if(el) el.value=v==null?'':v;};
  set('pdQuoteEditId',q&&q.id||'');
  set('pdQuoteProjectName',project.name||'');
  set('pdQuoteCompany',(q&&q.company_name)||project.company||project.co||'');
  set('pdQuoteKindAttn',(q&&q.kind_attn)||project.primaryContactName||'');
  set('pdQuoteTel',(q&&q.client_tel)||'');
  set('pdQuoteSubject',(q&&q.subject)||(project.name?`Price for ${project.name}`:''));
  set('pdQuoteSiteName',(q&&q.project_name)||project.name||'');
  set('pdQuoteRefNo',(q&&q.ref_no)||'');
  set('pdQuoteDiscount',(q&&q.discount_amount)!=null?q.discount_amount:0);
  set('pdQuoteIntro',(q&&q.intro_text)||QT_DEFAULTS.intro);
  set('pdQuoteNotes',(q&&q.notes_text)||QT_DEFAULTS.notes);
  set('pdQuoteExclusions',(q&&q.exclusions_text)||QT_DEFAULTS.exclusions);
  set('pdQuoteTerms',(q&&q.terms_text)||QT_DEFAULTS.terms);
  const body=document.getElementById('pdQuoteItemsBody');
  if(body) body.innerHTML='';
  const items=(q&&q.items&&q.items.length)?q.items:[{description:(project.name||'Services')+' — Services',quantity:1,unit_price:project.valueAmount||0}];
  items.forEach(it=>pdQuoteAddRow(it));
  const disc=document.getElementById('pdQuoteDiscount');
  if(disc&&!disc._qtBound){disc._qtBound=true;disc.addEventListener('input',pdQuoteRefreshTotals);}
}

function pdOpenQuote(){
  if(!project) return;
  if(!gatePrepareOrToast()) return;
  pdShowPanel('quotations');
  document.getElementById('pdQuoteModalTitle').textContent='New Quotation';
  document.getElementById('pdQuoteModalSub').textContent=`For project: ${project.name||'Untitled'}`;
  document.getElementById('pdQuoteSaveBtn').textContent='Save Quotation';
  pdQuoteFillDefaults(null);
  pdShowQuoteEditor(true);
  try{document.getElementById('pdQuoteEditor').scrollIntoView({behavior:'smooth',block:'start'});}catch(_){}
}
async function pdQuoteEdit(id){
  if(!gatePrepareOrToast()) return;
  try{
    const data=await apiGet(`/api/admin/bd/quotations/${id}`);
    const q=data.quotation;
    if(!q) throw new Error('Quote not found');
    pdShowPanel('quotations');
    document.getElementById('pdQuoteModalTitle').textContent='Edit Quotation';
    document.getElementById('pdQuoteModalSub').textContent=q.ref_no||q.quote_no||'';
    document.getElementById('pdQuoteSaveBtn').textContent='Update Quotation';
    pdQuoteFillDefaults(q);
    pdShowQuoteEditor(true);
    try{document.getElementById('pdQuoteEditor').scrollIntoView({behavior:'smooth',block:'start'});}catch(_){}
  }catch(e){pdToast(e.message||'Failed to load quote');}
}
function pdCloseQuote(){
  pdShowQuoteEditor(false);
}

function pdQuotePayload(){
  const company=(document.getElementById('pdQuoteCompany').value||'').trim();
  const items=pdQuoteCollectItems();
  return {
    company_name:company,
    contact_name:(document.getElementById('pdQuoteKindAttn').value||'').trim()||project.primaryContactName||'',
    contact_email:project.primaryContactEmail||'',
    kind_attn:(document.getElementById('pdQuoteKindAttn').value||'').trim(),
    client_tel:(document.getElementById('pdQuoteTel').value||'').trim(),
    subject:(document.getElementById('pdQuoteSubject').value||'').trim(),
    project_name:(document.getElementById('pdQuoteSiteName').value||'').trim(),
    ref_no:(document.getElementById('pdQuoteRefNo').value||'').trim()||undefined,
    discount_amount:Number(document.getElementById('pdQuoteDiscount').value||0),
    intro_text:(document.getElementById('pdQuoteIntro').value||'').trim(),
    notes_text:(document.getElementById('pdQuoteNotes').value||'').trim(),
    exclusions_text:(document.getElementById('pdQuoteExclusions').value||'').trim(),
    terms_text:(document.getElementById('pdQuoteTerms').value||'').trim(),
    owner_user_id:project.ownerUserId||project.owner_user_id||undefined,
    items,
    tax_pct:5,
  };
}

async function pdSaveQuote(){
  if(!gatePrepareOrToast()) return;
  const payload=pdQuotePayload();
  if(!payload.company_name){pdToast('Client name is required');return;}
  if(!payload.items.length){pdToast('Add at least one line item');return;}
  const editId=Number(document.getElementById('pdQuoteEditId').value||0);
  const btn=document.getElementById('pdQuoteSaveBtn');
  if(btn){btn.disabled=true;btn.textContent=editId?'Updating…':'Saving…';}
  try{
    if(editId){
      await apiPut(`/api/admin/bd/quotations/${editId}`,payload);
      pdToast('Quotation updated');
    }else{
      await apiPost('/api/admin/bd/quotations',Object.assign({bd_project_id:PROJECT_ID},payload));
      pdToast('Quotation created');
    }
    pdCloseQuote();
    await loadProject();
    pdShowPanel('quotations');
  }catch(e){pdToast(e.message||'Failed');}
  finally{if(btn){btn.disabled=false;btn.textContent=editId?'Update Quotation':'Save Quotation';}}
}

function pdEnsureSigModal(cb){
  if(!window.InjaazSignatureModal){
    pdToast('Signature pad failed to load — refresh the page');
    return;
  }
  // Load saved profile signature for "Use Saved"
  try{
    const token=localStorage.getItem('access_token');
    fetch('/api/auth/me',{headers:{Authorization:'Bearer '+(token||'')}})
      .then(r=>r.ok?r.json():null)
      .then(data=>{
        const saved=data&&data.user&&data.user.default_signature;
        if(saved) InjaazSignatureModal.setSavedSignature(saved);
      }).catch(()=>{});
  }catch(_){}
  cb();
}

async function pdQuotePdf(id){
  const token=localStorage.getItem('access_token');
  try{
    const r=await fetch(`/api/admin/bd/quotations/${id}/pdf`,{headers:{Authorization:'Bearer '+token}});
    if(!r.ok) throw new Error('PDF failed');
    const blob=await r.blob();
    window.open(URL.createObjectURL(blob),'_blank');
  }catch(e){pdToast(e.message||'PDF failed');}
}

let _pdSignoffDraft = null;

function pdCloseSignoffModal(){
  const veil=document.getElementById('pdSignoffModal');
  if(veil) veil.classList.remove('open');
  _pdSignoffDraft=null;
}

function pdReadSignoffForm(){
  return {
    signoff_label:(document.getElementById('pdSignoffLabel').value||'').trim()||QT_DEFAULTS.signoffLabel,
    signatory_name:(document.getElementById('pdSignoffName').value||'').trim()||QT_DEFAULTS.sigName,
    signatory_email:(document.getElementById('pdSignoffEmail').value||'').trim()||QT_DEFAULTS.sigEmail,
    signatory_phone:(document.getElementById('pdSignoffPhone').value||'').trim()||QT_DEFAULTS.sigPhone,
  };
}

function pdContinueSignoffToSign(){
  const id=Number(document.getElementById('pdSignoffQuoteId').value||0);
  if(!id) return;
  _pdSignoffDraft=pdReadSignoffForm();
  // Hide modal without clearing _pdSignoffDraft (pdCloseSignoffModal would wipe it)
  const veil=document.getElementById('pdSignoffModal');
  if(veil) veil.classList.remove('open');
  pdEnsureSigModal(()=>{
    InjaazSignatureModal.open({
      title:'Sign & submit quotation',
      confirmLabel:'I confirm Thanks & Regards / NOTE / EXCLUSION / TERMS as shown on this quotation.',
      onApply: async function(dataUrl){
        try{
          const signoff=_pdSignoffDraft||{};
          await apiPost(`/api/admin/bd/quotations/${id}/submit`,Object.assign({
            signature:dataUrl,
            confirm_thanks_remarks:true,
          }, signoff));
          _pdSignoffDraft=null;
          pdToast('Quotation submitted for approval');
          await loadProject();
        }catch(e){pdToast(e.message||'Submit failed');}
      }
    });
  });
}

async function pdQuoteSubmit(id){
  if(!gatePrepareOrToast()) return;
  const veil=document.getElementById('pdSignoffModal');
  if(!veil){
    pdToast('Sign-off dialog failed to load — refresh the page');
    return;
  }
  try{
    const data=await apiGet(`/api/admin/bd/quotations/${id}`);
    const q=data.quotation||{};
    document.getElementById('pdSignoffQuoteId').value=String(id);
    document.getElementById('pdSignoffLabel').value=q.signoff_label||QT_DEFAULTS.signoffLabel;
    document.getElementById('pdSignoffName').value=q.signatory_name||QT_DEFAULTS.sigName;
    document.getElementById('pdSignoffEmail').value=q.signatory_email||QT_DEFAULTS.sigEmail;
    document.getElementById('pdSignoffPhone').value=q.signatory_phone||QT_DEFAULTS.sigPhone;
    veil.classList.add('open');
    try{setTimeout(()=>document.getElementById('pdSignoffLabel').focus(),60);}catch(_){}
  }catch(e){pdToast(e.message||'Failed to load quotation');}
}
function pdQuoteApprove(id){
  pdEnsureSigModal(()=>{
    InjaazSignatureModal.open({
      title:'Approve quotation',
      onApply: async function(dataUrl){
        try{
          await apiPost(`/api/admin/bd/quotations/${id}/approve`,{signature:dataUrl});
          pdToast('Approved');
          await loadProject();
        }catch(e){pdToast(e.message||'Approve failed');}
      }
    });
  });
}

let _pdNotesCb = null;
let _pdNotesRequired = false;

function pdCloseNotesModal(){
  const veil=document.getElementById('pdNotesModal');
  if(veil) veil.classList.remove('open');
  _pdNotesCb=null;
  _pdNotesRequired=false;
  const err=document.getElementById('pdNotesErr');
  if(err) err.hidden=true;
}

function pdAskNotes(opts){
  opts=opts||{};
  const veil=document.getElementById('pdNotesModal');
  if(!veil){
    pdToast('Notes dialog failed to load — refresh the page');
    return;
  }
  _pdNotesRequired=!!opts.required;
  _pdNotesCb=typeof opts.onConfirm==='function'?opts.onConfirm:null;
  const title=document.getElementById('pdNotesTitle');
  const sub=document.getElementById('pdNotesSub');
  const label=document.getElementById('pdNotesLabel');
  const input=document.getElementById('pdNotesInput');
  const btn=document.getElementById('pdNotesConfirmBtn');
  const err=document.getElementById('pdNotesErr');
  if(title) title.textContent=opts.title||'Notes';
  if(sub) sub.textContent=opts.sub||'';
  if(label) label.textContent=_pdNotesRequired?'Notes *':'Notes (optional)';
  if(input){
    input.value='';
    input.placeholder=opts.placeholder||'Enter notes…';
  }
  if(btn) btn.textContent=opts.confirmLabel||'Confirm';
  if(err){
    err.hidden=true;
    err.textContent=opts.requiredMessage||'Notes are required';
  }
  veil.classList.add('open');
  try{setTimeout(()=>input&&input.focus(),60);}catch(_){}
}

function pdConfirmNotesModal(){
  const input=document.getElementById('pdNotesInput');
  const err=document.getElementById('pdNotesErr');
  const notes=((input&&input.value)||'').trim();
  if(_pdNotesRequired && !notes){
    if(err) err.hidden=false;
    if(input) input.focus();
    return;
  }
  const cb=_pdNotesCb;
  pdCloseNotesModal();
  if(cb) cb(notes);
}

function pdQuoteReject(id){
  pdAskNotes({
    title:'Reject quotation',
    sub:'Optional notes are shared with the sales team.',
    required:false,
    confirmLabel:'Reject',
    placeholder:'Reason for rejection (optional)',
    onConfirm: async function(notes){
      try{
        await apiPost(`/api/admin/bd/quotations/${id}/reject`,{notes:notes||''});
        pdToast('Rejected');
        await loadProject();
      }catch(e){pdToast(e.message||'Reject failed');}
    }
  });
}
function pdQuoteCancel(id){
  if(!gatePrepareOrToast()) return;
  pdAskNotes({
    title:'Cancel quotation',
    sub:'Cancellation notes are required and kept on the quote record.',
    required:true,
    requiredMessage:'Cancellation notes are required',
    confirmLabel:'Cancel quotation',
    placeholder:'Why is this quotation being cancelled?',
    onConfirm: async function(notes){
      try{
        await apiPost(`/api/admin/bd/quotations/${id}/cancel`,{notes});
        pdToast('Quotation cancelled');
        await loadProject();
      }catch(e){pdToast(e.message||'Cancel failed');}
    }
  });
}
async function pdPromote(){
  if(!project) return;
  if(!confirm('Mark this deal as won and promote to ticketing?')) return;
  try{
    await apiPost(`/api/admin/bd/projects/${PROJECT_ID}/promote`,{create_ticket_project:true});
    pdToast('Deal promoted');
    await loadProject();
  }catch(e){pdToast(e.message||'Promote failed');}
}

let _pdLpoQuoteId=null;
function pdQuoteAttachLpo(id){
  _pdLpoQuoteId=id;
  const inp=document.getElementById('pdLpoFileInput');
  if(!inp){pdToast('LPO picker failed to load — refresh the page');return;}
  inp.value='';
  inp.click();
}
async function pdLpoFileChosen(inp){
  const file=inp&&inp.files&&inp.files[0];
  const id=_pdLpoQuoteId;
  _pdLpoQuoteId=null;
  if(!file||!id) return;
  try{
    const token=localStorage.getItem('access_token');
    const fd=new FormData();
    fd.append('file',file);
    const r=await fetch(`/api/admin/bd/quotations/${id}/lpo`,{method:'POST',headers:{Authorization:'Bearer '+(token||'')},body:fd});
    const j=await r.json().catch(()=>({}));
    if(!r.ok||j.success===false) throw new Error(j.error||'LPO upload failed');
    pdToast('LPO attached');
    await loadProject();
  }catch(e){pdToast(e.message||'LPO upload failed');}
  finally{if(inp) inp.value='';}
}
async function pdQuoteDownloadLpo(id){
  const token=localStorage.getItem('access_token');
  try{
    const r=await fetch(`/api/admin/bd/quotations/${id}/lpo`,{headers:{Authorization:'Bearer '+(token||'')}});
    if(!r.ok) throw new Error('LPO not found');
    const blob=await r.blob();
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url;a.download='lpo';
    document.body.appendChild(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1500);
  }catch(e){pdToast(e.message||'LPO download failed');}
}

async function pdSetFollowupStatus(id,status){
  if(!id) return;
  try{
    await apiPut(`/api/admin/bd/followups/${id}`,{status});
    pdToast(status==='done'?'Follow-up completed':'Follow-up reopened');
    await loadProject();
  }catch(e){pdToast(e.message||'Failed to update follow-up');}
}

async function pdDeleteContact(id){
  if(!id) return;
  if(!window.confirm('Delete this contact?')) return;
  try{
    await apiDelete(`/api/admin/bd/contacts/${id}`);
    pdToast('Contact deleted');
    await loadProject();
  }catch(e){pdToast(e.message||'Failed to delete contact');}
}

async function pdDeleteProject(){
  if(!PROJECT_ID) return;
  if(!window.confirm('Delete this project? Quotations stay on file but are unlinked from the deal.')) return;
  try{
    await apiDelete(`/api/admin/bd/projects/${PROJECT_ID}`);
    pdToast('Project deleted');
    if(typeof window.bfCloseProjectDetail==='function'){
      window.bfCloseProjectDetail();
    }
    if(typeof window.loadBDData==='function'){
      await window.loadBDData();
    }else{
      window.location.href='/admin/bd';
    }
  }catch(e){pdToast(e.message||'Failed to delete project');}
}

window.pdShowPanel=pdShowPanel;
window.pdOpenEdit=pdOpenEdit;
window.pdCloseEdit=pdCloseEdit;
window.pdSaveProject=pdSaveProject;
window.pdOpenQuote=pdOpenQuote;
window.pdCloseQuote=pdCloseQuote;
window.pdSaveQuote=pdSaveQuote;
window.pdQuoteAddRow=pdQuoteAddRow;
window.pdQuoteEdit=pdQuoteEdit;
window.pdQuotePdf=pdQuotePdf;
window.pdQuoteSubmit=pdQuoteSubmit;
window.pdCloseSignoffModal=pdCloseSignoffModal;
window.pdContinueSignoffToSign=pdContinueSignoffToSign;
window.pdQuoteApprove=pdQuoteApprove;
window.pdQuoteReject=pdQuoteReject;
window.pdQuoteCancel=pdQuoteCancel;
window.pdCloseNotesModal=pdCloseNotesModal;
window.pdConfirmNotesModal=pdConfirmNotesModal;
window.pdPromote=pdPromote;
window.pdQuoteAttachLpo=pdQuoteAttachLpo;
window.pdLpoFileChosen=pdLpoFileChosen;
window.pdQuoteDownloadLpo=pdQuoteDownloadLpo;
window.pdSetFollowupStatus=pdSetFollowupStatus;
window.pdDeleteContact=pdDeleteContact;
window.pdDeleteProject=pdDeleteProject;

function applyHashPanel(){
  const hash=(location.hash||'').replace(/^#/,'').trim();
  if(['overview','contact','quotations','followups','activity','notes'].includes(hash)){
    pdShowPanel(hash);
  }
}

async function pdOpenProject(projectId, opts){
  opts = opts || {};
  PROJECT_ID = Number(projectId||0);
  onBackCb = typeof opts.onBack === 'function' ? opts.onBack : null;
  if(!PROJECT_ID) throw new Error('Project not found');
  const loading=document.getElementById('pdLoading');
  const err=document.getElementById('pdError');
  const ws=document.getElementById('pdWorkspace');
  if(loading){loading.style.display='block';loading.textContent='Loading project…';}
  if(err)err.style.display='none';
  if(ws)ws.style.display='none';
  pdShowPanel('overview');
  await loadProject();
  applyHashPanel();
  if(opts.panel) pdShowPanel(opts.panel);
}

function pdGoBack(){
  if(onBackCb){ onBackCb(); return; }
  window.location.href='/admin/bd';
}

window.pdOpenProject=pdOpenProject;
window.pdGoBack=pdGoBack;
window.addEventListener('hashchange',applyHashPanel);
})();
