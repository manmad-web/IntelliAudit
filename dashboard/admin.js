'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));
const state = {dataset:'pilot', session:null, reviewers:[], comparison:null, selected:null, refreshing:false};
const fieldNames = {judgement:'Judgment',error_type:'Error type',rows:'Statement rows',evidence_sufficiency:'Evidence sufficiency',authority_disposition:'Authority applicability',citations:'Paragraph citations',authority_currency:'Authority currency',proof_sets:'Sufficient proof families'};
const statusNames = {pending:'Another review needed',incomplete:'Incomplete initial record',disputed:'Initial differences',agreed:'Initial fields agree',resolved:'Curator resolution saved'};

function status(message, error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
async function api(path, body){
  const response=await fetch(path,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',headers:body?{'Content-Type':'application/json','X-CSRF-Token':state.session?.csrf_token||''}:{},body:body?JSON.stringify(body):undefined});
  let data;try{data=await response.json();}catch{throw new Error(`The server returned ${response.status}. Refresh and try again.`);}
  if(response.status===401){window.location.assign('/login.html');throw new Error('Your session has ended. Sign in again.');}
  if(!response.ok)throw new Error(data.error||data.message||`Request failed (${response.status}).`);
  return data;
}
function phaseLabel(protocol){
  if(!protocol)return 'Review not started';
  if(protocol.phase==='initial')return `${protocol.initial_completed}/${protocol.initial_total} initial cases saved`;
  if(protocol.phase==='waiting')return `First pass complete · repeats open ${dateLabel(protocol.repeat_ready_at)}`;
  if(protocol.phase==='repeat')return `${protocol.repeat_completed}/${protocol.repeat_required} delayed repeats saved`;
  return 'Initial pass and delayed repeats complete';
}
function dateLabel(value){const date=new Date(value);return Number.isNaN(date.getTime())?'date unavailable':date.toLocaleString();}
function renderPeople(){
  const reviewers=state.reviewers.filter(reviewer=>reviewer.role==='reviewer');
  $('reviewers').innerHTML=reviewers.map(reviewer=>`<article class="reviewer-card"><div><strong>${esc(reviewer.name||reviewer.id)}</strong><small>${esc(reviewer.qualification||'Qualification not recorded')}</small><span class="badge ${reviewer.active?'':'revoked'}">${reviewer.active?esc(phaseLabel(reviewer.protocol)):'Access revoked'}</span><small>${esc(reviewer.id)}</small></div>${reviewer.active?`<button type="button" class="danger revoke" data-id="${esc(reviewer.id)}">Revoke access</button>`:''}</article>`).join('')||'<p class="empty">Create the first accountant invitation to begin.</p>';
  for(const button of $('reviewers').querySelectorAll('.revoke'))button.addEventListener('click',async()=>{
    button.disabled=true;
    try{await api('/api/admin/revoke',{reviewer_id:button.dataset.id});await refresh();status('Accountant access revoked. Saved review records remain preserved.');}
    catch(error){button.disabled=false;status(error.message,true);}
  });
}
function renderOverview(){
  const report=state.comparison;
  $('case-count').textContent=report.case_count;
  $('reviewer-count').textContent=report.reviewer_count;
  $('dispute-count').textContent=report.dispute_queue.length;
  $('resolved-count').textContent=report.status_counts.resolved||0;
  $('agreement-metrics').innerHTML=Object.entries(report.agreement).map(([field,metric])=>`<div class="agreement-field"><span>${esc(fieldNames[field]||field)}</span><strong>${metric.ratio===null?'—':`${Math.round(metric.ratio*100)}%`}</strong><small>${metric.agreeing_pairs}/${metric.compared_pairs} reviewer pairs agree</small></div>`).join('');
  $('caveats').innerHTML=report.caveats.map(caveat=>`<li>${esc(caveat)}</li>`).join('');
}
function renderQueue(){
  const term=$('search').value.toLowerCase(),filter=$('status-filter').value;
  const cases=state.comparison.cases.filter(row=>(filter==='all'||row.status===filter)&&[row.id,row.company,row.fiscal_year].join(' ').toLowerCase().includes(term));
  const priority={disputed:0,incomplete:1,pending:2,agreed:3,resolved:4};
  cases.sort((left,right)=>priority[left.status]-priority[right.status]);
  $('case-list').innerHTML=cases.map(row=>`<button class="case ${row.id===state.selected?'selected':''}" data-id="${esc(row.id)}" aria-current="${row.id===state.selected}"><strong>${esc(row.company||'Case')} · ${esc(row.fiscal_year||'')}</strong><small>${esc(row.id)}</small><span class="badge ${esc(row.status)}">${esc(statusNames[row.status]||row.status)}</span><small>${row.review_count} independent initial ${row.review_count===1?'assessment':'assessments'}</small></button>`).join('')||'<p class="empty">No cases match these filters.</p>';
  for(const button of $('case-list').querySelectorAll('button'))button.addEventListener('click',()=>{state.selected=button.dataset.id;renderQueue();renderCase();});
}
function formatValue(value){if(value===null||value===undefined)return '—';if(Array.isArray(value))return value.length?value.map(item=>Array.isArray(item)?item.join(' + '):String(item)).join('\n'):'None selected';return String(value).replace(/_/g,' ');}
function resolutionOpen(){
  const observed=new Set(state.comparison.cases.flatMap(row=>row.reviews.map(event=>event.reviewer_id)));
  return observed.size>0&&[...observed].every(id=>state.reviewers.find(reviewer=>reviewer.id===id)?.protocol?.phase==='reconciliation');
}
function renderCase(){
  const row=state.comparison.cases.find(item=>item.id===state.selected);
  if(!row){$('case-detail').innerHTML='<p>Select a case to compare independent assessments.</p>';return;}
  const differences=new Set(row.differing_fields),open=resolutionOpen();
  $('case-detail').innerHTML=`<h2>${esc(row.company||'Case')} · ${esc(row.fiscal_year||'')}</h2><p class="case-meta">${esc(row.statement_type||'')} · ${esc(row.id)} · <span class="badge ${esc(row.status)}">${esc(statusNames[row.status]||row.status)}</span></p>
    ${row.missing_fields.length?`<div class="notice warning">Some initial records are incomplete: ${esc(row.missing_fields.join(', '))}.</div>`:''}
    ${row.reviews.length?`<div class="table-wrap"><table><thead><tr><th scope="col">Decision field</th>${row.reviews.map(event=>`<th scope="col">${esc(event.reviewer_name||event.reviewer_id)}<small>${esc(event.qualification)}</small></th>`).join('')}</tr></thead><tbody>${Object.entries(fieldNames).map(([field,label])=>`<tr class="${differences.has(field)?'difference':''}"><th scope="row">${esc(label)}</th>${row.reviews.map(event=>`<td class="annotation-value">${esc(formatValue(event.annotation[field]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div><div class="assessments">${row.reviews.map(event=>`<section class="assessment"><h3>${esc(event.reviewer_name||event.reviewer_id)}</h3><small>Initial record · ${esc(dateLabel(event.created_at))}</small><p>${esc(event.annotation.reasoning)}</p><details><summary>Authority source and full initial assessment</summary><pre>${esc(JSON.stringify(event.annotation,null,2))}</pre></details></section>`).join('')}</div>`:'<div class="notice">No initial assessment has been submitted for this case.</div>'}
    <form id="resolution-form" class="resolution"><h3>Record a curator resolution</h3><p class="notice ${open?'':'warning'}">${open?'Keep the expert reasoning and cite why a disagreement was resolved. The original submissions stay preserved.':'Resolutions open after every accountant who has submitted initial records completes the full blind pass and delayed repeats. This prevents early reconciliation from influencing independent work.'}</p><label>Start from an initial assessment<select id="resolution-source" ${row.reviews.length?'':'disabled'}>${row.reviews.map((event,index)=>`<option value="${index}">${esc(event.reviewer_name||event.reviewer_id)}</option>`).join('')}${row.latest_adjudication?.annotation?'<option value="latest">Latest curator resolution</option>':''}</select></label><label>Resolved assessment<textarea name="annotation" spellcheck="false" required ${open?'':'disabled'}></textarea></label><label>Reason for the resolution<textarea name="reason" placeholder="Explain the evidence and authority supporting this resolution, including any uncertainty." required maxlength="20000" ${open?'':'disabled'}></textarea></label><p class="form-error" id="resolution-error" role="alert"></p><button class="primary" type="submit" ${open&&row.reviews.length?'':'disabled'}>Save curator resolution</button></form>
    <section class="history"><h3>Preserved curator history</h3>${row.adjudications.map((record,index)=>`<details><summary>Resolution ${index+1} · ${esc(dateLabel(record.created_at))}</summary><p>${esc(record.reason)}</p><pre>${esc(JSON.stringify(record.annotation,null,2))}</pre></details>`).join('')||'<p>No curator resolution recorded.</p>'}</section>`;
  const form=$('resolution-form'),source=$('resolution-source');
  function chooseSource(){const annotation=source.value==='latest'?row.latest_adjudication?.annotation:row.reviews[Number(source.value)]?.annotation;form.elements.annotation.value=annotation?JSON.stringify(annotation,null,2):'';}
  source.addEventListener('change',chooseSource);chooseSource();
  form.addEventListener('submit',async event=>{
    event.preventDefault();$('resolution-error').textContent='';const button=form.querySelector('button[type=submit]');button.disabled=true;
    try{let annotation;try{annotation=JSON.parse(form.elements.annotation.value);}catch{throw new Error('The resolved assessment must be valid JSON.');}await api('/api/admin/adjudicate',{dataset:state.dataset,case_id:row.id,annotation,reason:form.elements.reason.value.trim()});await refresh();status('Curator resolution saved. Independent initial assessments remain preserved.');}
    catch(error){$('resolution-error').textContent=error.message;button.disabled=false;}
  });
}
async function refresh(){
  if(state.refreshing)return;state.refreshing=true;$('refresh').disabled=true;
  try{const [people,comparison]=await Promise.all([api(`/api/admin/reviewers?dataset=${state.dataset}`),api(`/api/admin/comparison?dataset=${state.dataset}`)]);state.reviewers=people.reviewers;state.comparison=comparison;if(!state.selected)state.selected=comparison.dispute_queue[0]||comparison.cases[0]?.id;renderPeople();renderOverview();renderQueue();renderCase();status('Curator records are up to date.');}
  finally{state.refreshing=false;$('refresh').disabled=false;}
}
$('refresh').addEventListener('click',()=>refresh().catch(error=>status(error.message,true)));
$('search').addEventListener('input',()=>state.comparison&&renderQueue());
$('status-filter').addEventListener('change',()=>state.comparison&&renderQueue());
$('logout').addEventListener('click',async()=>{try{await api('/api/auth/logout',{});window.location.assign('/login.html');}catch(error){status(error.message,true);}});
$('backup-button').addEventListener('click',async()=>{try{const backup=await api('/api/admin/export?dataset='+encodeURIComponent(state.dataset));const url=URL.createObjectURL(new Blob([JSON.stringify(backup,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=`intelliaudit-${state.dataset}-study-backup.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status('Study records exported. Store this backup privately; it contains reviewer names and assessments.');}catch(error){status(error.message,true);}});
$('invite-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');button.disabled=true;$('invite-result').hidden=true;$('invite-code').textContent='';
  try{const result=await api('/api/admin/invite',{name:form.elements.name.value.trim(),qualification:form.elements.qualification.value.trim()});$('invite-code').textContent=result.invite_code;$('invite-result').hidden=false;form.reset();await refresh();status('Invitation created. Copy the private code before leaving this page.');}
  catch(error){status(error.message,true);}finally{button.disabled=false;}
});
$('copy-invite').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('invite-code').textContent);status('Invitation code copied. Share it privately with the intended accountant.');}catch{status('Select and copy the displayed invitation code manually.');}});
(async()=>{try{state.session=await api('/api/auth/session');if(!state.session.authenticated){window.location.assign('/login.html');return;}if(state.session.reviewer?.role!=='curator'){window.location.assign('/');return;}$('account-name').textContent=state.session.reviewer.name||'Curator';await refresh();}catch(error){status(error.message,true);}})();
