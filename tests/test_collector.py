import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from collect import parse_assembly, detect_events

class MonitorTests(unittest.TestCase):
    def test_api_parse(self):
        raw = json.dumps({"nzmimeepazxkubdpn": [{"head": [{"list_total_count": 1}, {"RESULT": {"CODE": "INFO-000", "MESSAGE": "OK"}}]}, {"row": [{"BILL_NO": "2217324"}]}]}).encode()
        total, rows = parse_assembly(raw)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["BILL_NO"], "2217324")
    def test_baseline_has_no_false_alert(self):
        old = {"sources": {"assembly": {"status": "설정 대기"}, "law": {"status": "설정 대기"}}}
        items = [{"number": "2217324", "title": "제주특별법", "proposer": "의원", "date": "", "status": "미처리", "url": "https://likms.assembly.go.kr/bill/main.do"}]
        self.assertEqual(detect_events(old, items, None, True, False, "now"), [])
    def test_status_change(self):
        prior = {"number": "2217324", "title": "제주특별법", "proposer": "의원", "date": "", "status": "미처리", "url": "https://likms.assembly.go.kr/bill/main.do"}
        old = {"sources": {"assembly": {"status": "정상"}}, "bills": [prior]}
        changed = {**prior, "status": "수정가결"}
        items = detect_events(old, [changed], None, True, False, "now")
        self.assertEqual(len(items), 1)
        self.assertIn("수정가결", items[0]["message"])
    def test_failed_source_keeps_history(self):
        old = {"sources": {"assembly": {"status": "정상"}}, "bills": []}
        self.assertEqual(detect_events(old, [{"number": "22", "title": "제주특별법", "url": ""}], None, False, False, "now"), [])

if __name__ == '__main__':
    unittest.main()
