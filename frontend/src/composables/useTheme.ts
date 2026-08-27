import { computed, ref } from "vue";

type ThemeMode = "system" | "light" | "dark";

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

  function toggle(): void {
    mode.value = isDark.value ? "light" : "dark";
    localStorage.setItem("themeFollowSystem", "false");
    localStorage.setItem("theme", mode.value);
    applyDocumentTheme(isDark.value);
  }

  return { isDark, init, toggle };
}
