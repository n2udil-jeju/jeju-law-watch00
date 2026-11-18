"use strict";
const $=id=>document.getElementById(id);
const el=(tag,cls,txt)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(txt!==undefined)n.textContent=String(txt);return n};
const cleanUrl=v=>{try{const u=new URL(v);return u.protocol==='https:'&&['likms.assembly.go.kr','www.law.go.kr','law.go.kr','open.assembly.go.kr','www.assembly.go.kr','opinion.lawmaking.go.kr'].includes(u.hostname)?u.href:null}catch{return null}};
const fmtDate=v=>{if(!v)return '미확인';const x=String(v);return /^\d{8}$/.test(x)?`${x.slice(0,4)}-${x.slice(4,6)}-${x.slice(6,8)}`:x};
let bills=[],events=[],committeeSchedules=[],scheduleStatus='대기';
const NEW_DAYS=7;
function eventDate(v){const x=String(v||'').replace(' KST','+09:00').replace(' ','T');const d=new Date(x);return Number.isNaN(d.getTime())?null:d}
function isNewEvent(ev){const date=eventDate(ev?.detected);const delta=date?Date.now()-date.getTime():Infinity;return delta>=0&&delta<NEW_DAYS*86400000}
function updateForBill(b){return events.find(ev=>isNewEvent(ev)&&(String(ev.number||'')===String(b.number)||Array.isArray(ev.related_bill_numbers)&&ev.related_bill_numbers.map(String).includes(String(b.number))))||null}
function updateForSchedule(s){return events.find(ev=>isNewEvent(ev)&&String(ev.schedule_id||'')===String(s.id))||null}
function billUpdateLabel(ev,b){if(!ev)return '';
  if(String(ev.kind||'').startsWith('위원회 일정')){
    const named=(ev.confirmed_bill_numbers||[]).map(String).includes(String(b.number));
    return named?'해당 의안 관련 일정이 제목에 명시됨 (상정 여부 확인 필요)':'관련 위원회 회의 일정 신규 확인 · 해당 의안 심사안건 포함 여부 미확인';
  }
  return ev.message||ev.kind||'변경 확인';
}
const completionOrder=['alternative_unverified','withdrawn','rejected','discarded','other','promulgated'];
const completionLabels={alternative_unverified:'대안반영(공포 미확인·확인 필요)',withdrawn:'철회',rejected:'부결',discarded:'폐기',other:'기타 처리 종료',promulgated:'공포 확인(관련 대안 포함)'};
function completionKind(b){if(b.completion_kind&&completionLabels[b.completion_kind])return b.completion_kind;const s=String(b.status||'').replace(/\s/g,'');if(b.group==='promulgated'||(s.includes('공포')&&!s.includes('공포전')))return 'promulgated';if(s.includes('대안반영폐기')||s.includes('수정안반영폐기'))return 'alternative_unverified';if(s.includes('철회'))return 'withdrawn';if(s.includes('부결'))return 'rejected';if(s.includes('폐기')||s.includes('불부의'))return 'discarded';return 'other'}
function groupOf(b){if(b.group==='ongoing')return 'ongoing';if(b.group==='completed'||b.group==='closed'||b.group==='promulgated')return 'completed';const s=String(b.status||'').replace(/\s/g,'');return ['공포','대안반영폐기','수정안반영폐기','철회','부결','폐기','불부의'].some(x=>s.includes(x))?'completed':'ongoing'}
function stageOf(b){return b.stage||(groupOf(b)==='ongoing'?'세부 심사단계 미확인':'처리 종료')}
function displaySort(a,b){return Number(Boolean(updateForBill(b)))-Number(Boolean(updateForBill(a)))||String(b.date||'').localeCompare(String(a.date||''))||String(b.number||'').localeCompare(String(a.number||''))}
// 의안 원문 링크는 국회의 *개별 의안* 상세 URL임을 확인한 경우에만 제공합니다.
const validBillId=id=>/^(?:PRC_[A-Za-z0-9]{12,64}|[0-9]{4,15})$/.test(String(id||''));
function billDetailUrl(b){
  const id=String(b.bill_id||'');
  const raw=cleanUrl(b.url);
  if(raw){try{const u=new URL(raw);const fromUrl=u.searchParams.get('billId');
    if(u.hostname==='likms.assembly.go.kr'&&['/bill/bi/billDetailPage.do','/bill/billDetail.do'].includes(u.pathname)&&validBillId(fromUrl)&&(!validBillId(id)||id===fromUrl))return raw;
  }catch{}}
  if(validBillId(id))return 'https://likms.assembly.go.kr/bill/bi/billDetailPage.do?billId='+encodeURIComponent(id);
  // 위원회 대안: 국회 내부 BILL_ID가 없는 경우 법제처의 *해당 의안번호* 공식 상세페이지로 연결.
  const official=cleanUrl(b.official_detail_url||'');
  if(official){try{const u=new URL(official);if(u.hostname==='opinion.lawmaking.go.kr'&&u.pathname==='/gcom/nsmLmSts/out/'+String(b.number)+'/detailRP')return official;}catch{}}
  return null;
}
function addLink(parent,url,text){const safe=cleanUrl(url);if(safe){const a=el('a','soft-link',text);a.href=safe;a.target='_blank';a.rel='noopener noreferrer';parent.append(a)}else parent.append(el('span','muted','공식 개별 페이지 링크 미확인'))}
function appendBillLink(container,b,label){const link=billDetailUrl(b);if(link){const a=el('a','soft-link',label);a.href=link;a.target='_blank';a.rel='noopener noreferrer';a.title='국회 의안정보시스템 또는 법제처 국민참여입법센터의 해당 의안 상세페이지';container.append(a)}else container.append(el('span','muted','의안 상세주소 확인 중'))}
function appendDetails(tr,b){const more=el('tr','detail-row');const cell=el('td');cell.colSpan=5;const panel=el('div','detail-box');const timeline=[['발의일',b.date],['소관위 회부',b.details?.COMMITTEE_DT],['소관위 상정',b.details?.CMT_PRESENT_DT],['소관위 처리',b.details?.CMT_PROC_DT],['소관위 결과',b.details?.CMT_PROC_RESULT_CD],['법사위 회부',b.details?.LAW_SUBMIT_DT],['법사위 상정',b.details?.LAW_PRESENT_DT],['법사위 처리',b.details?.LAW_PROC_DT],['법사위 결과',b.details?.LAW_PROC_RESULT_CD],['본회의 의결',b.details?.PROC_DT],['본회의 결과',b.details?.PROC_RESULT_CD],['공포일',b.official_alternative?b.promulgation_date:null]];
  panel.append(el('h4','','확인된 의안 심사경과'));
  panel.append(el('p','fine','국회 공식 심사일자와 회의자료를 기반으로 표시하며, 조회되지 않은 단계는 생략합니다.'));
  const filled=timeline.filter(([,v])=>v);if(filled.length){const dl=el('div','detail-grid');filled.forEach(([k,v])=>{const item=el('div','detail-item');item.append(el('span','muted',k));item.append(el('strong','',/^\d{8}$/.test(v)?fmtDate(v):v));dl.append(item)});panel.append(dl)}else panel.append(el('p','fine','상세 심사경과는 현재 API에서 확인되지 않았습니다.'));
  if(b.related_alternative?.number){const alt=el('div','related-alt');const linked=b.related_alternative;const published=Boolean(linked.promulgation_date&&linked.law_number);alt.append(el('strong','',published?'대안반영 → 관련 위원회 대안 공포 완료':'대안반영 → 관련 위원회 대안 확인 (공포 여부 미확인)'));alt.append(el('p','',published?`원안 ${b.number}은 대안반영폐기 · 대안 ${linked.number} · 법률 제${linked.law_number}호 · ${fmtDate(linked.promulgation_date)} 공포`:`원안 ${b.number}은 대안반영폐기 · 관련 대안 ${linked.number}호 확인 · 공포 여부 추가 확인 중`));alt.append(el('p','fine','원안의 내용 전체가 동일하게 공포되었다는 의미는 아니며, 반영 범위는 대안 원문과 심사보고서를 비교해 확인해야 합니다.'));addLink(alt,linked.evidence_url,'관련 대안 '+linked.number+'호의 공식 처리정보 ↗');panel.append(alt)}
  if(b.official_alternative){
    const published=Boolean(b.law_number&&b.promulgation_date);const info=el('div','related-alt');info.append(el('strong','',published?'위원회 대안 최종 공포 확인':'위원회 대안 처리현황 (공포 여부 미확인)'));
    info.append(el('p','',published?`의안 ${b.number} · ${fmtDate(b.details?.PROC_DT)} 본회의 의결 · ${fmtDate(b.details?.GOV_SUBMIT_DT)} 정부 이송 · 법률 제${b.law_number}호 (${fmtDate(b.promulgation_date)} 공포)`:`의안 ${b.number} · ${fmtDate(b.details?.PROC_DT)} 본회의 의결 · 공포정보 확인 중`));
    addLink(info,b.official_detail_url||('https://opinion.lawmaking.go.kr/gcom/nsmLmSts/out/'+encodeURIComponent(b.number)+'/detailRP'),'대안 공식 처리정보 확인 ↗');panel.append(info);
    const originals=bills.filter(x=>String(x.related_alternative?.number||'')===String(b.number));
    if(originals.length){const rel=el('div','related-alt');rel.append(el('strong','',`이 대안에 연결된 원안 ${originals.length}건`));
      originals.forEach(orig=>{const item=el('div','alt-original-row');appendBillLink(item,orig,`[${orig.number}] ${orig.title}`);rel.append(item)});
      rel.append(el('p','fine','원안별 반영 범위는 대안 원문과 심사보고서를 비교해 확인해야 합니다.'));panel.append(rel)}
  }
  panel.append(el('h4','','상임위·법사위 회의정보'));
  if(b.meetings_ok&&b.meetings?.length){b.meetings.forEach(m=>panel.append(el('p','meeting-line',`${m.date?fmtDate(m.date)+' · ':''}${m.committee_type} · ${m.name} · ${m.result}`)))}else panel.append(el('p','fine','해당 의안의 회의일·심사결과가 자동 확인되지 않았습니다. 회의 개최가 곧 의결을 뜻하지 않습니다.'));
  const rel=committeeSchedules.filter(item=>(item.related_bill_numbers||[]).map(String).includes(String(b.number)));
  if(rel.length){panel.append(el('h4','','관련 위원회 예정 일정'));
    panel.append(el('p','fine','회의가 예정되었다는 사실만으로 해당 의안의 상정·심사·의결이 확정된 것은 아닙니다.'));
    rel.slice(0,8).forEach(s=>{const named=(s.confirmed_bill_numbers||[]).map(String).includes(String(b.number));
      panel.append(el('p','meeting-line',`${fmtDate(s.date)} ${s.time||''} · ${s.committee} ${s.kind} · ${s.title} · ${named?'일정 제목에서 제주특별법 언급':'의안 상정 여부 미확인'}`));});
    addLink(panel,'https://www.assembly.go.kr/portal/main/main.do#anchor7','국회 위원회 일정 바로가기 ↗');}
  appendBillLink(panel,b,'국회 의안 상세페이지 열기 (원문·검토보고서 확인) ↗');cell.append(panel);more.append(cell);tr.after(more);return more}
