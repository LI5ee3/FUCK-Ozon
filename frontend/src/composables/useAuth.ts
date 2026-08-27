import { onBeforeUnmount, onMounted, ref } from "vue";
import { getSession, login as loginRequest } from "../api/auth";
import { getErrorMessage, setCsrfToken, UNAUTHORIZED_EVENT } from "../api/client";

export function useAuth() {
  const authenticated = ref(false);
  const ready = ref(false);
  const loading = ref(false);
  const error = ref("");

  function applySession(session: { authenticated: boolean; csrf_token: string }): void {
    authenticated.value = session.authenticated;
    setCsrfToken(session.authenticated ? session.csrf_token : "");
  }

  async function restoreSession(): Promise<void> {
    loading.value = true;
    error.value = "";
    try {
      applySession(await getSession());
    } catch (cause) {
      setCsrfToken("");
      error.value = getErrorMessage(cause);
    } finally {
      loading.value = false;
      ready.value = true;
    }
  }

  async function login(password: string): Promise<boolean> {
    if (!password.trim()) {
      error.value = "请输入管理员密码";
      return false;
    }
    loading.value = true;
    error.value = "";
    try {
      await loginRequest(password);
      const session = await getSession();
      applySession(session);
      if (!authenticated.value) throw new Error("登录状态未建立");
      return true;
    } catch (cause) {
      setCsrfToken("");
      authenticated.value = false;
      error.value = getErrorMessage(cause);
      return false;
    } finally {
      loading.value = false;
    }
  }

  const handleUnauthorized = (): void => {
    authenticated.value = false;
    error.value = "登录状态已失效，请重新登录";
  };

  onMounted(() => window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized));
  onBeforeUnmount(() => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized));

  return { authenticated, ready, loading, error, restoreSession, login };
}
