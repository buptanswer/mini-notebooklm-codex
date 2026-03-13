# MinerU to RAG Pipeline 架构设计与数据流方案

## 1. 目标与范围

本文档定义一套从 MinerU SaaS 压缩包到 RAG 可用数据的完整工程方案，覆盖三层目标：

1. 解析 MinerU SaaS `full_zip_url` 压缩包
2. 标准化生成可扩展的 IR 中间格式
3. 基于结构与语义完成 Parent/Child 分层切片

本方案仅面向以下输入范围：

- PDF
- Word
- PPT
- 图片

并约束在以下 MinerU 在线 API 路径：

- 请求参数：`model_version=vlm`
- 实际产出：`layout.json` 中 `_backend=hybrid`

不纳入本方案主线的范围：

- HTML 输入
- `extra_formats` 导出的附加格式

## 1.1 本文档的前置依赖

本方案文档不是对 MinerU 原始输出格式的重新定义，而是建立在以下文档之上：

- [在线API输出文件格式（SaaS推断版）.md](.\在线API输出文件格式（SaaS推断版）.md)

理解方式：

- 上述文档负责回答“MinerU SaaS 实际输出了什么”
- 本文档负责回答“如何把这些输出组织成 RAG 可用的数据流”

如果将开发任务交给其他 AI 编程助手，建议默认把这两份文档一起作为唯一需求输入。

## 2. 设计原则

本方案严格遵循以下原则。

### 2.1 单一权威源

主输入以 `content_list_v2.json` 为准，因为它：

- 保留页面分组
- 保留 `title` 与 `paragraph` 的区别
- 对多模态对象使用结构化 `content`

`layout.json` 只承担两类职责：

- 提供 `page_size`
- 作为坐标回溯和结构补充层

### 2.2 结构先于文本

任何切片、富化、向量化，都必须以文档结构为上游约束：

- 不跨越标题边界
- 不把页眉页脚页码与正文物理拼接
- 不破坏列表、代码块原子性

### 2.3 多模态无损保留

不能把图片、表格仅退化成纯文本。IR 必须保留原始资产路径，以支持：

- 检索阶段的高质量召回
- 问答阶段对多模态大模型的直接透传

### 2.4 坐标锚定优先

IR 必须能支持前端回溯高亮，因此每个块必须同时保留：

- `bbox_norm1000`
- `bbox_page`
- `page_idx`
- `origin.pdf` 路径

### 2.5 Parent/Child 解耦

Embedding 与最终召回上下文不是同一个粒度：

- Child 用于检索
- Parent 用于还原上下文

因此 Parent/Child 必须显式建模，而不是隐式拼接。

### 2.6 Schema First

本方案的代码实现必须采用 `Schema First` 策略。

这不是可选优化，而是强约束：

- 不能使用松散的裸 `dict` 作为主数据结构贯穿全流程
- 必须先定义模型，再做解析、转换、富化、切片
- 任何进入 IR 和 Chunk 层的数据都必须经过结构校验

推荐技术实现：

- Python 使用 `Pydantic`

原因：

- MinerU SaaS 原始输出存在版本波动
- 本方案的 IR 结构层级深、字段多、关系复杂
- RAG 链路一旦写入脏数据，问题会在向量库和问答阶段被放大

因此必须通过显式 Schema 把“外部输入兼容”和“内部数据严格”分开。

### 2.7 宽进严出

代码实现必须分成两层模型：

第一层：Raw MinerU Models

- 负责接收 `content_list_v2.json`、`layout.json`、`*_content_list.json` 等原始输出
- 使用 `Pydantic` 建模
- 允许程序读取到未知字段，但绝不允许静默忽略
- 对可选字段保持兼容
- 目标是应对 MinerU 的小版本波动

更具体地说：

- 若出现未在 Raw Schema 中声明的字段，至少必须产生 warning
- 必须将未知字段原样保留到 `raw_source.extra_fields`、日志或等价结构中
- 不允许“解析成功但把未知字段直接吞掉”
- 可提供严格模式：一旦发现未知字段直接失败

当前项目实际实现说明：

- 默认策略为“warning + 原样保留 + `needs_review` 提示用户复核”
- 未知字段、未知 block 和 fallback content shape 不会默认中断整篇文档
- 若后续业务需要，可再切换到更强的 strict-fail 策略

第二层：Canonical IR / Chunk Models

- 负责 `document_ir.json`
- 负责 `document_ir_enriched.json`
- 负责 `parent_chunks.jsonl`
- 负责 `child_chunks.jsonl`
- 同样使用 `Pydantic` 建模
- 但这里必须严格定义字段、类型、嵌套关系和约束

