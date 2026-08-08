import {renderToStaticMarkup} from 'react-dom/server';
import {describe, expect, it} from 'vitest';
import CharacterProductCard from './CharacterProductCard';

describe('CharacterProductCard', () => {
  it('renders a preview card for each character image', () => {
    const html = renderToStaticMarkup(
      <CharacterProductCard products={[{artifactId: 'character:alice:v1:front', roleId: 'alice', roleVersion: 1, view: 'front', url: '/api/artifact?session=s1', caption: 'Alice · 正面'}]} />,
    );
    expect(html).toContain('Alice · 正面');
    expect(html).toContain('版本 1');
    expect(html).toContain('查看大图');
  });

  it('shows approval controls for the current unapproved version', () => {
    const product = {artifactId: 'character:alice:v1:front', roleId: 'alice', roleVersion: 1, view: 'front', url: '/api/artifact?session=s1', caption: 'Alice · 正面'};
    const html = renderToStaticMarkup(
      <CharacterProductCard products={[product]} approval={{runId: 'turn-1', sessionId: 's1', roles: [{roleId: 'alice', roleVersion: 1, displayName: 'Alice', description: 'short hair', approved: false, products: [product]}]}} />,
    );
    expect(html).toContain('确认 Alice');
    expect(html).toContain('编辑');
    expect(html).toContain('等待确认 1 个角色');
  });
});
