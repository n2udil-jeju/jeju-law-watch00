"""공식 공개 API에서 제주특별법 입법동향을 수집합니다.

표시 범위: 국회의원 발의 개정법률안 목록의 처리상태, 법제처 현행법령 기본정보.
정부제출안, 개별 소위심사, 신구조문 비교는 이 버전에 포함되지 않습니다.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PATH = Path(__file__).resolve().parents[1] / "site" / "data" / "monitor.json"
TITLE = "제주특별자치도 설치 및 국제자유도시 조성을 위한 특별법"
KST = ZoneInfo("Asia/Seoul")


def now():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")


def request(url, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(url + "?" + qs, headers={"User-Agent": "JejuLawWatch/0.1 (public legal data aggregator)"})
    with urllib.request.urlopen(req, timeout=24) as response:
        raw = response.read(4_000_000)
    return raw


def parse_assembly(data, code="nzmimeepazxkubdpn"):
    obj = json.loads(data.decode("utf-8-sig"))
    items = obj.get(code)
    if not isinstance(items, list):
        raise ValueError("국회 API 응답 형식 오류: 지정된 데이터셋 없음")
    head = next((block["head"] for block in items if isinstance(block, dict) and "head" in block), None)
    rows = next((block["row"] for block in items if isinstance(block, dict) and "row" in block), [])
    if head is None:
        raise ValueError("국회 API 헤더 없음")
    meta = head[0] if head and isinstance(head[0], dict) else {}
    result = next((v["RESULT"] for v in head if isinstance(v, dict) and "RESULT" in v), None)
    if result and result.get("CODE") not in ("INFO-000", "INFO-200"):
        raise ValueError("국회 API 오류: " + str(result.get("CODE")) + " " + str(result.get("MESSAGE", "")))
    if not isinstance(rows, list):
        raise ValueError("국회 API row 형식 오류")
    return int(meta.get("list_total_count", len(rows))), rows


def get_assembly(key):
    code = "nzmimeepazxkubdpn"
    base = "https://open.assembly.go.kr/portal/openapi/" + code
    params = {"KEY": key, "Type": "json", "pIndex": 1, "pSize": 100, "AGE": 22, "BILL_NAME": TITLE}
    total, rows = parse_assembly(request(base, params), code)
    if total == 0:
        raise ValueError("국회 API 검색결과가 0건입니다. 검색조건 또는 API 반환 범위를 확인하세요")
    if total > 1000:
        raise ValueError("국회 검색 결과가 1000건을 넘어 수집을 중단했습니다. 페이지 제한을 검토하세요")
    for page in range(2, (total - 1) // 100 + 2):
        params["pIndex"] = page
        _, more = parse_assembly(request(base, params), code)
        rows.extend(more)
    result = []
    for row in rows:
        title = str(row.get("BILL_NAME", ""))
        if "제주특별자치도" not in title or "특별법" not in title:
            continue
        number = str(row.get("BILL_NO", "")).strip()
        if not number:
            continue
        raw_link = str(row.get("DETAIL_LINK") or "")
        if not raw_link.startswith("https://likms.assembly.go.kr/"):
            raw_link = "https://likms.assembly.go.kr/bill/main.do"
        result.append({
            "number": number, "title": title, "proposer": str(row.get("PROPOSER") or row.get("RST_PROPOSER") or ""),
            "date": str(row.get("PROPOSE_DT") or ""), "status": str(row.get("PROC_RESULT") or "미처리"),
            "committee": str(row.get("COMMITTEE") or ""), "url": raw_link,
        })
    if total > 0 and not result:
        raise ValueError("국회 검색결과에 제주특별법 의안이 없습니다. 검색 조건을 확인하세요")
    uniq = {r["number"]: r for r in result}
    return sorted(uniq.values(), key=lambda b: (b["date"], b["number"]), reverse=True)


def get_law(oc):
    url = "https://www.law.go.kr/DRF/lawSearch.do"
    params = {"OC": oc, "target": "law", "type": "XML", "query": TITLE, "display": 100, "sort": "ddes"}
    raw = request(url, params)
    root = ET.fromstring(raw)
    found = []
    for record in root.iter():
        name = record.findtext("법령명한글")
        if not name or name.strip() != TITLE:
            continue
        found.append(record)
    if not found:
        raise ValueError("법제처에서 제주특별법의 정확한 법령명을 찾지 못했습니다")
    rec = found[0]
    return {"title": TITLE, "published": rec.findtext("공포일자") or "", "effective": rec.findtext("시행일자") or "",
            "number": rec.findtext("공포번호") or "", "amendment": rec.findtext("제개정구분명") or "",
            "serial": rec.findtext("법령일련번호") or "", "url": "https://www.law.go.kr/법령/제주특별자치도설치및국제자유도시조성을위한특별법"}


def detect_events(old, bills, law, assembly_ok, law_ok, ts):
    changes = []
    if assembly_ok and old.get("sources", {}).get("assembly", {}).get("status") == "정상":
        prev = {b["number"]: b for b in old.get("bills", [])}
        for b in bills:
            ob = prev.get(b["number"])
            if ob is None:
                changes.append({"kind": "신규 의안", "title": b["title"], "message": f"의안번호 {b['number']} · {b['proposer']} · {b['date']} 접수 확인", "detected": ts, "url": b["url"]})
            elif ob.get("status") != b.get("status"):
                changes.append({"kind": "처리상태 변경", "title": b["title"], "message": f"의안번호 {b['number']} · {ob.get('status', '미확인')} → {b.get('status','미확인')}", "detected": ts, "url": b["url"]})
    previous_law = old.get("law")
    if law_ok and previous_law and old.get("sources", {}).get("law", {}).get("status") == "정상":
        keys = ["published", "effective", "number", "amendment", "serial"]
        altered = [(k, previous_law.get(k), law.get(k)) for k in keys if previous_law.get(k) != law.get(k)]
        if altered:
            desc = ", ".join(f"{k}: {a or '미확인'} → {b or '미확인'}" for k, a, b in altered)
            changes.append({"kind": "법령", "title": TITLE, "message": desc + " (기본정보 변경이며 조문 내용 변경의 확인을 뜻하지 않음)", "detected": ts, "url": law["url"]})
    return changes


def main():
    old = json.loads(PATH.read_text(encoding="utf-8"))
    ts = now()
    sources = dict(old.get("sources", {}))
    bills = old.get("bills", [])
    law = old.get("law")
    ak = os.environ.get("ASSEMBLY_API_KEY", "").strip()
    oc = os.environ.get("LAW_OC", "").strip()
    assembly_ok = law_ok = False
    if not ak:
        sources["assembly"] = {"status": "인증키 미설정", "checked_at": ts}
    else:
        try:
            new_bills = get_assembly(ak)
            if not new_bills and bills:
                raise ValueError("기존 수집 결과가 있으나 조회값이 0건이어서 이전 자료를 유지합니다")
            bills = new_bills
            sources["assembly"] = {"status": "정상", "checked_at": ts}
            assembly_ok = True
        except Exception as exc:
            sources["assembly"] = {"status": "조회 오류", "checked_at": ts}
            print("ASSEMBLY ERROR", type(exc).__name__, str(exc), file=sys.stderr)
    if not oc:
        sources["law"] = {"status": "인증키 미설정", "checked_at": ts}
    else:
        try:
            law = get_law(oc)
            sources["law"] = {"status": "정상", "checked_at": ts}
            law_ok = True
        except Exception as exc:
            sources["law"] = {"status": "조회 오류", "checked_at": ts}
            print("LAW ERROR", type(exc).__name__, str(exc), file=sys.stderr)
    changes = detect_events(old, bills, law, assembly_ok, law_ok, ts)
    seen = {(ev.get("kind"), ev.get("title"), ev.get("message")) for ev in changes}
    history = changes + [ev for ev in old.get("events", []) if (ev.get("kind"), ev.get("title"), ev.get("message")) not in seen]
    new = {"checked_at": ts, "bills": bills, "law": law, "events": history[:250], "sources": sources}
    PATH.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"수집: 의안 {len(bills)}건, 법령 {'1' if law else '0'}건, 새 변경 {len(changes)}건 / 국회:{sources['assembly']['status']}, 법제처:{sources['law']['status']}")


if __name__ == "__main__":
    main()
