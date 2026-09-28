"use client";

import { Card, Empty, PageTitle, Sentiment, StatusPill } from "@/components/ui";
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
    ["Participants", data?.participants],
    ["Minutes this week", data?.minutes_this_week],
  ];

  return (
    <div>
      <PageTitle title="Executive dashboard" text="This week’s meetings, sentiment, open work, and follow-up reminders." />
      {error && <p className="mb-4 text-sm text-rose-700">{error}</p>}
      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {stats.map(([label, value]) => (
          <Card key={String(label)} className="p-4">
            <div className="text-xs uppercase tracking-wide text-stone-500">{label}</div>
            <div className="mt-2 font-serif text-3xl">{value ?? "—"}</div>
          </Card>
        ))}
      </div>
      {data && Object.keys(data.sentiment || {}).length > 0 && (
        <p className="mt-4 text-sm text-stone-600">
          Sentiment this week: {Object.entries(data.sentiment).map(([name, count]) => `${name} ${count}`).join(" · ")}
        </p>
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
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="font-serif text-xl">Recent meetings</h2>
          <div className="mt-4 space-y-3">
            {data && data.recent_meetings.length === 0 && <Empty>No meetings yet.</Empty>}
            {data?.recent_meetings.map((meeting) => (
              <Link key={meeting.id} href={`/meetings/${meeting.id}`} className="block rounded-lg border border-stone-200 px-3 py-3 hover:bg-stone-50">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium">{meeting.title}</div>
                  <StatusPill value={meeting.status} />
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-stone-500">
                  <span>{platformLabel(meeting.platform)}</span>
                  <span>·</span>
                  <span>{formatWhen(meeting.started_at || meeting.created_at)}</span>
                  <Sentiment value={meeting.sentiment} />
                </div>
              </Link>
            ))}
          </div>
        </Card>
        <Card>
          <h2 className="font-serif text-xl">Open tasks</h2>
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
