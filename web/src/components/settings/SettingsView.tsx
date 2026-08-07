import {useEffect, useState} from 'react';
import {App, Card, Form, Input, Button} from 'antd';
import {EyeInvisibleOutlined, EyeTwoTone, CheckCircleOutlined} from '@ant-design/icons';
import {getAgentConfig, saveAgentConfig} from '../../api';
import type {AgentConfig, ConfigSection} from '../../types';

const CONFIG_SECTIONS: Array<{key: keyof AgentConfig['sections']; title: string; description: string}> = [
  {key: 'llm', title: 'Agent LLM', description: '规划、工具选择和对话'},
  {key: 'image', title: '图片生成', description: '角色、关键帧和镜头画面'},
  {key: 'video', title: '视频生成', description: '镜头片段和最终视频'},
  {key: 'embedding', title: '向量嵌入', description: '可选的小说检索'},
  {key: 'reranker', title: '重排序器', description: '可选的小说检索排序'},
];

export default function SettingsView() {
  const {message: msgApi} = App.useApp();
  const [config, setConfig] = useState<AgentConfig>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedKey, setSavedKey] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void getAgentConfig()
      .then((payload) => { if (!cancelled) setConfig(payload); })
      .catch((error) => {
        if (!cancelled) msgApi.error(error instanceof Error ? error.message : String(error));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [msgApi]);

  const updateSection = (key: keyof AgentConfig['sections'], field: keyof ConfigSection, value: string) => {
    setConfig((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        sections: {
          ...prev.sections,
          [key]: {...prev.sections[key], [field]: value},
        },
      };
    });
    setSavedKey(null);
  };

  const handleSave = async () => {
    if (!config || saving) return;
    setSaving(true);
    try {
      await saveAgentConfig(config);
      setSavedKey('all');
      msgApi.success('已保存');
    } catch (error) {
      msgApi.error(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-ink-primary">设置</h1>
        <p className="mt-1 text-sm text-ink-secondary">configs/agent.local.yaml</p>
      </header>

      <div className="space-y-4">
        {CONFIG_SECTIONS.map((section) => (
          <Card
            key={section.key}
            size="small"
            className="rounded-xl border-line bg-bg-raised"
            styles={{body: {padding: '16px 20px'}}}
            title={
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-ink-primary">{section.title}</span>
                {config?.sections[section.key]?.has_api_key && (
                  <span className="inline-flex items-center gap-1 text-xs text-info">
                    <CheckCircleOutlined />
                    已配置
                  </span>
                )}
              </div>
            }
          >
            <p className="mb-3 text-xs text-ink-faint">{section.description}</p>
            <div className="space-y-3">
              <Form.Item label="模型供应商" labelCol={{span: 24}} wrapperCol={{span: 24}}>
                <Input
                  size="small"
                  value={config?.sections[section.key]?.model_provider || ''}
                  onChange={(e) => updateSection(section.key, 'model_provider', e.target.value)}
                  variant="borderless"
                  className="rounded-md bg-bg-canvas px-2"
                />
              </Form.Item>
              <Form.Item label="模型" labelCol={{span: 24}} wrapperCol={{span: 24}}>
                <Input
                  size="small"
                  value={config?.sections[section.key]?.model || ''}
                  onChange={(e) => updateSection(section.key, 'model', e.target.value)}
                  variant="borderless"
                  className="rounded-md bg-bg-canvas px-2"
                />
              </Form.Item>
              <Form.Item label="Base URL" labelCol={{span: 24}} wrapperCol={{span: 24}}>
                <Input
                  size="small"
                  value={config?.sections[section.key]?.base_url || ''}
                  onChange={(e) => updateSection(section.key, 'base_url', e.target.value)}
                  variant="borderless"
                  className="rounded-md bg-bg-canvas px-2"
                />
              </Form.Item>
              <Form.Item label="API Key" labelCol={{span: 24}} wrapperCol={{span: 24}}>
                <Input.Password
                  size="small"
                  value={config?.sections[section.key]?.api_key || ''}
                  onChange={(e) => updateSection(section.key, 'api_key', e.target.value)}
                  placeholder={config?.sections[section.key]?.has_api_key ? '留空则保持当前 key' : '输入 API key'}
                  iconRender={(visible) => visible ? <EyeTwoTone /> : <EyeInvisibleOutlined />}
                  variant="borderless"
                  className="rounded-md bg-bg-canvas px-2"
                  autoComplete="off"
                />
              </Form.Item>
            </div>
          </Card>
        ))}
      </div>

      <div className="mt-6 flex items-center justify-end gap-3">
        {savedKey === 'all' && (
          <span className="text-sm text-info">已保存</span>
        )}
        <Button
          type="primary"
          loading={saving}
          onClick={() => void handleSave()}
          disabled={loading || !config}
        >
          {saving ? '保存中' : '保存'}
        </Button>
      </div>

      {loading && (
        <div className="py-12 text-center text-sm text-ink-faint">加载中…</div>
      )}
    </div>
  );
}
