export const UNAUTHORIZED_EVENT = "opanel:unauthorized";
export const LOGOUT_EVENT = "opanel:logout";

let csrfToken = "";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function setCsrfToken(token: string): void {
  csrfToken = token;
}

function bodyMessage(body: unknown): string | undefined {
  if (typeof body === "string" && body) return body;
  if (typeof body !== "object" || body === null || !("detail" in body)) return undefined;
  const detail = body.detail;
  return typeof detail === "string" ? detail : undefined;
}

async function readBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  if (response.headers.get("content-type")?.includes("application/json")) {
    return response.json().catch(() => undefined);
  }
  return response.text();
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (method !== "GET" && method !== "HEAD" && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  const response = await fetch(path, {
    ...options,
    credentials: "include",
    headers,
  });
  const body = await readBody(response);

  if (response.status === 401) {
    setCsrfToken("");
    if (typeof window !== "undefined") window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      bodyMessage(body) ?? `请求失败（${response.status}）`,
      body,
    );
  }
  return body as T;
}

export function requestJson<T>(
  path: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body: unknown,
): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "请求失败";
}