一句话：

- 对外部输入宽容
- 对内部标准严格

## 3. 原始输入与输出契约

## 3.1 原始输入

一个 MinerU SaaS zip 包，核心文件集合约为：

```text
<zip-root>/
  <uuid>_model.json
  <uuid>_content_list.json
  <uuid>_origin.pdf
  content_list_v2.json
  layout.json
  full.md
  images/*.jpg
```

## 3.2 本方案的输出物

建议输出 4 类工件：

1. `document_ir.json`
2. `document_ir_enriched.json`
3. `parent_chunks.jsonl`
4. `child_chunks.jsonl`

当前项目实际采用的目录方案：

```text
storage/knowledge_bases/<knowledge_base_id>/
  uploads/
  mineru_bundles/<data_id>/bundle/
    content_list_v2.json
    layout.json
    document_ir.json
    document_ir_enriched.json
    parent_chunks.jsonl
    child_chunks.jsonl
    images/*
```

说明：

- `document_ir.json`：标准化后的基础 IR
- `document_ir_enriched.json`：在基础 IR 上增加 VLM/LLM 衍生字段
- `parent_chunks.jsonl`：父块
- `child_chunks.jsonl`：子块
- 当前没有单独再复制一份统一 `assets/`，而是直接复用 MinerU bundle 内的原始图片与派生产物路径，以减少重复存储并简化溯源关系

## 3.3 推荐的代码模块边界

为保证不同 AI 编程助手都能稳定实现，建议代码结构至少拆成下面几层。当前项目实际代码命名没有完全照搬这里的示例名称，但职责边界仍然对应这些层次：

1. `models_raw_mineru`
   - 定义原始 MinerU 输出的 `Pydantic` 模型
   - 允许捕获额外字段，但必须记录和告警
2. `models_ir`
   - 定义标准化 IR 模型
   - 严格校验
3. `models_chunk`
   - 定义 Parent / Child Chunk 模型
   - 严格校验
4. `adapters`
   - 实现 `raw -> ir`
5. `enrichers`
   - 实现图片描述、表格摘要等富化
6. `chunkers`
   - 实现 Parent / Child 切片
7. `validators`
   - 实现业务一致性校验
8. `writers`
   - 负责输出 JSON / JSONL

## 4. 总体数据流

完整数据流分 6 个阶段：

1. `Bundle Parse`
2. `Canonical Normalize`
3. `DOM Rebuild`
4. `Multimodal Enrichment`
5. `Parent/Child Chunking`
6. `Index Export`

### 4.1 Bundle Parse

输入：

- zip 包路径

输出：

- 根文件角色识别结果
- 原始文件清单
- `content_list_v2.json`
- `layout.json`
- `*_origin.pdf`
- `images/*`

### 4.2 Canonical Normalize

任务：

- 把 MinerU 的块统一成标准块类型
- 计算文档内顺序
- 统一坐标格式
- 将页眉页脚页码从正文语义流中转移到 metadata

输出：

- `document_ir.json`

### 4.3 DOM Rebuild

任务：

- 基于 `title.level` 维护 Title Stack
- 构建 Section Tree
- 为每个叶子块注入 `header_path`

输出：

- 完整 section tree
- 每个 block 挂载所属 section

### 4.4 Multimodal Enrichment

任务：

- 图片：补 VLM 描述
- 表格：补 LLM 摘要
- 行间公式：绑定上下文
- Footnote：尝试挂接到关联正文

输出：

- `document_ir_enriched.json`

### 4.5 Parent/Child Chunking

任务：

- 以 section 为父边界
- 生成 Parent
- 在 Parent 内生成 Child
- 为 Child 注入 header context

输出：

- `parent_chunks.jsonl`
- `child_chunks.jsonl`

### 4.6 Index Export

任务：

- 导出 Dense 向量化文本
- 导出关键词检索文本
- 导出问答阶段可回溯的多模态资产元信息

## 5. 标准化 IR Schema 设计

### 5.0 Schema 实现要求

本章定义的所有 IR 结构，在代码实现时都必须对应到 `Pydantic` 模型。

要求：

- 顶层对象必须有显式 Model
- 嵌套对象必须有显式 Model
- 枚举字段尽量使用 `Literal` 或 `Enum`
- `bbox`、`page_idx`、`header_path`、`assets`、`relations` 不允许用弱类型占位

建议：

