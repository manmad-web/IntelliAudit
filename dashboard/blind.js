'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const state = {dataset:new URLSearchParams(location.search).get('dataset')||'pilot-v2', index:null, protocol:null, selected:null, detail:null, history:[], revealed:null, reviewer:null, loading:0, proofSets:[], hosted:false, csrf:null, practice:false, initialIds:new Set()};
const identityKey = 'intelliaudit.blind.identity.v1';
const judgementLabels = {correct:'Supported by the supplied information', incorrect:'Contradicted by the supplied information', insufficient_evidence:'Insufficient information to decide', ambiguous:'Unclear / needs clarification'};
const qualityLabels = {statement_unclear:'Statement or scope is unclear', evidence_unclear:'Supporting information is unclear', evidence_insufficient:'Necessary information is missing', evidence_contradictory:'Information conflicts', scenario_unrealistic:'Scenario seems unrealistic', source_unclear:'Source or reliability is unclear', other:'Another issue'};
const blank = () => ({judgement:'', error_type:null, rows:[], evidence_sufficiency:'uncertain', authority_disposition:'unresolved', citations:[], authority_currency:'unresolved', authority_source:'', proof_sets:[], supporting_evidence:[], missing_information:'', case_quality_flags:[], case_quality_notes:'', alternative_treatments:'', contradictions:'', reasoning:'', confidence:''});

function status(message, error=false){ $('status').textContent=message; $('status').classList.toggle('error',error); }
async function api(path, body){
  const response=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json',...(state.csrf?{'X-CSRF-Token':state.csrf}:{})}:{},body:body?JSON.stringify(body):undefined,credentials:'same-origin',cache:'no-store'});
  let data; try{data=await response.json();}catch{throw new Error(`Server returned ${response.status}; please reload and try again.`);}
  if(response.status===401&&state.hosted){location.assign('/login.html');throw new Error('Please sign in again.');}
  if(!response.ok)throw new Error(data.error||data.message||`Request failed (${response.status}).`);
  return data;
}
function scope(){return {dataset:state.dataset,case_id:state.selected,reviewer_id:state.reviewer?.reviewer_id};}
function query(extra={}){return new URLSearchParams({...scope(),...extra}).toString();}
function draftKey(stage){return ['intelliaudit.blind.draft.v1',state.index?.fingerprint,state.reviewer?.reviewer_id,state.selected,stage].join(':');}
function readDraft(stage){try{return JSON.parse(localStorage.getItem(draftKey(stage)))||null;}catch{return null;}}
function storeDraft(){
  const form=$('annotation-form'); if(!form||!state.reviewer||state.practice)return;
  try{localStorage.setItem(draftKey(form.dataset.stage),JSON.stringify(formValue(false)));$('draft-note').textContent='Draft saved in this browser. Submit to save it to your review account.';}
  catch{$('draft-note').textContent='Browser draft storage is unavailable. Submit or copy your notes before leaving.';}
}
function savedBlind(){return state.history.find(e=>e.stage==='blind');}
function savedVerification(){return state.history.filter(e=>e.stage==='verification').at(-1);}
function repeatMode(){return !state.practice&&state.protocol?.phase==='repeat';}
function legacyProtocol(){return state.protocol?.plan_version===1||state.protocol?.protocol_version===1||Number(state.protocol?.repeat_required)>0;}
function autoProposalReady(){return !state.practice&&!legacyProtocol()&&state.protocol?.phase==='reconciliation'&&!!savedBlind();}
function queueCases(){return state.protocol?.phase==='repeat'?state.protocol.repeat_cases:(state.index?.cases||[]);}

function renderQueue(){
  if(!state.index)return;
  const term=$('search').value.toLowerCase(), cases=queueCases();
  const completed=new Set(state.protocol?.completed_case_ids||state.initialIds);
  const entries=cases.filter(c=>[c.id,c.company_display||c.company,c.fiscal_year,c.statement_type].join(' ').toLowerCase().includes(term));
  $('case-count').textContent=`${entries.length}/${cases.length}`;
  $('case-list').innerHTML=entries.map(c=>`<button class="case ${!state.practice&&c.id===state.selected?'selected':''}" data-id="${esc(c.id)}" aria-current="${!state.practice&&c.id===state.selected?'true':'false'}"><span class="case-line"><strong>${esc(c.company_display||c.company||'Case')}</strong>${completed.has(c.id)&&state.protocol?.phase!=='repeat'?'<span class="saved-tag">Saved</span>':''}</span><small>${esc(c.fiscal_year)} · Income statement</small><small class="case-id">${esc(c.id)}</small></button>`).join('')||'<p class="queue-foot">No matching cases.</p>';
  for(const button of $('case-list').querySelectorAll('button'))button.addEventListener('click',()=>loadCase(button.dataset.id));
}
function renderProtocol(){
  const p=state.protocol;if(!p)return;
  const initial=`${p.initial_completed} of ${p.initial_total} initial assessments saved`;
  const repeat=`${p.repeat_completed} of ${p.repeat_required} delayed repeats saved`;
  $('protocol-title').textContent={initial:'First pass: make your own assessment',waiting:'Initial pass complete: delayed repeat pending',repeat:'Delayed repeat: earlier answers hidden',reconciliation:'Initial pass complete: proposal comparison is open'}[p.phase]||'Review progress';
  $('protocol-progress').textContent=p.phase==='waiting'?`${initial}. This existing review packet uses the earlier delayed-repeat protocol. Its ${p.repeat_required}-case repeat opens ${new Date(p.repeat_ready_at).toLocaleString()}; proposals remain locked.`:p.phase==='repeat'?`${initial}; ${repeat}. Review the shuffled packet with new case labels. Earlier answers are hidden during this repeat.`:p.phase==='initial'?`${initial}. Complete all ${p.initial_total} initial assessments before opening proposals.${legacyProtocol()?' This existing packet also requires the previously scheduled delayed repeat.':''}`:`${initial}. ${legacyProtocol()?repeat+'. Open a case to reveal its proposal intentionally.':'Generated proposals now appear when you open a case.'} Compare your preserved answer with the proposal and record separate feedback.`;
  $('export-button').disabled=p.phase==='repeat';$('import-button').disabled=p.phase==='repeat';renderQueue();
}
async function refreshProtocol(){
  if(!state.reviewer){state.protocol=null;return;}
  state.protocol=await api('/api/review/protocol?'+new URLSearchParams({dataset:state.dataset,reviewer_id:state.reviewer.reviewer_id}));renderProtocol();
}

