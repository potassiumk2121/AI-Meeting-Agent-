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
import { usePathname, useRouter } from "next/navigation";
import { MouseEvent, ReactNode, useEffect, useState } from "react";

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
  const router = useRouter();
  const [brand, setBrand] = useState<PublicBrand>({
    company_name: "Development Monitors",
    company_tagline: "AI Meeting Intelligence",
    brand_color: "#102033",
  });
  useEffect(() => {
    fetch(`${API_URL}/api/settings/public`)
      .then((response) => response.json())
      .then((data: PublicBrand) =>
        setBrand({
          company_name: data.company_name || "Development Monitors",
          company_tagline: data.company_tagline || "AI Meeting Intelligence",
          brand_color: data.brand_color?.trim() || "#102033",
        }),
      )
      .catch(() => undefined);
  }, []);

  function openHome(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    if (pathname !== "/dashboard") router.push("/dashboard");
  }

  return (
    <div className="min-h-screen bg-[#f6f3ee]">
      <aside className="fixed inset-y-0 left-0 flex w-64 flex-col border-r border-stone-200/90 bg-[#f6f3ee]">
        <Link href="/dashboard" scroll={false} onClick={openHome} className="block px-6 pb-1 pt-8">
          <img src="/brand/development-monitors.png" alt={brand.company_name} className="h-auto w-full" />
        </Link>
        <div className="mx-6 mt-4 h-px w-8 bg-[#c46a3a]/80" />
        <div className="px-6 pb-6 pt-4 text-[10px] font-medium uppercase tracking-[0.22em] text-stone-400">
          {brand.company_tagline}
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {LINKS.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
            const Icon = link.icon;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm",
                  active ? "bg-[#ebe6df] text-stone-900" : "text-stone-500 hover:bg-[#ebe6df]/70 hover:text-stone-800",
                )}
              >
                <Icon size={15} strokeWidth={1.75} />
                {link.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="pl-64">
        <div className="mx-auto max-w-6xl px-10 py-10">{children}</div>
      </main>
    </div>
  );
}
