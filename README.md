# Meeting Intelligence

An internal meeting agent for Microsoft Teams and Google Meet. It keeps a live transcript with speaker names and timestamps, translates speech into English, detects action items and sentiment while the meeting is running, and writes an executive summary, a short manager summary, a PDF, and a searchable memory after the meeting ends.

Paste a line and the service still stores the transcript, finds commitments, classifies sentiment, and builds the PDF. Microphone transcription uses Gemini or Whisper. Translation into English uses Gemini. Add `GEMINI_API_KEY` before using the microphone or translating a non-English line.

## What a live meeting does

1. Create a meeting with a Teams or Meet join link.
2. Join it. The service opens a live session. If Graph or Meet credentials are set, it resolves the meeting and pulls any transcript already published.
3. Capture speech in one of two ways:
   - Microphone in the dashboard. The browser records the mic and uploads a clip every few seconds. Gemini or Whisper transcribes it.
   - Paste a line, or push JSON over the meeting WebSocket from a bot.
4. Each line is stored with the speaker, a timestamp, the original text, the detected language, and the English translation. Sentences such as "I will fix the login issue" become action items. Sentiment is one of `positive`, `neutral`, `urgent`, or `blocked`.
5. End the meeting. The service writes the executive summary, manager summary, decisions, risks, next steps, search index, and PDF.
6. Download `meeting_YYYY_MM_DD.pdf`, or email it through Resend.

Sentiment means:

| Label | Meaning |
| --- | --- |
| positive | Progress, no material risk |
| neutral | Status update |
| urgent | Open risk or time pressure |
| blocked | Someone or something cannot proceed |

## Architecture

```text
Dashboard (Next.js)
    |  REST + WebSocket
    v
FastAPI
    |-- Speech: OpenAI Whisper or Azure Speech
    |-- Language: OpenAI GPT or Gemini
    |-- Meetings: Microsoft Graph transcripts, Google Meet conference records
    |-- Mail: Microsoft Graph sendMail
    |-- PDF: ReportLab
    v
PostgreSQL + pgvector
    meetings, participants, transcript, chat, tasks, decisions, risks, summaries, embeddings
```

Teams and Meet do not allow an arbitrary service to sit inside the call and capture raw audio. This service uses the official transcript APIs when credentials exist, and a live ingest socket for audio or text from the dashboard or from a bot you register. Run one backend replica so the in-process WebSocket fan-out reaches every open dashboard. Meeting state itself is in PostgreSQL, so the REST API can be scaled separately later. A Redis pub/sub hub is the upgrade path for multiple replicas.

## Folder structure

```text
backend/app
  main.py                 HTTP app and health
  config.py               Environment settings
  models.py               PostgreSQL schema
  schemas.py              API contracts
  auth.py                 Passwords and JWT
  api/                    Auth, meetings, live socket, dashboard, search, Graph webhook
  services/
    pipeline.py           Ingest, join, finalize
    extract.py            Action items, sentiment, fallback summary
    summarize.py          Model summary, merged with the fallback
    translate.py          English translation
    speech.py             Whisper or Azure Speech
    llm.py                OpenAI and Gemini
    connectors.py         Graph, Meet, mail
    pdf_report.py         Branded PDF
    rag.py                Embeddings and search
frontend
  app/(app)               Overview, meetings, tasks, decisions, search, participants
  app/login
docker-compose.yml
infra/init.sql            CREATE EXTENSION vector
```

## Database schema

| Table | Stores |
| --- | --- |
| users | Dashboard accounts |
| meetings | Platform, status, join URL, external id, sentiment, report path |
| participants | Speaker names per meeting |
| transcript_segments | Speaker, timestamp, original text, language, English text, source |
| chat_messages | Meeting chat, original and English |
| action_items | Assignee, task, due label, open/done |
| decisions | Key decisions |
| risks | Risks and blockers |
| meeting_summaries | Executive, detailed, and manager summaries, next steps, model name |
| embedding_chunks | Summary and transcript chunks, optional 1536-dimension vector |
| email_deliveries | Recipients, sent or failed |

