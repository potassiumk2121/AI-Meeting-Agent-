"use client";

import { Button, PageTitle, TextInput } from "@/components/ui";
import { api } from "@/lib/api";
import type { MeetingDetail } from "@/lib/types";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

export default function NewMeetingPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [joinUrl, setJoinUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const detail = await api<MeetingDetail>("/api/meetings", {
        method: "POST",
        body: JSON.stringify({
          title,
          platform: "teams",
          join_url: joinUrl || null,
        }),
      });
      router.push(`/meetings/${detail.meeting.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the meeting");
      setBusy(false);
    }
  }

  return (
    <div className="max-w-xl">
      <PageTitle title="New meeting" text="Create the session, then join it from the live page with your microphone." />
      <form className="space-y-4 rounded-xl border border-stone-200 bg-white p-5" onSubmit={submit}>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Title</span>
          <TextInput value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Meeting title" required />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Teams join link</span>
          <TextInput value={joinUrl} onChange={(event) => setJoinUrl(event.target.value)} placeholder="https://teams.microsoft.com/l/meetup-join/…" required />
        </label>
        {error && <p className="text-sm text-rose-700">{error}</p>}
        <Button disabled={busy}>{busy ? "Joining…" : "Join meeting"}</Button>
      </form>
    </div>
  );
}
