# BiliOpinion 📊

> 基于 B 站（Bilibili）评论的**舆情演化分析管线** —— 一键完成「采集 → 清洗 → 时间演化 → 主题 → 情感立场 → 社会网络 → 自包含报告」。

本项目是一个**事件无关的 B 站舆情演化分析通用框架**，方法论文献化自两项计算传播学课程研究——"鹅腿阿姨"事件（动态 Gephi 网络 + 人机协作标注 Cohen's Kappa 0.97 + MacBERT 微调）与"康熙换种"事件（模块化 8 步脚本 + 无监督 TF-IDF/SVD/KMeans 与 BERTopic 主题 + BERT 弱监督情感）。原脚本把**事件日期、核心短语词典、绝对路径、Cookie** 全部硬编码，换个事件就得改一堆代码。本框架把它们全部抽成**配置 + 自动推断**，让任何人只需做两件事即可在本地跑通任意主题的整套分析：

1. 填入想分析的舆情主题（例如「某热点事件」）
2. 填入自己的 B 站 Cookie

---

## 功能一览

| 步骤 | 内容 | 对应论文方法 |
|------|------|--------------|
| Step0 | B 站视频搜索 + 一/二级评论穷尽抓取（WBI 签名、断点续爬） | 数据获取 |
| Step1 | 字段统一、时间标准化、文本清洗、去重集 | 3.1 数据清洗 |
| Step2 | 每日评论量 + 3 日移动平均、**自动阶段断点检测**、核心短语词云、每日短语热力图 | 4.1 时间演化 |
| Step3 | TF-IDF+SVD+KMeans 无监督主题（轮廓系数选 K）+ 可选编码手册优先级分类、时间演化、层级交叉、文本长度 | 3.2/4.2 主题 |
| Step4 | SnowNLP 情感三分类 + 可选事件规则立场（采信 vs 质疑） | 3.5/4.3 情感立场 |
| Step5 | 社会网络（belongs_to/comment/reply 三类边、Louvain、词共现网络）+ **Gephi 导出套件** | 3.6/4.4 SNA |
| Step6–8 | **可选** BERT 句向量 + c-TF-IDF 主题 + 弱监督情感（需 torch） | 深度扩展 |
| Step9 | 自包含 HTML 报告（图表 base64 内嵌）+ 可选 docx | 结果呈现 |

**关键设计**：阶段划分与核心短语默认走**自动推断**，不再依赖手写日期与词典，因此不同规模、不同时长的事件产出结构可比的分析；手写 `codebook`、`manual phases`、立场词典均作为可选项保留，方便做与论文严格对齐的复现。

---

## 快速开始

### 1. 安装依赖

```bash
cd BiliOpinion
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 可选：BERT 深度分析
pip install torch transformers
# 可选：导出 docx
pip install python-docx
```

### 2. 准备配置与 Cookie

```bash
cp configs/example.yaml config.yaml
```

编辑 `config.yaml`，至少填好 `project.topic`（如 `某热点事件`）。
Cookie 获取方式见 [docs/GET_COOKIE.md](docs/GET_COOKIE.md)，推荐写入仓库根目录的 `.env`：

```ini
BILI_COOKIE=你的整段Cookie
```

> Cookie 含账号凭证，已加入 `.gitignore`，**切勿提交到公开仓库**。

### 3. 一键运行

```bash
python run.py config.yaml
# 或：python -m biliopinion
```

运行结束后，所有结果位于 `outputs/<project.name>/`：
- `report.html` —— 自包含可视化报告（双击即可在浏览器打开）
- `figures/` —— 全部图表
- `data/` —— 中间数据（清洗后评论、主题/情感标注、网络指标、GEXF 等）
- `effective_config.yaml` —— 本次实际生效的完整配置（保证可复现）
- `raw/` —— 原始抓取数据（断点续爬用）

---

## 配置说明（要点）

完整字段与缺省值在 `biliopinion/defaults.py`，示例与注释在 `configs/example.yaml`。常用开关：

- `crawl.enabled: false` —— 已有 `raw/` 数据时不重新抓取，直接跑后续分析。
- `phases.mode`: `auto`（默认，自动断点）/ `manual`（填真实节点日期做严格复现）。
- `phrases.mode`: `auto` / `manual`（手写核心短语词典）/ `hybrid`。
- `topics.mode`: `auto`（无监督命名）/ `codebook`（提供编码手册做优先级规则分类，论文方法）。
- `sentiment.stance.enabled: true` + 填 `pos_words`/`neg_words` —— 开启立场分析。
- `network.export_gexf: true` —— 导出全套 Gephi 资产（见下节）。
- `network.export_per_video: true` / `per_video_top_n: 10` —— 为热门视频各导出一个子网络。
- `bert.enabled: true` —— 开启 BERT 深度分析（需 torch + transformers）。

