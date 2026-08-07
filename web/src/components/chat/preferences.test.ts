import {describe, expect, it} from 'vitest';
import type {PrefSelection} from './preferences';
import {
  DEFAULT_PREFERENCES,
  applySelection,
  clampSelection,
  fieldLabel,
  fieldOptions,
  fieldOrder,
  formatPreferenceBar,
} from './preferences';

describe('preferences', () => {
  it('provides sane defaults', () => {
    expect(DEFAULT_PREFERENCES.image).toEqual({aspect_ratio: '16:9', model: 'follow_config', quality: '2k'});
    expect(DEFAULT_PREFERENCES.video).toEqual({aspect_ratio: '16:9', model: 'follow_config', resolution: '1080p'});
  });

  it('orders fields per tab', () => {
    expect(fieldOrder('image')).toEqual(['aspect_ratio', 'model', 'quality']);
    expect(fieldOrder('video')).toEqual(['aspect_ratio', 'model', 'resolution']);
  });

  it('maps option keys to display labels', () => {
    expect(fieldLabel('image', 'aspect_ratio', 'auto')).toBe('智能');
    expect(fieldLabel('image', 'aspect_ratio', '16:9')).toBe('16:9');
    expect(fieldLabel('image', 'model', 'seedream_5_0_pro')).toBe('Seedream 5.0 Pro');
    expect(fieldLabel('image', 'quality', '2k')).toBe('2K');
  });

  it('applies a selection immutably to the chosen field only', () => {
    const selection: PrefSelection = {tab: 'image', field: 'quality', index: 0};
    const next = applySelection(DEFAULT_PREFERENCES, selection);
    expect(next.image.quality).toBe('1080');
    expect(next.image.aspect_ratio).toBe(DEFAULT_PREFERENCES.image.aspect_ratio);
    expect(next.video).toEqual(DEFAULT_PREFERENCES.video);
    expect(next).not.toBe(DEFAULT_PREFERENCES);
  });

  it('clamps selection index to option bounds', () => {
    const maxIndex = fieldOptions('image', 'aspect_ratio').length - 1;
    expect(clampSelection({tab: 'image', field: 'aspect_ratio', index: 99}).index).toBe(maxIndex);
    expect(clampSelection({tab: 'image', field: 'aspect_ratio', index: -1}).index).toBe(0);
  });

  it('formats a summary bar with width-sensitive detail', () => {
    const full = formatPreferenceBar(DEFAULT_PREFERENCES, 600);
    expect(full).toContain('16:9');
    expect(full).toContain('跟随配置');
    expect(full).toContain('2K');

    const medium = formatPreferenceBar(DEFAULT_PREFERENCES, 400);
    expect(medium).toContain('16:9');
    expect(medium).toContain('1080p');
    expect(medium).not.toContain('跟随配置');

    expect(formatPreferenceBar(DEFAULT_PREFERENCES, 300)).toContain('偏好');
  });
});
