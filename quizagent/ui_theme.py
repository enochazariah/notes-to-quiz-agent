"""Look and feel: a ruled-notebook study desk. Cool paper, pen-blue ink, a highlighter accent,
and a graded-exam score circled in pen colour.

All text that comes from the AI or the user is HTML-escaped before it enters markup."""
from __future__ import annotations

import html

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&display=swap');
:root{--paper:#F3F6FD;--sheet:#FFFFFF;--ink:#14213D;--soft:#4A5878;--pen:#3050D8;--pen-soft:#E4EAFF;--marker:#FFE45C;--ok:#118A5B;--ok-soft:#DDF5EA;--bad:#D6383E;--bad-soft:#FDE6E7;--rule:#E1E8F7;}
[data-testid="stAppViewContainer"]{background-color:var(--paper);background-image:linear-gradient(var(--rule) 1px,transparent 1px);background-size:100% 32px;}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stMainBlockContainer"]{max-width:760px;padding:2.2rem 1rem 4rem;}
footer,[data-testid="stDecoration"]{display:none;}
.stApp p,.stApp label,.stApp li,.stApp button,.stApp textarea,.stApp input,.stApp small{font-family:'Atkinson Hyperlegible',system-ui,-apple-system,'Segoe UI',sans-serif;color:var(--ink);}
.stApp h1,.stApp h2,.stApp h3,.nq-title,.nq-score-num{font-family:'Bricolage Grotesque','Atkinson Hyperlegible',system-ui,sans-serif;color:var(--ink);}
.nq-hero{margin:0 0 .4rem;}
.nq-title{font-size:clamp(2.3rem,7vw,3.5rem);font-weight:800;letter-spacing:-.025em;line-height:1.02;margin:0;}
.nq-lede{font-size:1.08rem;color:var(--soft);max-width:34rem;margin:.6rem 0 .8rem;line-height:1.5;}
.nq-badge{display:inline-block;font-size:.85rem;font-weight:700;padding:.18rem .75rem;border:1.5px solid var(--ink);border-radius:999px;}
.nq-badge.demo{background:var(--marker);}
.nq-badge.live{background:var(--pen-soft);}
.nq-steps{display:flex;gap:.5rem;flex-wrap:wrap;margin:1rem 0 1.4rem;}
.nq-step{font-size:.95rem;padding:.3rem .9rem;border-radius:8px;border:1.5px solid var(--rule);background:var(--sheet);color:var(--soft);}
.nq-step b{margin-right:.4rem;}
.nq-step.on{border-color:var(--ink);background:var(--marker);color:var(--ink);font-weight:700;}
.nq-step.done{border-color:var(--pen);color:var(--pen);}
.nq-topic{font-family:'Bricolage Grotesque',sans-serif;font-weight:800;font-size:1.7rem;margin:.2rem 0 .5rem;color:var(--ink);}
.nq-chip{display:inline-block;padding:.2rem .75rem;margin:0 .4rem .4rem 0;border:1.5px solid var(--ink);border-radius:999px;background:var(--pen-soft);font-size:.9rem;color:var(--ink);}
.nq-meta{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:.35rem;}
.nq-qnum{font-weight:700;color:var(--pen);}
.nq-tag{font-size:.82rem;padding:.1rem .6rem;border-radius:999px;background:var(--pen-soft);color:var(--ink);}
.nq-marks{font-size:.82rem;font-weight:700;padding:.1rem .6rem;border-radius:6px;background:var(--marker);border:1.5px solid var(--ink);color:var(--ink);}
[data-testid="stVerticalBlockBorderWrapper"]{background:var(--sheet);border-radius:12px;}
[data-testid="stForm"]{background:transparent;border:0;padding:0;}
[data-testid="stFileUploaderDropzone"]{background:var(--sheet);border:2px dashed var(--pen);border-radius:12px;}
[data-testid="stBaseButton-primary"],[data-testid="stBaseButton-primaryFormSubmit"]{background:var(--pen);color:#fff;border:1.5px solid var(--ink);border-radius:10px;font-weight:700;box-shadow:3px 3px 0 var(--ink);transition:transform .08s,box-shadow .08s;}
[data-testid="stBaseButton-primary"] p,[data-testid="stBaseButton-primaryFormSubmit"] p{color:#fff;}
[data-testid="stBaseButton-primary"]:hover,[data-testid="stBaseButton-primaryFormSubmit"]:hover{transform:translate(1px,1px);box-shadow:2px 2px 0 var(--ink);}
[data-testid="stBaseButton-secondary"]{border:1.5px solid var(--ink);border-radius:10px;background:var(--sheet);}
.nq-score{display:flex;gap:1.4rem;align-items:center;background:var(--sheet);border:2px solid var(--ink);border-radius:14px;padding:1.2rem 1.4rem;box-shadow:6px 6px 0 var(--marker);margin:.4rem 0 1.2rem;}
.nq-circle{flex:0 0 auto;width:7.2rem;height:6.4rem;display:flex;align-items:center;justify-content:center;border:4px solid var(--tone);border-radius:52% 48% 55% 45% / 48% 54% 46% 52%;transform:rotate(-5deg);}
.nq-score-num{font-size:2.7rem;font-weight:800;color:var(--tone);line-height:1;}
.nq-score-num small{font-size:1.1rem;font-weight:700;}
.nq-score h2{margin:0 0 .3rem;font-size:1.6rem;}
.nq-score p{margin:0;color:var(--soft);line-height:1.5;}
.nq-note{background:var(--sheet);border-left:5px solid var(--pen);border-radius:0 10px 10px 0;padding:.8rem 1rem;margin:.4rem 0 1rem;line-height:1.5;color:var(--ink);}
.nq-card{background:var(--sheet);border:1.5px solid var(--ink);border-radius:12px;padding:.8rem 1.1rem;height:100%;}
.nq-card h4{margin:0 0 .4rem;font-family:'Bricolage Grotesque',sans-serif;font-size:1.05rem;}
.nq-card ul{margin:0;padding-left:1.1rem;}
.nq-card li{margin:.2rem 0;color:var(--ink);}
:focus-visible{outline:3px solid var(--pen);outline-offset:2px;}
@media (max-width:640px){.nq-score{flex-direction:column;align-items:flex-start;}}
@media (prefers-reduced-motion:reduce){*{transition:none!important;}}
"""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def inject_css(st) -> None:
    css = "\n".join(line.strip() for line in CSS.splitlines() if line.strip())
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def hero(badge_text: str, demo: bool) -> str:
    kind = "demo" if demo else "live"
    return (f'<div class="nq-hero"><h1 class="nq-title">Notes to Quiz</h1>'
            f'<p class="nq-lede">Upload your notes. I split them into topics, quiz you on each one, '
            f'and coach you through the gaps. Your files are read in memory and never stored.</p>'
            f'<span class="nq-badge {kind}">{esc(badge_text)}</span></div>')


def stepper(active: int) -> str:
    names = ["Upload", "Answer", "Results"]
    items = []
    for i, name in enumerate(names, start=1):
        state = "on" if i == active else ("done" if i < active else "")
        items.append(f'<span class="nq-step {state}"><b>{i}</b>{esc(name)}</span>')
    return f'<div class="nq-steps">{"".join(items)}</div>'


def topic(title: str) -> str:
    return f'<div class="nq-topic">{esc(title)}</div>'


def chips(items: list[str]) -> str:
    return "".join(f'<span class="nq-chip">{esc(i)}</span>' for i in items)


def question_meta(label: str, subtopic: str, marks: int | None = None) -> str:
    badge = f'<span class="nq-marks">{marks} marks</span>' if marks else ""
    return (f'<div class="nq-meta"><span class="nq-qnum">{esc(label)}</span>'
            f'<span class="nq-tag">{esc(subtopic)}</span>{badge}</div>')


def tone_for(percent: int) -> str:
    return "var(--ok)" if percent >= 80 else ("var(--pen)" if percent >= 50 else "var(--bad)")


def score_card(percent: int, headline: str, message: str) -> str:
    return (f'<div class="nq-score"><div class="nq-circle" style="--tone:{tone_for(percent)}">'
            f'<span class="nq-score-num">{int(percent)}<small>%</small></span></div>'
            f'<div><h2>{esc(headline)}</h2><p>{esc(message)}</p></div></div>')


def list_card(title: str, items: list[str]) -> str:
    body = "".join(f"<li>{esc(i)}</li>" for i in items)
    return f'<div class="nq-card"><h4>{esc(title)}</h4><ul>{body}</ul></div>'
