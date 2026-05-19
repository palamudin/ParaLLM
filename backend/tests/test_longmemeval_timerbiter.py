from __future__ import annotations

import unittest

from scripts import build_longmemeval_pilot


class LongMemEvalTimerbiterTests(unittest.TestCase):
    def test_memory_units_add_bitemporal_anchor_and_after_event(self) -> None:
        record = {
            "question_id": "timer_case",
            "question_type": "temporal-reasoning",
            "question": "What was the first issue I had with my new car after its first service?",
            "question_date": "2023/04/10 (Mon) 23:07",
            "answer": "GPS system not functioning correctly",
            "haystack_sessions": [
                [
                    {
                        "role": "user",
                        "content": "I just got my car serviced for the first time on March 15th, and it was a great experience.",
                    },
                    {
                        "role": "user",
                        "content": "I recently had an issue with my car's GPS system on 3/22, and the dealership replaced it.",
                    },
                ]
            ],
        }

        unit = build_longmemeval_pilot.build_memory_units([record], "timer-bank")[0]
        timerbiter = unit["metadata"]["timerbiter"]

        self.assertEqual(timerbiter["schemaVersion"], "parallm-timerbiter/v0")
        self.assertEqual(timerbiter["storeClass"], "LTS")
        self.assertIn("depositedAt", timerbiter["systemClock"])
        self.assertIsNone(timerbiter["systemClock"]["retrievedAt"])
        self.assertIn("Timerbiter temporal authority", unit["text"])

        events = timerbiter["events"]
        self.assertTrue(
            any(
                event["eventAt"] == "2023-03-15"
                and event["temporalImportance"] == "anchor"
                and event["eventType"] == "maintenance"
                for event in events
            ),
            events,
        )
        self.assertTrue(
            any(
                event["eventAt"] == "2023-03-22"
                and event["eventType"] == "issue"
                and event["relation"] == "after_anchor"
                for event in events
            ),
            events,
        )

    def test_memory_units_add_open_obligation_ledger_without_gold_answer(self) -> None:
        record = {
            "question_id": "obligation_case",
            "question_type": "multi-session",
            "question": "How many items of clothing do I need to pick up or return from a store?",
            "question_date": "2023/02/15 (Wed) 19:47",
            "answer": "3",
            "haystack_sessions": [
                [
                    {
                        "role": "user",
                        "content": "I still need to pick up my dry cleaning for the navy blue blazer.",
                    },
                    {
                        "role": "user",
                        "content": "I need to return some boots to Zara; I exchanged them for a larger size.",
                    },
                    {
                        "role": "user",
                        "content": "I still need to pick up the new pair from Zara.",
                    },
                ]
            ],
        }

        unit = build_longmemeval_pilot.build_memory_units([record], "timer-bank")[0]
        timerbiter = unit["metadata"]["timerbiter"]

        obligations = timerbiter["obligations"]
        self.assertEqual(len(obligations), 3, obligations)
        self.assertTrue(all(obligation["status"] == "open_or_unconfirmed" for obligation in obligations))
        self.assertIn("Timerbiter obligation ledger", unit["text"])
        self.assertNotIn("answer", timerbiter)
        self.assertNotIn("Gold", unit["text"])

    def test_obligation_ledger_ignores_generic_advice_requests(self) -> None:
        record = {
            "question_id": "generic_advice_case",
            "question_type": "multi-session",
            "question": "How many items of clothing do I need to pick up or return from a store?",
            "question_date": "2023/02/15 (Wed) 19:47",
            "answer": "0",
            "haystack_sessions": [
                [
                    {
                        "role": "user",
                        "content": "Do you have any tips on how to keep track of items I need to pick up or return?",
                    },
                ]
            ],
        }

        unit = build_longmemeval_pilot.build_memory_units([record], "timer-bank")[0]
        timerbiter = unit["metadata"]["timerbiter"]

        self.assertEqual(timerbiter["obligations"], [])


if __name__ == "__main__":
    unittest.main()