---

## Gephi 网络导出

`network.export_gexf: true` 时，`data/` 下会生成可直接拖进 Gephi 的全套文件：

| 文件 | 说明 |
|------|------|
| `gephi_nodes.csv` / `gephi_edges.csv` | **动态网络**点边表，带 `Timestamp` + `Datetime` + `R/G/B` 预染色。在 Gephi 中导入后开启 **Timeline** 即可播放舆情演化动画 |
| `keyword_nodes.csv` / `keyword_edges.csv` | 核心短语共现网络，带 `Modularity Class` / `Size` / RGB |
| `networks/interaction_full.gexf` | 整体交互网络 |
| `networks/video_<BV>_<标题>.gexf` | 前 N 个热门视频的独立子网络 |
| `networks/topic_bipartite.gexf` | 用户–主题二部网络 |
| `networks/sentiment_bipartite.gexf` | 用户–情感二部网络 |
| `networks/stance_bipartite.gexf` | 用户–立场二部网络（开启立场分析时） |

节点 ID 约定：`video_<BV>` / `up_<UP名>` / `user_<mid>`；边类型：`belongs_to` / `comment` / `reply`。
节点颜色默认按 Louvain 社群染色，未参与社群划分的按节点类型染色。

> Gephi 导入提示：先导入 `gephi_nodes.csv`（选 Nodes table），再导入 `gephi_edges.csv`（选 Edges table），
> 在 Data Laboratory 中把 `Timestamp` 设为时间列即可启用 Timeline 动态演化。

---

## 项目结构

```
BiliOpinion/
├── biliopinion/
│   ├── defaults.py        # 全部缺省配置
│   ├── config.py          # YAML 深度合并 + 校验 + Cookie/路径解析
│   ├── utils.py           # 日志/中文字体/分词/自动阶段/自动短语/容错读
│   ├── crawler.py         # Step0 可配置爬虫
│   ├── main.py            # 管线编排器
│   ├── report.py          # Step9 自包含 HTML 报告 / docx
│   ├── gephi.py           # Gephi 导出套件（动态点边表/二部网络/每视频子网）
│   └── steps/
│       ├── step1_clean.py … step5_network.py   # 核心五步
│       └── step6_bert_embed.py … step8_bert_sentiment.py  # 可选 BERT
├── tools/
│   ├── convert_legacy.py  # 旧格式爬虫数据 -> 本项目 schema
│   └── smoke_test.py      # 小样本快速自检
├── configs/example.yaml
├── docs/GET_COOKIE.md
├── requirements.txt
└── run.py
```

### 复用已有数据

如果你手上已经有旧格式的抓取结果（无表头 `comments.csv` + 中文表头 `videos.csv`），
可以先转换再跑分析，跳过采集：

```bash
python tools/convert_legacy.py <旧数据目录> outputs/<project.name>/raw
# 然后在配置里设 crawl.enabled: false
python run.py config.yaml
```

转换器内置**逐行编码探测**，能处理多次追加写入导致的 UTF-8 / GBK 混合编码文件。

---

## 方法学说明

- **自动阶段划分**：以全局每日评论量峰值为基准，用相对比例阈值（启动/高峰/衰减/二次发酵）切出 P0 潜伏→P1 启动→P2 高峰→P3 衰减→P4 二次发酵→P5 长尾，使不同事件结构可比。
- **核心短语（评论级计数）**：一条评论中某短语出现多次只计 1 次，避免刷屏评论放大权重，与论文方法一致。
- **主题**：算力受限时以 TF-IDF/LSA 向量替代 BERT-768 向量，但聚类流程与评估标准（轮廓系数）一致；提供 `codebook` 模式做与论文编码表严格对齐的优先级分类。
- **情感/立场**：SnowNLP 词典法三分类 + 可配事件规则立场词典；可选 BERT 弱监督（SnowNLP 伪标签训练线性分类器）。
- **社会网络**：节点=用户/视频/UP 主，边=belongs_to/comment/reply；指标含度、密度、平均路径长度、直径、Louvain 模块化、聚类系数，并导出 GEXF 供 Gephi 进一步探索。

---

## 许可证与声明

仅用于学术与个人研究。请遵守 B 站相关协议与数据使用规范，勿将 Cookie 等凭证泄露或提交到公开仓库。
