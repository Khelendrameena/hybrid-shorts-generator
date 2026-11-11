import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { SESSION_TOKEN } from "@/lib/auth";
import Dashboard from "./Dashboard";

export const dynamic = "force-dynamic";

export default async function Home() {
  const store = await cookies();
  if (store.get("hsg_session")?.value !== SESSION_TOKEN) redirect("/login");
  return <Dashboard />;
}