- 对 `bbox_norm1000` 增加范围校验
- 对 `page_idx` 增加非负校验
- 对 `header_path` 增加最少为 `[]`、正文块通常非空的约束
- 对 `image/table/equation/code/list` 的结构做类型级约束
- 对 Raw MinerU 输入增加“未知字段检测与告警”机制

## 5.1 顶层对象

建议 `document_ir.json` 顶层结构如下：

```json
{
  "ir_version": "1.0.0",
  "pipeline_version": "1.0.0",
  "source": {},
  "bundle": {},
  "document": {},
  "pages": [],
  "sections": [],
  "blocks": [],
  "relations": {},
  "quality": {}
}
```

## 5.2 `source`

记录原始来源。

```json
{
  "doc_id": "sha1-or-business-id",
  "source_filename": "sample.pdf",
  "source_format": "pdf|docx|pptx|jpg|jpeg|png",
  "mineru_request_model": "vlm",
  "mineru_actual_backend": "hybrid",
  "mineru_version_name": "2.7.5",
  "origin_pdf_path": "db49..._origin.pdf"
}
```

说明：

- `doc_id` 不直接用 MinerU UUID，建议用你自己的稳定业务 ID
- `origin_pdf_path` 为后续 UI 高亮和问答透传基准

## 5.3 `bundle`

记录解析包清单。

```json
{
  "root_files": {
    "content_list_v2": "content_list_v2.json",
    "layout": "layout.json",
    "full_md": "full.md",
    "content_list_compat": "db49..._content_list.json",
    "model_raw": "db49..._model.json",
    "origin_pdf": "db49..._origin.pdf"
  },
  "asset_root": "images/",
  "asset_count": 18
}
```

## 5.4 `document`

```json
{
  "title": "The response of flow duration curves to afforestation",
  "language": "zh|en|mixed|unknown",
  "page_count": 13,
  "reading_order": "page_then_block",
  "has_multimodal": true,
  "has_code": false,
  "has_table": true,
  "has_equation": true,
  "has_footnote": true
}
```

## 5.5 `pages`

每一页一个对象。

```json
{
  "page_id": "p0001",
  "page_idx": 0,
  "page_size": {
    "width": 595,
    "height": 841,
    "unit": "origin_pdf_native"
  },
  "auxiliary": {
    "page_headers": [
      {"text": "Journal of ...", "block_id": "b0003"}
    ],
    "page_footers": [],
    "page_numbers": [
      {"text": "1", "block_id": "b0004"}
    ]
  },
  "footnotes": [
    {"block_id": "b0020", "text": "* Corresponding author..."}
  ],
  "block_ids": ["b0001", "b0002", "b0003"]
}
```

重要说明：

- `page_header/page_footer/page_number` 进入 `auxiliary`
- 不参与正文切片文本拼接
- 但会在 Chunk metadata 中按页透传

## 5.6 `sections`

每个标题节点和合成节点都是一个 section。

```json
{
  "section_id": "s0007",
  "parent_section_id": "s0002",
  "level": 2,
  "title": "1.2 实验方法",
  "header_path": ["第一章 绪论", "1.2 实验方法"],
  "synthetic": false,
  "page_span": [3, 6],
  "child_section_ids": ["s0008", "s0009"],
  "block_ids": ["b0140", "b0141", "b0142"],
  "order_start": 140,
  "order_end": 168
}
```

特殊情况：

- 无标题文档时创建一个或多个 `synthetic=true` 的 section
- 封面、目录、前言等可作为一级合成 section

## 5.7 `blocks`

这是 IR 的核心。

统一块类型枚举：

- `title`
- `paragraph`
- `list`
- `code`
- `table`
- `image`
- `equation`
- `page_header`
- `page_footer`
- `page_number`
- `page_footnote`

建议块结构：

```json
{
  "block_id": "b0142",
  "page_idx": 3,
  "order_in_page": 7,
  "order_in_doc": 142,
  "section_id": "s0007",
  "header_path": ["第一章 绪论", "1.2 实验方法"],
  "type": "paragraph",
  "subtype": null,
  "role": "main",
  "bbox_norm1000": [157, 219, 828, 242],
  "bbox_page": [94, 185, 493, 204],
  "anchor": {
    "page_id": "p0004",
    "origin_pdf_path": "db49..._origin.pdf",
    "coord_space": "origin_pdf_native",
    "render_formula": {
      "x": "bbox_norm1000.x / 1000 * page_width",
      "y": "bbox_norm1000.y / 1000 * page_height"
    }
  },
  "text": "The response of flow duration curves to afforestation",
  "segments": [
    {"type": "text", "content": "The response of flow duration curves to afforestation"}
  ],
  "assets": [],
  "metadata": {
    "title_level": 1,
    "code_language": null,
    "list_type": null,
    "math_type": null,
    "table_type": null,
    "page_auxiliary_ref": {
      "header_block_ids": ["b0003"],
      "footer_block_ids": [],
      "page_number_block_ids": ["b0004"]
    }
  },
  "footnote_links": [
    {
      "footnote_block_id": "b0020",
      "attach_mode": "inline_append",
      "confidence": 0.93
    }
  ],
  "raw_source": {
    "source_file": "content_list_v2.json",
    "source_type": "title"
  }
}
```

