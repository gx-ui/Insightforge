export type Theme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'insightforge-web-theme';

export function resolveTheme(stored: string | null | undefined, _prefersDark?: boolean): Theme {
  if (stored === 'light' || stored === 'dark') return stored;
  return 'dark';
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) meta.content = theme === 'dark' ? '#0A0C0E' : '#FAFBF7';
}