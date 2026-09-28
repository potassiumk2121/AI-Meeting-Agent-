"use client";

import { Button, Card, Empty, PageTitle, Sentiment, StatusPill, TextArea, TextInput } from "@/components/ui";
import { api, downloadReport, wsUrl } from "@/lib/api";
import type { ActionItem, MeetingDetail, Segment } from "@/lib/types";
import { platformLabel } from "@/lib/utils";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

type JoinResult = { status: string; warning?: string | null; pulled_segments: number };
type AskResult = {
  answer: string;
  summary: string;
  quotes: { speaker: string; timestamp: string; original: string; english: string }[];
};
type LiveMessage = {
  type: string;
  message?: string;
  sentiment?: string | null;
  segment?: Segment;
  actions?: ActionItem[];
  chat?: MeetingDetail["chat"][number];
};

const LEGEND = [
  ["positive", "Progress, no material risk"],
  ["neutral", "Status update"],
  ["urgent", "Open risk or time pressure"],
  ["blocked", "Work cannot proceed"],
];

export default function MeetingPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const router = useRouter();
  const [detail, setDetail] = useState<MeetingDetail | null>(null);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [pendingClips, setPendingClips] = useState(0);
  const [speaker, setSpeaker] = useState("");
  const [line, setLine] = useState("");
  const [chat, setChat] = useState("");
  const [recipients, setRecipients] = useState("");
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState<AskResult | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const stopMic = useRef(false);
  const endRef = useRef<HTMLDivElement | null>(null);
  const status = detail?.meeting.status;

  async function load() {
    const data = await api<MeetingDetail>(`/api/meetings/${id}`);
    setDetail(data);
  }

  useEffect(() => {
    load().catch((err: Error) => setError(err.message));
  }, [id]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [detail?.segments.length, detail?.chat.length]);

  useEffect(() => {
    if (status !== "live") return;
    let cancelled = false;
    let socket: WebSocket | null = null;
    const connect = () => {
      if (cancelled) return;
      socket = new WebSocket(wsUrl(`/api/meetings/${id}/live`));
      socketRef.current = socket;
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as LiveMessage;
        if (message.type === "error" && message.message) setError(message.message);
        if (message.type === "completed") {
          load().catch((err: Error) => setError(err.message));
          return;
        }
        setDetail((current) => applyLive(current, message));
      };
      socket.onclose = () => {
        if (!cancelled && socketRef.current === socket) {
          window.setTimeout(connect, 1500);
        }
      };
    };
    connect();
    return () => {
      cancelled = true;
      socket?.close();
      socketRef.current = null;
    };
  }, [id, status]);

  async function join() {
    setBusy(true);
    setError("");
    try {
      const result = await api<JoinResult>(`/api/meetings/${id}/join`, { method: "POST" });
      setWarning(result.warning || "");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not join");
    } finally {
      setBusy(false);
    }
  }

  async function sendLine(event: FormEvent) {
    event.preventDefault();
    if (!line.trim()) return;
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setError("Join the meeting before sending a line.");
      return;
    }
    socket.send(JSON.stringify({ type: "utterance", speaker: speaker.trim() || "Person A", text: line }));
    setLine("");
  }

  async function sendChat(event: FormEvent) {
    event.preventDefault();
    if (!chat.trim()) return;
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setError("Join the meeting before sending chat.");
      return;
    }
    socket.send(JSON.stringify({ type: "chat", sender: speaker.trim() || "Person A", text: chat }));
    setChat("");
  }

  async function toggleMic() {
    if (recording) {
      stopMic.current = true;
      if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
      setRecording(false);
      return;
    }
    if (detail?.meeting.status !== "live") await join();
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    stopMic.current = false;
    setRecording(true);
    setError("");
    const loop = async () => {
      while (!stopMic.current) {
        const blob = await recordClip(stream, recorderRef, 2000);
        if (blob && blob.size > 800) {
          const body = new FormData();
          body.append("file", blob, "chunk.webm");
          setPendingClips((count) => count + 1);
          void api(`/api/meetings/${id}/audio`, { method: "POST", body })
            .then(() => load())
            .catch((err: unknown) => {
              const message = err instanceof Error ? err.message : "Audio failed";
              if (!message.toLowerCase().includes("no speech")) setError(message);
            })
            .finally(() => setPendingClips((count) => Math.max(0, count - 1)));
        }
      }
      stream.getTracks().forEach((track) => track.stop());
      recorderRef.current = null;
    };
    void loop();
  }

  async function finish() {
    setBusy(true);
    setError("");
    try {
      await api(`/api/meetings/${id}/finalize`, { method: "POST" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not finish the meeting");
      await load().catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  async function askMeeting(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setAsked(
        await api<AskResult>("/api/ask", {
          method: "POST",
          body: JSON.stringify({ query: question, meeting_id: id }),
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not answer that question");
    } finally {
      setBusy(false);
    }
  }

  async function emailReport(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const recipient = recipients.trim();
      if (!recipient) {
        throw new Error("Enter a recipient email.");
      }
      await api("/api/email/send-report", {
        method: "POST",
        body: JSON.stringify({ recipient, meeting_id: id }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Email failed");
    } finally {
      setBusy(false);
    }
  }

  async function renameSpeaker(fromName: string, toName: string) {
    const next = toName.trim();
    if (!next || next === fromName) return;
    setError("");
    await api(`/api/meetings/${id}/speakers`, {
      method: "PATCH",
      body: JSON.stringify({ from_name: fromName, to_name: next }),
    });
    await load();
  }

  async function remove() {
    if (!window.confirm("Delete this meeting and its transcript?")) return;
    await api(`/api/meetings/${id}`, { method: "DELETE" });
    router.push("/meetings");
  }

  if (!detail) return <p className="text-sm text-stone-500">{error || "Loading meeting…"}</p>;
  const meeting = detail.meeting;
  const live = meeting.status === "live";

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <PageTitle title={meeting.title} text={`${platformLabel(meeting.platform)}${durationLabel(meeting.started_at, meeting.ended_at)}`} />
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <StatusPill value={meeting.status} />
            <Sentiment value={meeting.sentiment} />
            {meeting.participants.length > 0 && <span className="text-sm text-stone-500">{meeting.participants.join(", ")}</span>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {meeting.status === "scheduled" && (
            <Button onClick={join} disabled={busy}>
              Join
            </Button>
          )}
          {(live || meeting.status === "scheduled") && (
            <Button variant="danger" onClick={finish} disabled={busy || detail.segments.length === 0}>
              End and write report
            </Button>
          )}
          {(meeting.status === "completed" || meeting.status === "failed") && (
            <Button variant="secondary" onClick={finish} disabled={busy}>
              Regenerate report
            </Button>
          )}
          <Button variant="ghost" onClick={remove}>
            Delete
          </Button>
        </div>
      </div>

      {warning && <p className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">{warning}</p>}
      {meeting.error_message && <p className="mb-4 rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-800">{meeting.error_message}</p>}
      {meeting.report_stale && <p className="mb-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">The transcript changed after the report. Regenerate to refresh it.</p>}
      {error && <p className="mb-4 text-sm text-rose-700">{error}</p>}

      <div className="mb-4 flex flex-wrap gap-3 text-xs text-stone-500">
        {LEGEND.map(([name, text]) => (
          <span key={name} className="inline-flex items-center gap-2">
            <Sentiment value={name} />
            {text}
          </span>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-6">
          {detail.summary && (
            <Card>
              <h2 className="font-serif text-xl">Executive summary</h2>
              <p className="mt-3 text-sm leading-6 text-stone-700">{detail.summary.executive_summary}</p>
              <h3 className="mt-5 font-serif text-lg">Manager summary</h3>
              <pre className="mt-2 whitespace-pre-wrap font-sans text-sm leading-6 text-stone-700">{detail.summary.manager_summary}</pre>
              <p className="mt-3 text-xs text-stone-500">Generated with {detail.summary.model_name}.</p>
            </Card>
          )}

          <Card>
            <h2 className="font-serif text-xl">Transcript</h2>
            <div className="mt-4 hidden grid-cols-[88px_1fr_1fr] gap-3 text-xs uppercase tracking-wide text-stone-500 md:grid">
              <span>Timestamp</span>
              <span>Original</span>
              <span>English</span>
            </div>
            <div className="mt-2 max-h-[32rem] space-y-4 overflow-auto pr-1">
              {detail.segments.length === 0 && <Empty>Lines show up here as people speak.</Empty>}
              {detail.segments.map((segment) => (
                <article key={segment.id} className="grid gap-2 border-t border-stone-100 pt-3 md:grid-cols-[88px_1fr_1fr] md:gap-3">
                  <div className="text-xs text-stone-500">{segment.timestamp_label}</div>
                  <div>
                    <SpeakerName name={segment.speaker_name} onRename={(from, to) => renameSpeaker(from, to)} />
                    <p className="text-xs uppercase tracking-wide text-stone-400 md:hidden">Original</p>
                    <p className="text-sm leading-6 text-stone-800">{segment.original_text}</p>
                  </div>
                  <div>
                    <div className="hidden md:block">
                      <SpeakerName name={segment.speaker_name} onRename={(from, to) => renameSpeaker(from, to)} />
                    </div>
                    <p className="text-xs uppercase tracking-wide text-stone-400 md:hidden">English</p>
                    <p className="text-sm leading-6 text-stone-800">{segment.english_text}</p>
                  </div>
                </article>
              ))}
              {detail.chat.map((message) => (
                <article key={message.id} className="grid grid-cols-[88px_1fr] gap-3">
                  <div className="text-xs text-stone-500">{message.timestamp_label}</div>
                  <div className="rounded-md bg-stone-50 px-3 py-2 text-sm">
                    <span className="font-semibold">{message.sender_name}</span> in chat: {message.english_text}
                  </div>
                </article>
              ))}
              <div ref={endRef} />
            </div>
            {(live || meeting.status === "scheduled") && (
              <div className="mt-4 space-y-3 border-t border-stone-100 pt-4">
                {live && (
                  <>
                    <form className="flex gap-2" onSubmit={sendLine}>
                      <TextArea value={line} onChange={(event) => setLine(event.target.value)} placeholder="Paste a spoken line" rows={2} />
                      <Button type="submit">Send</Button>
                    </form>
                    <form className="flex gap-2" onSubmit={sendChat}>
                      <TextInput value={chat} onChange={(event) => setChat(event.target.value)} placeholder="Chat message" />
                      <Button type="submit" variant="secondary">
                        Chat
                      </Button>
                    </form>
                  </>
                )}
                <Button type="button" variant="secondary" onClick={() => toggleMic().catch((err: unknown) => setError(err instanceof Error ? err.message : "Microphone failed"))}>
                  {recording ? "Stop microphone" : "Start microphone"}
                </Button>
                <p className="text-xs text-stone-500">
                  {recording
                    ? `Listening through the laptop speaker. Voices are labeled Person A, Person B as they appear.${pendingClips > 0 ? " Translating…" : ""}`
                    : "Play the meeting on the laptop speakers, then start the microphone. Click a Person A or Person B label to rename it."}
                </p>
              </div>
            )}
          </Card>

          {detail.summary && (
            <Card>
              <h2 className="font-serif text-xl">Detailed notes</h2>
              <pre className="mt-3 whitespace-pre-wrap font-sans text-sm leading-6 text-stone-700">{detail.summary.detailed_summary}</pre>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card>
            <h2 className="font-serif text-xl">Ask this meeting</h2>
            <form className="mt-3 space-y-2" onSubmit={askMeeting}>
              <TextInput value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="What did Jim say about deployment?" required />
              <Button type="submit" disabled={busy}>Ask</Button>
            </form>
            {asked && (
              <div className="mt-4 space-y-3 text-sm">
                <p className="whitespace-pre-wrap leading-6 text-stone-800">{asked.answer}</p>
                {asked.summary && <p className="text-stone-600">{asked.summary}</p>}
                {asked.quotes.map((quote, index) => (
                  <div key={`${quote.timestamp}-${index}`} className="rounded-md border border-stone-200 px-3 py-2">
                    <div className="text-xs text-stone-500">{quote.speaker} · {quote.timestamp}</div>
                    <p className="mt-1">{quote.original}</p>
                    <p className="mt-1 text-stone-600">{quote.english}</p>
                  </div>
                ))}
              </div>
            )}
          </Card>
          <Card>
            <h2 className="font-serif text-xl">Speaker analytics</h2>
            <div className="mt-3 space-y-2">
              {speakerShares(detail.segments).map((row) => (
                <div key={row.name}>
                  <div className="flex justify-between gap-2 text-xs text-stone-600">
                    <SpeakerName name={row.name} onRename={(from, to) => renameSpeaker(from, to)} />
                    <span>{row.lines} lines · {Math.round(row.share * 100)}%</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded bg-stone-100">
                    <div className="h-1.5 rounded bg-teal-800" style={{ width: `${Math.max(4, row.share * 100)}%` }} />
                  </div>
                </div>
              ))}
              {detail.segments.length === 0 && <p className="text-sm text-stone-500">Speaker share appears after the first line.</p>}
            </div>
          </Card>
          <Card>
            <h2 className="font-serif text-xl">Action items</h2>
            <div className="mt-3 space-y-3">
              {detail.actions.length === 0 && <p className="text-sm text-stone-500">Commitments appear when someone says they will do the work.</p>}
              {detail.actions.map((action) => (
                <div key={action.id} className="rounded-md border border-stone-200 px-3 py-2 text-sm">
                  <div className="font-semibold">{action.assignee_name}</div>
                  <div>{action.description}</div>
                  <div className="mt-1 text-xs text-stone-500">
                    {action.status}
                    {action.due_label ? ` · ${action.due_label}` : ""}
                  </div>
                </div>
              ))}
            </div>
          </Card>
          {detail.decisions.length > 0 && (
            <Card>
              <h2 className="font-serif text-xl">Decisions</h2>
              <ul className="mt-3 list-disc space-y-2 pl-4 text-sm text-stone-700">
                {detail.decisions.map((item) => (
                  <li key={item.id}>{item.text}</li>
                ))}
              </ul>
            </Card>
          )}
          {detail.risks.length > 0 && (
            <Card>
              <h2 className="font-serif text-xl">Risks</h2>
              <ul className="mt-3 list-disc space-y-2 pl-4 text-sm text-stone-700">
                {detail.risks.map((item) => (
                  <li key={item.id}>{item.text}</li>
                ))}
              </ul>
            </Card>
          )}
          {(meeting.report_ready || meeting.status === "completed") && (
            <Card>
              <h2 className="font-serif text-xl">Report</h2>
              <Button
                className="mt-3"
                variant="secondary"
                onClick={() => downloadReport(meeting.id, meeting.report_filename || "meeting.pdf").catch((err: Error) => setError(err.message))}
              >
                Download PDF
              </Button>
              <form className="mt-4 space-y-2" onSubmit={emailReport}>
                <TextInput type="email" value={recipients} onChange={(event) => setRecipients(event.target.value)} placeholder="name@company.com" required />
                <Button type="submit" disabled={busy}>
                  Email PDF
                </Button>
              </form>
              {detail.email && (
                <p className="mt-3 text-xs text-stone-500">
                  Last email: {detail.email.status}
                  {detail.email.error ? ` — ${detail.email.error}` : ""}
                </p>
              )}
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function SpeakerName({ name, onRename }: { name: string; onRename: (from: string, to: string) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!editing) setValue(name);
  }, [name, editing]);

  async function save() {
    setSaving(true);
    try {
      await onRename(name, value);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1">
        <TextInput
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void save();
            }
          }}
          className="h-8 w-36"
          aria-label={`Rename ${name}`}
        />
        <button type="button" className="text-xs font-semibold text-teal-800" disabled={saving} onClick={() => void save()}>
          Save
        </button>
      </span>
    );
  }

  return (
    <button type="button" className="text-left text-sm font-semibold text-stone-900 hover:underline" onClick={() => setEditing(true)}>
      {name}
    </button>
  );
}

function applyLive(current: MeetingDetail | null, message: LiveMessage) {
  if (!current) return current;
  if (message.type === "segment" && message.segment) {
    if (current.segments.some((item) => item.id === message.segment?.id)) return current;
    const names = new Set(current.meeting.participants);
    names.add(message.segment.speaker_name);
    const known = new Set(current.actions.map((item) => item.id));
    const actions = [...current.actions, ...(message.actions || []).filter((item) => !known.has(item.id))];
    return {
      ...current,
      meeting: { ...current.meeting, sentiment: message.sentiment || current.meeting.sentiment, participants: Array.from(names), status: "live" },
      segments: [...current.segments, message.segment],
      actions,
    };
  }
  if (message.type === "chat" && message.chat) {
    if (current.chat.some((item) => item.id === message.chat?.id)) return current;
    return { ...current, chat: [...current.chat, message.chat] };
  }
  if (message.sentiment) {
    return { ...current, meeting: { ...current.meeting, sentiment: message.sentiment } };
  }
  return current;
}

function durationLabel(started: string | null, ended: string | null) {
  if (!started) return "";
  const end = ended ? new Date(ended).getTime() : Date.now();
  const minutes = Math.max(0, Math.round((end - new Date(started).getTime()) / 60000));
  if (minutes < 60) return ` · ${minutes} min`;
  return ` · ${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function speakerShares(segments: Segment[]) {
  const counts = new Map<string, number>();
  for (const segment of segments) counts.set(segment.speaker_name, (counts.get(segment.speaker_name) || 0) + 1);
  const total = segments.length || 1;
  return Array.from(counts.entries())
    .map(([name, lines]) => ({ name, lines, share: lines / total }))
    .sort((a, b) => b.lines - a.lines);
}

function recordClip(stream: MediaStream, recorderRef: { current: MediaRecorder | null }, ms: number) {
  return new Promise<Blob | null>((resolve) => {
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    recorderRef.current = recorder;
    const chunks: Blob[] = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data);
    };
    recorder.onstop = () => resolve(chunks.length ? new Blob(chunks, { type: recorder.mimeType || "audio/webm" }) : null);
    recorder.start();
    window.setTimeout(() => {
      if (recorder.state !== "inactive") recorder.stop();
    }, ms);
  });
}
