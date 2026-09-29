"use client";

import { Card, Empty, PageTitle, Sentiment, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import type { Meeting, Task } from "@/lib/types";
import { formatWhen, platformLabel } from "@/lib/utils";
import { Plus } from "lucide-react";
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
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <PageTitle className="mb-0" title="Overview" text="Length, sentiment, and open work for each meeting." />
        <Link
          href="/meetings/new"
          className="inline-flex shrink-0 items-center gap-2 self-start rounded-full bg-stone-900 px-4 py-2 text-sm font-medium text-stone-50 transition hover:bg-stone-800"
        >
          <Plus size={15} strokeWidth={2} />
          New meeting
        </Link>
      </div>
      {error && <p className="mt-4 text-sm text-rose-700">{error}</p>}
      <div className="mt-10 grid grid-cols-2 gap-y-6 border-y border-stone-200/80 py-6 sm:grid-cols-5">
        {stats.map(([label, value], index) => (
          <div key={String(label)} className={index ? "sm:border-l sm:border-stone-200/80 sm:pl-6" : ""}>
            <div className="text-[11px] uppercase tracking-[0.16em] text-stone-400">{label}</div>
            <div className="mt-1 font-serif text-4xl tabular-nums text-stone-900">{value ?? "—"}</div>
          </div>
        ))}
      </div>
      {data && Object.keys(data.sentiment || {}).length > 0 && (
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <span className="text-[11px] uppercase tracking-[0.16em] text-stone-400">Sentiment</span>
          {Object.entries(data.sentiment).map(([name, count]) => (
            <span key={name} className="inline-flex items-center gap-2 text-xs text-stone-600">
              <Sentiment value={name} />
              <span className="tabular-nums">{count}</span>
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
      <div className="mt-12 grid gap-12 lg:grid-cols-[minmax(0,1.5fr)_minmax(240px,0.7fr)]">
        <section>
          <div className="mb-1 flex items-baseline justify-between">
            <h2 className="font-serif text-2xl text-stone-900">Meetings</h2>
            <Link href="/meetings" className="text-[11px] uppercase tracking-[0.16em] text-stone-400 hover:text-stone-700">
              View all
            </Link>
          </div>
          <div className="divide-y divide-stone-200/80">
            {data && data.recent_meetings.length === 0 && <div className="pt-4"><Empty>No meetings yet.</Empty></div>}
            {data?.recent_meetings.map((meeting) => (
              <Link
                key={meeting.id}
                href={`/meetings/${meeting.id}`}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-6 py-5 hover:bg-white/40"
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
                <div className="font-serif text-lg tabular-nums text-stone-700">{minutesLabel(meeting)}</div>
              </Link>
            ))}
          </div>
        </section>
        <section>
          <div className="mb-4 flex items-baseline justify-between">
            <h2 className="font-serif text-2xl text-stone-900">Open tasks</h2>
            <Link href="/tasks" className="text-[11px] uppercase tracking-[0.16em] text-stone-400 hover:text-stone-700">
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
        </section>
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
