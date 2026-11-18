"""제주특별법 공개 입법동향 수집: 공식 API만 이용하고 미확인 사항은 미확인으로 표시.

기본: 22대 의원발의법률안 + 법제처 법률기본정보.
보완(조회 가능한 경우): 국회 TVBPMBILL11 단계별 심사일, BILLJUDGECONF 상임위 회의.
정부안·위원회안 전체포괄 및 법률-개별의안 공포 연결은 아직 완전 검증되지 않음.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
from html.parser import HTMLParser
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

PATH = Path(__file__).resolve().parents[1] / "site" / "data" / "monitor.json"
TITLE = "제주특별자치도 설치 및 국제자유도시 조성을 위한 특별법"
KST = ZoneInfo("Asia/Seoul")
ALT_MARKERS = ("대안반영폐기", "수정안반영폐기", "대안 반영 폐기", "수정안 반영 폐기")
END_MARKERS = ALT_MARKERS + ("임기만료폐기", "철회", "부결", "폐기", "불부의")
LINK_PATH = PATH.parent / "verified_alternatives.json"
OFFICIAL_HOSTS = {"likms.assembly.go.kr", "open.assembly.go.kr", "www.law.go.kr", "law.go.kr", "www.assembly.go.kr", "opinion.lawmaking.go.kr"}
SCHEDULE_URL = "https://www.assembly.go.kr/portal/main/main.do#anchor7"
SCHEDULE_CODES = (("nrsldhjpaemrmolla", "위원회 전체회의"), ("nrkqqbvfanfybishu", "법안심사소위원회"))
BILL_DETAIL_BASE = "https://likms.assembly.go.kr/bill/bi/billDetailPage.do"
BILL_DETAIL_PATHS = {"/bill/bi/billDetailPage.do", "/bill/billDetail.do"}


def valid_bill_id(value):
    """의안번호(BILL_NO)가 아닌 국회 내부의안ID(BILL_ID)만 사용."""
    return bool(re.fullmatch(r"(?:PRC_[A-Za-z0-9]{12,64}|[0-9]{4,15})", str(value or "")))


def detail_link(bill_id, api_link=""):
    """국회 개별 의안 상세페이지로 연결되는 URL만 반환한다.

    메인 URL을 반환하거나 의안번호로 BILL_ID를 추정하지 않는다.
    """
    raw = str(api_link or "").strip()
    try:
        parts = urlparse(raw)
        id_in_url = parse_qs(parts.query).get("billId", [""])[0]
        if (parts.scheme == "https" and parts.netloc == "likms.assembly.go.kr"
                and parts.path in BILL_DETAIL_PATHS and valid_bill_id(id_in_url)
                and (not valid_bill_id(bill_id) or id_in_url == str(bill_id))):
            return raw
    except ValueError:
        pass
    if valid_bill_id(bill_id):
        return BILL_DETAIL_BASE + "?" + urllib.parse.urlencode({"billId": str(bill_id)})
    return ""




def now():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")


def request(url, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(url + "?" + qs, headers={"User-Agent": "JejuLawWatch/0.2 (public legal data aggregator)"})
    with urllib.request.urlopen(req, timeout=12) as res:
        return res.read(4_000_000)


def parse_assembly(data, code="nzmimeepazxkubdpn"):
    obj = json.loads(data.decode("utf-8-sig"))
    items = obj.get(code)
    if not isinstance(items, list):
        raise ValueError("국회 API 응답에 데이터셋 없음: " + code)
    head = next((x['head'] for x in items if isinstance(x, dict) and 'head' in x), None)
    rows = next((x['row'] for x in items if isinstance(x, dict) and 'row' in x), [])
    if head is None:
        raise ValueError("국회 API 헤더 없음: " + code)
    result = next((x['RESULT'] for x in head if isinstance(x, dict) and 'RESULT' in x), None)
    if result and result.get('CODE') not in ('INFO-000', 'INFO-200'):
        raise ValueError(str(result.get('CODE')) + ' ' + str(result.get('MESSAGE', '')))
    meta = head[0] if head and isinstance(head[0], dict) else {}
    if not isinstance(rows, list):
        raise ValueError("국회 API row 형식 오류")
    return int(meta.get('list_total_count', len(rows))), rows


def assembly_query(key, code, parameters, max_results=100):
    params = {"KEY": key, "Type": "json", "pIndex": 1, "pSize": min(max_results, 100), **parameters}
    total, rows = parse_assembly(request('https://open.assembly.go.kr/portal/openapi/' + code, params), code)
    if total > max_results:
        raise ValueError('조회 범위 초과: ' + code)
    for i in range(2, (total - 1) // params['pSize'] + 2):
        params['pIndex'] = i
        _, more = parse_assembly(request('https://open.assembly.go.kr/portal/openapi/' + code, params), code)
        rows.extend(more)
    return rows


def get_assembly(key):
    rows = assembly_query(key, 'nzmimeepazxkubdpn', {'AGE': 22, 'BILL_NAME': TITLE}, 1000)
    if not rows:
        raise ValueError('국회 API 검색결과 0건. 검색조건 또는 승인 여부 확인 필요')
    items = []
    for row in rows:
        title = str(row.get('BILL_NAME') or '')
        if '제주특별자치도' not in title or '특별법' not in title:
            continue
        no = str(row.get('BILL_NO') or '').strip()
        if not no:
            continue
        bill_id = str(row.get('BILL_ID') or '').strip()
        link = detail_link(bill_id, row.get('DETAIL_LINK') or row.get('LINK_URL'))
        items.append({'number': no, 'bill_id': bill_id, 'title': title,
            'proposer': str(row.get('PROPOSER') or row.get('RST_PROPOSER') or ''),
            'date': str(row.get('PROPOSE_DT') or ''),
            'status': str(row.get('PROC_RESULT') or '미처리'),
            'committee': str(row.get('COMMITTEE') or ''), 'url': link})
    if not items:
        raise ValueError('국회 검색 응답에서 제주특별법 의안을 찾지 못함')
    return sorted({b['number']: b for b in items}.values(), key=lambda b: (b['date'], b['number']), reverse=True)


def date_value(row, *keys):
    for key in keys:
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ''


def normalize_meetings(rows, committee):
    """확인 가능한 회의 일자/명칭만 보여 줌. '회의 개최'와 '안건 의결'을 혼동하지 않음."""
    meetings = []
    for row in rows:
        date = date_value(row, 'CONF_DATE', 'CONF_DT', 'MEETING_DATE', 'MTG_DT', 'JRCMIT_CONF_DT', 'LWCMIT_CONF_DT', 'LWCMT_CONF_DT')
        name = date_value(row, 'CONF_NAME', 'CONF_NM', 'CLASS_NAME', 'TITLE', 'SUB_NAME', 'JRCMIT_CONF_NM', 'LWCMIT_CONF_NM', 'LWCMT_CONF_NM')
        result = date_value(row, 'CONF_RSLT', 'PROC_RESULT', 'JUDGE_RESULT', 'RSLT', 'JRCMIT_CONF_RSLT', 'LWCMIT_CONF_RSLT', 'LWCMT_CONF_RSLT')
        if not date and not name:
            continue
        meetings.append({'committee_type': committee, 'date': date, 'name': name or '회의 정보',
                         'result': result or '결과 확인 필요'})
    return meetings[-12:]


def get_details(key, bill):
    """개별 상세 API는 서비스별 반환 형식·승인 범위에 따라 일부만 동작할 수 있음."""
    result = {'number': bill['number'], 'details_ok': False, 'meetings_ok': False}
    try:
        rows = assembly_query(key, 'TVBPMBILL11', {'AGE': 22, 'BILL_NO': bill['number']}, 100)
        matching = [x for x in rows if str(x.get('BILL_NO') or '') == bill['number']]
        if matching:
            row = matching[0]
            result['details'] = {key: date_value(row, key) for key in (
                'COMMITTEE_DT', 'CMT_PRESENT_DT', 'CMT_PROC_DT', 'CMT_PROC_RESULT_CD',
                'LAW_SUBMIT_DT', 'LAW_PRESENT_DT', 'LAW_PROC_DT', 'LAW_PROC_RESULT_CD',
                'PROC_DT', 'PROC_RESULT_CD', 'CURR_COMMITTEE', 'GOV_SUBMIT_DT',
                'PROMULGATION_DT', 'PROMUL_DT', 'PROM_DT')}
            result['details_ok'] = True
    except (ValueError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        result['details_error'] = type(exc).__name__

    all_meetings = []
    observed = False
    if bill.get('bill_id'):
        for code, label in [('BILLJUDGECONF', '소관위원회'), ('BILLLWJUDGECONF', '법제사법위원회')]:
            try:
                rows = assembly_query(key, code, {'BILL_ID': bill['bill_id']}, 100)
                all_meetings.extend(normalize_meetings(rows, label))
                observed = True
            except (ValueError, OSError, TimeoutError, json.JSONDecodeError) as exc:
                result[code + '_error'] = type(exc).__name__
    try:
        rows = assembly_query(key, 'TVBPMCONFINFO', {'AGE': 22, 'BILL_NO': bill['number']}, 100)
        only_this_bill = [row for row in rows if str(row.get('BILL_NO') or bill['number']) == bill['number']]
        all_meetings.extend(normalize_meetings(only_this_bill, '법안심사소위원회'))
        observed = True
    except (ValueError, OSError, TimeoutError, json.JSONDecodeError) as exc:
        result['subcommittee_error'] = type(exc).__name__
    if observed:
        result['meetings'] = sorted({(m['committee_type'], m['date'], m['name'], m['result']): m for m in all_meetings}.values(),
                                    key=lambda m: (m['date'], m['name']))[-30:]
        result['meetings_ok'] = True
    return result


def official_evidence(url):
    """검증된 대안 관계는 국회·법제처 공식 자료 출처만 허용한다."""
    try:
        u = urlparse(str(url or ''))
        return u.scheme == 'https' and u.hostname in OFFICIAL_HOSTS
    except ValueError:
        return False


def official_alternative_url(no):
    return f"https://opinion.lawmaking.go.kr/gcom/nsmLmSts/out/{no}/detailRP"


class _GovPageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data.strip())


def parse_official_alternative_page(raw, number):
    """법제처 공식 의안 진행화면에서 *해당 의안*의 공포 항목만 추출.

    자동 수집 실패 시 기존 공포 사실을 지우지 않으며, 비슷한 법안명으로 공포를 추론하지 않음.
    """
    html = raw.decode('utf-8-sig', errors='replace') if isinstance(raw, bytes) else str(raw)
    parser = _GovPageText()
    parser.feed(html)
    text = ' '.join(x for x in parser.parts if x)
    expected = r'(?:제\s*)?' + re.escape(str(number)) + r'(?:\s*호)?'
    if not re.search(expected, text) or '제주특별자치도' not in text:
        raise ValueError('공식 페이지 의안번호 또는 의안명 불일치')
    def extract(label, pattern, default=''):
        found = re.search(re.escape(label) + r'\s*[:：]?\s*' + pattern, text)
        return found.group(1) if found else default
    date_pattern = r'((?:19|20)\d{2}\s*[.\-]\s*\d{1,2}\s*[.\-]\s*\d{1,2})'
    published = extract('공포일자', date_pattern)
    no = extract('공포번호', r'(?:법률\s*)?(?:제\s*)?(\d{4,7})\s*(?:호)?')
    def standard_date(value):
        if not value:
            return ''
        nums = re.findall(r'\d+', value)
        return f'{int(nums[0]):04d}-{int(nums[1]):02d}-{int(nums[2]):02d}' if len(nums)==3 else ''
    return {'promulgation_date': standard_date(published), 'law_number': no,
            'gov_transfer_date': standard_date(extract('정부이송일', date_pattern)),
            'evidence_url': official_alternative_url(number)}


def refresh_verified_alternatives(mappings, fetch=None):
    """이미 공식 확인된 위원회 대안의 후속 처리·공포를 공식 공개자료로 재확인.

    운영 서버에서 페이지가 차단/미갱신된 경우에도 검증된 과거 사실은 보존.
    새 원안·대안 간 연결관계의 자동 발견은 별도 수집기능이 필요함.
    """
    if fetch is None:
        fetch = lambda url: urllib.request.urlopen(
            urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; JejuLawWatch/0.6)'}), timeout=12).read(2_000_000)
    statuses = {}
    for alt_no, alt in (mappings.get('alternatives') or {}).items():
        if not alt.get('verified') or not official_evidence(alt.get('evidence_url')):
            statuses[alt_no] = '미검증'
            continue
        try:
            fetched = parse_official_alternative_page(fetch(official_alternative_url(alt_no)), alt_no)
            if fetched.get('promulgation_date') and fetched.get('law_number'):
                # API 지연 등으로 과거 공포기록을 되돌릴 수는 없음. 불일치 시 기존 검증값과 병행 점검.
                if (alt.get('promulgation_date') and alt['promulgation_date'] != fetched['promulgation_date']) or (alt.get('law_number') and str(alt['law_number']) != fetched['law_number']):
                    statuses[alt_no] = '공식자료 불일치(확인 필요)'
                    continue
                alt.update(fetched)
                statuses[alt_no] = '공식 페이지 재확인'
            else:
                statuses[alt_no] = '공포항목 미검출(기존 검증기록 유지)'
        except Exception as exc:
            statuses[alt_no] = '재조회 오류(기존 검증기록 유지): ' + type(exc).__name__
    return statuses


def append_verified_alternative_bills(bills, mappings):
    """의원발의 목록에 없는 위원회 대안을 별도 완료 의안으로 추가."""
    by_no = {str(b.get('number')): b for b in bills}
    for no, alt in (mappings.get('alternatives') or {}).items():
        if not (alt.get('verified') and re_date(str(alt.get('promulgation_date') or ''))
                and str(alt.get('law_number') or '').isdigit()
                and official_evidence(alt.get('evidence_url'))):
            continue
        row = by_no.get(no)
        if row is None:
            row = {'number': no, 'bill_id':'', 'title': alt.get('title') or TITLE + ' 일부개정법률안(대안)',
                   'date': alt.get('date') or '', 'proposer': alt.get('proposer') or '위원회 대안',
                   'committee': alt.get('committee') or '', 'status': alt.get('status') or '원안가결',
                   'url':alt['evidence_url'], 'official_alternative':True,
                   'details_ok':False, 'meetings_ok':False, 'meetings':[]}
            bills.append(row)
            by_no[no] = row
        row['official_alternative'] = True
        row['official_detail_url'] = alt['evidence_url']
        row['law_number'] = str(alt['law_number'])
        row['promulgation_source'] = alt['evidence_url']
        ds = dict(row.get('details') or {})
        ds.update({'PROMULGATION_DT': alt['promulgation_date']})
        if alt.get('plenary_date'):
            ds['PROC_DT'] = alt['plenary_date']
        if alt.get('plenary_result'):
            ds['PROC_RESULT_CD'] = alt['plenary_result']
        if alt.get('gov_transfer_date'):
            ds['GOV_SUBMIT_DT'] = alt['gov_transfer_date']
        row['details'] = ds
    return bills


def apply_verified_alternatives(bills, mappings):
    """원안→대안 연결은 검증된 출처가 등록된 경우에만 승인.

    자동으로 법률명·공포일이 비슷하다는 이유로 다른 의안을 연결하지 않는다.
    """
    count = 0
    links = mappings.get('links') or {}
    for bill in bills:
        bill.pop('related_alternative', None)
        no = str(bill.get('number') or '')
        entry = links.get(no) or {}
        if not isinstance(entry, dict) or entry.get('verified') is not True:
            continue
        if not any(mark.replace(' ', '') in str(bill.get('status') or '').replace(' ', '') for mark in ALT_MARKERS):
            continue
        alt_no = str(entry.get('alternative_bill_no') or '').strip()
        target = (mappings.get('alternatives') or {}).get(alt_no) or {}
        published = str(target.get('promulgation_date') or entry.get('promulgation_date') or '').strip()
        evidence = str(target.get('evidence_url') or entry.get('evidence_url') or '').strip()
        if not (alt_no.isdigit() and re_date(published) and official_evidence(evidence)):
            continue
        bill['related_alternative'] = {
            'number': alt_no,
            'promulgation_date': published,
            'law_number': str(target.get('law_number') or entry.get('law_number') or ''),
            'evidence_url': evidence,
            'relationship_evidence_url': str(entry.get('relationship_evidence_url') or ''),
            'plenary_date': str(target.get('plenary_date') or ''),
            'gov_transfer_date': str(target.get('gov_transfer_date') or ''),
            'note': str(entry.get('note') or '')[:250],
        }
        count += 1
    return count


def re_date(val):
    import re
    return bool(re.fullmatch(r'(?:19|20)\d{2}-?(?:0[1-9]|1[0-2])-?(?:0[1-9]|[12]\d|3[01])', val or ''))


def classify_bill(bill):
    """최신 단계 및 최종 처리결과를 분리. 대안반영폐기는 공포와 동일시하지 않는다."""
    status = str(bill.get('status') or '').strip()
    clean = status.replace(' ', '')
    details = bill.get('details') or {}
    dates = bill.get('dates') or {}
    def dt(k): return date_value(details, k) or str(dates.get(k) or '')
    alt = any(x.replace(' ', '') in clean for x in ALT_MARKERS)
    confirmed_alt = bill.get('related_alternative') or {}
    if alt:
        if confirmed_alt.get('number') and confirmed_alt.get('promulgation_date') and official_evidence(confirmed_alt.get('evidence_url')):
            return {'group':'completed', 'completion_kind':'promulgated', 'stage':'관련 대안 공포 확인',
                    'rank': 200, 'promulgation_date': confirmed_alt['promulgation_date']}
        return {'group':'completed', 'completion_kind':'alternative_unverified',
                'stage':'대안반영(관련 대안 확인 필요)', 'rank': 100, 'promulgation_date':''}
    promulgation = dt('PROMULGATION_DT') or dt('PROMUL_DT') or dt('PROM_DT')
    if promulgation or ('공포' in clean and '공포전' not in clean and '공포전' not in status):
        return {'group':'completed', 'completion_kind':'promulgated', 'stage':'공포 확인',
                'rank':200, 'promulgation_date':promulgation}
    if '철회' in clean:
        return {'group':'completed','completion_kind':'withdrawn','stage':'철회','rank':120,'promulgation_date':''}
    if '부결' in clean:
        return {'group':'completed','completion_kind':'rejected','stage':'부결','rank':130,'promulgation_date':''}
    if '폐기' in clean or '불부의' in clean:
        return {'group':'completed','completion_kind':'discarded','stage':'폐기','rank':140,'promulgation_date':''}
    if dt('GOV_SUBMIT_DT'):
        stage, rank = '정부 이송(공포 전)', 95
    elif dt('PROC_DT') or any(x in clean for x in ('가결', '의결')):
        # 원안가결·수정가결이 공포되었다고 추론하지 않는다.
        stage, rank = '본회의 의결(공포 미확인)', 90
    elif dt('LAW_PROC_DT'):
        stage, rank = '법사위 처리', 80
    elif dt('LAW_PRESENT_DT') and any(
            m.get('committee_type') == '법제사법위원회' and m.get('date')
            for m in bill.get('meetings', [])):
        stage, rank = '법사위 심사', 77
    elif dt('LAW_PRESENT_DT'):
        stage, rank = '법사위 상정', 75
    elif dt('LAW_SUBMIT_DT'):
        stage, rank = '법사위 접수', 70
    elif dt('CMT_PROC_DT'):
        # 심사결과가 대안반영·폐기일 수도 있어 '의결' 대신 공식 자료의 '처리' 사용.
        stage, rank = '소관위 처리', 65
    elif any(m.get('committee_type') == '법안심사소위원회' and m.get('date')
             for m in bill.get('meetings', [])):
        stage, rank = '소관위 심사(법안소위)', 58
    elif dt('CMT_PRESENT_DT') and any(
            m.get('committee_type') == '소관위원회' and m.get('date')
            for m in bill.get('meetings', [])):
        stage, rank = '소관위 심사', 57
    elif dt('CMT_PRESENT_DT'):
        stage, rank = '소관위 상정', 55
    elif dt('COMMITTEE_DT'):
        stage, rank = '소관위 접수', 45
    elif bill.get('date'):
        stage, rank = '접수(이후 단계 확인 필요)', 30
    else:
        stage, rank = '세부 심사단계 미확인', 999
    return {'group':'ongoing','completion_kind':'','stage':stage,'rank':rank,'promulgation_date':''}


def enrich_bills(key, bills, old_bills):
    previous = {b['number']: b for b in old_bills}
    responses = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for response in pool.map(lambda b: get_details(key, b), bills):
            responses[response['number']] = response
    details_count = meetings_count = 0
    for bill in bills:
        r = responses.get(bill['number']) or {}
        old = previous.get(bill['number']) or {}
        if not bill.get('url'):
            bill['url'] = detail_link(bill.get('bill_id') or old.get('bill_id'), old.get('url'))
        if r.get('details_ok'):
            bill['details'] = r['details']
            bill['details_ok'] = True
            details_count += 1
        else:
            bill['details'] = old.get('details') or {}
            bill['details_ok'] = False
        if r.get('meetings_ok'):
            bill['meetings'] = r.get('meetings') or []
            bill['meetings_ok'] = True
            meetings_count += 1
        else:
            bill['meetings'] = old.get('meetings') or []
            bill['meetings_ok'] = False
        bill.update(classify_bill(bill))
    return {'details': details_count, 'meetings': meetings_count, 'total': len(bills)}


def normalize_date(value):
    """국회 회의일자 문자열을 YYYY-MM-DD로 정규화."""
    raw = str(value or '').strip()
    matched = re.search(r'((?:19|20)\d{2})[.\-/ ]?(0[1-9]|1[0-2])[.\-/ ]?([0-2]\d|3[01])', raw)
    if not matched:
        return ''
    output = '-'.join(matched.groups())
    try:
        datetime.strptime(output, '%Y-%m-%d')
    except ValueError:
        return ''
    return output


def normalized_committee(name):
    """위원회명에 붙은 공백·대괄호 등을 정규화. 부분 일치 여부는 별도 판정."""
    return re.sub(r'[^가-힣A-Za-z0-9]', '', str(name or ''))


def related_committees(bills):
    # 법제사법위원회는 모든 의안이 체계·자구 심사를 거칠 수 있어 포함.
    labels = {'법제사법위원회'}
    for b in bills:
        if classify_bill(b)['group'] != 'ongoing':
            continue
        label = str(b.get('committee') or '').strip()
        if label and '위원회' in label and len(label) <= 40:
            labels.add(label)
    return sorted(labels)


def schedule_match_committee(text, committee):
    a, b = normalized_committee(text), normalized_committee(committee)
    # 예: '행정안전위원회' ↔ '행정안전위원회 법안심사제1소위원회'
    return bool(a and b and (a in b or b in a) and len(min((a,b),key=len)) >= 5)


def is_bill_on_agenda(schedule, bill):
    """위원회 일정 존재와 개별 법안 상정은 구분. 일정 제목에 법안번호/제주특별법 명시 시만 매칭."""
    title = str(schedule.get('title') or '')
    no = str(bill.get('number') or '').strip()
    bill_name = str(bill.get('title') or '')
    if no and no in title:
        return True
    if bill_name and len(bill_name) >= 24 and bill_name in title:
        return True
    return False


def normalize_schedule(row, kind):
    committee = date_value(row, 'COMMITTEE_NAME', 'COMM_NAME', 'CMT_NM')
    raw_date = date_value(row, 'MEETING_DATE', 'MEETTING_DATE', 'CONF_DATE', 'CONF_DT')
    meeting_date = normalize_date(raw_date)
    if not committee or not meeting_date:
        return None
    title = date_value(row, 'TITLE', 'MEETING_NAME', 'MEETING_TITLE', 'SUB_NAME') or kind
    clock = date_value(row, 'MEETING_TIME', 'MEETTING_TIME', 'CONF_TIME')
    session = date_value(row, 'SESS', 'SESSION', 'SESS_NO')
    degree = date_value(row, 'DEGREE', 'MEETING_COUNT')
    # 시간 변경은 동일 일정의 수정으로 감지해야 하므로 시간은 ID에 넣지 않음.
    base = '|'.join([kind, normalized_committee(committee), meeting_date, session, degree, title])
    identity = hashlib.sha256(base.encode('utf-8')).hexdigest()[:24]
    return {'id': identity, 'kind': kind, 'committee': committee,
            'date': meeting_date, 'time': clock, 'title': title,
            'session': session, 'degree': degree,
            'url': SCHEDULE_URL}


def get_committee_schedules(key, bills, at=None):
    """공식 위원회 전체회의·소위원회 일정 API 수집.

    각 위원회명으로 서버단 검색을 요청한다. API 지원 여부/결과는 실키 검증 필요.
    일부 API가 오류면 전체 성공으로 표시하지 않고 기존 자료를 유지한다.
    """
    clock = at or datetime.now(KST)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=KST)
    first = (clock - timedelta(days=7)).date()
    last = (clock + timedelta(days=35)).date()
    committees = related_committees(bills)
    records = {}
    errors = []
    queries = 0
    for committee in committees:
        for code, kind in SCHEDULE_CODES:
            queries += 1
            try:
                rows = assembly_query(key, code, {'COMMITTEE_NAME': committee}, max_results=1800)
            except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                errors.append(code + ':' + committee + ':' + type(exc).__name__)
                continue
            for row in rows:
                normalized = normalize_schedule(row, kind)
                if not normalized:
                    continue
                if not schedule_match_committee(normalized['committee'], committee):
                    continue
                date = datetime.strptime(normalized['date'], '%Y-%m-%d').date()
                if not first <= date <= last:
                    continue
                matched_bills = [b for b in bills if
                                 classify_bill(b)['group'] == 'ongoing' and
                                 (schedule_match_committee(normalized['committee'], b.get('committee', '')) or
                                  (normalized_committee(normalized['committee']) == normalized_committee('법제사법위원회')
                                   and classify_bill(b)['rank'] >= 70))]
                normalized['related_bill_numbers'] = sorted(set(str(b['number']) for b in matched_bills))
                normalized['confirmed_bill_numbers'] = [str(b['number']) for b in matched_bills
                                                       if is_bill_on_agenda(normalized, b)]
                records[normalized['id']] = normalized
    return sorted(records.values(), key=lambda x: (x['date'], x['time'], x['committee'], x['kind'])), errors, queries


def detect_schedule_events(old, schedules, ts, source_ok):
    """첫 성공 수집은 기준자료. 중간 API 오류와 일정 시간 만료로 취소를 추론하지 않음."""
    if not source_ok or old.get('sources', {}).get('schedule', {}).get('status') != '정상':
        return []
    previous = {item['id']: item for item in old.get('committee_schedules', [])}
    changes = []
    for item in schedules:
        before = previous.get(item['id'])
        if before is None:
            action = '위원회 일정 신규'
            message = f"{item['committee']} · {item['kind']} · {item['date']} {item['time']} · {item['title']}"
        elif before.get('time') != item.get('time'):
            action = '위원회 일정 변경'
            message = f"{item['committee']} · {item['kind']} · {item['date']} · 회의시간 {before.get('time') or '미확인'} → {item.get('time') or '미확인'}"
        else:
            continue
        if item['confirmed_bill_numbers']:
            message += ' · 일정 제목에 제주특별법 관련 안건 명시'
        else:
            message += ' · 해당 의안 심사안건 포함 여부 미확인'
        changes.append({'kind':action, 'number':'', 'schedule_id':item['id'],
                        'title': f"{item['committee']} {item['kind']} 일정", 'message':message,
                        'related_bill_numbers':item['related_bill_numbers'],
                        'confirmed_bill_numbers':item['confirmed_bill_numbers'],
                        'detected':ts, 'url':SCHEDULE_URL})
    return changes

def get_law(oc):
    raw = request('https://www.law.go.kr/DRF/lawSearch.do',
                  {'OC': oc, 'target': 'law', 'type': 'XML', 'query': TITLE, 'display': 100, 'sort': 'ddes'})
    root = ET.fromstring(raw)
    matches = [x for x in root.iter() if (x.findtext('법령명한글') or '').strip() == TITLE]
    if not matches:
        raise ValueError('법제처 현행법령 기본정보를 찾지 못함')
    record = matches[0]
    return {'title': TITLE, 'published': record.findtext('공포일자') or '',
            'effective': record.findtext('시행일자') or '', 'number': record.findtext('공포번호') or '',
            'amendment': record.findtext('제개정구분명') or '', 'serial': record.findtext('법령일련번호') or '',
            'url': 'https://www.law.go.kr/법령/제주특별자치도설치및국제자유도시조성을위한특별법'}


def detect_events(old, bills, law, assembly_ok, law_ok, ts):
    changes = []
    if assembly_ok and old.get('sources', {}).get('assembly', {}).get('status') == '정상':
        prev = {b['number']: b for b in old.get('bills', [])}
        for bill in bills:
            before = prev.get(bill['number'])
            if before is None:
                changes.append({'kind': '신규 의안', 'number': bill['number'], 'title': bill['title'],
                    'message': f"의안번호 {bill['number']} · {bill['proposer']} · {bill['date']} 접수 확인",
                    'detected': ts, 'url': bill['url']})
            elif before.get('status') != bill.get('status'):
                changes.append({'kind': '처리결과 변경', 'number': bill['number'], 'title': bill['title'],
                    'message': f"의안번호 {bill['number']} · {before.get('status', '미확인')} → {bill.get('status', '미확인')}",
                    'detected': ts, 'url': bill['url']})
            elif before.get('details_ok') and bill.get('details_ok') and (before.get('stage') != bill.get('stage')):
                changes.append({'kind': '심사단계 변경', 'number': bill['number'], 'title': bill['title'],
                    'message': f"의안번호 {bill['number']} · {before.get('stage')} → {bill.get('stage')}",
                    'detected': ts, 'url': bill['url']})
            if before and before.get('related_alternative') != bill.get('related_alternative') and bill.get('related_alternative'):
                linked = bill['related_alternative']
                changes.append({'kind': '대안 공포 연결 확인', 'number': bill['number'], 'title': bill['title'],
                    'message': f"원안 {bill['number']} → 관련 대안 {linked['number']} · 공포일 {linked['promulgation_date']} · 공포 근거 확인",
                    'detected': ts, 'url': linked['evidence_url']})
            if before and before.get('meetings_ok') and bill.get('meetings_ok'):
                before_keys = {(m.get('date'), m.get('name'), m.get('result')) for m in before.get('meetings', [])}
                for m in bill.get('meetings', []):
                    if (m.get('date'), m.get('name'), m.get('result')) not in before_keys:
                        changes.append({'kind': '회의정보 변경', 'number': bill['number'], 'title': bill['title'],
                            'message': f"{m.get('date') or '일자 미확인'} · {m.get('name')} · {m.get('result')}",
                            'detected': ts, 'url': bill['url']})
    previous_law = old.get('law')
    if law_ok and previous_law and old.get('sources', {}).get('law', {}).get('status') == '정상':
        keys = ['published', 'effective', 'number', 'amendment', 'serial']
        diff = [(k, previous_law.get(k), law.get(k)) for k in keys if previous_law.get(k) != law.get(k)]
        if diff:
            msg = ', '.join(f"{k}: {a or '미확인'} → {b or '미확인'}" for k, a, b in diff)
            changes.append({'kind': '법령 기본정보', 'title': TITLE,
                'message': msg + ' (조문 변경 여부는 별도 확인 필요)', 'detected': ts, 'url': law['url']})
    return changes


def main():
    old = json.loads(PATH.read_text(encoding='utf-8')) if PATH.exists() else {}
    ts = now()
    bills, law = old.get('bills', []), old.get('law')
    sources = dict(old.get('sources', {}))
    assembly_ok = law_ok = schedule_ok = False
    schedules = old.get('committee_schedules', [])
    ak, oc = os.getenv('ASSEMBLY_API_KEY', '').strip(), os.getenv('LAW_OC', '').strip()
    coverage = {'details': 0, 'meetings': 0, 'total': len(bills)}
    if not ak:
        sources['assembly'] = {'status': '인증키 미설정', 'checked_at': ts}
    else:
        try:
            new_bills = get_assembly(ak)
            coverage = enrich_bills(ak, new_bills, bills)
            bills = new_bills
            assembly_ok = True
            sources['assembly'] = {'status': '정상', 'checked_at': ts}
        except Exception as exc:
            sources['assembly'] = {'status': '조회 오류', 'checked_at': ts}
            print('ASSEMBLY ERROR', type(exc).__name__, str(exc), file=sys.stderr)
    if assembly_ok:
        try:
            new_schedules, schedule_errors, schedule_queries = get_committee_schedules(ak, bills)
            if schedule_errors:
                sources['schedule'] = {'status': '일부 확인', 'checked_at': ts,
                                       'queries': schedule_queries, 'errors': len(schedule_errors)}
                print('SCHEDULE ERROR', '; '.join(schedule_errors), file=sys.stderr)
                # 부분 조회는 신규로 단정하지 않는다. 지난 자료를 그대로 유지한다.
            else:
                schedules = new_schedules
                schedule_ok = True
                sources['schedule'] = {'status': '정상', 'checked_at': ts,
                                       'queries': schedule_queries, 'count': len(schedules)}
        except Exception as exc:
            sources['schedule'] = {'status': '조회 오류', 'checked_at': ts}
            print('SCHEDULE ERROR', type(exc).__name__, str(exc), file=sys.stderr)
    else:
        sources['schedule'] = {'status': '국회 API 미확인', 'checked_at': ts}
    if not assembly_ok:
        for b in bills:
            b['url'] = detail_link(b.get('bill_id'), b.get('url'))
            b.update(classify_bill(b))
    if not oc:
        sources['law'] = {'status': '인증키 미설정', 'checked_at': ts}
    else:
        try:
            law = get_law(oc)
            law_ok = True
            sources['law'] = {'status': '정상', 'checked_at': ts}
        except Exception as exc:
            sources['law'] = {'status': '조회 오류', 'checked_at': ts}
            print('LAW ERROR', type(exc).__name__, str(exc), file=sys.stderr)
    # 공식 자료로 대안 의안번호·공포일 연결을 확인한 사례만 결과로 인정.
    try:
        manual_links = json.loads(LINK_PATH.read_text(encoding='utf-8')) if LINK_PATH.exists() else {'links': {}}
    except (ValueError, OSError) as exc:
        print('ALTERNATIVE LINK FILE ERROR', type(exc).__name__, str(exc), file=sys.stderr)
        manual_links = {'links': {}}
    alternative_status = refresh_verified_alternatives(manual_links)
    bills = append_verified_alternative_bills(bills, manual_links)
    confirmed_links = apply_verified_alternatives(bills, manual_links)
    sources['alternatives'] = {'status': '공포이력 공식 확인', 'checked_at': ts, 'details': alternative_status,
                               'linked': confirmed_links, 'note':'기등록된 관계만 자동 추적; 신규 원안-대안 관계 발견은 미구현'}
    for b in bills:
        b.update(classify_bill(b))
    events = detect_events(old, bills, law, assembly_ok, law_ok, ts)
    events.extend(detect_schedule_events(old, schedules, ts, schedule_ok))
    seen = {(ev.get('kind'), ev.get('number'), ev.get('message')) for ev in events}
    cutoff = datetime.now(KST) - timedelta(days=730)
    def retained(event):
        try: return datetime.strptime(str(event.get('detected') or '')[:16], '%Y-%m-%d %H:%M').replace(tzinfo=KST) >= cutoff
        except ValueError: return True
    old_events = [ev for ev in old.get('events', []) if retained(ev) and (ev.get('kind'), ev.get('number'), ev.get('message')) not in seen]
    history = (events + old_events)[:1000]
    source_detail = {'status': '정상' if coverage['details'] == coverage['total'] and coverage['total'] else '일부 확인' if coverage['details'] else '미확인',
                     'checked_at': ts, **coverage}
    sources['detail'] = source_detail
    new = {'checked_at': ts, 'bills': bills, 'law': law, 'events': history, 'sources': sources,
           'committee_schedules': schedules,
           'scope': '22대 의원발의안 중심 + 공개자료로 검증된 위원회 대안 별도 수록. 대안 연결은 사전 검증된 관계를 유지하며 공식 페이지에서 공포일·법률번호를 재확인. 신규 위원회 대안 및 정부안 전체 자동발견은 추가 개발 필요.',
           'recent_days': 30}
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"검증된 원안-대안 공포 연결 {confirmed_links}건")
    print(f"의안 {len(bills)}건 · 새 변경 {len(events)}건 · 위원회 일정 {len(schedules)}건 · 일정조회 {sources['schedule']['status']} · 국회 {sources['assembly']['status']} · 법제처 {sources['law']['status']}")


if __name__ == '__main__':
    main()
