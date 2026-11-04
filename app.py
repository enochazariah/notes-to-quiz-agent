"""Notes to Quiz: Streamlit front end."""
from __future__ import annotations

import hmac

import streamlit as st

from quizagent import ui_theme as ui
from quizagent.agent import MAX_MCQ, MAX_THEORY_MARKS, QuizAgent, make_report
from quizagent.config import load_settings
from quizagent.pdf_input import PdfError, load_pdf
from quizagent.providers.base import ProviderError
from quizagent.providers.factory import build_provider
from quizagent.usage import DailyCounter

st.set_page_config(page_title="Notes to Quiz", page_icon="📝", layout="centered")
SETTINGS = load_settings()
ss = st.session_state
ui.inject_css(st)


@st.cache_resource
def get_agent() -> QuizAgent:
    return QuizAgent(build_provider(SETTINGS))


@st.cache_resource
def get_counter() -> DailyCounter:
    return DailyCounter(SETTINGS.max_daily_builds)


def agent_or_stop() -> QuizAgent:
    try:
        return get_agent()
    except Exception:  # noqa: BLE001 - never show raw errors (they could contain settings)
        st.error("Couldn't start the AI connection. Check AWS_BEARER_TOKEN_BEDROCK, AWS_REGION and "
                 "BEDROCK_MODEL_ID in .env (or in Render's Environment tab).")
        st.stop()


def header(step: int) -> None:
    st.markdown(ui.hero("Demo mode" if SETTINGS.use_mock else "Amazon Bedrock", SETTINGS.use_mock),
                unsafe_allow_html=True)
    st.markdown(ui.stepper(step), unsafe_allow_html=True)
    if SETTINGS.use_mock:
        st.warning("Demo mode: no AWS_BEARER_TOKEN_BEDROCK found, so questions come from a simple offline "
                   "mock, not real AI.")


def gate() -> None:
    if not SETTINGS.access_code or ss.get("authed"):
        return
    code = st.text_input("Access code", type="password")
    if code and hmac.compare_digest(code.encode(), SETTINGS.access_code.encode()):
        ss["authed"] = True
        st.rerun()
    elif code:
        st.error("Wrong access code.")
    st.stop()


def reset() -> None:
    for key in [k for k in ss.keys() if k not in ("authed", "builds")]:
        del ss[key]


def render_setup() -> None:
    with st.container(border=True):
        file = st.file_uploader(
            "Upload your notes (PDF)", type=["pdf"],
            help=f"Text-based PDF, up to {SETTINGS.max_pdf_mb} MB and {SETTINGS.max_pdf_pages} pages. "
                 "Scans and image-only PDFs can't be read.")
        left, right = st.columns(2)
        with left:
            with_mcq = st.toggle("Multiple-choice questions", value=True)
            n_mcq = st.slider("How many?", 5, MAX_MCQ, 10, step=5, disabled=not with_mcq)
        with right:
            theory_marks = st.slider("Theory marks (written answers)", 0, MAX_THEORY_MARKS, 10)
            style_label = st.radio("Feedback style", ["Coach", "Friendly", "Playful"], horizontal=True)
        clicked = st.button("Build quiz", type="primary", disabled=file is None)

    if not clicked:
        return
    if not with_mcq and theory_marks == 0:
        st.error("Choose multiple-choice questions, theory marks, or both.")
        return
    if ss.get("builds", 0) >= SETTINGS.max_builds_per_session:
        st.error("You've reached the limit of quizzes for this session.")
        return
    try:
        source = load_pdf(file.getvalue(), file.name,
                          max_mb=SETTINGS.max_pdf_mb, max_pages=SETTINGS.max_pdf_pages)
    except PdfError as exc:
        st.error(str(exc))
        return
    if not get_counter().try_consume():
        st.error("The app has reached its daily limit. Try again tomorrow.")
        return
    agent = agent_or_stop()
    try:
        with st.status("Reading your notes...", expanded=True) as status:
            cmap = agent.analyze(source)
            st.write(f"Found {len(cmap.subtopics)} subtopics in '{cmap.main_topic}'.")
            st.write("Writing questions and checking them against your notes...")
            quiz = agent.build_quiz(source, cmap, n_mcq if with_mcq else 0, theory_marks)
            status.update(label="Quiz ready", state="complete")
    except ProviderError as exc:
        st.error(str(exc))
        return
    if not quiz.mcqs and not quiz.theory:
        st.error("I couldn't build questions that match those notes. Try notes with more text.")
        return
    ss.update(source=source, quiz=quiz, style=style_label.lower(), builds=ss.get("builds", 0) + 1)
    st.rerun()


