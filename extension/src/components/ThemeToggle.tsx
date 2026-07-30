import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { getTheme, setTheme, type Theme } from "@/lib/theme";

/** A sun/moon button that flips the persisted light/dark theme. */
export function ThemeToggle() {
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    void getTheme().then(setThemeState);
  }, []);

  async function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setThemeState(next);
    await setTheme(next);
  }

  return (
    <button
      onClick={toggle}
      title={theme === "dark" ? "Switch to light" : "Switch to dark"}
      aria-label="Toggle theme"
      className="rounded-md p-1.5 text-fog-faint transition-colors duration-200 hover:bg-panel-raised hover:text-fog"
    >
      {theme === "dark" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
    </button>
  );
}
