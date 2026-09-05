# BiliOpinion 平台适配层设计方案

> 状态：设计稿 v1.0（2026-09）
> 目标：让 BiliOpinion 从「B 站舆情分析管线」升级为「多平台舆情分析框架」，同时**零破坏**兼容现有 B 站工作流与历史 outputs。

---

## 1. 现状分析

### 1.1 架构盘点

```
main.py::run_pipeline(cfg)
 ├─ Step0 采集        ← 唯一平台耦合点（crawler.run → BilibiliCrawler）
 ├─ Step1 清洗        ┐
 ├─ Step2 时间演化    │
 ├─ Step3 主题分析    │
 ├─ Step4 情感立场    ├─ 全部只消费标准化 CSV，平台无关 ✅
 ├─ Step5 社会网络    │
 ├─ Step6-8 BERT     ┘
 └─ Step9 报告（HTML/docx）
```

**关键结论**：平台耦合被完美隔离在 Step0。Step1-9 通过中间 CSV 文件解耦，天然支持多平台——只要任何采集器产出相同 schema 的 CSV，整条分析管线即可复用。

### 1.2 现有中间数据契约（事实标准）

**videos.csv**（`save_video` 写入）：

| 列 | 含义 | B 站来源字段 |
|---|---|---|
| `bvid` | 内容唯一 ID | `v["bvid"]` |
| `title` | 标题 | `v["title"]` |
| `desc` | 描述 | `v["desc"]` |
| `author` | 作者名 | `v["author"]` |
| `view` | 播放量 | `v["view"]` |
| `reply` | 评论数 | `v["reply"]` |
| `pubdate` | 发布时间 | `v["pubdate"]` |
| `crawled_at` | 采集时间 | 本地生成 |

**comments.csv**（`save_comment` 写入）：

| 列 | 含义 | B 站来源字段 |
|---|---|---|
| `rpid` | 评论唯一 ID | `c["rpid"]` |
| `bvid` | 所属内容 ID | — |
| `parent_id` | 父评论 ID（0=根） | — |
| `level` | 层级（1=根 2=楼中楼） | — |
| `mid` | 用户 ID | `c["member"]["mid"]` |
| `uname` | 用户名 | `c["member"]["uname"]` |
| `target` | 被回复人（SNA 边！） | 回复 @ 解析 |
| `message` | 正文 | `c["content"]["message"]` |
| `like` | 点赞 | `c["like"]` |
| `rcount` | 子评论数 | `c["rcount"]` |
| `ctime` | 评论时间 | `c["ctime"]` |
| `crawled_at` | 采集时间 | 本地生成 |

⚠️ **注意**：`comments.csv` 中的 `bvid`、`rpid`、`mid` 等列名是 B 站术语（BV号/回复ID/会员ID），下游 step1-5 直接按这些列名读取。**改名 = 破坏性变更**。

---

## 2. 设计目标与非目标

**目标**
1. 新平台（YouTube 等）以「适配器插件」方式接入，不修改 steps/ 与 report/
2. 现有 B 站用户升级后零感知：配置兼容、outputs 目录结构不变、CLI 不变
3. 多平台数据可比对：同一事件在两个平台各跑一条管线，产出同构报告

**非目标（本设计不做）**
- 跨平台混合网络分析（Step5 目前按单平台数据构建，留作 v2）
- 平台间数据合并不是简单拼接（用户 ID 体系不同），明确拒绝"跨平台合并去重"
- 抖音/微博等未验证平台的具体实现（设计保证可扩展即可）

---

## 3. 适配器契约

### 3.1 抽象基类（新文件 `biliopinion/adapters/base.py`）

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator

@dataclass
class ContentRef:
    """搜索阶段产出的内容引用"""
    content_id: str      # 平台内唯一 ID（B 站: bvid / YouTube: videoId）
    title: str = ""
    author: str = ""
    extra: dict = field(default_factory=dict)

@dataclass
class RawComment:
    """评论的标准中间表示——适配器负责把平台响应翻译成它"""
    comment_id: str
    content_id: str
    parent_id: str       # "" 表示根评论
    user_id: str
    username: str
    reply_to: str        # 被回复人用户名（SNA 边；无法判定时为 ""）
    message: str
    likes: int = 0
    reply_count: int = 0
    created_at: str      # "YYYY-MM-DD HH:MM:SS"
    raw: dict = field(default_factory=dict)   # 平台原始响应（调试用）

class PlatformAdapter(ABC):
    """平台适配器契约。实现类必须是无状态可重入的（cfg 通过方法传入）"""

    PLATFORM_ID: str            # 如 "bilibili"、"youtube"
    DISPLAY_NAME: str           # 如 "哔哩哔哩"

    def __init__(self, cfg: dict):
        self.cfg = cfg          # 仅保留引用，不深拷贝（与现状一致）

    @abstractmethod
    def search_content(self, keyword: str, page: int) -> list[ContentRef]: ...

    @abstractmethod
    def iter_comments(self, content: ContentRef) -> Iterator[RawComment]: ...

    @abstractmethod
    def health_check(self) -> bool:
        """凭据/网络可用性探测，供 CLI `--check` 与前端展示"""
