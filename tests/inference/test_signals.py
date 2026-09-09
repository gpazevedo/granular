"""Tests for the three structural inference signals."""

from __future__ import annotations

from granular.inference.signals.course_level import course_level_score
from granular.inference.signals.ku_cooccurrence import ku_cooccurrence_score
from granular.inference.signals.prerequisite_prior import PrerequisitePrior


class TestCourseLevelSignal:
    def test_higher_depends_on_lower(self):
        # 400-level depends on 200-level → positive
        score = course_level_score("48100", "25100")
        assert score > 0

    def test_lower_on_higher_is_zero(self):
        # 200-level "depends on" 400-level → 0 (never infer upward)
        score = course_level_score("25100", "48100")
        assert score == 0.0

    def test_same_level_is_zero(self):
        score = course_level_score("25100", "25200")
        assert score == 0.0


class TestPrerequisitePrior:
    def test_direct_prerequisite(self):
        prior = PrerequisitePrior({("CS-25100", "CS-18000")})
        assert prior.score("CS-25100", "CS-18000") == 1.0

    def test_no_relationship(self):
        prior = PrerequisitePrior({("CS-25100", "CS-18000")})
        assert prior.score("CS-25100", "CS-99999") == 0.0

    def test_transitive_depth_1(self):
        prior = PrerequisitePrior({
            ("CS-38100", "CS-25100"),
            ("CS-25100", "CS-18000"),
        })
        # 38100 → 18000 is transitive at depth 1
        score = prior.score("CS-38100", "CS-18000")
        assert score == 0.5

    def test_same_course_zero(self):
        prior = PrerequisitePrior({("CS-25100", "CS-18000")})
        assert prior.score("CS-25100", "CS-25100") == 0.0


class TestKUCooccurrence:
    def test_same_area_strong(self):
        assert ku_cooccurrence_score("AL", "AL") == 1.0

    def test_different_area_weaker(self):
        assert ku_cooccurrence_score("AL", "IS") == 0.5
