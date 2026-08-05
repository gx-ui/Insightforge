# 火山引擎 Ark API 支持方案

> 为 ViMax 项目新增火山引擎（Volcano Engine）官方 Ark API 的图片与视频生成支持。

---

## 1. 背景分析

### 1.1 现状

ViMax 的 `agent.local.yaml` 配置和 `agent_runtime/vimax_adapters.py` 工厂分发逻辑目前仅支持两种 API 通道：

| Provider | 图片生成器 | 视频生成器 |
|----------|------------|------------|
| OpenRouter | `ImageGeneratorOpenRouterAPI` | `VideoGeneratorOpenRouterAPI` |
| 云雾 (Yunwu) | `ImageGeneratorNanobananaYunwuAPI` (Google Gemini 代理) | `VideoGeneratorVeoYunwuAPI` (Veo 代理) |

Provider 的判定由 `agent_runtime/config.py` 中的 `api_provider_from_base_url()` 函数完成，通过匹配 URL 关键词识别：

```python
# agent_runtime/config.py (当前代码)
def api_provider_from_base_url(base_url: str) -> str:
    normalized = base_url.strip().lower()
    if "openrouter.ai" in normalized:
        return "openrouter"
    if "yunwu.ai" in normalized:
        return "yunwu"
    return ""
```

### 1.2 关键发现

项目中已存在两个 doubao 生成器类，但**均未接入工厂分发**且 **base_url 硬编码**：

| 类 | 文件 | 问题 |
|----|------|------|
| `ImageGeneratorDoubaoSeedreamYunwuAPI` | `tools/image_generator_doubao_seedream_yunwu_api.py` | base_url 硬编码为 `https://yunwu.ai/v1/images/generations`，不接受参数 |
| `VideoGeneratorDoubaoSeedanceYunwuAPI` | `tools/video_generator_doubao_seedance_yunwu_api.py` | URL 硬编码为 `https://yunwu.ai/volc/v1/contents/generations/tasks`，不接受参数 |

### 1.3 核心结论

火山引擎官方 Ark API 与云雾 doubao 代理使用**完全相同的 payload/response 格式**，唯一区别是 base_url 路径前缀：

| 功能 | 云雾代理 URL | 官方 Ark API URL |
|------|-------------|------------------|
| 图片生成 | `https://yunwu.ai/v1/images/generations` | `https://ark.cn-beijing.volces.com/api/v3/images/generations` |
| 视频创建 | `https://yunwu.ai/volc/v1/contents/generations/tasks` | `https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks` |
| 视频查询 | `.../tasks/{id}` | `.../tasks/{id}` |

认证方式一致：`Authorization: Bearer <ARK_API_KEY>`



---

## 2. 修改方案总览

```
新增文件:
  tools/image_generator_doubao_seedream_ark_api.py    <- 官方 Ark API 图片生成器
  tools/video_generator_doubao_seedance_ark_api.py     <- 官方 Ark API 视频生成器
  tests/test_ark_image_generator.py                    <- 图片生成器测试
  tests/test_ark_video_generator.py                    <- 视频生成器测试

修改文件:
  tools/__init__.py                  <- 注册新类
  agent_runtime/config.py            <- 新增 volcengine provider 检测
  agent_runtime/vimax_adapters.py    <- 工厂分发新增 volcengine 分支
  configs/agent.example.yaml          <- 更新配置模板
  configs/agent.local.yaml            <- 更新为火山引擎示例
  tests/test_agent_config.py          <- provider 检测测试
  tests/test_vimax_adapters.py        <- 工厂分发测试

```

---

## 3. 详细修改步骤

### 3.1 新建图片生成器

**文件**: `tools/image_generator_doubao_seedream_ark_api.py`

基于现有 `image_generator_doubao_seedream_yunwu_api.py` 改造，核心变更：
- `base_url` 改为构造函数参数（默认官方 Ark API 地址），不再硬编码
- 添加 `tenacity` 重试逻辑
- 添加 `VIMAX_IMAGE_REQUEST_TIMEOUT_SECONDS` 环境变量支持
- 添加 `progress` 回调支持

关键代码结构：

