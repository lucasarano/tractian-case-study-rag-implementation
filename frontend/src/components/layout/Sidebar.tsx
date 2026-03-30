import { NavLink } from "react-router-dom";
import { LayoutDashboard, MessageCircleQuestion, Wrench } from "lucide-react";

const links = [
  { to: "/", label: "Architecture", icon: LayoutDashboard },
  { to: "/rag", label: "RAG", icon: MessageCircleQuestion },
];

export function Sidebar() {
  return (
    <aside className="fixed inset-x-0 top-0 z-30 border-b border-border bg-white/90 backdrop-blur-xl md:inset-y-0 md:left-0 md:flex md:w-56 md:flex-col md:border-b-0 md:border-r">
      <div className="flex items-center gap-2.5 px-4 py-4 md:px-5 md:py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-accent-blue">
          <Wrench className="h-4 w-4 text-white" />
        </div>
        <p className="text-sm font-bold text-text-primary">Maintenance Copilot</p>
      </div>

      <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:overflow-visible md:px-3">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium transition-all ${
                isActive
                  ? "bg-accent-blue/10 text-accent-blue"
                  : "text-text-secondary hover:bg-bg-secondary hover:text-text-primary"
              }`
            }
          >
            <Icon className="h-[18px] w-[18px]" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="hidden mt-auto px-4 pb-5 md:block">
        <p className="text-[11px] leading-relaxed text-text-muted text-center">
          Demo &middot; First 50 pages loaded
        </p>
      </div>
    </aside>
  );
}