```

### 3.2 统一落盘层（修改 `crawler.py` → 新增 `adapters/writer.py`）

`RawComment` → `comments.csv` 的列映射**在框架层完成一次**，各适配器不再自己拼 CSV 行：

```python
# adapters/writer.py
COMMENT_COLUMNS = ["rpid", "bvid", "parent_id", "level", "mid", "uname",
                   "target", "message", "like", "rcount", "ctime", "crawled_at"]

def normalize_comment(rc: RawComment) -> list:
    return [
        rc.comment_id, rc.content_id, rc.parent_id or 0,
        1 if not rc.parent_id else 2,
        rc.user_id, rc.username, rc.reply_to, rc.message,
        rc.likes, rc.reply_count, rc.created_at,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]
```

**核心决策：CSV 列名保持 B 站原名不变。**
理由：① step1-5 与既有 outputs 零改动；② 列名只是历史包袱，语义已在本文档与 docstring 中固化；③ "通用列名 + 映射"的收益低于破坏性成本。

### 3.3 注册与选择（新文件 `adapters/__init__.py`）

```python
ADAPTERS: dict[str, type[PlatformAdapter]] = {}

def register(cls):
    ADAPTERS[cls.PLATFORM_ID] = cls
    return cls

def get_adapter(cfg) -> PlatformAdapter:
    platform = cfg["crawl"].get("platform", "bilibili")   # 默认 = 现状
    if platform not in ADAPTERS:
        raise ValueError(f"未知平台: {platform}，可选: {list(ADAPTERS)}")
    return ADAPTERS[platform](cfg)
```

`main.py` 中 `Step0` 一行改动：

```python
# 之前
_run_step("Step0 采集", lambda c: crawler.run(c), cfg, results)
# 之后
_run_step("Step0 采集", lambda c: adapters.get_adapter(c).run(), cfg, results)
```

`crawler.run(cfg)` 的现有职责（目录准备、seen 去重、flush、限速骨架）**上提为 `BaseCrawler.run()` 模板方法**（见 §4.1）。

---

## 4. BilibiliAdapter 迁移（零行为变化）

### 4.1 模板方法拆分

现有 `BilibiliCrawler` 拆为两块：

| 现有职责 | 去向 |
|---|---|
| `_init_files` / `flush` / `seen_*` 去重 / 限速骨架 / `run()` 编排 | `adapters/base.py::BaseCrawler`（框架层） |
| `_get_wbi_keys` / `_sign` / `search_videos` / `_get_main_replies` / `_get_sub_replies` / `bvid_to_aid` | `adapters/bilibili.py::BilibiliAdapter`（平台层） |

`BilibiliAdapter.run()` 复用 `BaseCrawler.run()` 模板，只覆写"搜索"与"拉评论"两个钩子。

**迁移验收标准**：对同一事件、同一 Cookie 重跑，新旧实现产出的 `videos.csv` 与 `comments.csv` **逐行 diff 为空**（时间戳列除外）。

### 4.2 Cookie 兼容

```yaml
crawl:
  platform: bilibili        # 新增，缺省 bilibili
  cookie: ""                # 保留（B 站场景）
```

环境变量回退链保持不变：`crawl.cookie` → `BILI_COOKIE`。
新平台凭据走独立键（互不污染）：如 YouTube 场景 `crawl.api_key` / `YOUTUBE_API_KEY`。

---

## 5. 第一个新平台：YouTubeAdapter

### 5.1 为什么 YouTube 是正确的第二个平台

- 已有工作基础：`YouTube-Public-Opinion-Analysis-System` 仓库已完成 YouTube Data API v3 评论采集，可直接移植
- 官方 API 稳定、无需逆向签名（与 B 站 WBI 形成对照，验证契约抽象度）

### 5.2 字段映射表

| RawComment | YouTube 来源 | 说明 |
|---|---|---|
| `comment_id` | `snippet.topLevelComment.id` / `reply.id` | |
| `content_id` | 请求参数 `videoId` | |
| `parent_id` | 顶层=空；回复=对应 `commentThreadId` 根 ID | YouTube 只有两层，与 B 站一致 |
| `user_id` | `snippet.authorChannelId.value` | 无 channel ID 的匿名评论回退为 `@handle` |
| `username` | `snippet.authorDisplayName` | |
| `reply_to` | 回复场景可从 `@mention` 正则提取；顶层为空 | 语义对齐 B 站 `target`，保 SNA 边 |
| `message` | `snippet.textOriginal` | |
| `likes` | `snippet.likeCount` | |
| `reply_count` | `snippet.totalReplyCount` | |
| `created_at` | `snippet.publishedAt` → 格式化 | |

**已知语义差异（必须写入适配器 docstring）**：
1. YouTube `view` 是播放次数（含重复），B 站 `view` 同义但统计口径不同 → 跨平台对比报告需加脚注
2. YouTube 无法穷尽全部评论历史（API 分页上限），B 站可穷尽 → `max_reply_pages` 语义差异需在报告中披露
3. `target` 字段在 YouTube 的准确率依赖 `@mention` 存在性，预计低于 B 站 → Step5 的 reply 边密度会不同，**这是平台差异，不是 bug**

### 5.3 依赖策略

`google-api-python-client` 不进基础 `requirements.txt`，采用 extras：

```toml
# pyproject.toml
[project.optional-dependencies]
youtube = ["google-api-python-client>=2.100"]
```

`YouTubeAdapter.health_check()` 在依赖缺失时给出安装指引而非裸 ImportError。

---

## 6. 前端与 CLI 适配

| 位置 | 改动 |
|---|---|
| `app/config_ui.py` | `crawl` 分区顶部加平台单选（从 `ADAPTERS` 动态渲染 + `health_check` 状态徽标） |
| `app/home.py` | 运行页眉显示 `DISPLAY_NAME`；报告 HTML 头部追加平台标识 |
| `biliopinion/main.py` | Step0 走 `adapters.get_adapter`（见 §3.3，一行） |
| CLI | `run.py` 增加 `--platform` 覆盖项（优先级：CLI > config > 默认 bilibili） |
| 报告 | `report.py` 模板加元信息行：`数据平台: 哔哩哔哩 | 采集窗口: … | 评论 N 条` |

---

## 7. 测试策略

### 7.1 契约测试（新增 `tests/test_adapter_contract.py`）

所有适配器共享同一套行为测试，参数化跑：

```python
ADAPTER_CASES = ["bilibili"]        # youtube 接入后加入

