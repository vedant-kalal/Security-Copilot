import { LogOut } from "lucide-react";
import { useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/useAuth";

const TITLES: Record<string, string> = {
  "/": "Overview",
  "/operations": "Security Operations",
  "/incidents": "Investigation",
  "/devices": "Devices",
  "/network": "Network",
  "/settings": "Settings",
};

function resolveTitle(pathname: string): string {
  if (TITLES[pathname]) return TITLES[pathname];
  if (pathname.startsWith("/incidents/")) return "Incident Detail";
  return "SentinelAI";
}

export function Topbar() {
  const location = useLocation();
  const { user, logout } = useAuth();

  return (
    <header className="flex h-16 items-center justify-between border-b border-panel-line bg-panel/40 px-6 backdrop-blur-sm">
      <h1 className="font-display text-lg font-semibold text-fog">{resolveTitle(location.pathname)}</h1>
      <div className="flex items-center gap-4">
        <span className="hidden text-sm text-fog-dim sm:inline">{user?.email}</span>
        <Button variant="ghost" size="sm" onClick={logout}>
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </header>
  );
}
