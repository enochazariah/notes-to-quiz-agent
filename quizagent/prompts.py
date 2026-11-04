"""All prompt text in one place."""
from __future__ import annotations

import json

SYSTEM_PROMPT = """You are a careful study-coach engine that turns a student's own notes into quizzes.
Rules you never break:
- Use ONLY the supplied notes. Never add outside facts, and never invent content.
- Test understanding (why / how / what happens if), not trivia or page numbers.
- Every question must include a source_quote: a short passage (max 25 words) copied word-for-word from the notes that supports it.
- Be accurate and honest. Encouraging tone never means inflating a result.
- Return only the JSON that matches the requested schema."""

STYLES = {
    "coach": "a warm, upbeat coach who celebrates progress and always points to the next step",
    "friendly": "a kind, encouraging study buddy who keeps things simple and reassuring",
    "playful": "a playful, witty mentor who uses light humour and a fresh metaphor or two, never sarcasm at the student's expense",
}


def concept_map_prompt() -> str:
    return (
        "Read the notes and break them into a concept map: the main topic, then 3 to 10 subtopics. "
        "Even if the notes cover a single subject, split it into the logical sub-ideas a learner must "
        "understand (definitions, process steps, causes and effects, examples, common confusions). "
        "For each subtopic give a one-sentence summary and 2 to 6 key points, each a full sentence "
        "taken from or closely based on the notes. Do not create subtopics the notes cannot support."
    )


def mcq_prompt(allocations: list[dict], avoid: list[str]) -> str:
    return (
        "Write multiple-choice questions from the notes, exactly as allocated below "
        "(subtopic and number of questions):\n"
        f"{json.dumps(allocations)}\n"
        "For each question: exactly 4 distinct options, one correct (correct_index is 0-3), "
        "plausible distractors built from real misconceptions or neighbouring ideas in the notes, "
        "an explanation of why the correct answer is right, why_tempting (why the most tempting wrong "
        "option is wrong), and a verbatim source_quote. Do not repeat or rephrase these existing questions: "
        f"{json.dumps(avoid[:60])}"
    )


def theory_prompt(allocations: list[dict]) -> str:
    return (
        "Write theory (written-answer) questions from the notes, one per allocation below. "
        "Each allocation gives the subtopic and the exact total marks for that question:\n"
        f"{json.dumps(allocations)}\n"
        "For each question give a model_answer and a mark_scheme: a list of distinct key points, "
        "each worth 1 or more marks, whose marks add up to EXACTLY the allocated marks. "
        "Add a verbatim source_quote."
    )


def grade_prompt(question: dict, answer: str) -> str:
    return (
        "Mark the student's answer against the mark scheme. For EACH mark-scheme point, in the same order, "
        "decide if the answer clearly covers it (earned true/false) and give a one-sentence comment "
        "(what they got right, or what is missing). Accept correct ideas in different words; do not give "
        "marks for vague or wrong statements. Then give missed_summary: one sentence on what to revise.\n"
        f"QUESTION: {question['question']}\n"
        f"MARK SCHEME: {json.dumps(question['mark_scheme'])}\n"
        f"STUDENT ANSWER: {answer}"
    )


def feedback_prompt(summary: dict, style: str) -> str:
    persona = STYLES.get(style, STYLES["coach"])
    return (
        f"Write feedback for a student as {persona}. Results (JSON): {json.dumps(summary)}.\n"
        "Rules: be specific to the subtopics named in the results; celebrate genuine strengths; "
        "frame weak subtopics as the next level to unlock, never as failure; stay honest (do not call a "
        "weak result great); keep it under 120 words. Return: a short headline, a message, "
        "strengths (1-3 items), and next_steps (1-3 concrete study actions)."
    )


def reteach_prompt(subtopics: list[dict]) -> str:
    return (
        "For each subtopic below, write a short, clear re-explanation (3-5 sentences, simple words, "
        "one concrete example if the notes have one) so a student who got it wrong can understand it. "
        f"Use only the notes. Subtopics: {json.dumps(subtopics)}"
    )
