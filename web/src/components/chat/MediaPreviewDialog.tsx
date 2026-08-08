import {useEffect} from 'react';
import {X} from 'lucide-react';

export type PreviewMedia = {
  kind: 'image' | 'video';
  url: string;
  title: string;
  detail?: string;
};

export default function MediaPreviewDialog({media, onClose}: {media: PreviewMedia; onClose: () => void}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div className="media-preview-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="media-preview-dialog" role="dialog" aria-modal="true" aria-label={`预览 ${media.title}`}>
        <header>
          <div><strong>{media.title}</strong>{media.detail && <span>{media.detail}</span>}</div>
          <button className="icon-button" onClick={onClose} aria-label="关闭预览"><X size={18} /></button>
        </header>
        <div className="media-preview-stage">
          {media.kind === 'image'
            ? <img src={media.url} alt={media.title} />
            : <video src={media.url} controls autoPlay playsInline preload="metadata" />}
        </div>
      </section>
    </div>
  );
}
