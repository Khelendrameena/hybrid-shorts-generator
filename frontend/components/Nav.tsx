"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/processing", label: "Processing" },
  { href: "/analysis", label: "AI Analysis" },
  { href: "/editor", label: "Shorts Editor" },
  { href: "/export", label: "Export" },
  { href: "/settings", label: "Settings" },
];

export default function Nav() {
  const path = usePathname();
  const params = useSearchParams();
  const pid = params.get("project") || (typeof window !== "undefined" ? localStorage.getItem("currentProject") : null);
  return (
    <header className="border-b border-white/10 bg-panel/80 sticky top-0 z-10 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-3 flex-wrap">
        <Link href="/" className="font-bold text-lg mr-3">🎬 Hybrid <span className="text-accent">Shorts</span> AI</Link>
        {LINKS.map((l) => {
          const href = pid && l.href !== "/" ? `${l.href}?project=${pid}` : l.href;
          const active = path === l.href;
          return (
            <Link key={l.href} href={href}
              className={`rounded-full px-3 py-1 text-sm ${active ? "bg-accent text-black font-semibold" : "text-white/70 hover:text-white"}`}>
              {l.label}
            </Link>
          );
        })}
        <span className="ml-auto hidden md:block text-xs text-white/40">Laya = decisions · Ollama qwen3:4b = creative · 100% local</span>
      </div>
    </header>
  );
}
