import type { GlobalThemeOverrides } from "naive-ui";
import { macaronTokens } from "./tokens";

type Palette = { [Key in keyof typeof macaronTokens.light]: string };

function createThemeOverrides(colors: Palette): GlobalThemeOverrides {
  return {
    common: {
      primaryColor: colors.primary,
      primaryColorHover: colors.primaryFocus,
      primaryColorPressed: colors.primaryActive,
      primaryColorSuppl: colors.primaryFocus,
      infoColor: colors.primary,
      successColor: colors.success,
      warningColor: colors.warning,
      errorColor: colors.danger,
      bodyColor: colors.canvas,
      cardColor: colors.panelSolid,
      modalColor: colors.panelSolid,
      popoverColor: colors.panelSolid,
      textColorBase: colors.text,
      textColor1: colors.text,
      textColor2: colors.muted,
      textColor3: colors.muted,
      borderColor: colors.line,
      dividerColor: colors.line,
    },
    Button: {
      borderRadiusMedium: macaronTokens.radius.input,
    },
    Card: {
      borderRadius: macaronTokens.radius.card,
    },
  };
}

export const lightThemeOverrides = createThemeOverrides(macaronTokens.light);
export const darkThemeOverrides = createThemeOverrides(macaronTokens.dark);
