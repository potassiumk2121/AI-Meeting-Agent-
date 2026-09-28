"use client";

import { Button, Empty, PageTitle, Sentiment, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import type { Meeting } from "@/lib/types";
import { formatWhen, platformLabel } from "@/lib/utils";
import Link from "next/link";
import { useEffect, useState } from "react";

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Meeting[]>("/api/meetings")
      .then(setMeetings)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div>
      <div className="flex items-end justify-between gap-4">
        <PageTitle title="Meetings" text="Join a Microsoft Teams session." />
        <Link href="/meetings/new">
          <Button>New meeting</Button>
        </Link>
      </div>
      {error && <p className="mb-4 text-sm text-rose-700">{error}</p>}
      {meetings.length === 0 ? (
        <Empty>No meetings yet.</Empty>
      ) : (
        <div className="overflow-hidden rounded-xl border border-stone-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
              <tr>
                <th className="px-4 py-3 font-medium">Meeting</th>
                <th className="px-4 py-3 font-medium">Platform</th>
                <th className="px-4 py-3 font-medium">When</th>
                <th className="px-4 py-3 font-medium">People</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Sentiment</th>
              </tr>
            </thead>
            <tbody>
              {meetings.map((meeting) => (
                <tr key={meeting.id} className="border-t border-stone-100">
                  <td className="px-4 py-3">
                    <Link href={`/meetings/${meeting.id}`} className="font-medium text-teal-900 hover:underline">
                      {meeting.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-stone-600">{platformLabel(meeting.platform)}</td>
                  <td className="px-4 py-3 text-stone-600">{formatWhen(meeting.started_at || meeting.created_at)}</td>
                  <td className="px-4 py-3 text-stone-600">{meeting.participants.join(", ") || "—"}</td>
                  <td className="px-4 py-3">
                    <StatusPill value={meeting.status} />
                  </td>
                  <td className="px-4 py-3">
                    <Sentiment value={meeting.sentiment} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
