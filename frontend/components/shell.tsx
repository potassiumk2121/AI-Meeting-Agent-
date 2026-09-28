"use client";

import { API_URL } from "@/lib/api";
import type { PublicBrand } from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  CalendarDays,
  CheckSquare,
  LayoutDashboard,
  MessagesSquare,
  Scale,
  Search,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";

const LINKS = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/meetings", label: "Meetings", icon: MessagesSquare },
  { href: "/participants", label: "Participants", icon: Users },
  { href: "/tasks", label: "Tasks", icon: CheckSquare },
  { href: "/decisions", label: "Decisions", icon: Scale },
  { href: "/search", label: "Ask", icon: Search },
  { href: "/reports", label: "Reports", icon: CalendarDays },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const [brand, setBrand] = useState<PublicBrand>({
    company_name: "RIGORA",
    company_tagline: "Meeting Intelligence",
    brand_color: "#102033",
  });
  useEffect(() => {
    fetch(`${API_URL}/api/settings/public`)
      .then((response) => response.json())
      .then((data: PublicBrand) =>
        setBrand({
          company_name: data.company_name || "RIGORA",
          company_tagline: data.company_tagline || "Meeting Intelligence",
          brand_color: data.brand_color?.trim() || "#102033",
        }),
      )
      .catch(() => undefined);
    setReady(true);
  }, []);

  if (!ready) return <div className="p-8 text-sm text-stone-500">Loading…</div>;

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 flex w-60 flex-col text-stone-100" style={{ background: brand.brand_color }}>
        <Link href="/dashboard" className="block px-5 py-6 hover:bg-white/5">
          <div className="font-serif text-2xl">{brand.company_name}</div>
          <div className="mt-1 text-xs uppercase tracking-wider text-stone-300">{brand.company_tagline}</div>
        </Link>
        <nav className="flex-1 space-y-1 px-3">
          {LINKS.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
            const Icon = link.icon;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                  active ? "bg-white/15 text-white" : "text-stone-300 hover:bg-white/10 hover:text-white",
                )}
              >
                <Icon size={16} />
                {link.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="pl-60">
        <div className="mx-auto max-w-6xl px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
