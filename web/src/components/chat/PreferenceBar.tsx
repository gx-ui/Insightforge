import {useCallback, useState} from 'react';
import {Settings, X, ChevronLeft, ChevronRight, RotateCcw} from 'lucide-react';
import type {PreferenceSnapshot} from '../../types';
import {
  DEFAULT_PREFERENCES,
  applySelection,
  clampSelection,
  defaultSelection,
  fieldLabel,
  fieldOptions,
  fieldOrder,
  formatPreferenceBar,
  nextSelection,
  prevSelection,
  type PrefSelection,
} from './preferences';

export default function PreferenceBar({
  prefs,
  version,
  onUpdate,
}: {
  prefs: PreferenceSnapshot;
  version: number;
  onUpdate: (prefs: PreferenceSnapshot, version: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const [selection, setSelection] = useState<PrefSelection>(defaultSelection());
  const {tab, field: activeField, index: activeIndex} = selection;
  const fields = fieldOrder(tab);
  const tabPrefs = tab === 'image' ? prefs.image : prefs.video;

  const handleSelect = useCallback(() => {
    const newPrefs = applySelection(prefs, selection);
    onUpdate(newPrefs, version);
  }, [prefs, selection, version, onUpdate]);

  const handleReset = useCallback(() => {
    onUpdate(DEFAULT_PREFERENCES, version);
  }, [version, onUpdate]);

  const summary = formatPreferenceBar(prefs, open ? 600 : 400);

  const fieldLabels: Record<string, string> = {
    aspect_ratio: '比例',
    model: '模型',
    quality: '画质',
    resolution: '分辨率',
  };

  return (
    <div className="preference-bar">
      <button className="pref-summary" onClick={() => setOpen((v) => !v)} title="生成偏好设置">
        <Settings size={14} className="pref-icon" />
        <span className="pref-summary-text">{summary}</span>
      </button>

      {open && (
        <div className="pref-panel" role="dialog" aria-label="生成偏好">
          <div className="pref-panel-header">
            <div className="pref-tabs">
              <button
                className={"pref-tab" + (tab === 'image' ? ' active' : '')}
                onClick={() => setSelection(clampSelection({tab: 'image', field: 'aspect_ratio', index: 0}))}
              >
                🖼 图片
              </button>
              <button
                className={"pref-tab" + (tab === 'video' ? ' active' : '')}
                onClick={() => setSelection(clampSelection({tab: 'video', field: 'aspect_ratio', index: 0}))}
              >
                🎬 视频
              </button>
            </div>
            <div className="pref-actions">
              <button className="pref-reset" onClick={handleReset} title="重置为默认值">
                <RotateCcw size={14} />
              </button>
              <button className="pref-close" onClick={() => setOpen(false)} title="关闭">
                <X size={14} />
              </button>
            </div>
          </div>

          <div className="pref-fields">
            {fields.map((field) => {
              const options = fieldOptions(tab, field);
              const currentValue = (tabPrefs as Record<string, string>)[field];
              const isActive = field === activeField;
              return (
                <div key={field} className={"pref-field" + (isActive ? ' active' : '')}>
                  <div className="pref-field-label" onClick={() => {
                    const idx = Math.max(0, options.indexOf(currentValue));
                    setSelection({tab, field, index: idx});
                  }}>
                    {fieldLabels[field]}: <strong>{fieldLabel(tab, field, currentValue)}</strong>
                  </div>
                  {isActive && (
                    <div className="pref-options">
                      <button
                        className="pref-arrow"
                        onClick={() => setSelection((sel) => clampSelection({...sel, index: Math.max(0, sel.index - 1)}))}
                        disabled={activeIndex <= 0}
                      >
                        <ChevronLeft size={14} />
                      </button>
                      <div className="pref-options-list">
                        {options.map((option, optIndex) => (
                          <button
                            key={option}
                            className={"pref-option" + (option === currentValue ? ' current' : '') + (optIndex === activeIndex ? ' selected' : '')}
                            onClick={() => {
                              const newSel = {...selection, index: optIndex};
                              setSelection(newSel);
                              const newPrefs = applySelection(prefs, newSel);
                              onUpdate(newPrefs, version);
                            }}
                          >
                            {fieldLabel(tab, field, option)}
                          </button>
                        ))}
                      </div>
                      <button
                        className="pref-arrow"
                        onClick={() => setSelection((sel) => clampSelection({...sel, index: sel.index + 1}))}
                        disabled={activeIndex >= options.length - 1}
                      >
                        <ChevronRight size={14} />
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}