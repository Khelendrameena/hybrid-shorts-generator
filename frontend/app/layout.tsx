import "./globals.css";
import { Suspense } from "react";
import Nav from "../components/Nav";

export const metadata = { title: "Hybrid Shorts AI", description: "Laya + Ollama YouTube Shorts generator — 100% local" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Suspense fallback={null}><Nav /></Suspense>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