```python
class ImageGeneratorDoubaoSeedreamArkAPI:
    def __init__(self, api_key, model="doubao-seedream-3-0-t2i-250415",
                 base_url="https://ark.cn-beijing.volces.com/api/v3"):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=30),
           retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
           reraise=True, after=after_func)
    async def generate_single_image(self, prompt, reference_image_paths=[],
                                    size=None, **kwargs) -> ImageOutput:
        url = f"{self.base_url}/images/generations"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "sequential_image_generation": "disabled",
            "response_format": "url",
            "size": size if size else "1024x1024",
        }
        if reference_image_paths:
            payload["image"] = [image_path_to_b64(p, mime=True) for p in reference_image_paths]
        headers = {"Authorization": f"Bearer {self.api_key}",
                   "Content-Type": "application/json"}
        # POST -> parse response_json["data"][0]["url"]
        return ImageOutput(fmt="url", ext="png", data=url)
```

**API 请求/响应格式**:

```
POST /api/v3/images/generations
Authorization: Bearer <ARK_API_KEY>
Content-Type: application/json

Request:
{
  "model": "doubao-seedream-3-0-t2i-250415",
  "prompt": "描述文本",
  "sequential_image_generation": "disabled",
  "response_format": "url",
  "size": "1024x1024",
  "image": ["data:image/png;base64,..."]
}

Response:
{
  "created": 1234567890,
  "data": [{"url": "https://..."}],
  "usage": {"total_tokens": 10}
}
```

### 3.2 新建视频生成器

**文件**: `tools/video_generator_doubao_seedance_ark_api.py`

基于现有 `video_generator_doubao_seedance_yunwu_api.py` 改造，核心变更：
- `base_url` 改为构造函数参数（默认官方 Ark API 地址），不再硬编码
- 将 `ff2v_model` / `flf2v_model` 合并为 `i2v_model`（图生视频模型，首帧/首尾帧共用）
- **自动推导 t2v/i2v 模型 ID**：用户只需填一个 `model`，构造函数检测到 `t2v` 或 `i2v` 关键词时自动换算出另一个（见下方推导逻辑）
- 添加 `progress` 回调支持
- 添加环境变量: `VIMAX_VIDEO_REQUEST_TIMEOUT_SECONDS`、`VIMAX_VIDEO_QUERY_TIMEOUT_SECONDS`、`VIMAX_VIDEO_POLL_INTERVAL_SECONDS`
- 参考 `video_generator_veo_yunwu_api.py` 的成熟轮询逻辑（deadline 超时、连续错误计数）

模型自动推导逻辑:
- 用户传入 `model="doubao-seedance-1-0-lite-t2v-250428"` → `t2v_model` = 传入值, `i2v_model` = `"...-i2v-250428"`
- 用户传入 `model="doubao-seedance-1-0-lite-i2v-250428"` → `i2v_model` = 传入值, `t2v_model` = `"...-t2v-250428"`
- 用户传入 `model="ep-xxx"`（Endpoint ID）→ `t2v_model` = `i2v_model` = `"ep-xxx"`（无需推导）

模型选择逻辑 (运行时):
- 0 张参考图 -> `t2v_model` (文生视频)
- 1 张参考图 -> `i2v_model` (首帧图生视频)
- 2 张参考图 -> `i2v_model` (首尾帧图生视频)

关键代码结构：

