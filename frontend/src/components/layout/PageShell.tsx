import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";

export function PageShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-bg-secondary">
      <Sidebar />
      <main className="px-4 pb-8 pt-28 sm:px-6 md:ml-56 md:px-8 md:pt-8">
        <div className="mx-auto max-w-[1440px]">{children}</div>
      </main>
    </div>
  );
}
