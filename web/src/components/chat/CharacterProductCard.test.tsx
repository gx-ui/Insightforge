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
});
