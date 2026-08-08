import {useEffect, useState} from 'react';
import {Expand, Pencil, RefreshCw, ShieldCheck} from 'lucide-react';
import type {CharacterApproval, CharacterApprovalRole, CharacterProduct} from '../../types';
import MediaPreviewDialog from './MediaPreviewDialog';

type Props = {
  products: CharacterProduct[];
  approval?: CharacterApproval;
  pendingRoleId?: string;
  onConfirm?: (role: CharacterApprovalRole, artifactId: string) => void;
  onRegenerate?: (role: CharacterApprovalRole, action: 'edit' | 'regenerate', displayName?: string, description?: string) => void;
};

export default function CharacterProductCard({products, approval, pendingRoleId, onConfirm, onRegenerate}: Props) {
  const [preview, setPreview] = useState<CharacterProduct>();
  const [editing, setEditing] = useState<CharacterApprovalRole>();
  if (products.length === 0) return null;
  const groups = groupProducts(products);
  const pendingCount = approval?.roles.filter((role) => !role.approved).length || 0;
  return (
    <section className="character-product-block" aria-label="已生成角色图">
      <header><span>角色图</span><small>{approval ? pendingCount ? `等待确认 ${pendingCount} 个角色` : '角色已全部确认' : `${products.length} 张已生成`}</small></header>
      <div className="character-product-grid">
        {groups.map((group) => {
          const role = approval?.roles.find((item) => item.roleId === group.roleId && item.roleVersion === group.roleVersion);
          const pending = pendingRoleId === group.roleId;
          return (
            <article key={`${group.roleId}:v${group.roleVersion}`} className="character-product-card">
              <div className="character-product-views">
                {group.products.map((product) => (
                  <button key={product.artifactId} className="character-product-image" onClick={() => setPreview(product)} aria-label={`查看 ${product.caption} 大图`}>
                    <img src={product.url} alt={product.caption} />
                    <span><Expand size={16} />查看大图</span>
                  </button>
                ))}
              </div>
              <div className="character-product-copy">
                <strong>{role?.displayName || group.products[0].caption.split(' · ')[0] || group.roleId}</strong>
                <small>版本 {group.roleVersion} · {group.products.map((product) => viewLabel(product.view)).join(' / ')}</small>
                {role && <ApprovalControls role={role} artifactId={group.products[0].artifactId} pending={pending} onConfirm={onConfirm} onRegenerate={onRegenerate} onEdit={() => setEditing(role)} />}
              </div>
            </article>
          );
        })}
      </div>
      {approval && <p className="character-approval-note">编辑仅影响显示名称与新的肖像特征，不会重写剧本和分镜中的角色引用。</p>}
      {preview && <MediaPreviewDialog media={{kind: 'image', url: preview.url, title: preview.caption, detail: `版本 ${preview.roleVersion}`}} onClose={() => setPreview(undefined)} />}
      {editing && <EditDialog role={editing} pending={pendingRoleId === editing.roleId} onCancel={() => setEditing(undefined)} onSave={(displayName, description) => {
        onRegenerate?.(editing, 'edit', displayName, description);
        setEditing(undefined);
      }} />}
    </section>
  );
}

function ApprovalControls({role, artifactId, pending, onConfirm, onRegenerate, onEdit}: {
  role: CharacterApprovalRole;
  artifactId: string;
  pending: boolean;
  onConfirm?: Props['onConfirm'];
  onRegenerate?: Props['onRegenerate'];
  onEdit: () => void;
}) {
  if (role.approved) return <span className="character-approved"><ShieldCheck size={14} />已确认</span>;
  return (
    <div className="character-product-actions">
      <button type="button" onClick={onEdit} disabled={pending} aria-label={`编辑 ${role.displayName}`}><Pencil size={13} />编辑</button>
      <button type="button" onClick={() => onRegenerate?.(role, 'regenerate')} disabled={pending} aria-label={`重生成 ${role.displayName}`}><RefreshCw size={13} />重生成</button>
      <button type="button" className="confirm" onClick={() => onConfirm?.(role, artifactId)} disabled={pending} aria-label={`确认 ${role.displayName}`}><ShieldCheck size={13} />{pending ? '提交中…' : `确认 ${role.displayName}`}</button>
    </div>
  );
}

function EditDialog({role, pending, onCancel, onSave}: {role: CharacterApprovalRole; pending: boolean; onCancel: () => void; onSave: (displayName: string, description: string) => void}) {
  const [displayName, setDisplayName] = useState(role.displayName);
  const [description, setDescription] = useState(role.description);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) onCancel();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onCancel, pending]);
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onCancel()}>
      <form className="character-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="character-edit-title" onSubmit={(event) => {
        event.preventDefault();
        onSave(displayName.trim() || role.displayName, description.trim());
      }}>
        <h2 id="character-edit-title">编辑 {role.displayName}</h2>
        <label>显示名称<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={64} autoFocus disabled={pending} /></label>
        <label>外貌描述<textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={800} rows={4} disabled={pending} /></label>
        <p>不会重写剧本和分镜中的角色引用。</p>
        <div className="dialog-actions"><button type="button" onClick={onCancel} disabled={pending}>取消</button><button type="submit" className="primary" disabled={pending}>{pending ? '提交中…' : '生成新版本'}</button></div>
      </form>
    </div>
  );
}

function groupProducts(products: CharacterProduct[]) {
  const groups = new Map<string, {roleId: string; roleVersion: number; products: CharacterProduct[]}>();
  for (const product of products) {
    const key = `${product.roleId}:v${product.roleVersion}`;
    const group = groups.get(key) || {roleId: product.roleId, roleVersion: product.roleVersion, products: []};
    group.products.push(product);
    groups.set(key, group);
  }
  return [...groups.values()];
}

function viewLabel(view: string) {
  return {front: '正面', side: '侧面', back: '背面'}[view] || '角色图';
}
