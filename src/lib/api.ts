import { invoke } from "@tauri-apps/api/core";

export interface ReportPayload {
  PATH: string;
  CLIENT_NAME: string;
  PROJECT_NAME: string;
  PROJECT_LOCATION: string;
  EMAIL_PREFIX: string;
  HAS_EXTENDED_TRAVEL: boolean;
  MAX_TD: number | null;
  GUIDANCE: "BS9991" | "ADB";
}

let cachedPort: number | null = null;

async function getSidecarPort(): Promise<number> {
  if (cachedPort != null) return cachedPort;
  const port = await invoke<number>("get_sidecar_port");
  cachedPort = port;
  return port;
}

export async function generateReport(
  payload: ReportPayload
): Promise<unknown> {
  const port = await getSidecarPort();
  const url = `http://127.0.0.1:${port}/generate-report`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }
  return response.json();
}