```python
class VideoGeneratorDoubaoSeedanceArkAPI:
    def __init__(self, api_key,
                 model="doubao-seedance-1-0-lite-t2v-250428",
                 base_url="https://ark.cn-beijing.volces.com/api/v3",
                 max_create_attempts=3, max_poll_attempts=300):
        self.base_url = base_url.rstrip("/")

        # 自动推导 t2v / i2v 模型 ID
        if "t2v" in model:
            self.t2v_model = model
            self.i2v_model = model.replace("t2v", "i2v")
        elif "i2v" in model:
            self.t2v_model = model.replace("i2v", "t2v")
            self.i2v_model = model
        else:
            # 不含 t2v/i2v（如 Endpoint ID ep-xxx），两个都用同一个
            self.t2v_model = model
            self.i2v_model = model
        # ...

    def _select_model(self, ref_count):
        if ref_count == 0: return self.t2v_model
        elif ref_count <= 2: return self.i2v_model
        else: raise ValueError("0, 1, or 2 images only")

    async def create_video_generation_task(self, prompt, reference_image_paths,
                                           resolution="720p", aspect_ratio="16:9",
                                           fps=16, duration=5, progress=None):
        url = f"{self.base_url}/contents/generations/tasks"
        content = [{"type": "text", "text": prompt + f" --rs {resolution} ..."}]
        if ref_images: content.append({"type": "image_url", ...})
        # POST -> return task_id

    async def query_video_generation_task(self, task_id, progress=None):
        url = f"{self.base_url}/contents/generations/tasks/{task_id}"
        # GET poll loop -> return video_url when status=="succeeded"

    async def generate_single_video(self, prompt, reference_image_paths=[],
                                     resolution="720p", aspect_ratio="16:9",
                                     fps=16, duration=5, **kwargs):
        task_id = await self.create_video_generation_task(...)
        video_url = await self.query_video_generation_task(task_id)
        return VideoOutput(fmt="url", ext="mp4", data=video_url)
```

**API 请求/响应格式**:

```
# 创建任务
POST /api/v3/contents/generations/tasks
Authorization: Bearer <ARK_API_KEY>

Request:
{
  "model": "doubao-seedance-1-0-lite-t2v-250428",
  "content": [
    {"type": "text", "text": "prompt --rs 720p --rt 16:9 --dur 5 --fps 16 --wm false --seed -1 --cf false"},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}, "role": "first_frame"}
  ]
}
Response: {"id": "cgt-xxx"}

# 查询任务
GET /api/v3/contents/generations/tasks/{task_id}
Authorization: Bearer <ARK_API_KEY>
Response:
{
  "id": "cgt-xxx",
  "status": "succeeded",    // succeeded | failed | running
  "content": {"video_url": "https://..."}
}
```


### 3.3 注册新类 - `tools/__init__.py`

在导入区和 `__all__` 列表中新增：

```python
# --- image generators 区块新增 ---
from .image_generator_doubao_seedream_ark_api import ImageGeneratorDoubaoSeedreamArkAPI

# --- video generators 区块新增 ---
from .video_generator_doubao_seedance_ark_api import VideoGeneratorDoubaoSeedanceArkAPI

# --- __all__ 新增 ---
"ImageGeneratorDoubaoSeedreamArkAPI",
"VideoGeneratorDoubaoSeedanceArkAPI",
```

---

### 3.4 更新 provider 检测 - `agent_runtime/config.py`

修改 `api_provider_from_base_url()`：

```python
def api_provider_from_base_url(base_url: str) -> str:
    normalized = base_url.strip().lower()
    if "openrouter.ai" in normalized:
        return "openrouter"
    if "yunwu.ai" in normalized:
        return "yunwu"
    if "volces.com" in normalized or "volcengine" in normalized:  # <- 新增
        return "volcengine"
    return ""
```

> `config.py` 无需新增任何函数。t2v/i2v 模型 ID 的推导完全在 `VideoGeneratorDoubaoSeedanceArkAPI.__init__` 内部完成，对外只暴露单一的 `model` 参数。

---

### 3.5 更新工厂分发 - `agent_runtime/vimax_adapters.py`

#### 3.5.1 新增导入

```python
from tools.image_generator_doubao_seedream_ark_api import ImageGeneratorDoubaoSeedreamArkAPI
from tools.video_generator_doubao_seedance_ark_api import VideoGeneratorDoubaoSeedanceArkAPI
```

> 无需修改 `.config` 导入行（不新增 t2v/i2v 配置函数）。

#### 3.5.2 修改 `_build_image_generator()`

```python
def _build_image_generator():
    ...
    provider = api_provider_from_base_url(base_url)
    if provider == "openrouter":
        return ImageGeneratorOpenRouterAPI(...)
    if provider == "volcengine":                           # <- 新增
        return ImageGeneratorDoubaoSeedreamArkAPI(
            api_key=api_key, model=model, base_url=base_url)
    return ImageGeneratorNanobananaYunwuAPI(...)
```