## 5.8 `assets`

所有多模态块必须保留资产对象。

### 图片

```json
[
  {
    "asset_id": "a0091",
    "asset_type": "image",
    "path": "images/fa6a....jpg",
    "usage": "primary",
    "mime": "image/jpeg"
  }
]
```

### 表格

```json
[
  {
    "asset_id": "a0110",
    "asset_type": "table_image",
    "path": "images/a85a....jpg",
    "usage": "qa_preferred"
  }
]
```

### 公式

公式可不一定需要图片参与向量化，但仍建议保留。

```json
[
  {
    "asset_id": "a0202",
    "asset_type": "equation_image",
    "path": "images/35e0....jpg",
    "usage": "debug_or_render"
  }
]
```

## 5.9 `document_ir_enriched.json`

富化后的 IR 在基础 IR 上增加 `enrichment` 字段。

### 图片块富化

```json
{
  "enrichment": {
    "image_caption_text": "图 1 数据采集流程",
    "image_vlm_description": "该图展示了...",
    "neighbor_context": {
      "prev_paragraphs": ["上一段..."],
      "next_paragraphs": ["下一段..."]
    },
    "embedding_text": "第一章 绪论 > 1.2 实验方法\n图 1 数据采集流程\n该图展示了...\n上一段...\n下一段..."
  }
}
```

### 表格块富化

```json
{
  "enrichment": {
    "table_caption_text": "表 2 用户-物品评分矩阵",
    "table_summary": "该表比较了 4 个用户对 4 个物品的评分...",
    "table_html_available": true,
    "embedding_text": "第二章 实验结果 > 2.1 推荐结果\n表 2 用户-物品评分矩阵\n该表比较了..."
  }
}
```

### 公式块富化

```json
{
  "enrichment": {
    "equation_context_text": "上一段讨论了损失函数定义...",
    "embedding_text": "第三章 模型方法 > 3.2 目标函数\n上一段讨论了损失函数定义...\n$$ MSE = ... $$"
  }
}
```

## 5.10 `relations`

显式记录 Parent/Child、Footnote、上下文邻接关系。

```json
{
  "parent_child": [],
  "footnote_attachment": [],
  "block_neighbors": []
}
```

## 6. DOM 重建与 Header Path 注入

## 6.1 标题栈策略

以 `content_list_v2.json` 为主输入，遍历顺序固定为：

- 按页
- 按页内块顺序

这里需要明确两个实现约束：

- `page_idx` 默认取 `content_list_v2.json` 顶层外层数组下标
- `order_in_page` 默认取页内数组下标

也就是说，在没有额外矫正信号时，应将：

- 外层数组顺序视为页顺序
- 内层数组顺序视为 MinerU 已给出的阅读顺序

只有当后续验证发现该顺序与 `layout.json` 明显冲突时，才允许引入校正逻辑；默认实现不应自行重排。

维护一个 `title_stack`，其中每个元素是当前打开的 section。

规则：

1. 遇到 `title(level=L)`：
2. 若栈为空，则作为根下第一个 section
3. 若 `L` 大于当前栈深度 + 1，可自动补齐中间 synthetic section，或直接挂到最近父级后标记 `level_gap=true`
4. 当当前栈深度 `>= L` 时，持续弹栈，直到栈深 `< L`
5. 新建当前标题对应的 section，挂到新的父 section 下
6. 压栈
7. 后续非标题块全部挂到当前栈顶 section

### 6.1.1 伪代码

```text
root = synthetic_root()
title_stack = []

for block in blocks_in_reading_order:
    if block.type == "title":
        L = max(1, block.metadata.title_level)
        while len(title_stack) >= L:
            title_stack.pop()
        parent = title_stack[-1] if title_stack else root
        section = create_section(parent, level=L, title=block.text)
        title_stack.append(section)
        attach_title_block_to_section(block, section)
    else:
        if title_stack is empty:
            section = get_or_create_preamble_section(root)
        else:
            section = title_stack[-1]
        attach_block_to_section(block, section)
        block.header_path = section.header_path
```

