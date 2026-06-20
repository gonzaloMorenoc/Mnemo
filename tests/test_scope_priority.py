import unittest

from src.scope_priority import prioritize_scoped_results


class ScopePriorityTests(unittest.TestCase):
    def test_priority_order_org_then_user_then_global(self):
        scoped = {
            "org": [{"chunk_id": "o1"}, {"chunk_id": "o2"}],
            "user": [{"chunk_id": "u1"}],
            "global": [{"chunk_id": "g1"}],
        }
        merged = prioritize_scoped_results(scoped, max_results=4)
        self.assertEqual([r["chunk_id"] for r in merged], ["o1", "o2", "u1", "g1"])

    def test_deduplicates_chunk_ids_across_scopes(self):
        scoped = {
            "org": [{"chunk_id": "same"}, {"chunk_id": "o2"}],
            "user": [{"chunk_id": "same"}, {"chunk_id": "u2"}],
            "global": [{"chunk_id": "g1"}],
        }
        merged = prioritize_scoped_results(scoped, max_results=5)
        self.assertEqual([r["chunk_id"] for r in merged], ["same", "o2", "u2", "g1"])

    def test_respects_top_k_limit(self):
        scoped = {
            "org": [{"chunk_id": "o1"}, {"chunk_id": "o2"}],
            "user": [{"chunk_id": "u1"}],
            "global": [{"chunk_id": "g1"}],
        }
        merged = prioritize_scoped_results(scoped, max_results=2)
        self.assertEqual([r["chunk_id"] for r in merged], ["o1", "o2"])


if __name__ == "__main__":
    unittest.main()
