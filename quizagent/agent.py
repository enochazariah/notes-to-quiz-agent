"""The quiz agent: map the notes -> write grounded questions -> mark -> coach.

The LLM never decides counts, marks arithmetic or file handling; code does. The LLM
reads, writes questions, judges answers, and writes feedback."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import prompts
from .pdf_input import SourceMaterial, normalize_tokens
from .providers.base import LLMProvider, ProviderError
from .schemas import (MCQ, ConceptMap, Feedback, MarkPoint, MCQBatch, PointVerdict, ReteachSet,
                      SubtopicReteach, TheoryBatch, TheoryQuestion, TheoryVerdict)

MAX_MCQ = 50
MAX_THEORY_MARKS = 20
BATCH_SIZE = 10
MARKS_PER_THEORY_QUESTION = 5
MAX_SUBTOPICS = 12
WEAK_THRESHOLD = 0.6
GROUNDING_RATIO = 0.8


# ---------- pure helpers (all unit-tested) ----------

def allocate(total: int, titles: list[str]) -> list[tuple[str, int]]:
    base, extra = divmod(total, len(titles))
    out = [(t, base + (1 if i < extra else 0)) for i, t in enumerate(titles)]
    return [(t, c) for t, c in out if c > 0]


def make_batches(allocs: list[tuple[str, int]], size: int = BATCH_SIZE) -> list[list[dict]]:
    flat = [t for t, c in allocs for _ in range(c)]
    batches = []
    for i in range(0, len(flat), size):
        counts: dict[str, int] = {}
        for t in flat[i:i + size]:
            counts[t] = counts.get(t, 0) + 1
        batches.append([{"subtopic": t, "count": c} for t, c in counts.items()])
    return batches


def is_grounded(quote: str, source: SourceMaterial) -> bool:
    """Cheap hallucination filter: at least 80% of the quote's words must occur in the notes.
    This checks vocabulary overlap, not that the exact sentence appears."""
    tokens = normalize_tokens(quote)
    if len(tokens) < 3:
        return False
    return sum(t in source.token_set for t in tokens) / len(tokens) >= GROUNDING_RATIO


def valid_mcq(q: MCQ) -> bool:
    if not q.question.strip() or len(q.options) != 4 or not 0 <= q.correct_index <= 3:
        return False
    opts = [" ".join(normalize_tokens(o)) for o in q.options]
    return all(opts) and len(set(opts)) == 4


def theory_split(total: int) -> list[int]:
    if total <= 0:
        return []
    full, rem = divmod(total, MARKS_PER_THEORY_QUESTION)
    return [MARKS_PER_THEORY_QUESTION] * full + ([rem] if rem else [])


def fix_scheme(scheme: list[MarkPoint], target: int) -> list[MarkPoint]:
    """Guarantee the mark scheme adds up to exactly `target` marks."""
    pts = [p for p in scheme if p.point.strip()]
    if not pts:
        return []
    if sum(p.marks for p in pts) == target and all(p.marks >= 1 for p in pts):
        return pts
    pts = pts[:target]
    base, extra = divmod(target, len(pts))
    return [MarkPoint(point=p.point, marks=base + (1 if i < extra else 0)) for i, p in enumerate(pts)]


# ---------- result containers ----------

@dataclass
class GeneratedQuiz:
    concept_map: ConceptMap
    mcqs: list[MCQ]
    theory: list[TheoryQuestion]
    notes: list[str] = field(default_factory=list)


@dataclass
class TheoryGrade:
    question: TheoryQuestion
    answer: str
    verdicts: list[PointVerdict]
    awarded: int
    total: int
    missed_summary: str


@dataclass
class QuizReport:
    mcq_correct: int
    mcq_total: int
    theory_awarded: int
    theory_total: int
    per_subtopic: dict[str, tuple[float, float]]

    @property
    def score(self) -> float:
        return self.mcq_correct + self.theory_awarded

    @property
    def possible(self) -> int:
        return self.mcq_total + self.theory_total

    @property
    def percent(self) -> int:
        return round(100 * self.score / self.possible) if self.possible else 0

    def _ranked(self) -> list[tuple[str, float]]:
        return sorted(((t, e / p) for t, (e, p) in self.per_subtopic.items() if p), key=lambda x: x[1])

    @property
    def weak_subtopics(self) -> list[str]:
        return [t for t, r in self._ranked() if r < WEAK_THRESHOLD]

    @property
    def strong_subtopics(self) -> list[str]:
        return [t for t, r in reversed(self._ranked()) if r >= 0.8]


def grade_mcqs(mcqs: list[MCQ], chosen: list[int | None]) -> list[bool]:
    return [c is not None and c == q.correct_index for q, c in zip(mcqs, chosen)]


def make_report(mcqs: list[MCQ], chosen: list[int | None], grades: list[TheoryGrade]) -> QuizReport:
    per: dict[str, list[float]] = {}
    correct_flags = grade_mcqs(mcqs, chosen)
    for q, ok in zip(mcqs, correct_flags):
        e = per.setdefault(q.subtopic, [0, 0])
        e[0] += 1 if ok else 0
        e[1] += 1
    for g in grades:
        e = per.setdefault(g.question.subtopic, [0, 0])
        e[0] += g.awarded
        e[1] += g.total
    return QuizReport(
        mcq_correct=sum(correct_flags), mcq_total=len(mcqs),
        theory_awarded=sum(g.awarded for g in grades), theory_total=sum(g.total for g in grades),
        per_subtopic={k: (v[0], v[1]) for k, v in per.items()},
    )


# ---------- the agent ----------

class QuizAgent:
    def __init__(self, provider: LLMProvider, *, seed: int | None = None):
        self.provider = provider
        self._rng = random.Random(seed)

    # step 1: understand the notes
    def analyze(self, source: SourceMaterial) -> ConceptMap:
        cmap = self.provider.generate(
            task="concept_map", schema=ConceptMap, prompt=prompts.concept_map_prompt(), source=source)
        seen, subs = set(), []
        for s in cmap.subtopics:
            key = s.title.strip().lower()
            points = [p for p in s.key_points if p.strip()]
            if key and key not in seen and points:
                seen.add(key)
                subs.append(s.model_copy(update={"key_points": points}))
        if not subs:
            raise ProviderError("I couldn't find enough structure in those notes to build a quiz.")
        return ConceptMap(main_topic=cmap.main_topic.strip() or source.filename, subtopics=subs[:MAX_SUBTOPICS])

    # step 2: write the quiz
    def build_quiz(self, source: SourceMaterial, cmap: ConceptMap, n_mcq: int, theory_marks: int) -> GeneratedQuiz:
        n_mcq = max(0, min(n_mcq, MAX_MCQ))
        theory_marks = max(0, min(theory_marks, MAX_THEORY_MARKS))
        notes: list[str] = []
        mcqs = self._make_mcqs(source, cmap, n_mcq, notes) if n_mcq else []
        theory = self._make_theory(source, cmap, theory_marks, notes) if theory_marks else []
        if source.truncated:
            notes.append("Your notes were very long, so only the first part was used.")
        return GeneratedQuiz(cmap, mcqs, theory, notes)

    def _snap_subtopic(self, name: str, titles: list[str]) -> str:
        lowered = {t.lower(): t for t in titles}
        return lowered.get(name.strip().lower(), name)

    def _make_mcqs(self, source, cmap, requested, notes) -> list[MCQ]:
        titles = [s.title for s in cmap.subtopics]
        capacity = min(MAX_MCQ, sum(max(1, len(s.key_points)) for s in cmap.subtopics) * 2)
        target = min(requested, capacity)
        if target < requested:
            notes.append(f"Your notes only support about {target} solid multiple-choice questions, "
                         f"so I built {target} instead of {requested}.")
        valid: list[MCQ] = []
        seen: set[str] = set()
        sub_dump = [s.model_dump() for s in cmap.subtopics]
        for _round in range(2):  # round 2 tops up any shortfall
            needed = target - len(valid)
            if needed <= 0:
                break
            for batch in make_batches(allocate(needed, titles)):
                avoid = [q.question for q in valid]
                res = self.provider.generate(
                    task="mcq_batch", schema=MCQBatch, prompt=prompts.mcq_prompt(batch, avoid),
                    source=source, params={"allocations": batch, "subtopics": sub_dump, "avoid": avoid})
                for q in res.questions:
                    key = " ".join(normalize_tokens(q.question))
                    if key in seen or not valid_mcq(q) or not is_grounded(q.source_quote, source):
                        continue
                    seen.add(key)
                    valid.append(self._shuffled(q.model_copy(
                        update={"subtopic": self._snap_subtopic(q.subtopic, titles)})))
                    if len(valid) >= target:
                        break
                if len(valid) >= target:
                    break
        if len(valid) < target:
            notes.append(f"I could only verify {len(valid)} good multiple-choice questions against your notes.")
        return valid[:target]

    def _shuffled(self, q: MCQ) -> MCQ:
        correct = q.options[q.correct_index]
        opts = list(q.options)
        self._rng.shuffle(opts)
        return q.model_copy(update={"options": opts, "correct_index": opts.index(correct)})

    def _make_theory(self, source, cmap, total_marks, notes) -> list[TheoryQuestion]:
        titles = [s.title for s in cmap.subtopics]
        allocs = [{"subtopic": titles[i % len(titles)], "marks": m} for i, m in enumerate(theory_split(total_marks))]
        res = self.provider.generate(
            task="theory_batch", schema=TheoryBatch, prompt=prompts.theory_prompt(allocs), source=source,
            params={"allocations": allocs, "subtopics": [s.model_dump() for s in cmap.subtopics]})
        out: list[TheoryQuestion] = []
        for alloc, q in zip(allocs, res.questions):
            scheme = fix_scheme(q.mark_scheme, alloc["marks"])
            if not q.question.strip() or not scheme or not is_grounded(q.source_quote, source):
                continue
            out.append(q.model_copy(update={"mark_scheme": scheme, "subtopic": alloc["subtopic"]}))
        got = sum(q.total_marks for q in out)
        if got != total_marks:
            notes.append(f"I could only verify {got} of the {total_marks} theory marks against your notes.")
        return out

    # step 3: mark
    def grade_theory(self, q: TheoryQuestion, answer: str) -> TheoryGrade:
        answer = answer.strip()
        if not answer:
            verdicts = [PointVerdict(point=p.point, earned=False, comment="No answer given.") for p in q.mark_scheme]
            missed = "You left this one blank: try writing even a rough answer next time."
        else:
            res = self.provider.generate(
                task="grade_theory", schema=TheoryVerdict, prompt=prompts.grade_prompt(q.model_dump(), answer),
                params={"question": q.model_dump(), "answer": answer})
            verdicts = list(res.verdicts)[: len(q.mark_scheme)]
            while len(verdicts) < len(q.mark_scheme):
                verdicts.append(PointVerdict(point=q.mark_scheme[len(verdicts)].point, earned=False, comment="Not covered."))
            missed = res.missed_summary
        awarded = sum(mp.marks for mp, v in zip(q.mark_scheme, verdicts) if v.earned)
        return TheoryGrade(q, answer, verdicts, awarded, q.total_marks, missed)

    # step 4: coach (degrades gracefully if the AI is unavailable)
    def feedback(self, report: QuizReport, style: str) -> Feedback:
        summary = {
            "percent": report.percent,
            "mcq": f"{report.mcq_correct}/{report.mcq_total}",
            "theory": f"{report.theory_awarded}/{report.theory_total}",
            "weak_subtopics": report.weak_subtopics[:3],
            "strong_subtopics": report.strong_subtopics[:3],
        }
        try:
            return self.provider.generate(
                task="feedback", schema=Feedback, prompt=prompts.feedback_prompt(summary, style),
                params={**summary, "style": style})
        except ProviderError:
            return Feedback(headline=f"You scored {report.percent}%", message="Review the explanations below, then try again.",
                            strengths=[], next_steps=[f"Revise: {t}" for t in report.weak_subtopics[:3]])

    def reteach(self, source: SourceMaterial, cmap: ConceptMap, report: QuizReport) -> list[SubtopicReteach]:
        by_title = {s.title: s for s in cmap.subtopics}
        weak = [by_title[t] for t in report.weak_subtopics[:3] if t in by_title]
        if not weak:
            return []
        subs = [{"title": s.title, "key_points": s.key_points} for s in weak]
        try:
            res = self.provider.generate(
                task="reteach", schema=ReteachSet, prompt=prompts.reteach_prompt(subs),
                source=source, params={"subtopics": subs})
            return res.items
        except ProviderError:
            return [SubtopicReteach(subtopic=s.title, explanation=" ".join(s.key_points)) for s in weak]
