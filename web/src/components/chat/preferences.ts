import type {ImagePreferences, VideoPreferences, PreferenceSnapshot} from '../../types';

export const DEFAULT_IMAGE_PREFERENCES: ImagePreferences = {
  aspect_ratio: '16:9',
  model: 'follow_config',
  quality: '2k',
};

export const DEFAULT_VIDEO_PREFERENCES: VideoPreferences = {
  aspect_ratio: '16:9',
  model: 'follow_config',
  resolution: '1080p',
};

export const DEFAULT_PREFERENCES: PreferenceSnapshot = {
  image: {...DEFAULT_IMAGE_PREFERENCES},
  video: {...DEFAULT_VIDEO_PREFERENCES},
};

export const IMAGE_ASPECT_RATIOS = ['auto', '1:1', '9:16', '16:9'];
export const VIDEO_ASPECT_RATIOS = ['auto', '1:1', '9:16', '16:9'];
export const IMAGE_MODELS = [
  {key: 'follow_config', label: '跟随配置'},
  {key: 'seedream_5_0_pro', label: 'Seedream 5.0 Pro'},
];
export const VIDEO_MODELS = [
  {key: 'follow_config', label: '跟随配置'},
  {key: 'seedance_2_0_fast', label: 'Seedance 2.0 Fast'},
];
export const IMAGE_QUALITIES = [
  {key: '1080', label: '1080'},
  {key: '2k', label: '2K'},
];
export const VIDEO_RESOLUTIONS = [
  {key: '480p', label: '480p'},
  {key: '720p', label: '720p'},
  {key: '1080p', label: '1080p'},
];

export type PrefTab = 'image' | 'video';
export type PrefField = 'aspect_ratio' | 'model' | 'quality' | 'resolution';

export type PrefSelection = {
  tab: PrefTab;
  field: PrefField;
  index: number;
};

const FIELD_ORDER_IMAGE: PrefField[] = ['aspect_ratio', 'model', 'quality'];
const FIELD_ORDER_VIDEO: PrefField[] = ['aspect_ratio', 'model', 'resolution'];

export function fieldOrder(tab: PrefTab): PrefField[] {
  return tab === 'image' ? FIELD_ORDER_IMAGE : FIELD_ORDER_VIDEO;
}

export function fieldOptions(tab: PrefTab, field: PrefField): string[] {
  if (field === 'aspect_ratio') return tab === 'image' ? IMAGE_ASPECT_RATIOS : VIDEO_ASPECT_RATIOS;
  if (field === 'model') return (tab === 'image' ? IMAGE_MODELS : VIDEO_MODELS).map((m) => m.key);
  if (field === 'quality') return IMAGE_QUALITIES.map((q) => q.key);
  if (field === 'resolution') return VIDEO_RESOLUTIONS.map((r) => r.key);
  return [];
}

export function fieldLabel(tab: PrefTab, field: PrefField, value: string): string {
  if (field === 'aspect_ratio') return value === 'auto' ? '智能' : value;
  if (field === 'model') {
    const models = tab === 'image' ? IMAGE_MODELS : VIDEO_MODELS;
    return models.find((m) => m.key === value)?.label ?? value;
  }
  if (field === 'quality') return value === '2k' ? '2K' : value;
  return value;
}

export function defaultSelection(): PrefSelection {
  return {tab: 'image', field: 'aspect_ratio', index: 0};
}

export function nextSelection(selection: PrefSelection): PrefSelection {
  const fields = fieldOrder(selection.tab);
  const fieldIdx = fields.indexOf(selection.field);
  if (fieldIdx < fields.length - 1) {
    return {tab: selection.tab, field: fields[fieldIdx + 1], index: 0};
  }
  return selection;
}

export function prevSelection(selection: PrefSelection): PrefSelection {
  const fields = fieldOrder(selection.tab);
  const fieldIdx = fields.indexOf(selection.field);
  if (fieldIdx > 0) {
    return {tab: selection.tab, field: fields[fieldIdx - 1], index: 0};
  }
  return selection;
}

export function clampSelection(selection: PrefSelection): PrefSelection {
  const options = fieldOptions(selection.tab, selection.field);
  const clampedIndex = Math.max(0, Math.min(selection.index, options.length - 1));
  return {...selection, index: clampedIndex};
}

export function applySelection(prefs: PreferenceSnapshot, selection: PrefSelection): PreferenceSnapshot {
  const options = fieldOptions(selection.tab, selection.field);
  const value = options[selection.index];
  if (!value) return prefs;
  if (selection.tab === 'image') {
    return {...prefs, image: {...prefs.image, [selection.field]: value}};
  }
  return {...prefs, video: {...prefs.video, [selection.field]: value}};
}

export function formatPreferenceBar(prefs: PreferenceSnapshot, width: number): string {
  const imgRatio = prefs.image.aspect_ratio === 'auto' ? '智能' : prefs.image.aspect_ratio;
  const vidRatio = prefs.video.aspect_ratio === 'auto' ? '智能' : prefs.video.aspect_ratio;
  const imgQuality = prefs.image.quality === '2k' ? '2K' : prefs.image.quality;
  const vidRes = prefs.video.resolution;

  if (width >= 500) {
    const imgModel = IMAGE_MODELS.find((m) => m.key === prefs.image.model)?.label ?? prefs.image.model;
    const vidModel = VIDEO_MODELS.find((m) => m.key === prefs.video.model)?.label ?? prefs.video.model;
    return `🖼 ${imgRatio} · ${imgModel} · ${imgQuality} │ 🎬 ${vidRatio} · ${vidModel} · ${vidRes}`;
  }
  if (width >= 360) {
    return `🖼 ${imgRatio} · ${imgQuality} │ 🎬 ${vidRatio} · ${vidRes}`;
  }
  return '🖼🎬 偏好';
}
