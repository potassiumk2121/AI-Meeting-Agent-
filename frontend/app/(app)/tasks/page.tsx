"use client";

import { Empty, PageTitle } from "@/components/ui";
import { api } from "@/lib/api";
import type { Task } from "@/lib/types";
import Link from "next/link";
import { useEffect, useState } from "react";

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [error, setError] = useState("");

  function load() {
    api<Task[]>("/api/tasks")
      .then(setTasks)
      .catch((err: Error) => setError(err.message));
  }

  useEffect(load, []);

  async function toggle(task: Task) {
    await api(`/api/action-items/${task.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: task.status === "open" ? "done" : "open" }),
    });
    load();
  }

  return (
    <div>
      <PageTitle title="Tasks" text="Action items detected during meetings and confirmed when the report is written." />
      {error && <p className="mb-4 text-sm text-rose-700">{error}</p>}
      {tasks.length === 0 ? (
        <Empty>No tasks yet.</Empty>
      ) : (
        <div className="space-y-2">
          {tasks.map((task) => (
            <div key={task.id} className="flex items-start gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3">
              <input type="checkbox" className="mt-1" checked={task.status === "done"} onChange={() => toggle(task)} />
              <div>
                <div className={task.status === "done" ? "text-sm text-stone-400 line-through" : "text-sm font-medium"}>{task.description}</div>
                <div className="mt-1 text-xs text-stone-500">
                  {task.assignee_name}
                  {task.due_label ? ` · ${task.due_label}` : ""} ·{" "}
                  <Link href={`/meetings/${task.meeting_id}`} className="text-teal-900 hover:underline">
                    {task.meeting_title}
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