def render_quiz() -> None:
    quiz = ss["quiz"]
    st.markdown(ui.topic(quiz.concept_map.main_topic), unsafe_allow_html=True)
    st.markdown(ui.chips([s.title for s in quiz.concept_map.subtopics]), unsafe_allow_html=True)
    for note in quiz.notes:
        st.info(note)

    with st.form("quiz_form", border=False):
        for i, q in enumerate(quiz.mcqs):
            with st.container(border=True):
                st.markdown(ui.question_meta(f"Question {i + 1}", q.subtopic), unsafe_allow_html=True)
                st.markdown(f"**{q.question}**")
                st.radio("Choose one", q.options, index=None, key=f"mcq_{i}", label_visibility="collapsed")
        for j, t in enumerate(quiz.theory):
            with st.container(border=True):
                st.markdown(ui.question_meta(f"Theory {j + 1}", t.subtopic, t.total_marks), unsafe_allow_html=True)
                st.markdown(f"**{t.question}**")
                st.text_area("Your answer", key=f"th_{j}", height=140, label_visibility="collapsed",
                             placeholder="Write your answer in your own words.")
        submitted = st.form_submit_button("Mark my answers", type="primary")

    if submitted:
        agent = agent_or_stop()
        chosen = [q.options.index(ss[f"mcq_{i}"]) if ss.get(f"mcq_{i}") is not None else None
                  for i, q in enumerate(quiz.mcqs)]
        try:
            with st.spinner("Marking your answers..."):
                grades = [agent.grade_theory(t, ss.get(f"th_{j}", "")) for j, t in enumerate(quiz.theory)]
                report = make_report(quiz.mcqs, chosen, grades)
                feedback = agent.feedback(report, ss["style"])
                reteach = agent.reteach(ss["source"], quiz.concept_map, report)
        except ProviderError as exc:
            st.error(str(exc))
            return
        ss.update(chosen=chosen, grades=grades, report=report, feedback=feedback, reteach=reteach)
        st.rerun()


def render_results() -> None:
    quiz, report, fb = ss["quiz"], ss["report"], ss["feedback"]
    st.markdown(ui.score_card(report.percent, fb.headline, fb.message), unsafe_allow_html=True)
    if report.percent >= 80 and not ss.get("celebrated"):
        ss["celebrated"] = True
        st.balloons()
    c1, c2 = st.columns(2)
    c1.metric("Multiple choice", f"{report.mcq_correct}/{report.mcq_total}")
    c2.metric("Theory marks", f"{report.theory_awarded}/{report.theory_total}")

    cards = [(t, x) for t, x in (("What you did well", fb.strengths), ("Your next steps", fb.next_steps)) if x]
    if cards:
        for col, (title, items) in zip(st.columns(len(cards)), cards):
            col.markdown(ui.list_card(title, items), unsafe_allow_html=True)

    if ss["reteach"]:
        st.subheader("Let's go over these again")
        for item in ss["reteach"]:
            with st.expander(item.subtopic):
                st.write(item.explanation)

    st.subheader("Review your answers")
    for i, q in enumerate(quiz.mcqs):
        picked = ss["chosen"][i]
        ok = picked == q.correct_index
        with st.expander(f"{'✅' if ok else '❌'} Question {i + 1}: {q.question}"):
            st.write(f"Your answer: {q.options[picked] if picked is not None else '(none)'}")
            st.write(f"Correct answer: {q.options[q.correct_index]}")
            st.write(q.explanation)
            if not ok:
                st.caption(q.why_tempting)
    for j, g in enumerate(ss["grades"]):
        with st.expander(f"Theory {j + 1}: {g.awarded}/{g.total} marks"):
            st.markdown(f"**{g.question.question}**")
            st.write(f"Your answer: {g.answer or '(blank)'}")
            for point, v in zip(g.question.mark_scheme, g.verdicts):
                st.markdown(f"{'✅' if v.earned else '⬜'} {point.point} ({point.marks}): {v.comment}")
            st.caption(g.missed_summary)
            st.markdown(f"**Model answer:** {g.question.model_answer}")

    if st.button("Use different notes"):
        reset()
        st.rerun()


step = 1 if ss.get("quiz") is None else (2 if ss.get("report") is None else 3)
header(step)
gate()
if step == 1:
    render_setup()
elif step == 2:
    render_quiz()
else:
    render_results()