#### 3.5.3 修改 `_build_video_generator()`

```python
def _build_video_generator():
    ...
    if provider == "openrouter":
        return VideoGeneratorOpenRouterAPI(...)
    if provider == "yunwu":
        return VideoGeneratorVeoYunwuAPI(...)
    if provider == "volcengine":                           # <- 新增
        return VideoGeneratorDoubaoSeedanceArkAPI(
            api_key=api_key,
            model=video_model(),      # 只传一个 model，内部自动推导 t2v/i2v
            base_url=base_url)
    raise RuntimeError(f"Unsupported video base_url: {base_url}")
```

---

### 3.6 更新配置模板

#### 3.6.1 `configs/agent.example.yaml`

```yaml
image:
  model: <YOUR_IMAGE_MODEL>
  # Supported providers (auto-detected from base_url):
  #   Volcano Engine Ark: https://ark.cn-beijing.volces.com/api/v3
  #   OpenRouter:         https://openrouter.ai/api/v1
  #   Yunwu proxy:        https://yunwu.ai
  base_url: <YOUR_IMAGE_BASE_URL>
  api_key: ''

video:
  # Model ID (e.g. doubao-seedance-1-0-lite-t2v-250428) or Endpoint ID (ep-xxx).
  # For doubao-seedance, t2v/i2v model IDs are auto-derived from this single field.
  model: <YOUR_VIDEO_MODEL>
  base_url: <YOUR_VIDEO_BASE_URL>
  api_key: ''
```

#### 3.6.2 `configs/agent.local.yaml` (火山引擎示例)

```yaml
image:
  model: doubao-seedream-3-0-t2i-250415
  base_url: https://ark.cn-beijing.volces.com/api/v3
  api_key: '<YOUR_ARK_API_KEY>'

video:
  model: doubao-seedance-1-0-lite-t2v-250428
  base_url: https://ark.cn-beijing.volces.com/api/v3
  api_key: '<YOUR_ARK_API_KEY>'
```


### 3.7 新增测试

#### 3.7.1 `tests/test_ark_image_generator.py`

```python
import unittest
from unittest.mock import patch

from agent_runtime.vimax_adapters import _build_image_generator
from tools.image_generator_doubao_seedream_ark_api import ImageGeneratorDoubaoSeedreamArkAPI


class ArkImageGeneratorFactoryTests(unittest.TestCase):
    def test_factory_selects_ark_from_volcengine_base_url(self):
        with patch("agent_runtime.vimax_adapters.image_api_key", return_value="ark-key"), \
             patch("agent_runtime.vimax_adapters.image_model",
                   return_value="doubao-seedream-3-0-t2i-250415"), \
             patch("agent_runtime.vimax_adapters.image_base_url",
                   return_value="https://ark.cn-beijing.volces.com/api/v3"):
            generator = _build_image_generator()
        self.assertIsInstance(generator, ImageGeneratorDoubaoSeedreamArkAPI)
        self.assertEqual(generator.model, "doubao-seedream-3-0-t2i-250415")
        self.assertEqual(generator.base_url, "https://ark.cn-beijing.volces.com/api/v3")
```

#### 3.7.2 `tests/test_ark_video_generator.py`

