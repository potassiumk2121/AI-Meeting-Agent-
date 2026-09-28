"use client";

import { Button, Card, Empty, PageTitle, Sentiment, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import type { Meeting, Task } from "@/lib/types";
import { formatWhen, platformLabel } from "@/lib/utils";
import Link from "next/link";
import { useEffect, useState } from "react";

type Dashboard = {
  meetings: number;
  live_meetings: number;
  open_tasks: number;
  decisions: number;
  participants: number;
  minutes_this_week: number;
  sentiment: Record<string, number>;
  follow_ups: string[];
  recent_meetings: Meeting[];
  open_task_preview: Task[];
};

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Dashboard>("/api/dashboard")
      .then(setData)
      .catch((err: Error) => setError(err.message));
  }, []);

  const stats = [
    ["Meetings", data?.meetings],
    ["Live now", data?.live_meetings],
    ["Open tasks", data?.open_tasks],
    ["Decisions", data?.decisions],
    ["People", data?.participants],
  ];

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <PageTitle title="Executive dashboard" text="Each meeting shows its own length. Open a row to review the transcript, translation, and report." />
        <Link href="/meetings/new">
          <Button>New meeting</Button>
        </Link>
      </div>
      {error && <p className="mb-4 text-sm text-rose-700">{error}</p>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {stats.map(([label, value]) => (
          <Card key={String(label)} className="p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-stone-500">{label}</div>
            <div className="mt-2 font-serif text-3xl tabular-nums text-stone-900">{value ?? "—"}</div>
          </Card>
        ))}
      </div>
      {data && Object.keys(data.sentiment || {}).length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-stone-500">Sentiment</span>
          {Object.entries(data.sentiment).map(([name, count]) => (
            <span key={name} className="inline-flex items-center gap-2 rounded-full bg-white px-2.5 py-1 text-xs ring-1 ring-stone-200">
              <Sentiment value={name} />
              <span className="tabular-nums text-stone-600">{count}</span>
            </span>
          ))}
        </div>
      )}
      {data && data.follow_ups.length > 0 && (
        <Card className="mt-6">
          <h2 className="font-serif text-xl">Follow-up reminders</h2>
          <ul className="mt-3 list-disc space-y-2 pl-4 text-sm text-stone-700">
            {data.follow_ups.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Card>
      )}
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.8fr)]">
        <Card className="p-0">
          <div className="flex items-center justify-between border-b border-stone-100 px-5 py-4">
            <h2 className="font-serif text-xl">Meetings</h2>
            <Link href="/meetings" className="text-sm font-semibold text-teal-800 hover:underline">
              View all
            </Link>
          </div>
          <div>
            {data && data.recent_meetings.length === 0 && <div className="p-5"><Empty>No meetings yet.</Empty></div>}
            {data?.recent_meetings.map((meeting) => (
              <Link
                key={meeting.id}
                href={`/meetings/${meeting.id}`}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 border-t border-stone-100 px-5 py-4 first:border-t-0 hover:bg-stone-50"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="truncate font-medium text-stone-900">{meeting.title}</div>
                    <StatusPill value={meeting.status} />
                    <Sentiment value={meeting.sentiment} />
                  </div>
                  <div className="mt-1 text-xs text-stone-500">
                    {platformLabel(meeting.platform)} · {formatWhen(meeting.started_at || meeting.created_at)}
                    {meeting.participants.length > 0 ? ` · ${meeting.participants.join(", ")}` : ""}
                  </div>
                </div>
                <div className="font-serif text-xl tabular-nums text-stone-900">{minutesLabel(meeting)}</div>
              </Link>
            ))}
          </div>
        </Card>
        <Card>
          <div className="flex items-center justify-between">
            <h2 className="font-serif text-xl">Open tasks</h2>
            <Link href="/tasks" className="text-sm font-semibold text-teal-800 hover:underline">
              View all
            </Link>
          </div>
          <div className="mt-4 space-y-3">
            {data && data.open_task_preview.length === 0 && <Empty>No open tasks.</Empty>}
            {data?.open_task_preview.map((task) => (
              <Link key={task.id} href={`/meetings/${task.meeting_id}`} className="block rounded-lg border border-stone-200 px-3 py-3 hover:bg-stone-50">
                <div className="text-sm font-medium">{task.description}</div>
                <div className="mt-1 text-xs text-stone-500">
                  {task.assignee_name} · {task.meeting_title}
                  {task.due_label ? ` · ${task.due_label}` : ""}
                </div>
              </Link>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function minutesLabel(meeting: Meeting) {
  const minutes = meeting.duration_minutes;
  if (minutes == null) return "—";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}
