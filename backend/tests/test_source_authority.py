import unittest

from backend.app import source_authority
from runtime.engine import activate_research_for_recall


class SourceAuthorityTests(unittest.TestCase):
    def test_anonymous_imageboard_is_excluded_from_evidence_and_memory(self) -> None:
        grade = source_authority.grade_source("https://boards.4chan.org/g/thread/123")

        self.assertEqual(grade["sourceClass"], "anonymous_imageboard")
        self.assertEqual(grade["evidenceRole"], "excluded")
        self.assertFalse(grade["evidenceEligible"])
        self.assertFalse(grade["standaloneEligible"])
        self.assertFalse(grade["memoryEligible"])

    def test_arxiv_is_admissible_preprint_evidence_not_automatic_truth(self) -> None:
        grade = source_authority.grade_source("https://arxiv.org/abs/2608.01234")

        self.assertEqual(grade["sourceClass"], "research_preprint")
        self.assertTrue(grade["evidenceEligible"])
        self.assertTrue(grade["memoryEligible"])
        self.assertFalse(grade["standaloneEligible"])
        self.assertTrue(grade["requiresCorroboration"])
        self.assertIn("preprint", grade["caveat"].lower())

    def test_official_standard_source_can_stand_alone_with_scope_checks(self) -> None:
        grade = source_authority.grade_source("https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final")

        self.assertEqual(grade["sourceClass"], "official_or_standards_source")
        self.assertTrue(grade["evidenceEligible"])
        self.assertTrue(grade["standaloneEligible"])
        self.assertTrue(grade["memoryEligible"])

    def test_unknown_web_source_can_be_inspected_but_not_retained_without_classification(self) -> None:
        grade = source_authority.grade_source("https://example.test/article")

        self.assertEqual(grade["sourceClass"], "general_web_source")
        self.assertTrue(grade["evidenceEligible"])
        self.assertFalse(grade["standaloneEligible"])
        self.assertFalse(grade["memoryEligible"])

    def test_no_memory_automatically_enables_research(self) -> None:
        policy = activate_research_for_recall(
            {"enabled": False, "automaticOnMemoryMiss": True, "externalWebAccess": True},
            {"resultCount": 0},
        )

        self.assertTrue(policy["enabled"])
        self.assertTrue(policy["autoTriggered"])
        self.assertEqual(policy["knowledgeMode"], "automatic_research")

    def test_retrieved_memory_does_not_force_research(self) -> None:
        policy = activate_research_for_recall(
            {"enabled": False, "automaticOnMemoryMiss": True, "externalWebAccess": True},
            {"resultCount": 2},
        )

        self.assertFalse(policy["enabled"])
        self.assertFalse(policy["autoTriggered"])
        self.assertEqual(policy["knowledgeMode"], "retrieved_memory")

    def test_offline_no_memory_is_explicitly_unverified_model_prior(self) -> None:
        policy = activate_research_for_recall(
            {"enabled": False, "automaticOnMemoryMiss": True, "externalWebAccess": False},
            {"resultCount": 0},
        )

        self.assertFalse(policy["enabled"])
        self.assertFalse(policy["autoTriggered"])
        self.assertEqual(policy["knowledgeMode"], "unverified_model_prior")


if __name__ == "__main__":
    unittest.main()