## 6.2 无标题文档处理

若全文不存在标题：

- 创建 `ROOT > 无标题文档` synthetic section
- 所有正文块挂到该 section 下
- 如果正文极长，可按页或按段落密度生成子 synthetic section：
  - `无标题文档 / 第 1-5 页`
  - `无标题文档 / 第 6-10 页`

但这些 synthetic section 只用于结构组织，不应伪装成真实标题。

## 6.3 Header Path 生成

对每个 `main` 块强注入：

```json
["第一章 绪论", "1.2 实验方法", "1.2.1 数据采集"]
```

同时生成文本形式：

```text
第一章 绪论 > 1.2 实验方法 > 1.2.1 数据采集
```

用途：

- Child chunk contextual enrichment
- Parent chunk display
- 检索召回后给大模型的上下文提示

## 7. metadata 转移策略

## 7.1 Page Header / Footer / Page Number

这三类信息绝对不能和正文物理拼接成 chunk 文本。

处理方式：

- 保存在 `pages[].auxiliary`
- 在 `blocks[].metadata.page_auxiliary_ref` 中存引用
- 在 Parent/Child chunk metadata 中透传相关页的辅助信息

这样做的好处：

- 不污染语义向量
- 前端仍可显示原始页面信息
- 需要调试版问答时仍可显式拼回

## 7.2 Page Footnote

`page_footnote` 的处理比页眉页脚更复杂，因为它常常有语义价值。

建议采用“链接优先、拼装次之”的策略：

1. 先把 footnote 保留为独立 block
2. 尝试在同页内寻找最可能的锚点正文
3. 若能定位，则将 footnote 文本追加到该正文块的 `footnote_links`
4. Chunking 阶段可把 footnote 作为附加文本拼到该正文 chunk 尾部

### 7.2.1 Footnote 关联启发式

按优先级：

1. 标记匹配
   - 正文中存在 `*`、`†`、`①`、`1)` 等脚注标记
   - 脚注文本开头也存在相同标记
2. 同页最近前驱正文
   - 选择该 footnote 之前最近的 `paragraph/title/list/code/equation/table/image`
3. 垂直距离最小
   - 同页内 `y` 更接近页面底部的正文优先
4. Section 一致性优先
   - 与 footnote 同 section 的正文优先

### 7.2.2 Footnote 伪代码

```text
for footnote in page_footnotes:
    candidates = main_blocks_on_same_page_before_footnote()
    scored = score(candidates,
        marker_match,
        section_match,
        vertical_proximity,
        block_type_preference)
    if best_candidate.score >= threshold:
        link_footnote(best_candidate, footnote, mode="inline_append")
    else:
        keep_footnote_as_orphan(page_idx)
```

### 7.2.3 无法确定归属时

不要强行拼正文。应：

- 保留 `orphan_footnote=true`
- 在 page metadata 中独立挂载
- 问答阶段可作为附加上下文候选

## 8. 坐标换算与 UI 高亮溯源

## 8.1 坐标源

来自两个文件：

- `content_list_v2.json`：`bbox` 为 `0-1000`
- `layout.json`：`page_size = [width, height]`

## 8.2 统一换算

对任意块：

```text
x0_page = x0_norm / 1000 * page_width
y0_page = y0_norm / 1000 * page_height
x1_page = x1_norm / 1000 * page_width
y1_page = y1_norm / 1000 * page_height
```

### 重要说明

严格来说，这里换算得到的是 `origin.pdf` 的原生页坐标，不一定等于屏幕像素。

这是正确的做法，因为：

- PDF 前端渲染会有缩放
- 真正稳定的高亮锚点应是“文档页坐标”

因此 IR 建议存两套字段：

- `bbox_norm1000`
- `bbox_page`

前端渲染时再按当前页面缩放系数换成最终屏幕像素。

### 8.2.1 前端高亮公式

若前端将该页渲染为：

- `rendered_width`
- `rendered_height`

则屏幕坐标为：

```text
x0_screen = x0_page / page_width * rendered_width
y0_screen = y0_page / page_height * rendered_height
x1_screen = x1_page / page_width * rendered_width
y1_screen = y1_page / page_height * rendered_height
```

## 9. 多模态对象的无损双轨绑定

## 9.1 图片 `image`

IR 必须保留：

