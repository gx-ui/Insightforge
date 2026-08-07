import {theme as antdAlgorithm, type ThemeConfig} from 'antd';
import type {Theme} from '../theme';
import {fontStacks, radius, tokensFor} from './tokens';

export function buildAntdTheme(theme: Theme): ThemeConfig {
  const tokens = tokensFor(theme);
  return {
    algorithm: theme === 'dark' ? antdAlgorithm.darkAlgorithm : antdAlgorithm.defaultAlgorithm,
    token: {
      colorBgLayout: tokens.bgCanvas,
      colorBgContainer: tokens.bgRaised,
      colorBgElevated: tokens.bgOverlay,
      colorText: tokens.inkPrimary,
      colorTextSecondary: tokens.inkSecondary,
      colorTextTertiary: tokens.inkFaint,
      colorPrimary: tokens.accent,
      colorPrimaryHover: tokens.accent,
      colorPrimaryActive: tokens.accentDeep,
      colorError: tokens.error,
      colorWarning: tokens.warn,
      colorInfo: tokens.info,
      colorBorder: tokens.line,
      colorBorderSecondary: tokens.line,
      borderRadius: radius.control,
      fontFamily: fontStacks.body,
      fontFamilyCode: fontStacks.mono,
      boxShadow: '0 8px 32px rgba(0,0,0,.5)',
      motionDurationMid: '0.2s',
    },
    components: {
      Button: {
        colorPrimary: tokens.accent,
        colorPrimaryHover: tokens.accent,
        colorPrimaryActive: tokens.accentDeep,
        colorTextLightSolid: tokens.onAccent,
        fontWeight: 600,
      },
      Modal: {
        borderRadiusLG: radius.overlay,
      },
      Message: {
        borderRadiusLG: radius.control,
      },
      Input: {
        activeBorderColor: tokens.accent,
        hoverBorderColor: tokens.lineStrong,
      },
    },
  };
}