"use client";

import { Card, Empty, PageTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { formatWhen } from "@/lib/utils";
import Link from "next/link";
import { useEffect, useState } from "react";

type Row = { id: string; meeting_id: string; meeting_title: string; text: string; created_at: string };

export default function DecisionsPage() {
  const [decisions, setDecisions] = useState<Row[]>([]);
  const [risks, setRisks] = useState<Row[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api<Row[]>("/api/decisions"), api<Row[]>("/api/risks")])
      .then(([decisionRows, riskRows]) => {
        setDecisions(decisionRows);
        setRisks(riskRows);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div>
      <PageTitle title="Decisions and risks" text="What was settled, and what can still stop the work." />
      {error && <p className="mb-4 text-sm text-rose-700">{error}</p>}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="font-serif text-xl">Decisions</h2>
          <div className="mt-4 space-y-3">
            {decisions.length === 0 && <Empty>No decisions recorded.</Empty>}
            {decisions.map((item) => (
              <Link key={item.id} href={`/meetings/${item.meeting_id}`} className="block rounded-lg border border-stone-200 px-3 py-3 hover:bg-stone-50">
                <div className="text-sm">{item.text}</div>
                <div className="mt-1 text-xs text-stone-500">
                  {item.meeting_title} · {formatWhen(item.created_at)}
                </div>
              </Link>
            ))}
          </div>
        </Card>
        <Card>
          <h2 className="font-serif text-xl">Risks</h2>
          <div className="mt-4 space-y-3">
            {risks.length === 0 && <Empty>No risks recorded.</Empty>}
            {risks.map((item) => (
              <Link key={item.id} href={`/meetings/${item.meeting_id}`} className="block rounded-lg border border-stone-200 px-3 py-3 hover:bg-stone-50">
                <div className="text-sm">{item.text}</div>
                <div className="mt-1 text-xs text-stone-500">
                  {item.meeting_title} · {formatWhen(item.created_at)}
                </div>
              </Link>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