- `image_source.path`
- `image_caption`
- 所在 `header_path`
- 前后相邻段落 ID

富化阶段再增加：

- `image_vlm_description`

### 9.1.1 图片 Chunk 文本构成

用于 embedding 的文本：

```text
[header_path]
[caption]
[VLM描述]
[前相邻段落]
[后相邻段落]
```

但该 chunk 必须继续保留：

- 图片原路径
- 块坐标
- 所属页码

这样在最终 QA 阶段可以把原图直接透传给多模态模型。

## 9.2 表格 `table`

IR 必须保留：

- `content.html`
- `image_source.path`
- `table_caption`
- `table_footnote`

富化阶段：

- 对 `html` 调用 LLM 生成 `table_summary`
- 若 `html` 缺失，则直接对截图调用多模态模型生成 `table_summary_fallback`

### 9.2.1 表格 Chunk 文本构成

用于 embedding 的文本：

```text
[header_path]
[caption]
[table_summary]
[必要的上下文段落]
```

问答阶段优先使用：

- 表格截图

而不是把长 HTML 原文直接塞给最终回答模型。

## 9.3 行间公式 `equation_interline`

IR 必须保留：

- `math_content`
- `math_type`
- `image_source.path`（可选调试/渲染）

用于 embedding 的文本：

```text
[header_path]
[相邻上下文]
[latex]
```

对于公式检索，优先使用 LaTeX 文本，而不是截图。

## 10. 结构感知 Chunking 方案

## 10.1 Chunking 总原则

1. 不跨 section 边界
2. 不跨 H1/H2 逻辑边界
3. 不把辅助块混入正文文本
4. 列表、代码尽量整体保留
5. Child 开头必须注入 `header_path`

## 10.2 Parent Chunk

Parent 的粒度定义为：

- 当前最低层级标题下的完整连续内容

也就是“整个小节”。

### 10.2.1 Parent 结构

```json
{
  "parent_chunk_id": "pc0007",
  "doc_id": "sample",
  "section_id": "s0007",
  "header_path": ["第一章 绪论", "1.2 实验方法"],
  "title": "1.2 实验方法",
  "page_span": [3, 6],
  "block_ids": ["b0140", "b0141", "b0142"],
  "text_for_generation": "完整小节文本 ...",
  "assets": ["a0110", "a0202"],
  "metadata": {
    "page_headers": [],
    "page_footers": [],
    "page_numbers": ["4", "5", "6"]
  }
}
```

用途：

- 检索命中后回填大上下文
- 最终问答时作为 Big Context

## 10.3 Child Chunk

Child 的粒度定义为：

- 专门服务 embedding 的小粒度文本块

### 10.3.1 文本段落切分策略

仅在同一 Parent 内切分。

步骤：

1. 先按段落组织语义单元
2. 再按标点做滑动窗口
3. 窗口建议 `150-250 tokens`
4. 重叠建议 `10%-20%`

Child 的开头强制拼接：

```text
第一章 绪论 > 1.2 实验方法
```

### 10.3.2 Child 结构

```json
{
  "child_chunk_id": "cc0142_02",
  "parent_chunk_id": "pc0007",
  "doc_id": "sample",
  "section_id": "s0007",
  "header_path": ["第一章 绪论", "1.2 实验方法"],
  "chunk_type": "paragraph",
  "page_span": [4, 4],
  "source_block_ids": ["b0142"],
  "embedding_text": "第一章 绪论 > 1.2 实验方法\n这里是切片后的正文...",
  "retrieval_text": "这里是切片后的正文...",
  "assets": [],
  "metadata": {
    "page_numbers": ["5"],
    "code_language": null,
    "is_atomic": false
  }
}
```

## 10.4 原子块策略

### 列表 `list`

默认整个列表作为一个 Child，不从中间切断。

只有在极端超长时，才允许：

- 按列表项切
- 但不能切断单个列表项内部内容

### 代码 `code`

默认整个代码块作为一个 Child。

保留：

- `code_language`
- 原始换行
- 所在 section

只有极端超长时，才允许按以下边界切：

- 函数边界
- 类边界
- 注释块边界
- 固定行段边界

并设置：

- `is_atomic_fragment=true`
- `fragment_index`
- `fragment_total`

## 10.5 多模态块的 Child 生成

### 图片

Child 不只是 caption，而是：

```text
[header_path]
[caption]
[vlm_description]
[prev_context]
[next_context]
```

### 表格

Child 不直接塞长 HTML，而是：

```text
[header_path]
[caption]
[table_summary]
[prev_context_if_needed]
[next_context_if_needed]
```