function billTable(rows){const wrap=el('div','table-scroll');const tbl=el('table');const thead=el('thead');const thr=el('tr');['의안번호','법률안명 / 제안자','최신 단계','국회 처리결과','세부 경과'].forEach(k=>thr.append(el('th','',k)));thead.append(thr);tbl.append(thead);const tbody=el('tbody');rows.sort(displaySort).forEach(b=>{const tr=el('tr');const numCell=el('td','num');appendBillLink(numCell,b,b.number||'—');tr.append(numCell);const nameCell=el('td');const upd=updateForBill(b);if(upd)tr.classList.add('new-bill');
  const strong=el('strong','bill-title');appendBillLink(strong,b,b.title||'—');nameCell.append(strong);
  if(upd){nameCell.append(el('span','new-mark','NEW'));nameCell.append(el('div','bill-update',billUpdateLabel(upd,b)));}nameCell.append(el('div','muted',`${b.proposer||'제안자 미확인'} · ${fmtDate(b.date)}`));if(b.committee)nameCell.append(el('div','muted',b.committee));
  if(b.related_alternative?.number){const linked=b.related_alternative;const published=Boolean(linked.promulgation_date&&linked.law_number);const info=el('div','alt-inline',published?`대안 ${linked.number}호 → 법률 제${linked.law_number}호 · ${fmtDate(linked.promulgation_date)} 공포`:`관련 대안 ${linked.number}호 확인 · 공포 여부 확인 중`);nameCell.append(info)}
  if(b.official_alternative&&b.law_number){nameCell.append(el('div','alt-inline',`위원회 대안 · 법률 제${b.law_number}호 공포`))}
  tr.append(nameCell);tr.append(el('td','',stageOf(b)));tr.append(el('td','',b.status||'미확인'));const td=el('td');const button=el('button','details-btn','경과 보기 +');button.type='button';button.setAttribute('aria-expanded','false');button.addEventListener('click',()=>{const on=button.getAttribute('aria-expanded')==='true';button.setAttribute('aria-expanded',String(!on));button.textContent=on?'경과 보기 +':'접기 −';if(on){if(tr.nextElementSibling?.classList.contains('detail-row'))tr.nextElementSibling.remove()}else appendDetails(tr,b)});td.append(button);td.append(el('div','link-gap'));appendBillLink(td,b,'의안·공포 상세정보 ↗');tr.append(td);tbody.append(tr)});tbl.append(tbody);wrap.append(tbl);return wrap}
