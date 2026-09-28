"use client";

import { Button, Card, Empty, PageTitle } from "@/components/ui";
import { api } from "@/lib/api";
import Link from "next/link";
import { useEffect, useState } from "react";

type Speaker = { name: string; lines: number; share: number };
type Period = {
  label: string;
  meetings: number;
  minutes: number;
  decisions: number;
  open_actions: number;
  sentiment: Record<string, number>;
  speakers: Speaker[];
  highlights: string[];
};
type FollowUp = {
  meeting_id: string;
  meeting_title: string;
  assignee_name: string;
  reminder: string;
};
type Calendar = {
  configured: boolean;
  detail: string;
  events: { title: string; start: string; end: string; join_url: string | null; organizer: string | null }[];
};

export default function ReportsPage() {
  const [weekly, setWeekly] = useState<Period | null>(null);
  const [monthly, setMonthly] = useState<Period | null>(null);
  const [followUps, setFollowUps] = useState<FollowUp[]>([]);
  const [calendar, setCalendar] = useState<Calendar | null>(null);
  const [error, setError] = useState("");
  const [scanNote, setScanNote] = useState("");

  function load() {
    Promise.all([
      api<Period>("/api/reports/weekly"),
      api<Period>("/api/reports/monthly"),
      api<FollowUp[]>("/api/reports/follow-ups"),
      api<Calendar>("/api/calendar/upcoming"),
    ])
      .then(([week, month, reminders, events]) => {
        setWeekly(week);
        setMonthly(month);
        setFollowUps(reminders);
        setCalendar(events);
      })
      .catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    load();
  }, []);

  async function scan() {
    setScanNote("");
    try {
      const result = await api<{ started: number; closed: number; detail: string }>("/api/calendar/scan", { method: "POST" });
      setScanNote(`${result.detail} Started ${result.started}, closed ${result.closed}.`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Calendar scan failed");
    }
  }

  return (
    <div>
      <PageTitle title="Reports" text="Weekly and monthly rollups, follow-up reminders, and the Outlook calendar." />
      {error && <p className="mb-4 text-sm text-rose-700">{error}</p>}
      <div className="grid gap-6 lg:grid-cols-2">
        {weekly && <PeriodCard title="Weekly meeting report" report={weekly} />}
        {monthly && <PeriodCard title="Monthly team report" report={monthly} />}
      </div>
      <Card className="mt-6">
        <h2 className="font-serif text-xl">Follow-up reminders</h2>
        <div className="mt-4 space-y-3">
          {followUps.length === 0 && <Empty>No open action items.</Empty>}
          {followUps.map((item) => (
            <Link key={item.reminder} href={`/meetings/${item.meeting_id}`} className="block rounded-lg border border-stone-200 px-3 py-3 hover:bg-stone-50">
              <div className="text-sm">{item.reminder}</div>
              <div className="mt-1 text-xs text-stone-500">{item.assignee_name} · {item.meeting_title}</div>
            </Link>
          ))}
        </div>
      </Card>
      <Card className="mt-6">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-serif text-xl">Outlook calendar</h2>
          <Button variant="secondary" onClick={scan}>Check for live meetings</Button>
        </div>
        <p className="mt-2 text-sm text-stone-600">{calendar?.detail}</p>
        {scanNote && <p className="mt-2 text-sm text-teal-900">{scanNote}</p>}
        <div className="mt-4 space-y-3">
          {calendar && calendar.events.length === 0 && <Empty>No events in the next 7 days.</Empty>}
          {calendar?.events.map((event) => (
            <div key={`${event.title}-${event.start}`} className="rounded-lg border border-stone-200 px-3 py-3 text-sm">
              <div className="font-medium">{event.title}</div>
              <div className="mt-1 text-xs text-stone-500">
                {new Date(event.start).toLocaleString()} – {new Date(event.end).toLocaleString()}
                {event.organizer ? ` · ${event.organizer}` : ""}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function PeriodCard({ title, report }: { title: string; report: Period }) {
  const sentiment = Object.entries(report.sentiment);
  return (
    <Card>
      <h2 className="font-serif text-xl">{title}</h2>
      <p className="mt-1 text-sm text-stone-500">{report.label}</p>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <Stat label="Meetings" value={report.meetings} />
        <Stat label="Minutes" value={report.minutes} />
        <Stat label="Decisions" value={report.decisions} />
        <Stat label="Open actions" value={report.open_actions} />
      </div>
      {sentiment.length > 0 && (
        <p className="mt-4 text-xs uppercase tracking-wide text-stone-500">
          Sentiment {sentiment.map(([name, count]) => `${name} ${count}`).join(" · ")}
        </p>
      )}
      <div className="mt-4 space-y-2">
        {report.speakers.map((speaker) => (
          <div key={speaker.name} className="text-sm text-stone-700">
            {speaker.name} · {speaker.lines} lines · {Math.round(speaker.share * 100)}%
          </div>
        ))}
      </div>
      <div className="mt-4 space-y-2">
        {report.highlights.map((line) => (
          <p key={line} className="text-sm leading-6 text-stone-700">{line}</p>
        ))}
      </div>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-stone-500">{label}</div>
      <div className="font-serif text-2xl">{value}</div>
    </div>
  );
}