function option(value,label,selected){return `<option value="${esc(value)}" ${value===selected?'selected':''}>${esc(label)}</option>`;}
function select(name,label,choices,value,wide=false,required=false){return `<div class="${wide?'wide':''}"><label for="annotation-${esc(name)}">${label}</label><select id="annotation-${esc(name)}" name="${name}" ${required?'required':''}>${option('','Select…',value)}${choices.map(x=>option(x[0],x[1],value)).join('')}</select></div>`;}
function evidenceUnits(){
  const provided=state.detail?.presentation?.evidence;
  const byId=new Map((provided||[]).map(unit=>[unit.id,unit]));
  return (state.detail?.evidence_units||[]).map((unit,index)=>{
    const extra=byId.get(unit.id)||{};
    return {...unit,...extra,label:extra.label||`EV-${String(index+1).padStart(3,'0')}`,category:extra.category||(unit.source==='statement'?/^\s*\[row\s+\d+\]/i.test(unit.text)?'statement':'context':/^\[/.test(unit.text)?'movement':/^\s*-\s/.test(unit.text)?'period_end_fact':'context')};
  });
}
function evidenceLabel(id){return evidenceUnits().find(unit=>unit.id===id)?.label||id;}
function evidenceChoiceText(unit){
  if(unit.source==='statement'||unit.category==='statement'){
    const row=statementRows().find(item=>item.unit_id===unit.id);
    if(row)return `${row.label}: ${row.amount} (row ${row.row})`;
    return String(unit.text).replace(/^\s*\[row\s+(\d+)\]\s*:\s*/i,'').replace(/\s*\|\s*/g,': ').replace(/\s*\[SEP\]\s*$/,'');
  }
  return unit.category==='movement'&&unit.heading?unit.heading+' · '+unit.text:unit.text;
}
function statementRows(){
  const rows=state.detail?.presentation?.statement_rows;
  if(Array.isArray(rows))return rows;
  return String(state.detail?.exam?.statement_text||'').split('\n').map((line,index)=>{
    const match=line.match(/^\s*\[row\s+(\d+)\]\s*:\s*(.*?)\s*\|\s*(.*?)(?:\s*\[SEP\])?\s*$/i);
    return match?{row:Number(match[1]),label:match[2],amount:match[3],unit_id:`statement:L${String(index+1).padStart(4,'0')}`}:null;
  }).filter(Boolean);
}
function tableHTML(rows,caption='Reported statement'){
  if(!rows.length)return '<p class="notice warning">The statement format needs clarification. Use the original source text below and flag the issue in your assessment.</p>';
  return `<div class="table-scroll"><table class="statement-table"><caption>${esc(caption)}</caption><thead><tr><th scope="col">Row</th><th scope="col">Line item</th><th scope="col" class="amount">Reported amount</th></tr></thead><tbody>${rows.map(row=>`<tr><td class="row-number">${esc(row.row)}</td><th scope="row">${esc(row.label)}${row.derived?`<small class="derived-note">${esc(row.note||'Reconstructed residual; not an individually reported filing fact.')}</small>`:''}</th><td class="amount">${esc(row.amount)}</td></tr>`).join('')}</tbody></table></div>`;
}
function sourceHTML(){
  const presentation=state.detail.presentation||{}, units=evidenceUnits();
  const supporting=units.filter(unit=>unit.source!=='statement'&&unit.category!=='statement');
  const movement=supporting.filter(unit=>unit.category==='movement'), facts=supporting.filter(unit=>unit.category==='period_end_fact'), context=supporting.filter(unit=>!['movement','period_end_fact'].includes(unit.category));
  const cards=list=>list.map(unit=>`<article class="evidence-card"><header><span class="evidence-label">${esc(unit.label)}</span>${unit.heading?`<strong>${esc(unit.heading)}</strong>`:''}</header><p>${esc(unit.text)}</p></article>`).join('');
  return `<section class="source-pane" aria-label="Statement and supporting information"><h3>Reported financial statement</h3><p class="hint">Amounts as presented for review. Row numbers identify statement lines.</p>${tableHTML(statementRows())}<h3>Supporting information</h3><div class="notice source-note"><strong>Synthetic case information</strong><p>${esc(presentation.source_notes||'The statement uses source financial figures. The component movements and period-end facts were generated for this exercise. They are not actual invoices, contracts or independently verified audit evidence.')}</p></div><section aria-label="Component movements"><h4>1. Component movements</h4><p class="hint">Synthetic account summaries for reconciling the reported amounts. Positive and negative signs refer to the line as presented.</p>${cards(movement)||'<p class="empty">No component movements were supplied.</p>'}</section><section aria-label="Period-end facts"><h4>2. Period-end facts</h4><p class="hint">Supplied facts to consider when assessing recognition for the reporting period. Decide whether they are adequate and consistent.</p>${cards(facts)||'<p class="empty">No period-end facts were supplied. Decide what information is necessary before reaching a conclusion.</p>'}</section>${context.length?`<details class="source-context"><summary>Source context and other supplied information</summary>${cards(context)}</details>`:''}${presentation.limitations?`<p class="hint">${esc(presentation.limitations)}</p>`:''}<details class="original-source"><summary>View original supplied text and evidence references</summary><h4>Statement text</h4><pre>${esc(state.detail.exam.statement_text||'No statement supplied.')}</pre><h4>Supporting text</h4><pre>${esc(typeof state.detail.exam.transaction_data==='string'?state.detail.exam.transaction_data:JSON.stringify(state.detail.exam.transaction_data,null,2))}</pre><p class="hint">Evidence labels refer to these same supplied lines. They do not indicate whether an answer is correct.</p>${units.map(unit=>`<p class="evidence-reference"><strong>${esc(unit.label)}</strong> · ${esc(unit.text)}</p>`).join('')}</details></section>`;
}
function formHTML(stage, draft){
  const value={...blank(),...draft}, verification=stage==='verification';state.proofSets=structuredClone(value.proof_sets||[]);
  const title=verification?'Your proposal feedback':stage==='repeat'?'Your delayed independent assessment':'Stage A · Your initial assessment';
  const rows=statementRows(), checked=new Set(value.rows||[]);
  return `<form id="annotation-form" class="review" data-stage="${stage}"><h3>${title}</h3><p class="hint">${verification?'Record a separate answer and the reason for agreeing, revising or leaving the proposal unresolved. Your original answer stays unchanged.':'Answer the focused revenue question using only the information supplied. It is acceptable to record uncertainty or missing information.'}</p><div class="form-grid">${verification?select('disposition','How do you assess the generated proposal?',[['agree','Agree'],['revise','Disagree / revise'],['unresolved','Unresolved — needs follow-up'],['exclude','Flag for exclusion']],value.disposition||'',true,true):''}${select('judgement',verification?'Your conclusion after comparison':'Is reported revenue supported for this period?',Object.entries(judgementLabels),value.judgement,true,true)}${select('confidence','Confidence',[['high','High'],['medium','Medium'],['low','Low']],value.confidence,true,true)}<fieldset class="wide row-selection"><legend>Affected statement rows, if any</legend><p class="hint">Select lines affected by your conclusion. Leave blank if no row applies.</p><div class="row-options">${rows.map(row=>`<label><input type="checkbox" name="rows" value="${esc(row.row)}" ${checked.has(row.row)?'checked':''}>Row ${esc(row.row)} · ${esc(row.label)}</label>`).join('')||'<p>No explicit row labels supplied.</p>'}</div></fieldset><fieldset class="wide supporting-selection"><legend>Information supporting your conclusion</legend><p class="hint">Choose relevant statement lines and supplied facts. Selection does not certify that these items prove the conclusion.</p><div class="supporting-options">${evidenceUnits().filter(unit=>unit.category!=='context').map(unit=>`<label><input type="checkbox" name="supporting_evidence" value="${esc(unit.id)}" ${(value.supporting_evidence||[]).includes(unit.id)?'checked':''}><span><strong>${esc(unit.label)}</strong> · ${esc(evidenceChoiceText(unit))}</span></label>`).join('')}</div></fieldset><label class="wide">Information you would need to decide<textarea name="missing_information" aria-label="Information you would need to decide" placeholder="Name missing facts or source documents; leave blank if no additional information is needed.">${esc(value.missing_information)}</textarea></label><label class="wide">${verification?'Reason for your feedback':'Short reason for your conclusion'}<textarea name="reasoning" aria-label="${verification?'Reason for your feedback':'Short reason for your conclusion'}" required placeholder="Explain what supports or contradicts revenue, or why you cannot decide.">${esc(value.reasoning)}</textarea></label><details class="wide case-quality"><summary>Flag a problem with this case <span class="optional">optional</span></summary><div class="quality-options">${Object.entries(qualityLabels).map(([code,label])=>`<label><input name="case_quality_flags" type="checkbox" value="${code}" ${(value.case_quality_flags||[]).includes(code)?'checked':''}>${label}</label>`).join('')}</div><label>Describe the problem<textarea name="case_quality_notes" aria-label="Describe the problem" placeholder="Explain the issue without guessing an intended answer.">${esc(value.case_quality_notes)}</textarea></label></details><details class="wide standards-details"><summary>Stage B · Accounting standards and detailed evidence <span class="optional">optional</span></summary><p class="hint">Complete what you can verify. Unknown or not verified is an accepted answer; a citation is not required for an initial assessment.</p><div class="form-grid"><label class="wide">Error type, if identified<input name="error_type" placeholder="e.g. recognition timing; leave blank if unknown" value="${esc(value.error_type||'')}"></label>${select('evidence_sufficiency','Are the supplied facts sufficient?',[['sufficient','Sufficient for this conclusion'],['insufficient','Insufficient'],['uncertain','Unknown / uncertain']],value.evidence_sufficiency,true)}${select('authority_disposition','Accounting-standard paragraph applicability',[['governing_paragraph','Applicable paragraph identified'],['no_governing_paragraph','No specific paragraph needed — explain why'],['insufficient_evidence','Insufficient information to decide applicability'],['unresolved','Unknown / not verified']],value.authority_disposition,true)}<label class="wide">Applicable citation(s), if verified<textarea name="citations" aria-label="Applicable citation(s), if verified" placeholder="One exact paragraph per line; leave blank if not verified">${esc((value.citations||[]).join('\n'))}</textarea><span class="hint">A broad topic reference alone does not establish applicability.</span></label>${select('authority_currency','Valid for the reporting date?',[['verified','Verified against a dated source'],['unresolved','Unknown / not verified'],['not_applicable','Not applicable — explain why']],value.authority_currency,true)}<label class="wide">Standards source and reporting-date check<textarea name="authority_source" aria-label="Standards source and reporting-date check" placeholder="Source URL/reference and effective-date check, if available">${esc(value.authority_source)}</textarea></label><label class="wide">Alternative accounting treatments<textarea name="alternative_treatments" aria-label="Alternative accounting treatments" placeholder="Describe accepted alternatives or unresolved treatments, if relevant.">${esc(value.alternative_treatments)}</textarea></label><label class="wide">Contradictions in the supplied information<textarea name="contradictions" aria-label="Contradictions in the supplied information" placeholder="Describe conflicting facts, if any.">${esc(value.contradictions)}</textarea></label><div class="wide"><h4>Jointly sufficient evidence sets</h4><p class="hint">Only add a set if those items together are sufficient for your conclusion. Each additional set is an alternative sufficient route. Leave this empty if you cannot establish one.</p><div id="proof-sets"></div><button id="add-proof" type="button">Add sufficient evidence set</button></div></div></details></div><p id="form-error" class="form-error" role="alert" tabindex="-1" hidden></p><p id="draft-note" class="hint">${state.practice?'Practice only. Nothing is sent to the review database.':'Drafts stay in this browser until submitted.'}</p><div class="form-actions"><button type="submit" class="primary">${state.practice?'Check practice answer':verification?'Save separate proposal feedback':stage==='repeat'?'Submit and lock repeat assessment':'Submit and lock initial assessment'}</button>${!state.practice&&!verification&&stage!=='repeat'?'<button id="next-case" type="button">Save draft and next case</button>':''}</div><p class="hint">${state.practice?'This fictional exercise does not count toward the 20 pilot cases.':'Submission preserves an immutable record. Unverified sources and unresolved accounting questions remain unresolved.'}</p></form>`;
}
function renderProofs(){
  const holder=$('proof-sets');if(!holder)return;
  holder.innerHTML=state.proofSets.map((ids,i)=>`<fieldset class="proof-set"><legend>Sufficient evidence set ${i+1}</legend><div class="proof-options">${evidenceUnits().filter(unit=>unit.category!=='context').map(unit=>`<label><input type="checkbox" data-set="${i}" value="${esc(unit.id)}" ${ids.includes(unit.id)?'checked':''}><span><strong>${esc(unit.label)}</strong> · ${esc(evidenceChoiceText(unit))}</span></label>`).join('')}</div><button class="remove-proof" type="button" data-remove="${i}">Remove this set</button></fieldset>`).join('');
  holder.querySelectorAll('input').forEach(input=>input.addEventListener('change',()=>{const i=Number(input.dataset.set);state.proofSets[i]=[...holder.querySelectorAll(`input[data-set="${i}"]:checked`)].map(x=>x.value);storeDraft();}));
  holder.querySelectorAll('[data-remove]').forEach(button=>button.addEventListener('click',()=>{state.proofSets.splice(Number(button.dataset.remove),1);renderProofs();storeDraft();}));
}
function formValue(){
  const form=$('annotation-form'),data=new FormData(form);
  return {judgement:data.get('judgement'),error_type:String(data.get('error_type')||'').trim()||null,rows:data.getAll('rows').map(Number),evidence_sufficiency:data.get('evidence_sufficiency')||'uncertain',authority_disposition:data.get('authority_disposition')||'unresolved',citations:String(data.get('citations')||'').split(/[\n,;]/).map(x=>x.trim()).filter(Boolean),authority_currency:data.get('authority_currency')||'unresolved',authority_source:String(data.get('authority_source')||'').trim(),proof_sets:state.proofSets.filter(x=>x.length),supporting_evidence:data.getAll('supporting_evidence'),missing_information:String(data.get('missing_information')||'').trim(),case_quality_flags:data.getAll('case_quality_flags'),case_quality_notes:String(data.get('case_quality_notes')||'').trim(),alternative_treatments:String(data.get('alternative_treatments')||'').trim(),contradictions:String(data.get('contradictions')||'').trim(),reasoning:String(data.get('reasoning')||'').trim(),confidence:data.get('confidence'),...(form.dataset.stage==='verification'?{disposition:data.get('disposition')}:{})};
}

function annotationSummary(annotation){
  const value=annotation||{},ids=value.supporting_evidence?.length?value.supporting_evidence:[...new Set((value.proof_sets||[]).flat())];
  return `<dl class="assessment-summary"><dt>Conclusion</dt><dd>${esc(judgementLabels[value.judgement]||value.judgement||'Not recorded')}</dd><dt>Affected rows</dt><dd>${esc(value.rows?.length?value.rows.join(', '):'None recorded')}</dd><dt>Supporting items</dt><dd>${esc(ids.length?ids.map(evidenceLabel).join(', '):'None recorded')}</dd><dt>Reason</dt><dd>${esc(value.reasoning||'Not recorded')}</dd>${value.missing_information?`<dt>Missing information</dt><dd>${esc(value.missing_information)}</dd>`:''}<dt>Confidence</dt><dd>${esc(value.confidence||'Not recorded')}</dd>${value.case_quality_flags?.length?`<dt>Case issues</dt><dd>${esc(value.case_quality_flags.map(code=>qualityLabels[code]||code).join('; '))}${value.case_quality_notes?'<br>'+esc(value.case_quality_notes):''}</dd>`:''}<dt>Standards check</dt><dd>${esc(value.authority_currency==='verified'?'Verified against the recorded source':value.authority_currency==='not_applicable'?'Marked not applicable':'Unknown / not verified')}${value.citations?.length?'<br>'+esc(value.citations.join('; ')):''}</dd></dl>`;
}
function lockedHTML(event,label){return `<section class="locked"><div class="notice"><strong>${esc(label)}</strong><p>Saved ${esc(new Date(event.created_at).toLocaleString())} · ${esc(event.reviewer_name||state.reviewer?.reviewer_id||'Reviewer')}. The submitted record stays preserved.</p></div><details><summary>Read saved assessment</summary>${annotationSummary(event.annotation)}<details><summary>Full recorded detail</summary><pre>${esc(JSON.stringify(event.annotation,null,2))}</pre></details></details></section>`;}
function proposalHTML(){
  const answer=state.revealed.answer||{}, errors=state.revealed.errors||[];
  const rawJudgement=answer.general_judgement||answer.judgement||'Not specified';
  const judgement=judgementLabels[String(rawJudgement).toLowerCase().replace(/\s+/g,'_')]||rawJudgement;
  const explanation=answer.explanation||answer.reasoning||answer.proposal_note;
  return `<div class="proposal-summary"><dl class="assessment-summary"><dt>Generated conclusion</dt><dd>${esc(judgement)}</dd>${errors.length?`<dt>Proposed issue(s)</dt><dd>${errors.map(error=>{
    const row=error.affected_row??error.post_inject_row??error.problematic_entry;
    const injection=error.injection_detail||{};
    const proposed=injection.original_value;
    return `<p>${esc(error.error_type||answer.error_type||'Issue proposed')}${error.affected_label?' · '+esc(error.affected_label):''}${row!==undefined?' · row '+esc(row):''}${proposed!==undefined?'<br>Proposed amount: '+esc(typeof proposed==='number'?proposed.toLocaleString('en-US'):proposed)+' (in the statement unit)':''}</p>`;
  }).join('')}</dd>`:'<dt>Proposed issue(s)</dt><dd>No specific error proposed.</dd>'}${explanation?`<dt>Generated explanation</dt><dd>${esc(explanation)}</dd>`:''}</dl>${errors.map(error=>{const cite=error.ground_truth_citations||{};return cite.asc_full?`<p class="hint">Proposed citation: ${esc(cite.asc_full)}. Applicability and reporting-date validity need independent checking.</p>${cite.rationale?`<p class="proposal-rationale">${esc(cite.rationale)}</p>`:''}`:'';}).join('')}<details><summary>Read the full generated proposal</summary><pre>${esc(JSON.stringify({answer,errors},null,2))}</pre></details></div>`;
}
function renderDetail(){
  const exam=state.detail.exam,meta=exam.metadata||{},presentation=state.detail.presentation||{},blind=savedBlind(),verification=savedVerification();
  const active=state.revealed?2:1;let review='';
  if(state.practice)review=formHTML('blind',blank());
  else if(!state.reviewer)review='<div class="notice warning">Enter a reviewer ID, name and qualification, then open your queue to begin.</div>';
  else if(repeatMode())review=formHTML('repeat',readDraft('repeat')||blank());
  else if(!blind)review=formHTML('blind',readDraft('blind')||blank());
  else{
    review=lockedHTML(blind,'Initial assessment saved and locked');
    if(!state.revealed)review+=`<section class="reveal-panel"><h3>Compare with the generated proposal</h3><p>${legacyProtocol()?'This existing packet opens proposals after its initial pass and scheduled delayed repeat.':'Proposals open after all 20 initial assessments are submitted. Your saved first answer is never replaced.'}</p><button id="reveal-button" class="primary" ${state.protocol?.phase==='reconciliation'?'':'disabled'}>Open generated proposal</button></section>`;
    else{
      review+=`<section class="proposal"><h3>Your original answer and the generated proposal</h3><div class="notice warning">The proposal is a candidate answer, not expert approval. You may disagree, revise, flag a case, or leave it unresolved.</div><div class="comparison"><section><h4>Your preserved initial answer</h4>${annotationSummary(blind.annotation)}</section><section><h4>Generated proposal</h4>${proposalHTML()}</section></div></section>`;
      if(verification)review+=lockedHTML(verification,'Latest separate proposal feedback saved');
      review+=formHTML('verification',readDraft('verification')||verification?.annotation||{...blind.annotation,disposition:''});
    }
  }
  const company=presentation.company_display||meta.company_display||meta.company||'Review case';
  const period=presentation.reporting_period||meta.period||meta.reporting_date||meta.fiscal_year||'Not specified';
  const unit=presentation.unit||meta.unit||'Not specified',currency=presentation.currency||meta.currency||(/USD/.test(String(unit))?'USD':'Not specified');
  $('case-detail').innerHTML=`${state.practice?'<div class="notice practice-banner"><strong>Fictional practice · outside the 20-case pilot</strong><p>No practice answer is submitted or saved to your review account.</p><button id="return-pilot" type="button">Return to pilot</button></div>':''}<div class="case-heading"><div><p class="eyebrow">${state.practice?'PRACTICE':esc(exam.exam_id||state.selected)}</p><h2>${esc(company)}</h2></div><span class="statement-kind">${esc(presentation.statement_title||'Statement of operations (income statement)')}</span></div><ul class="case-badges" aria-label="Accounting context"><li><strong>Framework</strong>${esc(presentation.framework||'US GAAP')}</li><li><strong>Reporting period</strong>${esc(typeof period==='object'?JSON.stringify(period):period)}</li><li><strong>Currency</strong>${esc(currency)}</li><li><strong>Unit</strong>${esc(unit)}</li></ul>${presentation.reporting_date_note?`<p class="hint reporting-date-note">${esc(presentation.reporting_date_note)}</p>`:''}<section class="task-panel" aria-labelledby="task-title"><h3 id="task-title">Your task: assess reported revenue</h3><p>Using only the statement and supporting information below, decide whether revenue is supported, contradicted, insufficiently evidenced, or unclear for this reporting period. Explain your conclusion and identify information you would need.</p></section><ol class="steps" aria-label="Review stages"><li class="${active===1?'active':''}">${repeatMode()?'Delayed independent assessment':'1 · Initial assessment'}</li><li class="${active===2?'active':''}">2 · Proposal comparison after the first pass</li></ol><div class="columns">${sourceHTML()}<section class="review-pane" aria-label="Your assessment">${review}</section></div>`;
  if($('annotation-form')){
    renderProofs();$('add-proof').addEventListener('click',()=>{state.proofSets.push([]);renderProofs();storeDraft();});
    $('annotation-form').addEventListener('input',storeDraft);$('annotation-form').addEventListener('change',storeDraft);$('annotation-form').addEventListener('submit',submit);
    $('next-case')?.addEventListener('click',nextCase);
  }
  $('reveal-button')?.addEventListener('click',reveal);$('return-pilot')?.addEventListener('click',returnToPilot);
}

async function loadCase(id,saveDraft=true){
  if(saveDraft)storeDraft();const seq=++state.loading;state.practice=false;state.selected=id;state.revealed=null;state.history=[];renderQueue();$('case-detail').innerHTML='<p>Loading the statement and supplied information…</p>';
  try{
    await refreshProtocol();if(seq!==state.loading)return;
    if(!queueCases().some(c=>c.id===id)){const next=queueCases()[0]?.id;if(next)return loadCase(next,false);$('case-detail').textContent='This review stage has no pending cases.';return;}
    const endpoint=repeatMode()?'/api/review/repeat-case?':'/api/blind/case?';
    const [detail,history]=await Promise.all([api(endpoint+new URLSearchParams({dataset:state.dataset,id,...(repeatMode()?{reviewer_id:state.reviewer.reviewer_id}:{})})),state.reviewer&&!repeatMode()?api('/api/review/history?'+query()):Promise.resolve({events:[]})]);
    if(seq!==state.loading)return;state.detail=detail;state.history=history.events||[];if(savedBlind())state.initialIds.add(id);renderDetail();renderQueue();
    status(repeatMode()?'Repeat case loaded. Earlier answers remain hidden.':'Case loaded. Review the statement and supplied information before making your assessment.');
    if(autoProposalReady())await openProposal(seq,true);
  }catch(error){if(seq===state.loading){$('case-detail').textContent='Unable to load this case.';status(error.message,true);}}
}
async function nextCase(){
  storeDraft();const cases=queueCases(),index=cases.findIndex(c=>c.id===state.selected);const next=cases[(index+1)%cases.length];if(next)await loadCase(next.id,false);
}
async function submit(event){
  event.preventDefault();const form=event.currentTarget,stage=form.dataset.stage,seq=state.loading,savedKey=draftKey(stage),button=form.querySelector('[type=submit]');button.disabled=true;
  try{
    const annotation=formValue();
    if(state.practice){
      const feedback=document.createElement('section');feedback.id='practice-feedback';feedback.className='notice practice-feedback';feedback.setAttribute('tabindex','-1');feedback.innerHTML=`<h3>Practice explanation</h3><p>The supplied movements total 120 − 20 = 100, matching reported revenue. The period-end fact says that all included obligations were satisfied by 31 December. Within this fictional packet, these facts support revenue of 100.</p><p>You can still distinguish internally consistent information from independently verified evidence: no actual contract or delivery document is supplied. An accountant may record a reliability limitation or request those documents.</p><p>Your practice choice: <strong>${esc(judgementLabels[annotation.judgement])}</strong>. This explanation is teaching material, not a pilot proposal or a scored assessment.</p><button id="practice-return" type="button">Return to the pilot</button>`;$('practice-feedback')?.remove();form.after(feedback);$('practice-return').addEventListener('click',returnToPilot);feedback.focus();button.disabled=false;status('Practice completed. Nothing was submitted to the review database.');return;
    }
    const response=await api(stage==='repeat'?'/api/review/repeat-submit':'/api/review/submit',{...scope(),...state.reviewer,...(stage==='repeat'?{}:{stage}),annotation});
    try{localStorage.removeItem(savedKey);}catch{}if(seq!==state.loading)return;
    if(stage==='repeat'){await refreshProtocol();const next=queueCases()[0]?.id;if(next)await loadCase(next,false);}
    else{
      state.history.push(response.record);if(stage==='blind')state.initialIds.add(state.selected);
      renderDetail();renderQueue();
      try{await refreshProtocol();}catch(error){if(seq===state.loading)status(`Your submission is saved and preserved. Progress could not be refreshed: ${error.message} Use “Refresh progress” to retry; do not resubmit the initial answer.`,true);return;}
      if(seq!==state.loading)return;renderDetail();renderQueue();
    }
    status(stage==='verification'?'Separate proposal feedback saved. Your initial assessment remains preserved.':stage==='repeat'?'Repeat assessment saved and locked.':'Initial assessment saved and locked. Select the next case to continue.');
    if(stage==='blind'&&autoProposalReady())await openProposal(seq,true);
  }catch(error){if(seq!==state.loading){status(error.message,true);return;}if($('form-error')){$('form-error').hidden=false;$('form-error').textContent=error.message;$('form-error').focus();}else status(error.message,true);button.disabled=false;}
}
async function openProposal(seq=state.loading,automatic=false){
  const button=$('reveal-button');if(button)button.disabled=true;
  try{
    const revealed=await api('/api/review/reveal',scope());if(seq!==state.loading)return false;
    state.revealed=revealed;
    if(revealed.record&&!state.history.some(record=>record.event_id===revealed.record.event_id))state.history.push(revealed.record);
    renderDetail();status(automatic?'All initial assessments are saved. The generated proposal is now shown beside your preserved answer.':'Proposal opened. Compare it with your original answer and save separate feedback.');return true;
  }catch(error){
    if(seq!==state.loading)return false;
    status(automatic?`Your initial assessment is saved and locked. The generated proposal could not be loaded: ${error.message} Use “Open generated proposal” to retry; do not resubmit the initial answer.`:error.message,true);
    if($('reveal-button'))$('reveal-button').disabled=false;return false;
  }
}
async function reveal(){return openProposal(state.loading,false);}
function practiceDetail(){
  const exam={exam_id:'PRACTICE-ONLY',metadata:{company:'Fictional Cedar Services',fiscal_year:2025,period:'2025-01-01 to 2025-12-31',statement_type:'IncomeStatement',unit:'USD thousands',currency:'USD'},statement_text:'[Time]: 2025-12-31 [SEP]\n[row 0]: Revenue | $100 [SEP]\n[row 1]: Operating expenses | ($60) [SEP]\n[row 2]: Operating income | $40 [SEP]',transaction_data:'Fictional training case. All information below was invented for this practice exercise.\n[Revenue] fees for completed services: +120; returns and allowances: −20.\n- Revenue: all services included above were completed, and the related performance obligations were satisfied, by 31 December 2025.'};
  const evidence_units=[];for(const [source,field] of [['statement','statement_text'],['transactions','transaction_data']])exam[field].split('\n').forEach((text,index)=>{if(text.trim())evidence_units.push({id:`${source}:L${String(index+1).padStart(4,'0')}`,source,text});});
  return {exam,evidence_units,presentation:{company_display:'Fictional Cedar Services',source_notes:'All statement amounts, movements and facts in this practice case are fictional teaching material. No real company, invoice or contract is represented.'}};
}
function openPractice(){storeDraft();state.returnCase=state.practice?state.returnCase:state.selected;++state.loading;state.practice=true;state.selected='PRACTICE-ONLY';state.revealed=null;state.history=[];state.detail=practiceDetail();renderDetail();renderQueue();status('Practice case opened. It is outside your pilot and will not affect review progress.');$('case-detail').focus();}
async function returnToPilot(){const id=state.returnCase&&queueCases().some(c=>c.id===state.returnCase)?state.returnCase:queueCases()[0]?.id;if(id)await loadCase(id,false);$('case-detail').focus();}

async function applyIdentity(){
  if(state.hosted)return;storeDraft();const reviewer={reviewer_id:$('reviewer-id').value.trim(),reviewer_name:$('reviewer-name').value.trim(),qualification:$('qualification').value.trim()};
  if(Object.values(reviewer).some(v=>!v)){status('Enter your reviewer ID, name and qualification first.',true);return;}
  state.reviewer=reviewer;state.initialIds.clear();try{localStorage.setItem(identityKey,JSON.stringify(reviewer));}catch{}await refreshProtocol();
  if(state.practice){renderDetail();return;}if(state.selected)await loadCase(state.selected,false);else status('Reviewer selected. Choose a case.');
}
async function exportReviews(){
  if(!state.reviewer){status('Open your reviewer queue before exporting.',true);return;}
  try{const envelope=await api('/api/review/export?'+query()),blob=new Blob([JSON.stringify(envelope,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`intelliaudit-${state.dataset}-${state.reviewer.reviewer_id.replace(/[^a-zA-Z0-9_-]/g,'_')}-reviews.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status('Saved assessments exported. Browser drafts are not included.');}catch(error){status(error.message,true);}
}
async function importReviews(file){
  if(!file)return;
  try{
    if(file.size>2000000)throw new Error('Backup is too large (maximum 2 MB).');const envelope=JSON.parse(await file.text());
    if(!envelope.scope||!Array.isArray(envelope.events))throw new Error('This is not an immutable review backup.');
    if(!state.reviewer||envelope.scope.reviewer_id!==state.reviewer.reviewer_id)throw new Error('Open the reviewer ID recorded in this backup before importing it.');
    if(envelope.scope.dataset!==state.dataset||envelope.scope.fingerprint!==state.index.fingerprint)throw new Error('Backup dataset or fingerprint differs from this pilot; use its matching dataset version.');
    await api('/api/review/import',envelope);if(state.practice)await returnToPilot();else if(state.selected)await loadCase(state.selected);status('Backup imported. Submitted initial answers remain preserved.');
  }catch(error){status(error.message,true);}finally{$('import-file').value='';}
}
async function start(){
  try{
    const session=await api('/api/auth/session');state.hosted=!!session.hosted;state.csrf=session.csrf_token;
    if(state.hosted&&!session.authenticated){location.assign('/login.html');return;}
    if(state.hosted&&session.reviewer?.role==='curator'){location.replace('/admin.html');return;}
    if(state.hosted){
      const reviewer=session.reviewer;state.reviewer={reviewer_id:reviewer.id,reviewer_name:reviewer.name,qualification:reviewer.qualification};$('apply-identity').hidden=true;$('logout-button').hidden=false;$('import-button').hidden=true;$('identity-note').textContent='Signed in with your personal invitation. Submitted answers are saved centrally to your account. Drafts remain in this browser.';
      $('reviewer-id').closest('label').hidden=true;document.querySelector('.identity').classList.add('hosted-identity');
      for(const id of ['reviewer-id','reviewer-name','qualification'])$(id).readOnly=true;
    }else{try{const saved=JSON.parse(localStorage.getItem(identityKey)||'null');if(saved?.reviewer_id&&saved.reviewer_name&&saved.qualification)state.reviewer=saved;}catch{}}
    if(state.reviewer){$('reviewer-id').value=state.reviewer.reviewer_id;$('reviewer-name').value=state.reviewer.reviewer_name;$('qualification').value=state.reviewer.qualification;}
    $('apply-identity').addEventListener('click',applyIdentity);$('logout-button').addEventListener('click',async()=>{try{storeDraft();await api('/api/auth/logout',{});location.assign('/login.html');}catch(error){status(error.message,true);}});
    $('refresh-protocol').addEventListener('click',async()=>{try{await refreshProtocol();if(state.practice)return;const next=queueCases().some(c=>c.id===state.selected)?state.selected:queueCases()[0]?.id;if(next)await loadCase(next);}catch(error){status(error.message,true);}});
    $('guide-button').addEventListener('click',()=>$('guide-dialog').showModal());$('close-guide').addEventListener('click',()=>$('guide-dialog').close());$('practice-button').addEventListener('click',openPractice);
    $('search').addEventListener('input',renderQueue);$('export-button').addEventListener('click',exportReviews);$('import-button').addEventListener('click',()=>$('import-file').click());$('import-file').addEventListener('change',()=>importReviews($('import-file').files[0]));
    state.index=await api('/api/blind/index?dataset='+encodeURIComponent(state.dataset));await refreshProtocol();renderQueue();
    if(queueCases().length)await loadCase(queueCases()[0].id);else status('The pilot has no pending cases.');
  }catch(error){status(error.message,true);}
}
start();
