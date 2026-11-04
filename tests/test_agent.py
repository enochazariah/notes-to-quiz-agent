import unittest

from quizagent.agent import (QuizAgent, allocate, fix_scheme, is_grounded, make_batches,
                             make_report, theory_split, valid_mcq)
from quizagent.providers.base import LLMProvider, ProviderError
from quizagent.providers.mock import MockProvider
from quizagent.schemas import MCQ, MarkPoint, MCQBatch
from tests.helpers import sample_source


def mcq(**kw):
    base = dict(subtopic="s", question="Q?", options=["a1", "b2", "c3", "d4"], correct_index=0,
                explanation="e", why_tempting="w", source_quote="chlorophyll absorbs red and blue")
    base.update(kw)
    return MCQ(**base)


class HelperTests(unittest.TestCase):
    def test_allocate_spreads_evenly(self):
        self.assertEqual(allocate(10, ["a", "b", "c"]), [("a", 4), ("b", 3), ("c", 3)])
        self.assertEqual(allocate(2, ["a", "b", "c"]), [("a", 1), ("b", 1)])

    def test_batches_cap_size(self):
        batches = make_batches([("a", 12), ("b", 3)], 10)
        self.assertEqual([sum(x["count"] for x in b) for b in batches], [10, 5])

    def test_grounding(self):
        src = sample_source()
        self.assertTrue(is_grounded("Chlorophyll absorbs mostly red and blue light", src))
        self.assertFalse(is_grounded("Mitochondria are the powerhouse of the cell", src))
        self.assertFalse(is_grounded("too short", src))

    def test_valid_mcq(self):
        self.assertTrue(valid_mcq(mcq()))
        self.assertFalse(valid_mcq(mcq(options=["a", "a", "b", "c"])))
        self.assertFalse(valid_mcq(mcq(options=["a", "b", "c"])))
        self.assertFalse(valid_mcq(mcq(correct_index=4)))

    def test_theory_split(self):
        self.assertEqual(theory_split(20), [5, 5, 5, 5])
        self.assertEqual(theory_split(12), [5, 5, 2])
        self.assertEqual(theory_split(0), [])

    def test_fix_scheme_forces_exact_total(self):
        fixed = fix_scheme([MarkPoint(point="a", marks=3), MarkPoint(point="b", marks=3)], 5)
        self.assertEqual(sum(p.marks for p in fixed), 5)
        fixed = fix_scheme([MarkPoint(point=str(i), marks=1) for i in range(8)], 3)
        self.assertEqual((len(fixed), sum(p.marks for p in fixed)), (3, 3))
        self.assertEqual(fix_scheme([], 5), [])


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.src = sample_source()
        self.agent = QuizAgent(MockProvider(), seed=1)
        self.cmap = self.agent.analyze(self.src)

    def test_single_topic_notes_become_subtopics(self):
        self.assertGreaterEqual(len(self.cmap.subtopics), 2)

    def test_mcq_quiz_is_valid_and_unique(self):
        quiz = self.agent.build_quiz(self.src, self.cmap, 10, 0)
        self.assertEqual(len(quiz.mcqs), 10)
        self.assertEqual(len({q.question for q in quiz.mcqs}), 10)
        for q in quiz.mcqs:
            self.assertTrue(valid_mcq(q))

    def test_theory_is_exactly_20_marks(self):
        quiz = self.agent.build_quiz(self.src, self.cmap, 0, 20)
        self.assertEqual(sum(t.total_marks for t in quiz.theory), 20)
        self.assertEqual(len(quiz.theory), 4)

    def test_caps_are_enforced(self):
        quiz = self.agent.build_quiz(self.src, self.cmap, 500, 99)
        self.assertLessEqual(len(quiz.mcqs), 50)
        self.assertLessEqual(sum(t.total_marks for t in quiz.theory), 20)

    def test_small_notes_reduce_count_with_note(self):
        quiz = self.agent.build_quiz(self.src, self.cmap, 50, 0)
        self.assertLess(len(quiz.mcqs), 50)
        self.assertTrue(any("only support" in n for n in quiz.notes))

    def test_grading_and_report(self):
        quiz = self.agent.build_quiz(self.src, self.cmap, 5, 10)
        chosen = [q.correct_index for q in quiz.mcqs]
        grades = [self.agent.grade_theory(t, t.model_answer) for t in quiz.theory]
        report = make_report(quiz.mcqs, chosen, grades)
        self.assertEqual(report.percent, 100)
        self.assertEqual(report.theory_awarded, report.theory_total)
        self.assertEqual(report.weak_subtopics, [])

    def test_blank_and_wrong_answers_score_zero(self):
        quiz = self.agent.build_quiz(self.src, self.cmap, 5, 5)
        grades = [self.agent.grade_theory(t, "   ") for t in quiz.theory]
        self.assertEqual(sum(g.awarded for g in grades), 0)
        wrong = [(q.correct_index + 1) % 4 for q in quiz.mcqs]
        report = make_report(quiz.mcqs, wrong, grades)
        self.assertEqual(report.percent, 0)
        self.assertTrue(report.weak_subtopics)
        self.assertTrue(self.agent.reteach(self.src, self.cmap, report))

    def test_unanswered_mcq_counts_wrong(self):
        quiz = self.agent.build_quiz(self.src, self.cmap, 5, 0)
        report = make_report(quiz.mcqs, [None] * 5, [])
        self.assertEqual(report.mcq_correct, 0)

    def test_feedback_has_content(self):
        quiz = self.agent.build_quiz(self.src, self.cmap, 5, 0)
        report = make_report(quiz.mcqs, [q.correct_index for q in quiz.mcqs], [])
        fb = self.agent.feedback(report, "playful")
        self.assertTrue(fb.headline and fb.message)


class FakeBadProvider(LLMProvider):
    """Returns questions with ungrounded quotes (hallucination test) and fails feedback."""
    def __init__(self):
        self.mock = MockProvider()

    def generate(self, *, task, schema, prompt, source=None, params=None):
        if task == "feedback":
            raise ProviderError("down")
        res = self.mock.generate(task=task, schema=schema, prompt=prompt, source=source, params=params)
        if task == "mcq_batch":
            for q in res.questions:
                q.source_quote = "completely invented sentence about volcanoes and dragons"
        return res


class SafetyTests(unittest.TestCase):
    def test_ungrounded_questions_are_dropped_with_note(self):
        agent = QuizAgent(FakeBadProvider())
        src = sample_source()
        quiz = agent.build_quiz(src, agent.analyze(src), 5, 0)
        self.assertEqual(quiz.mcqs, [])
        self.assertTrue(any("could only verify" in n for n in quiz.notes))

    def test_feedback_falls_back_when_ai_fails(self):
        agent = QuizAgent(FakeBadProvider())
        src = sample_source()
        cmap = agent.analyze(src)
        quiz = agent.build_quiz(src, cmap, 0, 5)
        grades = [agent.grade_theory(t, "") for t in quiz.theory]
        fb = agent.feedback(make_report([], [], grades), "coach")
        self.assertIn("0%", fb.headline)


if __name__ == "__main__":
    unittest.main()
