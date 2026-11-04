"""Offline mock provider: deterministic, no network, no key. Used for demo mode and tests.
It is NOT real AI: it recombines sentences from the notes."""
from __future__ import annotations

import itertools
import math
import re
from typing import Any

from ..pdf_input import SourceMaterial, normalize_tokens
from .base import LLMProvider, ProviderError, T

_FALLBACK = [
    "Demo mode could not find any text in these notes to build questions from.",
    "Demo mode recombines sentences from your notes, so it needs text to work with.",
    "Add a real AWS Bedrock token to get questions written by an AI model.",
    "Demo mode exists so you can test the full flow without any API key.",
    "Real AI mode writes deeper questions and grades theory answers by meaning.",
    "Text-based PDFs work best, because the text is read directly from the file.",
]


def _sentences(source: SourceMaterial | None) -> list[str]:
    if source is None or not source.text:
        return list(_FALLBACK)
    parts = re.split(r"(?<=[.!?])\s+", " ".join(source.text.split()))
    out = list(dict.fromkeys(p.strip() for p in parts if len(p.strip()) > 25))
    return out or list(_FALLBACK)


def _head(sentence: str, n: int = 5) -> str:
    return " ".join(sentence.split()[:n]).rstrip(".,;:!?")


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self) -> None:
        self._counter = itertools.count(1)

    def generate(self, *, task: str, schema: type[T], prompt: str,
                 source: SourceMaterial | None = None, params: dict[str, Any] | None = None) -> T:
        handler = getattr(self, f"_{task}", None)
        if handler is None:
            raise ProviderError(f"Mock provider cannot handle task '{task}'.")
        return schema.model_validate(handler(source, params or {}))

    def _concept_map(self, source, params):
        sents = _sentences(source)
        n = max(1, min(4, len(sents) // 3))
        size = math.ceil(len(sents) / n)
        chunks = [sents[i:i + size] for i in range(0, len(sents), size)]
        subs = [
            {"title": f"{i + 1}. {_head(c[0])}", "summary": c[0], "key_points": c[:3]}
            for i, c in enumerate(chunks)
        ]
        return {"main_topic": _head(sents[0], 6), "subtopics": subs}

    def _mcq_batch(self, source, params):
        subs = {s["title"]: s for s in params["subtopics"]}
        all_points = list(dict.fromkeys(p for s in subs.values() for p in s["key_points"]))
        fillers = ["The notes say the opposite of this.", "This is not mentioned in the notes.",
                   "The notes only mention this in passing, as an exception."]
        questions = []
        for alloc in params["allocations"]:
            title = alloc["subtopic"]
            pool = subs[title]["key_points"] if title in subs else all_points
            for k in range(alloc["count"]):
                correct = pool[k % len(pool)]
                distractors = ([p for p in all_points if p != correct] + fillers)[:3]
                opts = [correct] + distractors
                rot = k % 4
                opts = opts[rot:] + opts[:rot]
                questions.append({
                    "subtopic": title,
                    "question": f'Which statement about "{title}" is supported by your notes? (#{next(self._counter)})',
                    "options": opts,
                    "correct_index": opts.index(correct),
                    "explanation": f"The notes state this directly: {correct}",
                    "why_tempting": "The other options come from different parts of the notes, so they sound familiar but answer a different point.",
                    "source_quote": correct,
                })
        return {"questions": questions}

    def _theory_batch(self, source, params):
        subs = {s["title"]: s for s in params["subtopics"]}
        all_points = list(dict.fromkeys(p for s in subs.values() for p in s["key_points"]))
        questions = []
        for alloc in params["allocations"]:
            title, marks = alloc["subtopic"], alloc["marks"]
            pts = subs[title]["key_points"] if title in subs else all_points
            n = max(1, min(len(pts), marks))
            base, extra = divmod(marks, n)
            questions.append({
                "subtopic": title,
                "question": f'Explain, in your own words, the key ideas of "{title}". (#{next(self._counter)})',
                "model_answer": " ".join(pts[:n]),
                "mark_scheme": [{"point": pts[i], "marks": base + (1 if i < extra else 0)} for i in range(n)],
                "source_quote": pts[0],
            })
        return {"questions": questions}

    def _grade_theory(self, source, params):
        answer_tokens = set(normalize_tokens(params["answer"]))
        verdicts = []
        for mp in params["question"]["mark_scheme"]:
            words = [w for w in normalize_tokens(mp["point"]) if len(w) > 3]
            hit = bool(words) and sum(w in answer_tokens for w in words) / len(words) >= 0.4
            verdicts.append({
                "point": mp["point"], "earned": hit,
                "comment": "Covered." if hit else "Not clearly covered in your answer.",
            })
        missed = [v["point"] for v in verdicts if not v["earned"]]
        return {"verdicts": verdicts,
                "missed_summary": "Revise: " + "; ".join(missed) if missed else "Nothing missed."}

    def _feedback(self, source, params):
        pct = params["percent"]
        weak = params.get("weak_subtopics", [])
        strong = params.get("strong_subtopics", [])
        if pct >= 80:
            headline = "Strong work!"
        elif pct >= 50:
            headline = "Solid foundation, a few gaps to close"
        else:
            headline = "Good start: now the real learning begins"
        return {
            "headline": headline,
            "message": f"You scored {pct}%. (Demo-mode feedback; real AI mode writes it in your chosen style.)",
            "strengths": [f"Good grip on {s}" for s in strong[:3]] or ["You finished the whole quiz."],
            "next_steps": [f"Re-read the notes on {w}, then retry" for w in weak[:3]] or ["Try a bigger quiz next."],
        }

    def _reteach(self, source, params):
        return {"items": [
            {"subtopic": s["title"], "explanation": " ".join(s["key_points"])} for s in params["subtopics"]
        ]}
