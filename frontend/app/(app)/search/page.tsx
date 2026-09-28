"use client";

import { Button, Card, Empty, PageTitle, TextInput } from "@/components/ui";
import { api } from "@/lib/api";
import Link from "next/link";
import { FormEvent, useState } from "react";

type AskResult = {
  answer: string;
  summary: string;
  quotes: {
    meeting_id: string;
    meeting_title: string;
    speaker: string;
    timestamp: string;
    original: string;
    english: string;
  }[];
};

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      setResult(await api<AskResult>("/api/ask", { method: "POST", body: JSON.stringify({ query }) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageTitle title="Ask Meeting" text="Search the stored transcript, decisions, and action items. Example: What did Jim say about deployment?" />
      <form className="flex gap-2" onSubmit={submit}>
        <TextInput value={query} onChange={(event) => setQuery(event.target.value)} placeholder="What did Jim say about deployment?" />
        <Button disabled={busy || query.trim().length < 2}>{busy ? "Searching…" : "Ask"}</Button>
      </form>
      {error && <p className="mt-4 text-sm text-rose-700">{error}</p>}
      {result && (
        <div className="mt-6 space-y-4">
          <Card>
            <h2 className="font-serif text-xl">Answer</h2>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-stone-800">{result.answer}</p>
            {result.summary && (
              <>
                <h3 className="mt-5 font-serif text-lg">Summary</h3>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-stone-700">{result.summary}</p>
              </>
            )}
          </Card>
          {result.quotes.length === 0 && <Empty>No matching transcript lines.</Empty>}
          {result.quotes.map((quote, index) => (
            <Card key={`${quote.meeting_id}-${quote.timestamp}-${index}`}>
              <Link href={`/meetings/${quote.meeting_id}`} className="font-medium text-teal-900 hover:underline">
                {quote.meeting_title}
              </Link>
              <div className="mt-2 text-xs text-stone-500">
                Speaker: {quote.speaker} · Timestamp: {quote.timestamp}
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div>
                  <div className="text-xs uppercase tracking-wide text-stone-400">Original</div>
                  <p className="mt-1 text-sm leading-6">{quote.original}</p>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-stone-400">Translated</div>
                  <p className="mt-1 text-sm leading-6">{quote.english}</p>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
