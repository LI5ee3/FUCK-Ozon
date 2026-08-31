import type { GlobalThemeOverrides } from "naive-ui";
import { macaronTokens } from "./tokens";

type Palette = { [Key in keyof typeof macaronTokens.light]: string };

function createThemeOverrides(colors: Palette): GlobalThemeOverrides {
  return {
    common: {
      fontFamily: macaronTokens.fontFamily,
      borderRadius: macaronTokens.radius.input,
      borderRadiusSmall: macaronTokens.radius.input,
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
    Input: { borderRadius: macaronTokens.radius.input },
    InternalSelection: { borderRadius: macaronTokens.radius.input },
    // Select uses InternalSelection; DatePicker and InputNumber use Input peers.
    Select: { peers: { InternalSelection: { borderRadius: macaronTokens.radius.input } } },
    DatePicker: { peers: { Input: { borderRadius: macaronTokens.radius.input } } },
    Tag: { borderRadius: macaronTokens.radius.pill },
    Button: {
      borderRadiusTiny: macaronTokens.radius.input,
      borderRadiusSmall: macaronTokens.radius.input,
      borderRadiusLarge: macaronTokens.radius.input,
      borderRadiusMedium: macaronTokens.radius.input,
    },
    Card: {
      borderRadius: macaronTokens.radius.card,
    },
  };
}

export const lightThemeOverrides = createThemeOverrides(macaronTokens.light);
export const darkThemeOverrides = createThemeOverrides(macaronTokens.dark);