`status` moves `scheduled → live → processing → completed`. A failed report can be regenerated. Vectors use pgvector HNSW with cosine distance. Full-text search uses a GIN index on `to_tsvector('english', content)`.

## API

Interactive docs are at `http://localhost:8000/docs`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/settings/public` | Company name and brand color |
| POST | `/api/meetings` | Create a Teams or Meet session |
| GET | `/api/meetings` | List meetings |
| GET | `/api/meetings/{id}` | Transcript, chat, tasks, summary |
| POST | `/api/meetings/{id}/join` | Go live and pull a platform transcript |
| POST | `/api/meetings/{id}/sync` | Pull newly published transcript lines |
| POST | `/api/meetings/{id}/finalize` | Summaries, index, and PDF |
| POST | `/api/meetings/{id}/audio` | Multipart audio clip plus `speaker` |
| GET | `/api/meetings/{id}/report.pdf` | Download the PDF |
| POST | `/api/email/send-report` | Generate the PDF if needed and send it through Resend |
| DELETE | `/api/meetings/{id}` | Delete a meeting |
| WS | `/api/meetings/{id}/live` | Live ingest |
| GET | `/api/demo/script` | Sample Jim / Pranjay / David dialogue |
| GET | `/api/dashboard` | Counts, recent meetings, open tasks |
| GET | `/api/tasks` | Action items |
| PATCH | `/api/action-items/{id}` | `{"status":"open"\|"done"}` |
| GET | `/api/decisions` | Decisions across meetings |
| GET | `/api/risks` | Risks across meetings |
| GET | `/api/participants` | People |
| POST | `/api/search` | `{"query":"..."}` |
| POST | `/api/webhooks/graph` | Graph validation and transcript notifications |

WebSocket messages:

```json
{"type":"utterance","speaker":"Pranjay","text":"I will fix the login issue.","language":"en","timestamp_label":"10:06 AM"}
{"type":"chat","sender":"Jim","text":"Checklist is in the channel."}
{"type":"ping"}
```

The server broadcasts `segment`, `chat`, `sentiment`, and `completed` events.

## Access

The dashboard opens directly. There is no sign-in screen. Put the site behind the company network or HTTPS if the transcripts should stay private.

## Run with Docker

```powershell
copy .env.example .env
docker compose up --build
```

Open `http://localhost:3000`. The API is at `http://localhost:8000`.

If something else is already bound to `127.0.0.1:8000`, `docker-compose.override.yml` also publishes the API on port 8001 and builds the dashboard against that port. That file is only needed on a machine with the conflict. Delete it, and rebuild the frontend, when 8000 is free.

Create a meeting, join it, start the microphone or paste a line, then choose **End and write report**. The PDF is named `meeting_YYYY_MM_DD.pdf` for the first report of that day.

PostgreSQL is published on port 5432. The API is on port 8000. Reports are stored in the `reports` volume (`/data/reports` in the container).

## Run the tests

```powershell
cd backend
python -m pip install -r requirements.txt
python -m pytest
```

The tests cover the sample meeting summary, Teams WebVTT parsing, password and JWT handling, language detection, and PDF generation. They do not need a database.

## Configuration

Copy `.env.example`. The important groups:

