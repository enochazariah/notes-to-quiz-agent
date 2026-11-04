"""Loopback stand-in for the Bedrock Converse REST endpoint (NOT real AWS). Lets the real boto3
client run end to end in tests with no network access and no credentials."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import count
from urllib.parse import unquote

from tests.helpers import SAMPLE_TEXT

SENTS = [s.strip() + "." for s in SAMPLE_TEXT.split(".") if s.strip()]
TITLES = ["Light reactions", "Calvin cycle", "Limiting factors"]
_ids = count(1)


def task_of(prompt: str) -> str:
    for key, name in [("break them into a concept map", "concept"), ("Write multiple-choice questions", "mcq"),
                      ("Write theory (written-answer)", "theory"), ("Mark the student's answer", "grade"),
                      ("Write feedback for a student", "feedback"), ("re-explanation", "reteach")]:
        if key in prompt:
            return name
    return "ping"


def first_list(prompt: str):
    return json.loads(re.search(r"\n(\[\{.*?\}\])\n", prompt, re.S).group(1))


def build(task: str, prompt: str) -> dict:
    if task == "concept":
        return {"main_topic": "Photosynthesis", "subtopics": [
            {"title": t, "summary": SENTS[3 + 3 * i], "key_points": SENTS[3 + 3 * i: 6 + 3 * i]} for i, t in enumerate(TITLES)]}
    if task == "mcq":
        qs = []
        for a in first_list(prompt):
            for _ in range(a["count"]):
                i, n = next(_ids), len(SENTS)
                opts = [SENTS[i % n], SENTS[(i + 3) % n], SENTS[(i + 5) % n], SENTS[(i + 7) % n]]
                r = i % 4
                opts = opts[r:] + opts[:r]
                qs.append({"subtopic": a["subtopic"], "question": f"Fake question {i} about {a['subtopic']}?", "options": opts,
                           "correct_index": opts.index(SENTS[i % n]), "explanation": "The notes say so.",
                           "why_tempting": "It sounds similar.", "source_quote": SENTS[i % n]})
        return {"questions": qs}
    if task == "theory":
        qs = []
        for a in first_list(prompt):
            m = a["marks"]
            n = min(m, 3)
            base, extra = divmod(m, n)
            pts = [SENTS[(len(qs) + j) % len(SENTS)] for j in range(n)]
            qs.append({"subtopic": a["subtopic"], "question": f"Explain {a['subtopic']}.", "model_answer": " ".join(pts),
                       "mark_scheme": [{"point": p, "marks": base + (1 if j < extra else 0)} for j, p in enumerate(pts)],
                       "source_quote": pts[0]})
        return {"questions": qs}
    if task == "grade":
        scheme = json.loads(re.search(r"MARK SCHEME: (\[.*?\])\n", prompt, re.S).group(1))
        return {"verdicts": [{"point": s["point"], "earned": True, "comment": "Covered."} for s in scheme], "missed_summary": "Nothing missed."}
    if task == "feedback":
        return {"headline": "Fake headline", "message": "Fake motivational message.", "strengths": ["a"], "next_steps": ["b"]}
    if task == "reteach":
        return {"items": []}
    return {"answer": "ready"}


class State:
    mode = "ok"
    log: list = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj, error_type=None):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        if error_type:
            self.send_header("x-amzn-ErrorType", error_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt = body["messages"][0]["content"][-1]["text"]
        task = task_of(prompt)
        State.log.append({"path": unquote(self.path), "auth": self.headers.get("Authorization", ""), "body": body, "task": task})
        mode = State.mode
        if mode == "403":
            return self._send(403, {"message": "The security token included in the request is invalid. SECRET-TOKEN-999"}, "AccessDeniedException")
        if mode == "400_model":
            return self._send(400, {"message": "The provided model identifier is invalid."}, "ValidationException")
        if mode == "tool_unsupported" and "toolConfig" in body:
            return self._send(400, {"message": "This model doesn't support the toolChoice.tool field."}, "ValidationException")
        payload = build(task, prompt)
        if mode == "stringified":
            payload = {k: (json.dumps(v) if isinstance(v, list) else v) for k, v in payload.items()}
        if mode == "tool_unsupported" or mode == "text_json":
            content = [{"text": json.dumps(payload)}]
        else:
            content = [{"toolUse": {"toolUseId": "t1", "name": "submit_result", "input": payload}}]
        stop = "max_tokens" if mode == "max_tokens" else ("end_turn" if mode in ("tool_unsupported", "text_json") else "tool_use")
        self._send(200, {"output": {"message": {"role": "assistant", "content": content}}, "stopReason": stop,
                         "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 1}})


def start():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]
