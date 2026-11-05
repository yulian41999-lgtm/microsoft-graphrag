import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compare_modes import usage_summary
class Costs(unittest.TestCase):
    def test_failed_format_response_still_costs(self):
        rows=[dict(response_received=True,usage=dict(prompt_tokens=7,completion_tokens=3,total_tokens=10),api_seconds=2,status='error'),dict(response_received=True,usage=dict(prompt_tokens=8,completion_tokens=4,total_tokens=12),api_seconds=3,status='ok')]
        s=usage_summary(rows); self.assertEqual(s['total_tokens'],22);self.assertEqual(s['saved_api_responses'],2);self.assertEqual(s['failed_attempts'],1);self.assertEqual(s['api_seconds_sum'],5)
    def test_absent_usage_is_not_zero(self):
        self.assertIsNone(usage_summary([dict(response_received=True,usage=None,status='ok')])['total_tokens'])
    def test_zero_calls(self):
        self.assertEqual(usage_summary([])['total_tokens'],0)
    def test_failed_transport_is_not_saved_response(self):
        self.assertEqual(usage_summary([dict(response_received=False,status='error',api_seconds=1)])['saved_api_responses'],0)
    def test_partial_usage_is_only_a_subtotal(self):
        s=usage_summary([dict(response_received=True,usage=dict(prompt_tokens=5,completion_tokens=2,total_tokens=7),status='ok'),dict(response_received=True,usage=None,status='ok')])
        self.assertIsNone(s['total_tokens']); self.assertEqual(s['recorded_usage_subtotal']['total_tokens'],7); self.assertFalse(s['usage_complete'])
    def test_transport_failure_has_unknown_consumption(self):
        s=usage_summary([dict(response_received=False,status='error',api_seconds=1)])
        self.assertIsNone(s['total_tokens']);self.assertEqual(s['unknown_consumption_attempts'],1)