| Group | Variables |
| --- | --- |
| App | `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `COMPANY_NAME`, `BRAND_COLOR`, `DEFAULT_TIMEZONE` |
| Model | `AI_PROVIDER=openai` or `gemini`, plus the matching key and model |
| Speech | `SPEECH_PROVIDER=openai` or `azure` |
| Embeddings | `OPENAI_API_KEY` and `OPENAI_EMBED_MODEL=text-embedding-3-small` (1536 dimensions) |
| Graph | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `GRAPH_SENDER` |
| Meet | `GOOGLE_CREDENTIALS_FILE`, `GOOGLE_DELEGATED_USER` |
| Mail | `RESEND_API_KEY`, `EMAIL_FROM` |

`AI_PROVIDER=gemini` uses Gemini for summaries and translation. Embeddings stay on OpenAI so the vector column stays 1536 dimensions. With no embedding key, search uses PostgreSQL full text.

Whisper accepts the dashboard's WebM microphone clips. Azure Speech expects WAV.

## Microsoft Teams and Graph

Register an app in Microsoft Entra ID. Create a client secret. Grant application permissions and admin consent:

- `OnlineMeetings.Read.All`
- `OnlineMeetingTranscript.Read.All`

Set `GRAPH_SENDER` to the user id or UPN that owns the Teams meeting when the meeting row has no organizer email. Join then calls:

`GET /users/{organizer}/onlineMeetings?$filter=JoinWebUrl eq '{url}'`

and downloads the latest transcript as WebVTT.

To receive transcript notifications, expose `https://<your-host>/api/webhooks/graph` as `WEBHOOK_URL` and set `WEBHOOK_SECRET`. The join flow creates a Graph subscription on that meeting's transcripts. The webhook answers Graph's validation token and then pulls new lines.

## Google Meet

Enable the Google Meet REST API. Create a service account, download the JSON, and set `GOOGLE_CREDENTIALS_FILE`. For Workspace meetings, enable domain-wide delegation for `https://www.googleapis.com/auth/meetings.space.readonly` and set `GOOGLE_DELEGATED_USER` to a user who can read the conference record.

The connector lists conference records for the Meet code in the join link (`abc-defg-hij`) and reads transcript entries.

## Email

`POST /api/email/send-report` with `{"recipient":"a@company.com","meeting_id":"..."}` generates the PDF if needed and sends it through Resend. Set `RESEND_API_KEY` and `EMAIL_FROM`. `EMAIL_FROM` must be an address on a domain Resend has verified.

`POST /api/ask` answers from stored transcript lines and the executive summary. Each line keeps the speaker, original text, English translation, and timestamp. Embeddings cover the transcript, decisions, and action items when `OPENAI_API_KEY` is set.

The calendar watcher checks Outlook every minute when Graph is configured. Grant `Calendars.Read`. A live Teams event is joined, transcribed, and translated. When the event ends, the service writes the summary and PDF, then emails `EMAIL_DEFAULT_RECIPIENTS` and the organizer.

## PDF

ReportLab writes a branded A4 report: company name and tagline, executive summary, manager summary, decisions, risks, next steps, action items, the English transcript with the original line when it differs, and chat. `BRAND_COLOR` should be a dark hex color. The container image includes DejaVu Sans so non-English original lines render. On Windows, the local font fallback is Arial.

## Deployment

For a single VM, put Caddy or nginx in front of the two published ports and proxy WebSockets.

```caddy
meetings.example.com {
    reverse_proxy localhost:3000
}
api.meetings.example.com {
    reverse_proxy localhost:8000
}
```

Rebuild the frontend with the public API URL:

```powershell
docker compose build --build-arg NEXT_PUBLIC_API_URL=https://api.meetings.example.com frontend
```

Set `CORS_ORIGINS=https://meetings.example.com`.

On Azure Container Apps, use Azure Database for PostgreSQL Flexible Server with the `vector` extension, store the secret values in the container app secrets, and mount a volume at `/data/reports` (or copy reports to Blob Storage). The Graph webhook URL must be the public HTTPS API host.

Back up the Postgres volume. Losing it loses transcripts and the search index. PDFs can be regenerated from the transcript while the database is intact.

## Security checklist

- Serve the site over HTTPS only, on a private network.
- Do not publish port 5432 outside the private network.
- Grant Graph and Google the minimum permissions above.
- Treat transcripts as confidential. The PDF footer says so.
