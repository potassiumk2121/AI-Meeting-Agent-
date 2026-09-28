"use client";

import { Empty, PageTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { formatWhen } from "@/lib/utils";
import { useEffect, useState } from "react";

type Person = { name: string; email: string | null; meetings: number; last_seen: string | null };

export default function ParticipantsPage() {
  const [people, setPeople] = useState<Person[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Person[]>("/api/participants")
      .then(setPeople)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div>
      <PageTitle title="Participants" text="Everyone identified in a transcript or chat." />
      {error && <p className="mb-4 text-sm text-rose-700">{error}</p>}
      {people.length === 0 ? (
        <Empty>No participants yet.</Empty>
      ) : (
        <div className="overflow-hidden rounded-xl border border-stone-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-stone-50 text-xs uppercase tracking-wide text-stone-500">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Meetings</th>
                <th className="px-4 py-3 font-medium">Last seen</th>
              </tr>
            </thead>
            <tbody>
              {people.map((person) => (
                <tr key={person.name} className="border-t border-stone-100">
                  <td className="px-4 py-3 font-medium">{person.name}</td>
                  <td className="px-4 py-3 text-stone-600">{person.email || "—"}</td>
                  <td className="px-4 py-3 text-stone-600">{person.meetings}</td>
                  <td className="px-4 py-3 text-stone-600">{formatWhen(person.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
