export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function errorMessage(body: unknown, fallback: string) {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (first?.msg) return first.msg;
    }
  }
  return fallback;
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const { headers, body, ...rest } = options;
  const requestHeaders = new Headers(headers);
  if (body && !(body instanceof FormData) && !requestHeaders.has("Content-Type")) {
    requestHeaders.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...rest, body, headers: requestHeaders });
  } catch {
    throw new Error("The meeting service is not reachable.");
  }
  if (response.status === 204) return null as T;
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(errorMessage(payload, response.statusText));
  return payload as T;
}

export function wsUrl(path: string) {
  const base = API_URL.replace(/^http/, "ws");
  return `${base}${path}`;
}

export async function downloadReport(id: string, filename: string) {
  const response = await fetch(`${API_URL}/api/meetings/${id}/report.pdf`);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(errorMessage(payload, "Could not download the PDF"));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
