import { LayoutDashboard, Radar, ShieldAlert, Laptop2, Network, Settings, ShieldHalf } from "lucide-react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/operations", label: "Security Operations", icon: ShieldAlert },
  { to: "/incidents", label: "Investigation", icon: Radar },
  { to: "/devices", label: "Devices", icon: Laptop2 },
  { to: "/network", label: "Network", icon: Network },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-panel-line bg-panel/60 backdrop-blur-sm md:flex">
      <div className="flex items-center gap-2.5 px-6 py-5">
        <ShieldHalf className="h-6 w-6 text-sentinel" />
        <div>
          <p className="font-display text-sm font-semibold leading-none text-fog">SentinelAI</p>
          <p className="mt-1 text-[11px] uppercase tracking-wider text-fog-faint">Security Copilot</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-2">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sentinel/10 text-sentinel"
                  : "text-fog-dim hover:bg-panel-raised hover:text-fog"
              )
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-panel-line px-4 py-4">
        <div className="flex items-center gap-2 text-xs text-fog-faint">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sentinel/60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-sentinel" />
          </span>
          Monitoring active
        </div>
      </div>
    </aside>
  );
}
