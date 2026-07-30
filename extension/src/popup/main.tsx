import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { initTheme } from "@/lib/theme";
import { Popup } from "@/popup/Popup";
import "@/popup/index.css";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Root element not found");

// Apply the saved theme before first render so there's no flash.
void initTheme().finally(() => {
  createRoot(rootElement).render(
    <StrictMode>
      <Popup />
    </StrictMode>
  );
});