@pytest.mark.parametrize("platform", ADAPTER_CASES)
def test_comment_schema(platform, adapter_fixture):
    """每个适配器产出的 RawComment 必须满足契约"""
    rc = first_comment(adapter_fixture)
    assert rc.comment_id and rc.content_id
    assert rc.message
    assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", rc.created_at)

@pytest.mark.parametrize("platform", ADAPTER_CASES)
def test_normalize_roundtrip(platform, adapter_fixture):
    """RawComment → CSV 行 → 列名与行宽与现网完全一致"""
```

### 7.2 回归测试

- 现有 `tests/` 全量保留并通过
- §4.1 的 diff 验收用例固化为 `tests/test_bilibili_regression.py`（用录制的 API 响应 fixture 回放，不打真实网络）

---

## 8. 实施路线（三阶段，每阶段独立可合并）

| 阶段 | 内容 | 风险 | 预估规模 |
|---|---|---|---|
| **P1** | 抽取 `adapters/base.py`（契约 + BaseCrawler + writer），`BilibiliAdapter` 包装迁移，diff 回归 | 低——纯重构，行为锁定 | ~2 个 PR：契约+迁移、回归测试 |
| **P2** | 配置层 `crawl.platform` 选择器 + CLI `--platform` + Streamlit 平台单选 + health_check | 低——默认值即现状 | ~1 个 PR |
| **P3** | `YouTubeAdapter` 实现 + extras 依赖 + 契约测试扩容 + 报告平台标识 | 中——真实 API 联调 | ~1-2 个 PR |

**每阶段完成定义**：pytest 全绿 + B 站冒烟（真实事件小样本跑通 Step0→Step9）+ 文档更新。

---

## 9. 风险与开放问题

1. **B 站反爬演进**：WBI 签名、风控策略随时可能变化。适配层不增加新风险（签名逻辑原样搬迁），但建议在 `BilibiliAdapter` 中保留现有全部 `log.warning` 探针
2. **`target` 字段质量差异**：YouTube 的 reply 边可能明显稀疏，Step5 报告应输出"边密度"指标辅助解读（P3 顺带）
3. **open question**：`comments.csv` 是否要新增 `platform` 列？——**暂不**。单次运行只处理单平台数据（`project.name` 已区分），列变更收益不抵回归成本。若未来支持"混合分析"再议
4. **YouTube API 配额**：默认 `quota` 保守限速（10k units/天）；适配器暴露 `crawl.quota_guard` 布尔开关，触顶时优雅停止并保留已采数据（现有 flush 机制天然支持断点续采）

---

## 10. 附录：目标目录结构

```
biliopinion/
├── adapters/
│   ├── __init__.py        # 注册表 + get_adapter
│   ├── base.py            # PlatformAdapter / ContentRef / RawComment / BaseCrawler
│   ├── writer.py          # RawComment → CSV 统一落盘（列名锁定为现网 schema）
│   ├── bilibili.py        # BilibiliAdapter（自 crawler.py 迁移）
│   └── youtube.py         # YouTubeAdapter（P3，移植自 YouTube-Public-Opinion-Analysis-System）
├── steps/                 # 不动
├── crawler.py             # 过渡期保留 re-export：from .adapters.bilibili import BilibiliCrawler（防外部引用断裂）
├── main.py                # Step0 一行改动
└── report.py              # 平台元信息行
```
