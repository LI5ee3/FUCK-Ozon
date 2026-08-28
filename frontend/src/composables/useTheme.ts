import { computed, ref } from "vue";

export type ThemeMode = "system" | "light" | "dark";

const mode = ref<ThemeMode>("system");
const systemDark = ref(false);
let initialized = false;

function readMode(): ThemeMode {
  try {
    if (localStorage.getItem("themeFollowSystem") !== "false") return "system";
    return localStorage.getItem("theme") === "dark" ? "dark" : "light";
  } catch {
    return "system";
  }
}

function applyDocumentTheme(dark: boolean): void {
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

const isDark = computed(() => mode.value === "dark" || (mode.value === "system" && systemDark.value));

export function useTheme() {
  function init(): void {
    if (initialized) return;
    initialized = true;
    mode.value = readMode();
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    systemDark.value = media.matches;
    media.addEventListener("change", (event) => {
      systemDark.value = event.matches;
      if (mode.value === "system") applyDocumentTheme(event.matches);
    });
    applyDocumentTheme(isDark.value);
  }

  function setMode(next: ThemeMode): void {
    mode.value = next;
    if (next === "system") {
      localStorage.setItem("themeFollowSystem", "true");
      localStorage.removeItem("theme");
    } else {
      localStorage.setItem("themeFollowSystem", "false");
      localStorage.setItem("theme", next);
    }
    applyDocumentTheme(isDark.value);
  }

  function toggle(): void {
    setMode(isDark.value ? "light" : "dark");
  }

  return { mode, isDark, init, toggle, setMode };
}
