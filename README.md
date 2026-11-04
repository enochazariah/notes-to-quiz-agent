# Notes to Quiz Agent

Upload a PDF of notes. The agent splits them into topics and subtopics, writes multiple-choice
questions (5 to 50) and a theory paper (up to 20 marks), marks your answers, and gives specific,
encouraging feedback plus a short re-explanation of the topics you struggled with.

AI provider: **Amazon Bedrock** (Converse API). Nothing is stored: files are read in memory.

## How it works
1. **Map**: reads the notes and builds a concept map (main topic, subtopics, key points).
2. **Write**: generates questions per subtopic in batches of 10, as structured output (the model is
   forced to call a tool whose schema is the question format).
3. **Verify**: each question must carry a source quote, and at least 80% of that quote's words must
   occur in your notes. This is a vocabulary check, not an exact-sentence match, so it catches
   invented topics but not every subtle error. Duplicates are dropped. Thin notes produce fewer
   questions, and the app says so.
4. **Mark**: multiple choice is marked by code. Theory answers are judged by the model against a mark
   scheme, and the marks are added up by code.
5. **Coach**: feedback in the style you choose, and weak subtopics are re-taught.

Only **text-based PDFs** work (you can select and copy the words). Scans and image-only PDFs are
rejected with a clear message.

## Run on your computer (Windows PowerShell)
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
Edit `.env` (see the next section), then:
```
python scripts/check_bedrock.py
streamlit run app.py
```
While the token is still the `PASTE_...` placeholder, the app runs in **demo mode** (an offline
mock, clearly labelled) so you can test the whole flow without any key. A sample PDF is in `samples/`.

## Settings (`.env` locally, Render's Environment tab online)
| Name | What it is |
|---|---|
| `AWS_BEARER_TOKEN_BEDROCK` | Your Bedrock API key. Required for real AI. Never commit it. |
| `AWS_REGION` | The region where your key and model are. Default `us-east-1`. |
| `BEDROCK_MODEL_ID` | The model or inference-profile ID. Default `us.anthropic.claude-sonnet-4-6`. |
| `ACCESS_CODE` | Optional. A short code visitors must type. |
| `MAX_PDF_MB`, `MAX_PDF_PAGES` | Optional. Default 25 MB and 60 pages. |
| `BEDROCK_MAX_TOKENS` | Optional. Default 4096 (maximum length of each AI answer). |

**Get the key:** AWS console -> Amazon Bedrock -> API keys -> generate a key. Choose an expiry date.
AWS recommends long-term keys only for exploration and development, so set a short expiry and
rotate it. Create the key in the same region you set in `AWS_REGION`.

**Pick the model:** use a Claude or Amazon Nova model (they support the forced tool use this app
relies on). Newer models need an inference-profile ID with a region prefix (`us.`, `eu.`, `apac.` or
`global.`). `python scripts/check_bedrock.py` lists what your account can see and makes one small test
call. If your account has not enabled the model yet, Bedrock will refuse the call: enable it in the
Bedrock console first.

## Deploy on Render
1. Push the folder to GitHub. `.env` is git-ignored, so your key never leaves your computer.
2. Render dashboard -> New -> Blueprint (it reads `render.yaml`), or a Web Service with
   build `pip install -r requirements.txt` and start
   `streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true`.
3. Environment tab: add `AWS_BEARER_TOKEN_BEDROCK` (your real key), and check `AWS_REGION` and
   `BEDROCK_MODEL_ID`. Optional: `ACCESS_CODE`.
4. Deploy and share the `onrender.com` link. Free instances sleep when idle: open the link a minute
   before a demo, because the first load can take 30 to 60 seconds.

## Limits
PDF 25 MB / 60 pages (the upload size is set in two places that must match: `.streamlit/config.toml`
`maxUploadSize` and `MAX_PDF_MB`), 5 quizzes per visitor session, 100 quizzes per day for the whole app.
Only the first 200,000 characters of a very long PDF are used.

## Troubleshooting
| You see | Cause and fix |
|---|---|
| "Bedrock refused the request..." | Token wrong, expired, or the account can't use that model in this region. |
| "Couldn't reach Bedrock in ..." | Check for a typo or unsupported AWS region in `AWS_REGION` (for example, `us-north-1` is not a valid region). Use a Bedrock-supported region such as `us-east-1`, where your key and model are available. |
| "The model '...' isn't available in ..." | Wrong `BEDROCK_MODEL_ID` for your region. Run `scripts/check_bedrock.py`. |
| "Bedrock is rate-limiting requests" | Wait a minute and retry, or build a smaller quiz. |
| "The AI's answer was cut off" | Ask for fewer questions or raise `BEDROCK_MAX_TOKENS`. |
| "couldn't find enough selectable text" | The PDF is a scan. Upload a text-based PDF. |
| Yellow "Demo mode" banner | The token is missing or still the placeholder. |

## Security
- Keep keys only in `.env` (local) or Render's Environment tab. `.gitignore` blocks `.env` and other
  secret files; `.env.example` holds placeholders only.
- The app never prints or logs the token, and error messages never include it.
- If a key leaks, delete it in the Bedrock console and create a new one.

## Layout
`app.py` (UI) · `quizagent/ui_theme.py` (look and feel) · `quizagent/agent.py` (pipeline) ·
`quizagent/prompts.py` · `quizagent/schemas.py` · `quizagent/providers/` (`bedrock.py`, offline `mock.py`,
`factory.py`) · `scripts/check_bedrock.py` · `tests/` (run: `python -m unittest discover -s tests -t .`)
