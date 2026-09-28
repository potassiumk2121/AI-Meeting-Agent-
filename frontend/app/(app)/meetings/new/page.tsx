"use client";

import { Button, PageTitle, Select, TextInput } from "@/components/ui";
import { api } from "@/lib/api";
import type { MeetingDetail } from "@/lib/types";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

export default function NewMeetingPage() {
  const router = useRouter();
  const [title, setTitle] = useState("RIGORA deployment review");
  const [platform, setPlatform] = useState("teams");
  const [joinUrl, setJoinUrl] = useState("");
  const [organizer, setOrganizer] = useState("");
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
          platform,
          join_url: joinUrl || null,
          organizer_email: organizer || null,
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
      <PageTitle title="New meeting" text="Create the session, then join it. The live page accepts microphone audio, pasted lines, and a sample dialogue." />
      <form className="space-y-4 rounded-xl border border-stone-200 bg-white p-5" onSubmit={submit}>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Title</span>
          <TextInput value={title} onChange={(event) => setTitle(event.target.value)} required />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Platform</span>
          <Select value={platform} onChange={(event) => setPlatform(event.target.value)}>
            <option value="teams">Microsoft Teams</option>
            <option value="google_meet">Google Meet</option>
          </Select>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Join link</span>
          <TextInput value={joinUrl} onChange={(event) => setJoinUrl(event.target.value)} placeholder="https://teams.microsoft.com/l/meetup-join/… or https://meet.google.com/abc-defg-hij" />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Organizer email</span>
          <TextInput type="email" value={organizer} onChange={(event) => setOrganizer(event.target.value)} placeholder="Used to pull a Teams transcript" />
        </label>
        {error && <p className="text-sm text-rose-700">{error}</p>}
        <Button disabled={busy}>{busy ? "Creating…" : "Create meeting"}</Button>
      </form>
    </div>
  );
}
