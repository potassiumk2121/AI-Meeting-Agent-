import { cn } from "@/lib/utils";
import {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" }) {
  const styles = {
    primary: "bg-teal-800 text-white hover:bg-teal-900",
    secondary: "bg-white text-stone-800 ring-1 ring-stone-300 hover:bg-stone-50",
    ghost: "text-stone-600 hover:bg-stone-200/70",
    danger: "bg-rose-700 text-white hover:bg-rose-800",
  };
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-md px-3 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50",
        styles[variant],
        className,
      )}
      {...props}
    />
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={cn(
        "w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none ring-teal-700 focus:ring-2",
        props.className,
      )}
    />
  );
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={cn(
        "w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none ring-teal-700 focus:ring-2",
        props.className,
      )}
    />
  );
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={cn(
        "w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none ring-teal-700 focus:ring-2",
        props.className,
      )}
    />
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cn("rounded-xl border border-stone-200 bg-white p-5 shadow-sm", className)}>{children}</section>;
}

const SENTIMENT: Record<string, string> = {
  positive: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  neutral: "bg-stone-100 text-stone-700 ring-stone-200",
  urgent: "bg-amber-50 text-amber-900 ring-amber-200",
  blocked: "bg-rose-50 text-rose-800 ring-rose-200",
};

export function Sentiment({ value }: { value?: string | null }) {
  if (!value) return <span className="text-xs text-stone-400">—</span>;
  return (
    <span className={cn("inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize ring-1 ring-inset", SENTIMENT[value] || SENTIMENT.neutral)}>
      {value}
    </span>
  );
}

const STATUS: Record<string, string> = {
  scheduled: "bg-stone-100 text-stone-700",
  live: "bg-rose-50 text-rose-700",
  processing: "bg-amber-50 text-amber-800",
  completed: "bg-emerald-50 text-emerald-800",
  failed: "bg-rose-50 text-rose-800",
};

export function StatusPill({ value }: { value: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize", STATUS[value] || STATUS.scheduled)}>
      {value === "live" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-rose-600" />}
      {value}
    </span>
  );
}

export function PageTitle({ title, text, className }: { title: string; text?: string; className?: string }) {
  return (
    <div className={cn("mb-6", className)}>
      <h1 className="font-serif text-3xl text-stone-900">{title}</h1>
      {text && <p className="mt-1 max-w-2xl text-sm text-stone-600">{text}</p>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-stone-300 bg-white px-4 py-8 text-center text-sm text-stone-500">{children}</div>;
}
