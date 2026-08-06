import {createRoot} from 'react-dom/client';
import App from './App';
import './styles.css';
import {applyTheme, resolveTheme, THEME_STORAGE_KEY} from './theme';

let storedTheme: string | null = null;
try {
  storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
} catch {
  // 在加固的浏览器环境中，本地存储可能不可用。
}
applyTheme(resolveTheme(storedTheme, window.matchMedia('(prefers-color-scheme: dark)').matches));

createRoot(document.getElementById('root')!).render(<App />);