```python
import unittest
from unittest.mock import patch

from agent_runtime.vimax_adapters import _build_video_generator
from tools.video_generator_doubao_seedance_ark_api import VideoGeneratorDoubaoSeedanceArkAPI


class ArkVideoGeneratorFactoryTests(unittest.TestCase):
    def test_factory_selects_ark_from_volcengine_base_url(self):
        with patch("agent_runtime.vimax_adapters.video_api_key", return_value="ark-key"), \
             patch("agent_runtime.vimax_adapters.video_model",
                   return_value="doubao-seedance-1-0-lite-t2v-250428"), \
             patch("agent_runtime.vimax_adapters.video_base_url",
                   return_value="https://ark.cn-beijing.volces.com/api/v3"):
            generator = _build_video_generator()
        self.assertIsInstance(generator, VideoGeneratorDoubaoSeedanceArkAPI)
        self.assertEqual(generator.t2v_model, "doubao-seedance-1-0-lite-t2v-250428")
        self.assertEqual(generator.i2v_model, "doubao-seedance-1-0-lite-i2v-250428")


class ArkVideoGeneratorAutoDerivationTests(unittest.TestCase):
    def test_t2v_input_derives_i2v(self):
        gen = VideoGeneratorDoubaoSeedanceArkAPI(
            api_key="k", model="doubao-seedance-1-0-lite-t2v-250428")
        self.assertEqual(gen.t2v_model, "doubao-seedance-1-0-lite-t2v-250428")
        self.assertEqual(gen.i2v_model, "doubao-seedance-1-0-lite-i2v-250428")

    def test_i2v_input_derives_t2v(self):
        gen = VideoGeneratorDoubaoSeedanceArkAPI(
            api_key="k", model="doubao-seedance-1-0-lite-i2v-250428")
        self.assertEqual(gen.t2v_model, "doubao-seedance-1-0-lite-t2v-250428")
        self.assertEqual(gen.i2v_model, "doubao-seedance-1-0-lite-i2v-250428")

    def test_endpoint_id_no_derivation(self):
        gen = VideoGeneratorDoubaoSeedanceArkAPI(
            api_key="k", model="ep-20240xxx-xxxxx")
        self.assertEqual(gen.t2v_model, "ep-20240xxx-xxxxx")
        self.assertEqual(gen.i2v_model, "ep-20240xxx-xxxxx")


class ArkVideoGeneratorModelSelectionTests(unittest.TestCase):
    def test_t2v_model_when_no_reference_images(self):
        gen = VideoGeneratorDoubaoSeedanceArkAPI(
            api_key="k", model="doubao-seedance-1-0-lite-t2v-250428")
        self.assertEqual(gen._select_model(0), "doubao-seedance-1-0-lite-t2v-250428")

    def test_i2v_model_when_one_reference_image(self):
        gen = VideoGeneratorDoubaoSeedanceArkAPI(
            api_key="k", model="doubao-seedance-1-0-lite-t2v-250428")
        self.assertEqual(gen._select_model(1), "doubao-seedance-1-0-lite-i2v-250428")

    def test_i2v_model_when_two_reference_images(self):
        gen = VideoGeneratorDoubaoSeedanceArkAPI(
            api_key="k", model="doubao-seedance-1-0-lite-t2v-250428")
        self.assertEqual(gen._select_model(2), "doubao-seedance-1-0-lite-i2v-250428")

    def test_raises_when_more_than_two(self):
        gen = VideoGeneratorDoubaoSeedanceArkAPI(api_key="k")
        with self.assertRaises(ValueError):
            gen._select_model(3)
```

#### 3.7.3 更新 `tests/test_agent_config.py`

在 `test_video_provider_is_inferred_from_base_url` 方法中新增断言：

```python
def test_video_provider_is_inferred_from_base_url(self):
    self.assertEqual(api_provider_from_base_url("https://openrouter.ai/api/v1"), "openrouter")
    self.assertEqual(api_provider_from_base_url("https://yunwu.ai/v1"), "yunwu")
    self.assertEqual(api_provider_from_base_url("https://example.com/v1"), "")
    # 新增: 火山引擎官方 Ark API URL
    self.assertEqual(
        api_provider_from_base_url("https://ark.cn-beijing.volces.com/api/v3"),
        "volcengine")
    self.assertEqual(
        api_provider_from_base_url("https://ark.cn-beijing.volces.com"),
        "volcengine")
```

---

### 3.8 更新文档 - `README_ZH.md`

在供应商配置说明部分（约第 221 行附近）新增火山引擎配置示例和说明。

---

## 4. 环境变量参考

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `VIMAX_IMAGE_REQUEST_TIMEOUT_SECONDS` | `300` | 图片生成 HTTP 请求超时（秒） |
| `VIMAX_VIDEO_REQUEST_TIMEOUT_SECONDS` | `60` | 视频任务创建/查询 HTTP 请求超时（秒） |
| `VIMAX_VIDEO_QUERY_TIMEOUT_SECONDS` | `600` | 视频任务轮询总超时（秒） |
| `VIMAX_VIDEO_POLL_INTERVAL_SECONDS` | `5` | 视频任务轮询间隔（秒） |
| `VIMAX_VIDEO_MAX_QUERY_ERRORS` | `5` | 视频轮询连续错误上限 |

