import type {Theme} from '../theme';

export type DesignTokens = {
  bgCanvas: string;
  bgRaised: string;
  bgOverlay: string;
  inkPrimary: string;
  inkSecondary: string;
  inkFaint: string;
  accent: string;
  accentDeep: string;
  accentGlow: string;
  flowTeal: string;
  error: string;
  warn: string;
  info: string;
  line: string;
  lineStrong: string;
  onAccent: string;
};

export const darkTokens: DesignTokens = {
  bgCanvas: '#0A0C0E',
  bgRaised: '#12151A',
  bgOverlay: '#1A1E24',
  inkPrimary: '#F2F5F0',
  inkSecondary: '#9AA38F',
  inkFaint: '#5A6255',
  accent: '#C6F135',
  accentDeep: '#8FBF1F',
  accentGlow: 'rgba(198,241,53,.35)',
  flowTeal: '#3ED6A4',
  error: '#FF6B5E',
  warn: '#FFB224',
  info: '#5EB0FF',
  line: 'rgba(255,255,255,.08)',
  lineStrong: 'rgba(255,255,255,.14)',
  onAccent: '#0A0C0E',
};

export const lightTokens: DesignTokens = {
  bgCanvas: '#FAFBF7',
  bgRaised: '#FFFFFF',
  bgOverlay: '#FFFFFF',
  inkPrimary: '#1C211A',
  inkSecondary: '#5A6255',
  inkFaint: '#9AA38F',
  accent: '#8FBF1F',
  accentDeep: '#6F9618',
  accentGlow: 'rgba(143,191,31,.25)',
  flowTeal: '#2BA384',
  error: '#D63B2F',
  warn: '#A96D17',
  info: '#1769D2',
  line: 'rgba(28,33,26,.10)',
  lineStrong: 'rgba(28,33,26,.18)',
  onAccent: '#1C211A',
};

export function tokensFor(theme: Theme): DesignTokens {
  return theme === 'dark' ? darkTokens : lightTokens;
}

export const fontStacks = {
  display: `'Smiley Sans', 'Space Grotesk', 'MiSans', system-ui, sans-serif`,
  body: `'MiSans', -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif`,
  mono: `'JetBrains Mono', ui-monospace, 'SF Mono', Consolas, monospace`,
};

export const radius = {control: 8, card: 12, overlay: 16, capsule: 999};

export const typeScale = [12, 14, 16, 20, 25, 31, 39] as const;

export const motion = {hover: 150, panel: 200, message: 240, theme: 300, flowBand: '8-12s'};