function stageCard(label,rows){const section=el('section','stage-card');const head=el('div','stage-head');head.append(el('h4','',label));head.append(el('span','pill',rows.length+'건'));section.append(head);section.append(billTable(rows));return section}
function showBills(){const term=$('search').value.trim().toLowerCase(),stage=$('stage').value;const filtered=bills.filter(b=>(!term||[b.number,b.title,b.proposer,b.committee,b.related_alternative?.number].join(' ').toLowerCase().includes(term))&&(!stage||stageOf(b)===stage));const ongoing=filtered.filter(b=>groupOf(b)==='ongoing');const completed=filtered.filter(b=>groupOf(b)==='completed');$('ongoing-total').textContent=ongoing.length+'건';$('completed-total').textContent=completed.length+'건';const open=$('ongoing-groups'),done=$('completed-groups');open.replaceChildren();done.replaceChildren();if(!ongoing.length)open.append(el('div','empty','표시할 진행 중 의안이 없습니다.'));else{const byStage=new Map();for(const b of ongoing){const rank=Number(b.rank??999),name=stageOf(b),key=rank+'|'+name;if(!byStage.has(key))byStage.set(key,{rank,name,rows:[]});byStage.get(key).rows.push(b)}[...byStage.values()].sort((a,b)=>a.rank-b.rank||a.name.localeCompare(b.name)).forEach(g=>open.append(stageCard(g.name,g.rows)))}if(!completed.length)done.append(el('div','empty','표시할 처리 완료 의안이 없습니다.'));else completionOrder.forEach(kind=>{const matches=completed.filter(b=>completionKind(b)===kind);if(matches.length)done.append(stageCard(completionLabels[kind],matches))})}
function showEvents(){const period=$('recent-period').value;const now=Date.now();const rows=events.filter(v=>period==='all'||(eventDate(v)&&now-eventDate(v.detected).getTime()<=Number(period)*86400000&&now>=eventDate(v.detected).getTime()-86400000));const box=$('events');box.replaceChildren();$('recent-count').textContent=period==='all'?'저장된 전체 · '+rows.length+'건':'최근 '+period+'일 · '+rows.length+'건';if(!rows.length){box.append(el('div','empty','해당 기간에 확인된 변경사항이 없습니다. 첫 정상 수집은 기준자료로만 저장됩니다.'));return}rows.slice(0,100).forEach(v=>{const card=el('article','event'),top=el('div','event-top');top.append(el('span','tag',v.kind||'변경'));if(isNewEvent(v))top.append(el('span','new-mark','NEW'));top.append(el('strong','',v.title||'변경사항'));top.append(el('time','',v.detected||''));card.append(top);card.append(el('p','',v.message||''));const bill=bills.find(x=>String(x.number)===String(v.number));if(bill)appendBillLink(card,bill,'해당 의안 상세 보기 ↗');else if(String(v.kind||'').startsWith('위원회 일정'))addLink(card,v.url,'국회 위원회 일정 확인 ↗');else if(v.kind==='법령 기본정보')addLink(card,v.url,'법령 원문 확인 ↗');else card.append(el('span','muted','의안 상세주소 확인 중'));box.append(card)});if(rows.length>100)box.append(el('p','fine','최근 100건만 화면에 표시됩니다.'))}
function showCommitteeSchedules(){
  const target=$('committee-schedules');if(!target)return;target.replaceChildren();
  if(scheduleStatus!=='정상'){
    target.append(el('p','fine','국회 위원회 일정 API의 확인 결과가 아직 충분하지 않습니다. 기존 자료가 있다면 마지막 정상 확인분이 표시될 수 있습니다.'));
  }
  const base=new Date(Date.now()+9*3600000).toISOString().slice(0,10);
  const rows=committeeSchedules.filter(s=>String(s.date||'')>=base).sort((a,b)=>String(a.date+' '+a.time).localeCompare(String(b.date+' '+b.time))).slice(0,12);
  if(!rows.length){target.append(el('p','fine','현재 표시할 예정 일정이 확인되지 않았습니다. 실제 일정이 없다는 의미는 아닙니다.'));return}
  rows.forEach(s=>{const card=el('article','schedule-item');const head=el('div','schedule-head');head.append(el('strong','',`${fmtDate(s.date)} ${s.time||''} · ${s.committee}`));
    if(updateForSchedule(s))head.append(el('span','new-mark','NEW'));card.append(head);
    card.append(el('p','',`${s.kind} · ${s.title}`));
    if((s.confirmed_bill_numbers||[]).length)card.append(el('p','fine',`일정 제목에 제주특별법 관련 의안 언급 · ${s.confirmed_bill_numbers.join(', ')} (상정 여부 공식 안건 확인 필요)`));
    else card.append(el('p','fine','관련 위원회 일정입니다. 개별 제주특별법 의안의 상정 여부는 미확인입니다.'));
    addLink(card,s.url,'국회 위원회 일정 ↗');target.append(card)});
}
async function init(){try{const response=await fetch('data/monitor.json?ts='+Date.now(),{cache:'no-store'});if(!response.ok)throw Error('공개 데이터 파일 조회 실패');const d=await response.json();bills=Array.isArray(d.bills)?d.bills:[];events=Array.isArray(d.events)?d.events:[];committeeSchedules=Array.isArray(d.committee_schedules)?d.committee_schedules:[];scheduleStatus=d.sources?.schedule?.status||'대기';$('last-check').textContent=d.checked_at?'마지막 수집 시도: '+d.checked_at:'수집 대기';$('count-bills').textContent=bills.length;const committeeBills=bills.filter(b=>b.official_alternative||String(b.proposer_kind||'').includes('위원장')).length;const governmentBills=bills.filter(b=>String(b.proposer_kind||'').includes('정부')||String(b.proposer||'').trim()==='정부').length;const memberBills=bills.length-committeeBills-governmentBills;$('bill-breakdown').textContent=`의원발의 등 ${Math.max(0,memberBills)} · 정부제출 ${governmentBills} · 위원회 대안 ${committeeBills}`;const ongoing=bills.filter(b=>groupOf(b)==='ongoing'),completed=bills.filter(b=>groupOf(b)==='completed');$('count-pending').textContent=ongoing.length;$('count-completed').textContent=completed.length;const legislaturePending=ongoing.filter(b=>Number(b.rank||999)<90).length;$('pending-breakdown').textContent=`국회 계류 ${legislaturePending} · 본회의 의결/정부 이송 등 ${ongoing.length-legislaturePending}`;
  const numbers=Object.fromEntries(completionOrder.map(k=>[k,completed.filter(b=>completionKind(b)===k).length]));const confirmedLawNums=new Set(completed.map(b=>String(b.law_number||b.related_alternative?.law_number||'')).filter(Boolean));const txt=`공포 연계 의안 ${numbers.promulgated}건 (법률번호 확인 ${confirmedLawNums.size}종) · 대안 결과 확인 필요 ${numbers.alternative_unverified}건 · 철회 ${numbers.withdrawn}건 · 부결 ${numbers.rejected}건 · 폐기 ${numbers.discarded}건 · 기타 ${numbers.other}건`;$('completed-breakdown').textContent='처리 완료 세부 · '+txt;$('completion-breakdown-inline').textContent=txt;
  const src=d.sources||{},as=src.assembly?.status||'대기',law=src.law?.status||'대기',detail=src.detail;const note=$('notice');note.className='notice good';note.textContent=as==='정상'&&law==='정상'?'국회·법제처 API를 기반으로 연결되었습니다. 확인된 공개 입법정보를 제공합니다.':'국회·법제처 공식 API 기반 입법정보 서비스입니다. 현재 일부 데이터는 확인 중이며, 확인되지 않았다는 것이 해당 정보가 없다는 뜻은 아닙니다.';
  const altStats=src.alternatives||{};const remain=Array.isArray(altStats.unresolved_originals)?altStats.unresolved_originals.length:0;
  $('source-status').textContent=`수집 상태: 국회 ${as} · 법제처 ${law} · 통합 의안검색 ${src.integrated_bills?.status||'미확인'} · 위원회 일정 ${scheduleStatus} · 심사단계 상세 ${detail?.details??0}/${detail?.total??bills.length}건 · 회의정보 ${detail?.meetings??0}/${detail?.total??bills.length}건 · 대안 연결 확인 ${altStats.linked??0}건 · 연결 미확인 ${remain}건`;
  const opts=[...new Set(bills.map(stageOf))].sort();opts.forEach(x=>{const option=el('option','',x);option.value=x;$('stage').append(option)});
  const lawInfo=d.law;const box=$('law-card');box.replaceChildren();if(lawInfo){box.append(el('p','law-title',lawInfo.title||'제주특별법'));const info=el('div','law-info');[['공포일',fmtDate(lawInfo.published)],['시행일',fmtDate(lawInfo.effective)],['공포번호',lawInfo.number||'미확인'],['제·개정',lawInfo.amendment||'미확인']].forEach(([k,v])=>{const x=el('span');x.append(el('strong','',k+' '));x.append(document.createTextNode(v));info.append(x)});box.append(info)}else box.append(el('div','empty','법제처의 현행법 정보가 아직 확인되지 않았습니다.'));
  $('search').addEventListener('input',showBills);$('stage').addEventListener('change',showBills);$('recent-period').addEventListener('change',showEvents);showBills();showEvents();showCommitteeSchedules()}catch(err){$('notice').textContent='사이트 데이터 파일을 읽지 못했습니다. GitHub Actions 배포 상태를 확인하세요.';$('notice').className='notice warn';}}
init();
