import {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {App as AntdApp, ConfigProvider} from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import {buildAntdTheme} from './design/antdTheme';
import './styles.css';
import {applyTheme, resolveTheme, THEME_STORAGE_KEY, type Theme} from './theme';

let storedTheme: string | null = null;
try {
  storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
} catch {
  // 在加固的浏览器环境中，本地存储可能不可用。
}
applyTheme(resolveTheme(storedTheme, window.matchMedia('(prefers-color-scheme: dark)').matches));

function Root() {
  const [theme, setTheme] = useState<Theme>(() => resolveTheme(document.documentElement.dataset.theme, false));

  useEffect(() => {
    applyTheme(theme);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // 当持久化不可用时，主题仍然生效。
    }
  }, [theme]);

  const toggleTheme = () => setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  return (
    <ConfigProvider theme={buildAntdTheme(theme)} locale={zhCN}>
      <AntdApp>
        <App theme={theme} onToggleTheme={toggleTheme} />
      </AntdApp>
    </ConfigProvider>
  );
}

createRoot(document.getElementById('root')!).render(<Root />);