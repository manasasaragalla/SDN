export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
export const isApiConfigured = Boolean(API_BASE_URL);
export const AUTH_DISABLED =
  process.env.NEXT_PUBLIC_INTENTFLOW_AUTH_DISABLED === "true";

export class ApiConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiConfigurationError";
  }
}

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiConfigurationError(
      "Backend API is not configured. Set NEXT_PUBLIC_API_BASE_URL when the Python API is available.",
    );
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: AUTH_DISABLED ? "omit" : "include",
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null) as
      | { detail?: string }
      | null;
    throw new ApiRequestError(
      payload?.detail ?? `Backend request failed with HTTP ${response.status}.`,
      response.status,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
