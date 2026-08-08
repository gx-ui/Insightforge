import {useState} from 'react';
import {Expand} from 'lucide-react';
import type {CharacterProduct} from '../../types';
import MediaPreviewDialog from './MediaPreviewDialog';

export default function CharacterProductCard({products}: {products: CharacterProduct[]}) {
  const [preview, setPreview] = useState<CharacterProduct>();
  if (products.length === 0) return null;
  return (
    <section className="character-product-block" aria-label="已生成角色图">
      <header><span>角色图</span><small>{products.length} 张已生成</small></header>
      <div className="character-product-grid">
        {products.map((product) => (
          <article key={product.artifactId} className="character-product-card">
            <button className="character-product-image" onClick={() => setPreview(product)} aria-label={`查看 ${product.caption} 大图`}>
              <img src={product.url} alt={product.caption} />
              <span><Expand size={16} />查看大图</span>
            </button>
            <div><strong>{product.caption}</strong><small>版本 {product.roleVersion} · {viewLabel(product.view)}</small></div>
          </article>
        ))}
      </div>
      {preview && <MediaPreviewDialog media={{kind: 'image', url: preview.url, title: preview.caption, detail: `版本 ${preview.roleVersion}`}} onClose={() => setPreview(undefined)} />}
    </section>
  );
}

function viewLabel(view: string) {
  return {front: '正面', side: '侧面', back: '背面'}[view] || '角色图';
}