### 公式

Child 为：

```text
[header_path]
[equation_context]
[latex]
```

## 11. 解析与切片核心工作流

## 11.1 Phase A：Zip 解析

```text
1. 解压 zip
2. 按后缀和固定文件名识别角色
3. 校验 content_list_v2.json 与 layout.json 是否存在
4. 建立 page_size 映射
5. 建立 assets 索引
```

## 11.2 Phase B：块标准化

```text
1. 遍历 content_list_v2.json
2. 将 MinerU type 映射到标准 type
3. 统一生成 block_id
4. 保存 bbox_norm1000
5. 用 page_size 计算 bbox_page
6. 对辅助块写入 pages[].auxiliary
7. 对 main 块写入 blocks[]
```

## 11.3 Phase C：Section Tree 重建

```text
1. 初始化 synthetic root
2. 维护 title_stack
3. 遇到 title 建 section
4. 遇到非 title 挂到当前 section
5. 为每个 block 注入 header_path
```

## 11.4 Phase D：Footnote 拼装

```text
1. 收集每页 page_footnote
2. 同页寻找候选正文
3. 按 marker / proximity / section score 排序
4. 命中则建立 footnote_links
5. 未命中则保留 orphan
```

## 11.5 Phase E：多模态富化

```text
1. image -> caption + vlm_description + neighbor_context
2. table -> html -> table_summary
3. equation -> latex + neighbor_context
4. 写入 document_ir_enriched.json
```

## 11.6 Phase F：Parent 生成

```text
1. 以 section 为边界
2. 收集 section 下所有 main block
3. 生成 text_for_generation
4. 记录 assets 和 page metadata
5. 输出 parent_chunks.jsonl
```

## 11.7 Phase G：Child 生成

```text
1. 逐个 Parent 处理
2. paragraph 按标点滑窗
3. list / code 尽量整块保留
4. image / table / equation 使用富化文本
5. 每个 Child 注入 header_path
6. 记录 parent_chunk_id
7. 输出 child_chunks.jsonl
```

## 12. 容错与降级策略

## 12.1 缺失 `content_list_v2.json`

降级到 `*_content_list.json`：

- `text + text_level` 还原 `title/paragraph`
- `header/footer/page_number/page_footnote` 保留为辅助块
- `table/image/code/equation/list` 做兼容映射

## 12.2 缺失 `layout.json`

仍可生成 IR，但：

- 只能保留 `bbox_norm1000`
- `bbox_page` 为空
- 前端高亮能力降级

同时在 `quality` 中标记：

- `ui_anchor_degraded=true`

## 12.3 无标题纯文本长文

策略：

- 建 synthetic root section
- 进一步按页或段簇切分 synthetic 子 section
- Child 仍可生成，但 `header_path` 变为：
  - `["无标题文档"]`
  - 或 `["无标题文档", "第 1-5 页"]`

## 12.4 标题层级跳变异常

例如从 `H1` 直接跳到 `H4`。

处理：

- 允许建节点
- 标记 `level_gap=true`
- 挂到最近合法父节点

不要因为层级异常而中断解析。

## 12.5 图片型文档为主，几乎无正文

策略：

- 每张图片块单独成 chunk
- 用 `caption + vlm_description` 作为主 embedding 文本
- 无相邻段落时允许上下文为空

## 12.6 极长表格且没有 HTML 只有截图

策略：

- `table_html_available=false`
- 直接使用多模态模型对截图做结构化总结
- 保留截图资产供最终 QA 透传

如果表格信息极其关键，可增加第二条摘要链：

- `table_summary_short`
- `table_summary_detailed`

## 12.7 极长代码块

策略：

- 默认整体保留
- 超过阈值再切分为多个 `atomic_fragment`
- 片段之间建立顺序链

## 12.8 Footnote 无法可靠归属

策略：

- 不强拼正文
- 标记为 orphan
- 仅在 Parent metadata 中透传

## 12.9 多模态富化失败

例如：

- 图片描述服务超时
- 表格摘要失败

策略：

- IR 基础层仍然有效
- Child chunk 退化为：
  - 图片：`header_path + caption + neighbor_context`
  - 表格：`header_path + caption + html_strip_text`

并在 metadata 中标记：

- `enrichment_status=partial_failed`

## 13. 质量信号与评估字段

建议在 `quality` 中记录：

```json
{
  "title_coverage": 0.92,
  "footnote_attach_rate": 0.67,
  "table_summary_coverage": 1.0,
  "image_vlm_coverage": 0.95,
  "ui_anchor_coverage": 1.0,
  "degraded_modes": []
}
```

