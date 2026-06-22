import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

const el = document.getElementById("dc-root");
if (!el) throw new Error("#dc-root not found");
createRoot(el).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
