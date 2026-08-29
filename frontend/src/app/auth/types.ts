export interface SessionResponse {
  authenticated: boolean;
  csrf_token: string;
}

export interface LoginResponse {
  ok: boolean;
}
