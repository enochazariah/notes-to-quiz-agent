"""Pydantic schemas. Kept free of constraints (min/max, defaults) so they convert cleanly
to a Bedrock tool schema; real validation happens in agent.py."""
from __future__ import annotations

from pydantic import BaseModel


class Subtopic(BaseModel):
    title: str
    summary: str
    key_points: list[str]


class ConceptMap(BaseModel):
    main_topic: str
    subtopics: list[Subtopic]


class MCQ(BaseModel):
    subtopic: str
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    why_tempting: str
    source_quote: str


class MCQBatch(BaseModel):
    questions: list[MCQ]


class MarkPoint(BaseModel):
    point: str
    marks: int


class TheoryQuestion(BaseModel):
    subtopic: str
    question: str
    model_answer: str
    mark_scheme: list[MarkPoint]
    source_quote: str

    @property
    def total_marks(self) -> int:
        return sum(p.marks for p in self.mark_scheme)


class TheoryBatch(BaseModel):
    questions: list[TheoryQuestion]


class PointVerdict(BaseModel):
    point: str
    earned: bool
    comment: str


class TheoryVerdict(BaseModel):
    verdicts: list[PointVerdict]
    missed_summary: str


class Feedback(BaseModel):
    headline: str
    message: str
    strengths: list[str]
    next_steps: list[str]


class SubtopicReteach(BaseModel):
    subtopic: str
    explanation: str


class ReteachSet(BaseModel):
    items: list[SubtopicReteach]
