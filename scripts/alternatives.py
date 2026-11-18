"""국회 공개 의안의 위원회 대안 탐색 및 직접 참조 식별자 기반 관계 연결.

공개 API에서 실제 참조식별자가 원안/대안을 정확히 가리키는 경우만 연결한다.
제목·일자·소관위가 비슷하다는 이유로 연결을 만들어내지 않는다.
"""
from __future__ import annotations

import re

JEJU_TITLE = '제주특별자치도 설치 및 국제자유도시 조성을 위한 특별법'
REFERENCE_KEYS = ('BILL_ID_REF', 'ALT_BILL_ID', 'ALTERNATIVE_BILL_ID',
                  'ORIGINAL_BILL_ID', 'ORIGINAL_BILL_IDS', 'RELATED_BILL_ID')
ALT_STATUS = ('대안반영폐기', '대안 반영 폐기', '수정안반영폐기', '수정안 반영 폐기')


def jeju_bill_title(value):
    cleaned = re.sub(r'\s+', '', str(value or ''))
    return ('제주특별자치도설치및국제자유도시조성을위한특별법' in cleaned)


def is_alternative(bill):
    title = re.sub(r'\s+', '', str(bill.get('title') or ''))
    proposer = re.sub(r'\s+', '', str(bill.get('proposer') or ''))
    kind = re.sub(r'\s+', '', str(bill.get('proposer_kind') or ''))
    return '대안' in title and ('위원장' in proposer or kind in ('위원장','위원회'))


def absorbed(bill):
    text = re.sub(r'\s+', '', str(bill.get('status') or ''))
    return any(re.sub(r'\s+', '', mark) in text for mark in ALT_STATUS)


def as_references(value):
    """참조필드의 값만 해석한다. 본문 제목이나 날짜에 있는 번호는 사용하지 않는다."""
    result = []
    if isinstance(value, (tuple,list)):
        for item in value:
            result.extend(as_references(item))
        return sorted(set(result))
    for token in re.split(r'[,;\s|]+', str(value or '').strip()):
        if re.fullmatch(r'PRC_[A-Za-z0-9]{12,64}', token) or re.fullmatch(r'22\d{5}', token):
            result.append(token)
    return sorted(set(result))


def normalize_integrated_row(row, detail_link_fn):
    """TVBPMBILL11의 의원·정부·위원장 법률안을 동일한 모델로 정규화."""
    title = str(row.get('BILL_NAME') or row.get('BILL_NM') or '').strip()
    number = str(row.get('BILL_NO') or '').strip()
    if not (re.fullmatch(r'22\d{5}', number) and jeju_bill_title(title)):
        return None
    bill_id = str(row.get('BILL_ID') or '').strip()
    proposer = str(row.get('PROPOSER') or row.get('RST_PROPOSER') or row.get('PPSR_KIND') or '').strip()
    details = {key: str(row.get(key) or '') for key in (
        'COMMITTEE_DT','CMT_PRESENT_DT','CMT_PROC_DT','CMT_PROC_RESULT_CD',
        'LAW_SUBMIT_DT','LAW_PRESENT_DT','LAW_PROC_DT','LAW_PROC_RESULT_CD',
        'PROC_DT','PROC_RESULT_CD','GOV_SUBMIT_DT','PROMULGATION_DT') if row.get(key)}
    alt_name = ('대안' in re.sub(r'\s+', '', title) and
                ('위원장' in proposer or str(row.get('PROPOSER_KIND') or '') == '위원장'))
    return {
        'official_alternative': alt_name,
        'number': number, 'bill_id': bill_id, 'title': title,
        'date': str(row.get('PROPOSE_DT') or row.get('PPSL_DT') or '').strip(),
        'proposer': proposer,
        'proposer_kind': str(row.get('PROPOSER_KIND') or row.get('PPSR_KIND') or ''),
        'status': str(row.get('PROC_RESULT_CD') or row.get('PROC_RESULT') or '미처리'),
        'committee': str(row.get('CURR_COMMITTEE') or row.get('COMMITTEE') or '').strip(),
        'url': detail_link_fn(bill_id, row.get('LINK_URL') or row.get('DETAIL_LINK')),
        'details': details, 'ref_ids': sorted({x for key in REFERENCE_KEYS
                                               for x in as_references(row.get(key))}),
        'integrated_source': 'TVBPMBILL11'
    }


def merge_integrated_bills(members, integrated):
    """기존 의원발의 목록 유지, 의원·정부·위원장안 새로 발견/보완, 중복 의안 제거."""
    found = {str(b['number']): dict(b) for b in members}
    discovered = 0
    for new in integrated:
        number = str(new.get('number') or '')
        if not number:
            continue
        if number not in found:
            found[number] = dict(new)
            discovered += 1
        else:
            old = found[number]
            for key in ('proposer_kind','ref_ids','integrated_source','official_alternative'):
                if new.get(key): old[key] = new[key]
            if not old.get('bill_id') and new.get('bill_id'):
                old['bill_id'] = new['bill_id']
            if not old.get('url') and new.get('url'):
                old['url'] = new['url']
            if not old.get('committee') and new.get('committee'):
                old['committee'] = new['committee']
            if (old.get('status') in ('', '미처리', '계류') and
                    new.get('status') not in ('', '미처리', '계류')):
                old['status'] = new['status']
    return sorted(found.values(), key=lambda b:(b.get('date') or '', b.get('number') or ''), reverse=True), discovered


def link_by_explicit_reference(bills):
    """공식 API 참조식별자가 실제 다른 의안의 ID/번호에 매칭할 때에만 쌍을 구성.

    - 원안은 국회 API 처리결과가 대안반영폐기여야 한다.
    - 연결 상대는 위원장 제안 대안이어야 한다.
    - 한 원안에 서로 다른 대안 후보가 둘이면 자동 연결하지 않는다.
    """
    index = {}
    for b in bills:
        for key in (b.get('bill_id'), b.get('number')):
            if key: index[str(key)] = b
    potential = {}
    for b in bills:
        for key in b.get('ref_ids') or []:
            other = index.get(str(key))
            if not other or str(other['number']) == str(b['number']):
                continue
            if absorbed(b) and is_alternative(other):
                original, alternative = b, other
            elif is_alternative(b) and absorbed(other):
                original, alternative = other, b
            else:
                continue
            # 두 의안은 같은 제주특별법이어야 한다. 타 법률 참조는 무시.
            if not (jeju_bill_title(original.get('title')) and
                    jeju_bill_title(alternative.get('title'))):
                continue
            # 국회 공식 공개 응답에서 특정 참조식별자 매칭 자체를 근거로 삼는다.
            potential.setdefault(str(original['number']), set()).add(str(alternative['number']))
    links, conflicts = {}, []
    for original, targets in potential.items():
        if len(targets) != 1:
            conflicts.append(original)
            continue
        alt_no = next(iter(targets))
        links[original] = {
            'verified': True, 'alternative_bill_no': alt_no,
            'relationship_method': 'official_api_reference',
            'relationship_evidence_url': 'https://open.assembly.go.kr/portal/openapi/TVBPMBILL11',
            'note': '공식 의안검색 API의 참조식별자와 양쪽 의안 ID/번호가 직접 일치함'
        }
    return links, conflicts
