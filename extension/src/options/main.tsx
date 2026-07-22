import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { Options } from "@/options/Options";
import "@/options/index.css";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Root element not found");

createRoot(rootElement).render(
  <StrictMode>
    <Options />
  </StrictMode>
);