这样后续你可以：

- 做离线评估
- 发现某些文档类型的解析短板
- 决定是否需要回退到人工检查或更重的多模态流程

## 14. 推荐的最终落地顺序

## 14.1 结构校验与业务校验必须分离

仅有 `Pydantic` 还不够，代码实现还必须区分两类校验：

第一类：结构校验

- 由 `Pydantic` 完成
- 负责字段、类型、嵌套结构、默认值、基础范围约束

第二类：业务校验

- 由自定义 `validators` 完成
- 负责跨对象一致性和语义约束

必须至少覆盖这些业务校验项：

- `block.section_id` 必须指向存在的 section
- `child.parent_chunk_id` 必须指向存在的 parent
- `header_path` 必须与所属 section 对齐
- `bbox_norm1000` 必须与 `page_idx` 合法对应
- `image` 块必须至少有 1 个图片资产
- `table` 块必须至少有 `html` 或 `table_image`
- `equation` 块必须有 `math_content`
- `page_header/page_footer/page_number` 不能进入正文文本切片
- `page_footnote` 若被附着，目标块必须与其页码一致，或有明确降级说明

### 14.2 失败策略

当 `Pydantic` 校验失败时：

- 原始输入层：若字段缺失或类型轻微异常，可记录 warning 并进入兼容降级逻辑
- 原始输入层：若出现未知字段，至少必须记录 warning，并保留原始字段内容
- IR / Chunk 层：默认应阻止脏数据继续写入最终产物

也就是说：

- 原始层可容错
- 标准层应早失败

补充原则：

- “可容错”不等于“可静默丢弃”
- 对未知字段必须可观测、可追踪、可复现
- 如果某个未知字段疑似影响后续语义理解，应允许切换到严格失败模式

建议按下面顺序实施，而不是一次把所有模块写满：

第一阶段：

- Zip 解析
- `content_list_v2.json` 标准化
- `layout.json` 坐标换算
- DOM 重建
- `document_ir.json`

第二阶段：

- Footnote 关联
- Parent/Child Chunking
- `parent_chunks.jsonl`
- `child_chunks.jsonl`

第三阶段：

- 图片 VLM 描述
- 表格摘要
- `document_ir_enriched.json`

第四阶段：

- 向量化
- 混合检索
- 前端 PDF 高亮联动

## 15. 结论

对于高级个人多模态知识库，本方案的关键不是“把 MinerU 输出读出来”，而是把它变成一套同时满足下面三件事的数据层：

1. 对结构敏感
2. 对多模态无损
3. 对前端高亮和最终 QA 可回溯

因此本方案的核心主线是：

> `content_list_v2.json` 重建文档树，`layout.json` 补足坐标锚点，多模态资产保留原图，Chunking 严守 section 边界，并用 Parent/Child 显式建模 Small-to-Big 检索。

下一轮如果你确认这份 Schema 与流程没有问题，就可以直接进入代码实现阶段，优先从以下 3 个模块开始：

1. `zip -> document_ir.json`
2. `document_ir.json -> parent_chunks / child_chunks`
3. `document_ir_enriched.json` 的多模态富化接口定义

## 16. 交付完成定义

如果由其他 AI 编程助手直接根据本文档开发，至少应交付并满足下面这些完成条件：

### 16.1 基础交付物

- 能读取 MinerU SaaS zip 包
- 能生成 `document_ir.json`
- 能生成 `parent_chunks.jsonl`
- 能生成 `child_chunks.jsonl`
- 所有核心对象均有 `Pydantic` 模型

### 16.2 行为完成条件

- 能基于 `content_list_v2.json` 重建 section tree
- 能为每个 main block 注入 `header_path`
- 能把 `page_header/page_footer/page_number` 转入 metadata
- 能基于 `layout.json.page_size` 计算 `bbox_page`
- 能为图片、表格、公式保留原始资产路径
- Child chunk 不跨 section 边界
- `list/code` 默认作为原子块保留
- Child 与 Parent 之间存在显式 ID 映射

### 16.3 失败与报错完成条件

- 原始层字段异常时，能给出清晰 warning 或降级日志
- 原始层出现未知字段时，必须有显式 warning，并能在日志或原始痕迹中看到字段名与原始内容
- IR / Chunk 层结构不合法时，必须阻止输出最终产物
- 不能把未通过校验的脏数据写入 `document_ir.json`、`parent_chunks.jsonl`、`child_chunks.jsonl`
