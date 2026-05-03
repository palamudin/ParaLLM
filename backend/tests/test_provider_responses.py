from __future__ import annotations

import json
import unittest

from backend.app import provider_responses


class ProviderResponseNormalizerTests(unittest.TestCase):
    def test_normalize_openai_prefers_top_level_answer(self) -> None:
        normalized = provider_responses.normalize_provider_response(
            "openai",
            {"answer": "OpenAI answer.", "stance": "go", "confidenceNote": "high confidence"},
        )
        self.assertEqual(normalized["answer"], "OpenAI answer.")
        self.assertEqual(normalized["sourceField"], "answer")

    def test_normalize_deepseek_uses_openai_compatible_choice_content(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "{\"answer\":\"DeepSeek answer.\",\"stance\":\"careful\",\"confidenceNote\":\"medium\"}"
                    }
                }
            ]
        }
        normalized = provider_responses.normalize_provider_response("deepseek", payload)
        self.assertEqual(normalized["answer"], "DeepSeek answer.")
        self.assertEqual(normalized["stance"], "careful")
        self.assertEqual(normalized["sourceField"], "choices.0.message.content")

    def test_normalize_anthropic_renders_structured_plan(self) -> None:
        payload = {
            "incident": {
                "title": "RMM compromise",
                "severity": "critical",
                "wake_senior_lead": {"decision": "yes", "justification": "multi-tenant blast radius"},
            },
            "phases": [
                {
                    "phase": 1,
                    "name": "Containment",
                    "window": "0-15 min",
                    "goal": "Stop further spread",
                    "steps": [{"step": 1, "action": "Suspend push", "detail": "pause automations"}],
                }
            ],
        }
        normalized = provider_responses.normalize_provider_response("anthropic", payload)
        self.assertIn("## Summary", normalized["answer"])
        self.assertIn("## Phases", normalized["answer"])
        self.assertEqual(normalized["sourceField"], "anthropic.rendered")

    def test_normalize_minimax_renders_structured_plan(self) -> None:
        payload = {
            "incident": {"title": "Compromise", "severity": "critical", "status": "active"},
            "immediateActions": [{"time": "0-10m", "action": "Suspend push", "rationale": "stop spread"}],
            "decisionGates": [{"gate": "payload confirmed", "action": "isolate"}],
        }
        normalized = provider_responses.normalize_provider_response("minimax", payload)
        self.assertIn("## Immediate actions", normalized["answer"])
        self.assertIn("## Decision gates", normalized["answer"])
        self.assertEqual(normalized["sourceField"], "minimax.rendered")

    def test_normalize_minimax_prefers_answer_draft_over_structured_shape(self) -> None:
        payload = {
            "answerDraft": "Use per-customer incident ownership and preserve control-plane evidence first.",
            "leadDirection": "Preserve evidence before any control-plane action.",
            "incident": {"title": "Compromise", "severity": "critical", "status": "active"},
            "immediateActions": [{"time": "0-10m", "action": "Suspend push", "rationale": "stop spread"}],
        }
        normalized = provider_responses.normalize_provider_response("minimax", payload)
        self.assertEqual(
            normalized["answer"],
            "Use per-customer incident ownership and preserve control-plane evidence first.",
        )
        self.assertEqual(normalized["sourceField"], "answerDraft")
        self.assertEqual(normalized["stance"], "Preserve evidence before any control-plane action.")

    def test_normalize_ollama_prefers_answer_draft(self) -> None:
        payload = {"answerDraft": "Use a reversible containment step first.", "leadDirection": "contain"}
        normalized = provider_responses.normalize_provider_response("ollama", payload)
        self.assertEqual(normalized["answer"], "Use a reversible containment step first.")
        self.assertEqual(normalized["sourceField"], "answerDraft")

    def test_extract_normalized_provider_answer_handles_fenced_json(self) -> None:
        raw = "```json\n{\"incident\":{\"title\":\"Compromise\",\"severity\":\"critical\"},\"phases\":[{\"name\":\"Containment\"}]}\n```"
        answer = provider_responses.extract_normalized_provider_answer("anthropic", raw)
        self.assertIn("Containment", answer)

    def test_extract_normalized_provider_answer_skips_minimax_schema_echo(self) -> None:
        raw = (
            "<think>Reasoning for display.</think>\n\n"
            '{"type":"object","additionalProperties":false,"required":["frontAnswer"],'
            '"properties":{"frontAnswer":{"type":"object"}}}}\n\n'
            '{"frontAnswer":{"answer":"Request confirmation of package provenance and any known compromise disclosures.",'
            '"stance":"act","leadDirection":"contain","adversarialPressure":"none","confidenceNote":"medium"},'
            '"summarizerOpinion":{"stance":"act","because":"multi-tenant risk",'
            '"uncertainty":"root cause open","integrationMode":"gated"},"sourceWorkers":[]}'
        )
        answer = provider_responses.extract_normalized_provider_answer("minimax", raw)
        self.assertIn("package provenance", answer)
        self.assertNotIn('"type":"object"', answer)

    def test_extract_normalized_provider_answer_skips_minimax_direct_schema_payload_echo(self) -> None:
        raw = (
            "<think>MiniMax echoed a compact schema before the answer.</think>\n\n"
            '{"answer":{"type":"string"},"stance":{"type":"string"},"confidenceNote":{"type":"string"}}\n\n'
            '{"answer":"Run the first-hour incident bridge with per-customer ownership.",'
            '"stance":"contain safely","confidenceNote":"medium"}'
        )
        answer = provider_responses.extract_normalized_provider_answer("minimax", raw)
        self.assertIn("per-customer ownership", answer)
        self.assertNotIn("{'type': 'string'}", answer)

    def test_extract_normalized_provider_answer_prefers_real_payload_over_placeholder(self) -> None:
        raw = (
            '<think>drafting...</think>\n'
            '{"answer":"...\\n...","stance":"...","confidenceNote":"..."}\n'
            '{"answer":"Run the first-hour incident bridge with per-customer ownership and evidence capture.",'
            '"stance":"contain safely","confidenceNote":"medium"}'
        )
        answer = provider_responses.extract_normalized_provider_answer("minimax", raw)
        self.assertIn("evidence capture", answer)
        self.assertNotEqual(answer.strip(), "...\n...")

    def test_parse_embedded_json_value_repairs_truncated_json(self) -> None:
        repaired = provider_responses.parse_embedded_json_value('{"outer":{"inner":"value"}')
        self.assertEqual(repaired, {"outer": {"inner": "value"}})

    def test_normalize_minimax_renders_flat_truncated_plan(self) -> None:
        payload = {
            "incident_id": "INC-TEST",
            "severity": "P1 - CRITICAL",
            "current_status": "ACTIVE_INVESTIGATION",
            "control_plane_trust_status": "UNTRUSTED",
            "confidence_level": "MEDIUM",
            "first_hour_objectives": ["Contain spread", "Preserve evidence"],
            "immediate_actions_0_to_15_minutes": {
                "revoke_automation_package": {
                    "action": "Suspend the package",
                    "rationale": "Stop the blast path",
                },
                "short_term_actions_15_to_30_minutes": {
                    "validate_package_revocation": {
                        "action": "Confirm the package is no longer queued",
                        "decision_gate": "If it is still queued, isolate harder",
                    },
                    "medium_term_actions_30_to_60_minutes": {
                        "prepare_tenant_communication": {
                            "action": "Prepare tenant-specific communication",
                            "caveats": ["Do not notify unaffected tenants"],
                        },
                        "risk_acceptances_needed": {
                            "overall_risk_posture": "Containment first",
                            "post_first_hour_immediate_priorities": ["Rotate credentials"],
                            "compliance_considerations": {
                                "potential_obligations": ["GDPR Article 33"],
                            },
                        },
                    },
                },
            },
        }
        raw = json.dumps(payload)
        truncated = raw[:-3]
        normalized = provider_responses.normalize_provider_response("minimax", truncated)
        self.assertEqual(normalized["sourceField"], "minimax.rendered_flat_plan")
        self.assertIn("## Immediate actions (0-15 minutes)", normalized["answer"])
        self.assertIn("Suspend the package", normalized["answer"])
        self.assertIn("GDPR Article 33", normalized["answer"])
        self.assertIn("Control-plane trust: UNTRUSTED", normalized["stance"])


if __name__ == "__main__":
    unittest.main()