---

## 5. 数据流图

```
configs/agent.local.yaml
    |
    v
agent_runtime/config.py
    +-- image_base_url()  -->  api_provider_from_base_url()
    |                            +-- "openrouter"  -->  ImageGeneratorOpenRouterAPI
    |                            +-- "volcengine"  -->  ImageGeneratorDoubaoSeedreamArkAPI  [NEW]
    |                            +-- (default)     -->  ImageGeneratorNanobananaYunwuAPI
    |
    +-- video_base_url()  -->  video_provider()
                               +-- "openrouter"  -->  VideoGeneratorOpenRouterAPI
                               +-- "yunwu"       -->  VideoGeneratorVeoYunwuAPI
                               +-- "volcengine"  -->  VideoGeneratorDoubaoSeedanceArkAPI  [NEW]
                                                     (内部自动将 model 推导为 t2v_model/i2v_model)
                               +-- (other)       -->  RuntimeError
```

---

## 6. 修改清单汇总

| # | 操作 | 文件路径 | 说明 |
|---|------|----------|------|
| 1 | **NEW** | `tools/image_generator_doubao_seedream_ark_api.py` | 官方 Ark API 图片生成器 |
| 2 | **NEW** | `tools/video_generator_doubao_seedance_ark_api.py` | 官方 Ark API 视频生成器（含 t2v/i2v 自动推导） |
| 3 | **MOD** | `tools/__init__.py` | 注册新类的导入和导出 |
| 4 | **MOD** | `agent_runtime/config.py` | 新增 volcengine provider 检测 |
| 5 | **MOD** | `agent_runtime/vimax_adapters.py` | 工厂分发新增 volcengine 分支 |
| 6 | **MOD** | `configs/agent.example.yaml` | 更新配置模板注释说明 |
| 7 | **MOD** | `configs/agent.local.yaml` | 更新为火山引擎示例配置 |
| 8 | **NEW** | `tests/test_ark_image_generator.py` | 图片生成器单元测试 + 工厂测试 |
| 9 | **NEW** | `tests/test_ark_video_generator.py` | 视频生成器自动推导测试 + 模型选择测试 + 工厂测试 |
| 10 | **MOD** | `tests/test_agent_config.py` | 新增 volcengine provider 检测断言 |
| 11 | **MOD** | `README_ZH.md` | 新增火山引擎配置文档 |

---

## 7. 注意事项

1. **向后兼容**：现有 OpenRouter 和云雾配置不受影响，新增逻辑仅在 `base_url` 包含 `volces.com` 或 `volcengine` 时触发。

2. **模型 ID vs Endpoint ID**：火山引擎支持两种模型标识方式：
   - 模型 ID（如 `doubao-seedance-1-0-lite-t2v-250428`）：填入 `model` 即可，构造函数自动推导 t2v/i2v
   - Endpoint ID（如 `ep-20240xxx-xxxxx`）：填入 `model`，不含 t2v/i2v 关键词时不触发推导，t2v_model 和 i2v_model 均使用该值

3. **视频模型自动推导**：doubao-seedance 的 t2v 和 i2v 有不同模型 ID，但用户只需配置一个 `model`。构造函数通过检测模型名中的 `t2v`/`i2v` 关键词自动换算出另一个。对用户完全透明，无需手动配置两个字段。

4. **API 格式来源**：本方案的 API 请求/响应格式基于项目中已有的云雾 doubao 代理代码（`image_generator_doubao_seedream_yunwu_api.py` 和 `video_generator_doubao_seedance_yunwu_api.py`），云雾代理使用的格式与火山引擎官方 Ark API 完全一致。

5. **影响范围**：本方案仅覆盖 agent runtime（`agent.local.yaml` + TUI / Web UI）。如需在 `main_idea2video.py` / `main_script2video.py` 脚本入口也使用火山引擎，需额外修改 `configs/idea2video.yaml` / `configs/script2video.yaml` 中的 `class_path` 配置。