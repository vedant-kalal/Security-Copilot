import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { initTheme } from "@/lib/theme";
import { Blocked } from "@/blocked/Blocked";
import "@/blocked/index.css";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Root element not found");

void initTheme().finally(() => {
  createRoot(rootElement).render(
    <StrictMode>
      <Blocked />
    </StrictMode>
  );
});
