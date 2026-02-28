# Agent 人才搜索模块设计文档

> 版本：v0.4
> 日期：2024-02
> 状态：设计阶段
> 关联文档：[06-架构图.md](./06-架构图.md)

---

## 1. 概述

本文档描述面向 Agent 网络的人才库搜索模块设计，包括系统架构、模块划分、接口设计和能力规划。

### 1.1 设计目标

- 支持自然语言交互，而非仅关键词匹配
- 为 Agent 提供可组合的搜索能力（Skills）
- 支持对话式、渐进式的搜索体验
- 透明化搜索推理过程，增强用户信任
- **按需走层**：根据操作复杂度选择最短有效路径

### 1.2 核心原则

| 原则 | 说明 |
|------|------|
| **不用分数，用解释** | 不输出匹配度分数，用自然语言解释"为什么合适/不合适" |
| **支持对话** | 搜索是渐进式细化的过程，不是一次性查询 |
| **透明推理** | 让用户看到 Agent 的搜索逻辑和过程 |
| **主动澄清** | 条件模糊时主动询问，而非盲目猜测 |
| **优雅降级** | 结果为空时，建议放宽条件或替代方案 |
| **按需走层** | 简单操作直达数据层，复杂操作经过完整路径 |

---

## 2. 系统架构

### 2.1 模块划分

系统采用分层架构，但**不强制所有请求走完整路径**。根据操作复杂度，请求可以选择最短有效路径。

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户 / Agent                            │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                        ┌─────┴─────┐
                        │  路由决策  │
                        └─────┬─────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        │ Full Path           │ Service Path        │ Direct Path
        │ (复杂查询)          │ (业务操作)          │ (简单查询)
        ▼                     │                     │
┌───────────────────────────┐ │                     │
│    上下文层 (可选)         │ │                     │
│  ┌─────────┐ ┌─────────┐  │ │                     │
│  │Job Ctx  │ │Cand. KB │  │ │                     │
│  └─────────┘ └─────────┘  │ │                     │
└───────────┬───────────────┘ │                     │
            │                 │                     │
            ▼                 ▼                     │
┌───────────────────────────────────────┐          │
│         服务层 (可选)                  │          │
│  ┌────────┐ ┌────────┐ ┌────────┐    │          │
│  │Search  │ │Evaluate│ │Import  │    │          │
│  └────────┘ └────────┘ └────────┘    │          │
└───────────────────┬───────────────────┘          │
                    │                              │
                    ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      基础设施层 (必经)                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │PostgreSQL│  │  Redis   │  │AI Service│  │ Storage  │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 为什么职位上下文独立

| 考量 | 说明 |
|------|------|
| **生命周期不同** | 职位定义在搜索之前，可被多次搜索复用 |
| **避免重复计算** | 每次搜索都解析 JD 是浪费 |
| **多下游消费** | 搜索、评估、沟通都需要职位上下文 |
| **关注点分离** | 搜索模块专注"找人"，不应理解"什么是好 JD" |

### 2.3 两种上下文的对比

| 维度 | Job Context（职位上下文） | Candidate Knowledge Base（候选人知识库） |
|------|--------------------------|----------------------------------------|
| **本质** | 意图理解（想要什么） | 事实解读 + 知识积累 |
| **来源** | 用户输入（JD/口头描述） | 简历 + 系统生成 + 交互累积 |
| **生命周期** | 搜索期间存在 | 长期存在，持续增长 |
| **结构** | 单一结构 | 分层结构（缓存 + 数据库 + 内存） |
| **可重算** | 完全可重算 | 部分可重算，部分不可重算 |

### 2.4 路由策略：按需走层

不同操作需要不同的处理路径，系统根据操作复杂度自动选择最短有效路径。

#### 2.4.1 四种路由路径

| 路径 | 经过的层 | 适用场景 | 示例 |
|------|----------|----------|------|
| **Full Path** | 上下文→服务→基础设施 | 复杂自然语言查询 | "有大模型经验的产品经理" |
| **Semantic Path** | 上下文→基础设施 | 需要语义理解但无复杂业务逻辑 | 相似候选人搜索 |
| **Service Path** | 服务→基础设施 | 业务操作，不需要语义理解 | 批量导入、记录反馈 |
| **Direct Path** | 基础设施 | 简单查询 | "Python 北京"、获取详情 |

#### 2.4.2 路由决策逻辑

```
请求进入
    │
    ▼
需要语义理解？ ──是──▶ 需要业务逻辑？ ──是──▶ Full Path
    │                      │
    否                     否
    │                      │
    ▼                      ▼
需要业务逻辑？         Semantic Path
    │
  ┌─┴─┐
  是  否
  │   │
  ▼   ▼
Service  Direct
Path     Path
```

#### 2.4.3 路径选择矩阵

| 操作类型 | 路径 | 原因 |
|----------|------|------|
| 自然语言搜索 | Full | 需要意图解析 + 关键词扩展 + 排序 |
| 多轮对话搜索 | Full | 需要上下文累积 |
| 候选人评估 | Full | 需要职位上下文 + AI 分析 |
| 简单关键词搜索 | Direct | 关键词明确，直接匹配 |
| 精确字段查询 | Direct | 已是结构化条件 |
| 获取候选人详情 | Direct | 简单 ID 查询 |
| 批量导入简历 | Service | 需要业务逻辑，不需要搜索上下文 |
| 记录沟通反馈 | Service | 需要业务校验 |
| 语义相似搜索 | Semantic | 需要语义理解，不需要复杂业务逻辑 |

#### 2.4.4 为什么这样设计

| 设计决策 | 理由 |
|----------|------|
| **按需走层** | 避免简单操作的性能开销 |
| **路径可选** | 给 Agent 灵活性，不强制走固定流程 |
| **保留完整路径** | 复杂操作仍然需要完整的语义理解和业务逻辑 |
| **透明路由** | Agent 可以显式选择路径或让系统自动决策 |

### 2.5 工程挑战与解决方案

#### 2.5.1 挑战一：私有库加密 vs AI 语义处理的技术矛盾

**矛盾描述**：

```
PRD 要求：私有库加密密钥由用户端管理，服务端不存储
架构需求：AI Service 需要读取原始简历生成 Embedding 和画像

这两个需求在技术上是互斥的：
- 如果服务端没有密钥，LLM 如何读取简历？
- 如果客户端解密后传给服务端，带宽和延迟不可接受
- 如果服务端内存解密，就不是"不存储密钥"
```

**解决方案：放弃纯 E2EE，采用租户级隔离 + 运行时解密**

```
┌─────────────────────────────────────────────────────────────────┐
│                      安全模型重新设计                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  原方案（不可行）          修正方案（可行）                       │
│  ──────────────           ──────────────                        │
│  客户端持有密钥            KMS 服务持有主密钥                     │
│  服务端完全无法解密        服务端运行时解密，内存处理              │
│  E2EE 端到端加密          租户级隔离 + 传输加密 + 存储加密        │
│                                                                 │
│  安全保障：                                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. KMS 管理：AWS KMS / HashiCorp Vault                  │   │
│  │ 2. 租户隔离：每个猎头独立加密密钥（KEK）                   │   │
│  │ 3. 运行时解密：数据只在内存中明文存在，处理完即销毁         │   │
│  │ 4. 审计日志：所有解密操作记录，可追溯                      │   │
│  │ 5. 访问控制：AI Service 只能访问授权范围内的数据           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**数据处理流程**：

```
简历导入时：
  原文 → 服务端 → KMS 获取租户密钥 → 加密存储 → 生成 Embedding（内存中）
                                              → 生成 Profile（内存中）
                                              → 存储加密后的派生数据

搜索时：
  查询 → 获取候选人 ID → KMS 解密画像 → 内存中匹配 → 返回结果 → 清除内存
```

**必须明确告知用户**：

> ⚠️ 私有库数据会在服务端进行 AI 处理。我们通过 KMS 加密、租户隔离、
> 审计日志等措施保障安全，但这不是端到端加密。如需纯本地处理方案，
> 请联系我们讨论私有化部署。

#### 2.5.2 挑战二：Full Path 延迟过长导致的体验灾难

**问题描述**：

```
Full Path 串行调用链：
  1. 解析意图 (LLM)        ~2s
  2. 扩展关键词 (LLM)      ~2s
  3. 数据库查询            ~0.5s
  4. 批量获取画像          ~1s
  5. AI 排序筛选 (LLM)     ~3s
  6. 生成解释 (LLM)        ~2s
  ─────────────────────────────
  总计                     ~10-15s

用户体验：在飞书/前端干等 15 秒 = 系统"卡死了"
```

**解决方案：流式输出 + 中间状态透传 + 并行优化**

```typescript
// 1. 流式响应设计
interface StreamingSearchResponse {
  type: 'status' | 'partial_result' | 'final_result' | 'error'

  // 状态更新
  status?: {
    stage: 'parsing' | 'expanding' | 'searching' | 'ranking' | 'explaining'
    message: string      // "正在解析您的需求..."
    progress?: number    // 0-100
  }

  // 部分结果（边搜边返回）
  partial_result?: {
    candidates: Candidate[]
    is_ranked: boolean   // 是否已排序
    more_coming: boolean
  }

  // 最终结果
  final_result?: SearchResult
}
```

**交互时序优化**：

```
传统（串行，阻塞）：
用户  ──────────────────────────────────[等待 15s]──────────────────────► 收到结果

优化后（流式，非阻塞）：
用户  ──┬─► "正在解析需求..." (0.5s)
        ├─► "正在扩展关键词..." (2s)
        ├─► "找到 50 个初步匹配..." (3s) + 显示前 5 个未排序结果
        ├─► "正在智能排序..." (5s) + 逐个更新排序
        └─► "完成，共 12 个高匹配候选人" (7s)

用户感知：3 秒后就能看到内容，而不是干等 15 秒
```

**并行优化策略**：

```
原串行流程：
  解析意图 → 扩展关键词 → 查询 → 画像 → 排序 → 解释

优化后并行流程：
  ┌─ 解析意图 ─┐
  │            ├──► 查询（用初步条件）──► 返回初步结果
  └─ 扩展关键词 ┘                          │
       │                                   │
       └──────► 补充查询 ──────────────────┘
                    │
                    ▼
              并行处理：
              ├── 画像获取
              ├── AI 排序（可流式）
              └── 解释生成（可后置/异步）
```

**API 设计**：

```yaml
# 流式搜索接口
POST /api/v1/search/natural/stream
  输入：{ query: string, ... }
  输出：Server-Sent Events (SSE) 流

  事件流示例：
  event: status
  data: {"stage": "parsing", "message": "正在解析需求..."}

  event: status
  data: {"stage": "searching", "message": "正在搜索数据库..."}

  event: partial_result
  data: {"candidates": [...前5个], "is_ranked": false, "more_coming": true}

  event: partial_result
  data: {"candidates": [...更新排序后], "is_ranked": true, "more_coming": false}

  event: final_result
  data: {"candidates": [...], "search_process": [...], "reasoning": "..."}
```

#### 2.5.3 挑战三：CKB 层级数据冲突的处理机制

**冲突场景**：

```
Layer 1 (Source)：简历原文写"熟悉高并发系统"
Layer 2 (Profile)：AI 推断"具备高并发经验"，标签：[高并发, 分布式]
Layer 3 (Knowledge)：猎头面试备注"高并发是吹牛的，只有 CRUD 经验"

Agent 搜索"高并发工程师"时：
  - 如果听 Layer 2 → 会推荐这个人（错误）
  - 如果听 Layer 3 → 不会推荐（正确）

系统应该听谁的？
```

**解决方案：明确层级优先级 + 冲突标记 + 反馈校准机制**

```
┌─────────────────────────────────────────────────────────────────┐
│                      层级优先级规则                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   优先级（高 → 低）：                                            │
│                                                                 │
│   1. Layer 3 (Knowledge) - 人类显式修正                          │
│      │  猎头/HR 的面试反馈、人工标注                             │
│      │  权重：最高，可直接覆写 Layer 2 的标签                     │
│      │                                                          │
│   2. Layer 1 (Source) - 原始事实                                 │
│      │  简历原文、用户提交的信息                                  │
│      │  权重：高，是事实基础                                      │
│      │                                                          │
│   3. Layer 2 (Profile) - AI 推断                                 │
│      │  机器生成的标签、推断的特质                                │
│      │  权重：最低，可被 Layer 3 覆写                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**数据结构扩展**：

```typescript
interface CandidateProfile {
  // ... 原有字段 ...

  // 新增：标签置信度与来源
  skills_with_confidence: Array<{
    skill: string
    confidence: 'high' | 'medium' | 'low'
    source: 'resume' | 'ai_inferred' | 'human_verified' | 'human_denied'

    // 如果被人工修正
    correction?: {
      corrected_by: string
      corrected_at: string
      original_value: string
      reason: string
    }
  }>

  // 新增：冲突标记
  conflicts: Array<{
    field: string
    layer2_value: string
    layer3_value: string
    resolution: 'layer3_wins' | 'pending_review'
  }>
}
```

**搜索时的处理逻辑**：

```python
def should_match_skill(candidate, required_skill):
    skill_entry = find_skill(candidate.skills_with_confidence, required_skill)

    if skill_entry is None:
        return False

    # Layer 3 人工否定 → 直接排除
    if skill_entry.source == 'human_denied':
        return False

    # Layer 3 人工确认 → 优先匹配
    if skill_entry.source == 'human_verified':
        return True, boost=1.5  # 加权

    # Layer 1 简历原文 → 正常匹配
    if skill_entry.source == 'resume':
        return True, boost=1.0

    # Layer 2 AI 推断 → 匹配但降权
    if skill_entry.source == 'ai_inferred':
        if skill_entry.confidence == 'high':
            return True, boost=0.8
        else:
            return True, boost=0.5
```

**反馈校准机制**：

```
猎头标记"候选人 X 的高并发经验是假的"
    │
    ▼
系统自动处理：
    1. 在 Layer 3 记录反馈
    2. 将 skills_with_confidence 中 "高并发" 的 source 改为 'human_denied'
    3. 标记冲突：layer2_value="高并发经验" vs layer3_value="无真实经验"
    4. 下次搜索时，该候选人不会因"高并发"被召回
    5. （可选）触发 Layer 2 重新生成画像，移除该标签
```

**UI 透出冲突信息**：

```
搜索结果卡片：
┌─────────────────────────────────────────────────┐
│ 张三 - 后端工程师 @ 某公司                        │
│                                                 │
│ 技能：Java ✓  分布式 ✓  高并发 ⚠️               │
│                        └─ "面试反馈：经验存疑"    │
│                                                 │
│ [查看详情] [对比] [联系]                         │
└─────────────────────────────────────────────────┘
```

### 3.1 职责

- 解析 JD 文本，提取结构化要求
- 理解口头描述，构建职位画像
- 推理隐含条件（如"带团队"→需要管理经验）
- 生成搜索提示词和评估维度

### 3.2 数据结构

```typescript
interface JobContext {
  // 基础信息
  id: string
  title: string                    // 职位名称
  level?: string                   // 职级 P6/P7/总监
  team_size?: string               // 团队规模

  // 硬性要求（必须满足）
  must_have: {
    skills?: string[]              // 必备技能
    experience_years?: {           // 经验年限
      min?: number
      max?: number
    }
    education?: string             // 学历要求
    certifications?: string[]      // 必要证书
    management_experience?: boolean // 是否需要管理经验
  }

  // 软性要求（加分项）
  nice_to_have: {
    skills?: string[]              // 加分技能
    background?: string[]          // 加分背景（大厂、创业等）
    traits?: string[]              // 软素质
  }

  // 约束条件
  constraints: {
    locations?: string[]           // 工作地点
    salary_range?: {
      min?: number
      max?: number
    }
    availability?: string          // 到岗时间要求
  }

  // 搜索优化（供搜索模块使用）
  search_hints: {
    expanded_keywords: string[]    // 扩展关键词
    related_titles: string[]       // 相关职位名称
    related_domains: string[]      // 相关领域
  }

  // 评估维度（供评估模块使用）
  evaluation_criteria: Array<{
    dimension: string              // 评估维度
    weight: 'high' | 'medium' | 'low'
    description?: string
  }>
}
```

### 3.3 接口设计

```
POST /api/v1/jobs/parse
  描述：解析 JD 文本，返回结构化 JobContext
  输入：{ jd_text: string }
  输出：JobContext

POST /api/v1/jobs/from-description
  描述：从口头描述构建 JobContext
  输入：{ description: string }
  输出：JobContext

GET /api/v1/jobs/{id}/context
  描述：获取已保存的职位上下文
  输出：JobContext

PUT /api/v1/jobs/{id}/refine
  描述：补充或修正职位上下文
  输入：{ updates: Partial<JobContext> }
  输出：JobContext
```

---

## 4. 候选人知识库 (Candidate Knowledge Base)

候选人知识库是一个分层的存储系统，包含缓存、持久存储和临时状态三种性质的数据。

### 4.1 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: Source of Truth（源数据层）                            │
│  ─────────────────────────────────────────────────────────────  │
│  内容：原始简历文件、导入时的元信息、用户手动修正的信息             │
│  特点：不可变 / 只有用户能改 / 是"真相"                           │
│  存储：数据库（永久）                                            │
│  示例：resume.pdf, 手机号修正, 入库时间                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: Derived Profile（派生画像层）                          │
│  ─────────────────────────────────────────────────────────────  │
│  内容：AI 解析的结构化信息、推断的特质、职业轨迹分析、亮点/风险    │
│  特点：可重新生成 / 是"缓存" / 加速后续使用                        │
│  存储：数据库 + 缓存（可失效重算）                                │
│  示例：技术深度=deep, 职业轨迹=climbing, 亮点=["大厂背景"]        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: Accumulated Knowledge（累积知识层）                    │
│  ─────────────────────────────────────────────────────────────  │
│  内容：面试反馈、沟通记录、状态变更、猎头备注、历史匹配职位         │
│  特点：随时间增长 / 不可重新生成 / 是"记忆"                        │
│  存储：数据库（永久）                                            │
│  示例：面试反馈="技术扎实但沟通一般", 状态=已面试                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4: Session Context（会话上下文层）                        │
│  ─────────────────────────────────────────────────────────────  │
│  内容：当前搜索中的相关性、与当前职位的匹配分析、临时评估笔记       │
│  特点：临时 / 会话结束即丢弃（或选择性保存到 Layer 3）             │
│  存储：内存 / Redis / Session Store                             │
│  示例：本次搜索匹配原因="技能匹配+地点合适"                        │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 各层特性对比

| 层级 | 类型 | 生命周期 | 能否重算 | 存储方式 |
|------|------|---------|---------|---------|
| Source | 数据库 | 永久 | 不适用（是源头） | PostgreSQL/MySQL |
| Derived | 缓存 | 长期但可失效 | ✅ 可以 | DB + Redis |
| Accumulated | 数据库 | 永久 | ❌ 不可以 | PostgreSQL/MySQL |
| Session | 内存 | 短期 | 不需要 | Redis/Memory |

### 4.3 数据结构

#### 4.3.1 源数据 (Source Data)

```typescript
interface CandidateSource {
  id: number

  // 原始文件
  resume_file_path?: string       // 简历文件路径
  resume_raw_text?: string        // 简历原始文本

  // 基础信息（可能用户修正过）
  name: string
  phone?: string
  email?: string

  // 元数据
  imported_by: string             // 谁导入的
  import_source: string           // 来源渠道（Boss直聘/猎聘/内推）
  created_at: string
  updated_at: string
}
```

#### 4.3.2 派生画像 (Derived Profile)

```typescript
interface CandidateProfile {
  id: number
  candidate_id: number            // 关联源数据

  // ===== 结构化解析（从简历提取）=====
  parsed: {
    current_title?: string
    current_company?: string
    years_of_experience?: number
    location?: string
    skills: string[]
    education?: {
      degree: string
      school: string
      major?: string
    }
    work_history: Array<{
      company: string
      title: string
      duration: string
      highlights?: string[]
    }>
  }

  // ===== AI 推断的特质 =====
  inferred_traits: {
    // 技术特征
    technical_depth: 'deep' | 'broad' | 'balanced'
    technical_domains: string[]   // ["后端", "分布式", "大数据"]

    // 职业特征
    career_trajectory: 'climbing' | 'stable' | 'pivoting' | 'unclear'
    career_stage: 'junior' | 'mid' | 'senior' | 'lead' | 'executive'

    // 工作风格（推断）
    work_style?: string[]         // ["独立工作", "跨团队协作", "带团队"]

    // 行业经验
    industry_experience: string[] // ["电商", "金融", "ToB SaaS"]
    company_tiers: string[]       // ["大厂", "独角兽", "创业公司"]
  }

  // ===== 亮点和风险 =====
  highlights: string[]            // ["大厂背景", "从0到1经验", "开源贡献者"]
  potential_concerns: string[]    // ["跳槽频繁", "薪资期望较高", "经验较浅"]

  // ===== 一句话总结 =====
  one_liner: string               // "5年后端开发，字节跳动背景，擅长高并发系统"

  // ===== 搜索优化 =====
  search_keywords: string[]       // 用于搜索匹配的关键词集合

  // ===== 元数据 =====
  profile_version: number         // 画像版本，用于判断是否需要重新生成
  generated_at: string
  model_version: string           // 生成画像的 AI 模型版本
}
```

#### 4.3.3 累积知识 (Accumulated Knowledge)

```typescript
interface CandidateKnowledge {
  candidate_id: number

  // ===== 状态追踪 =====
  status: 'new' | 'contacted' | 'interviewing' | 'offered' | 'hired' | 'rejected' | 'withdrawn'
  status_history: Array<{
    status: string
    changed_at: string
    changed_by: string
    job_context_id?: string       // 关联哪个职位
    notes?: string
  }>

  // ===== 沟通记录 =====
  contact_history: Array<{
    type: 'email' | 'phone' | 'wechat' | 'other'
    direction: 'outbound' | 'inbound'
    timestamp: string
    by: string                    // 哪个猎头
    summary?: string              // 沟通摘要
    outcome?: string              // 结果
  }>

  // ===== 面试反馈 =====
  interview_feedback: Array<{
    job_context_id: string
    round: string                 // "一面/二面/HR面"
    interviewer?: string
    timestamp: string

    // 结构化反馈
    ratings?: {
      technical?: 'strong' | 'adequate' | 'weak'
      communication?: 'strong' | 'adequate' | 'weak'
      culture_fit?: 'strong' | 'adequate' | 'weak'
    }

    // 自由文本反馈
    strengths?: string[]
    concerns?: string[]
    recommendation: 'strong_yes' | 'yes' | 'maybe' | 'no' | 'strong_no'
    notes?: string
  }>

  // ===== 猎头备注 =====
  recruiter_notes: Array<{
    by: string
    timestamp: string
    note: string
    tags?: string[]               // ["高潜力", "需要跟进", "薪资敏感"]
  }>

  // ===== 历史匹配 =====
  job_matches: Array<{
    job_context_id: string
    job_title: string
    matched_at: string
    outcome?: 'hired' | 'rejected' | 'withdrawn' | 'no_response'
    notes?: string
  }>
}
```

#### 4.3.4 会话上下文 (Session Context)

```typescript
interface CandidateSessionContext {
  session_id: string
  candidate_id: number
  job_context_id?: string         // 当前关联的职位

  // ===== 当前搜索相关性 =====
  search_relevance?: {
    matched_keywords: string[]
    match_explanation: string     // 为什么出现在搜索结果中
  }

  // ===== 当前职位匹配分析 =====
  job_fit_analysis?: {
    strengths: string[]           // 与职位匹配的点
    gaps: string[]                // 与职位不匹配的点
    overall_assessment: string    // 整体评价
  }

  // ===== 对比上下文 =====
  comparison_context?: {
    compared_with: number[]       // 对比的其他候选人 ID
    relative_strengths: string[]  // 相对优势
    relative_weaknesses: string[] // 相对劣势
  }

  // ===== 临时笔记 =====
  session_notes?: string[]

  // ===== 元数据 =====
  created_at: string
  expires_at: string              // 会话过期时间
}
```

### 4.4 接口设计

#### 4.4.1 画像管理

```
POST /api/v1/candidates/{id}/profile/generate
  描述：生成或更新候选人画像
  触发场景：导入简历时自动调用，或简历更新后手动刷新
  输入：{ force_regenerate?: boolean }
  输出：CandidateProfile

GET /api/v1/candidates/{id}/profile
  描述：获取候选人完整画像
  输出：CandidateProfile

GET /api/v1/candidates/{id}/profile/summary
  描述：获取简短摘要（用于列表展示）
  输出：{
    one_liner: string,
    highlights: string[],
    career_stage: string
  }

POST /api/v1/candidates/batch-profile
  描述：批量获取画像（用于搜索结果）
  输入：{ candidate_ids: number[] }
  输出：{ profiles: CandidateProfile[] }
```

#### 4.4.2 知识管理

```
GET /api/v1/candidates/{id}/knowledge
  描述：获取候选人累积知识
  输出：CandidateKnowledge

POST /api/v1/candidates/{id}/knowledge/status
  描述：更新候选人状态
  输入：{
    status: string,
    job_context_id?: string,
    notes?: string
  }

POST /api/v1/candidates/{id}/knowledge/contact
  描述：记录沟通
  输入：{
    type: string,
    direction: string,
    summary?: string,
    outcome?: string
  }

POST /api/v1/candidates/{id}/knowledge/feedback
  描述：记录面试反馈
  输入：InterviewFeedback

POST /api/v1/candidates/{id}/knowledge/note
  描述：添加备注
  输入：{
    note: string,
    tags?: string[]
  }
```

#### 4.4.3 会话上下文

```
POST /api/v1/candidates/{id}/session-context
  描述：创建或更新会话上下文
  输入：{
    session_id: string,
    job_context_id?: string,
    search_relevance?: object,
    job_fit_analysis?: object
  }
  输出：CandidateSessionContext

GET /api/v1/candidates/{id}/session-context/{session_id}
  描述：获取会话上下文
  输出：CandidateSessionContext

POST /api/v1/candidates/{id}/session-context/{session_id}/save
  描述：将会话中的内容保存为永久知识
  输入：{
    save_fit_analysis?: boolean,   // 保存匹配分析为备注
    save_notes?: boolean           // 保存临时笔记
  }
```

### 4.5 使用场景

#### 场景 1: 简历导入

```
1. 用户上传简历
2. 系统保存源数据 (Layer 1)
3. 自动触发画像生成 (Layer 2)
4. 初始化累积知识，状态=new (Layer 3)
```

#### 场景 2: 搜索候选人

```
1. 搜索模块查询候选人
2. 从 Layer 2 获取 search_keywords 进行匹配
3. 命中后，创建 Session Context (Layer 4)
4. 记录搜索相关性和匹配原因
```

#### 场景 3: 评估候选人

```
1. 评估模块接收候选人 ID + 职位上下文
2. 从 Layer 2 获取画像信息
3. 从 Layer 3 获取历史反馈（如有）
4. 生成评估结果，存入 Session Context (Layer 4)
5. 用户确认后，可选保存到 Layer 3
```

#### 场景 4: 面试完成

```
1. 面试官提交反馈
2. 系统将反馈存入 Layer 3 (interview_feedback)
3. 更新候选人状态
4. 如果反馈影响对候选人的理解，可触发 Layer 2 重新生成
```

### 4.6 缓存策略

| 数据 | 缓存时间 | 失效条件 |
|------|---------|---------|
| Derived Profile | 7天 | 源数据更新 / 手动刷新 / AI模型升级 |
| Session Context | 会话期间 | 会话结束 / 超时（默认2小时） |
| Knowledge | 不缓存 | 直接读数据库 |

### 4.7 与其他模块的关系

```
┌─────────────────────────────────────────────────────────────────┐
│                  Candidate Knowledge Base                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│   │   Source    │  │   Profile   │  │  Knowledge  │            │
│   │   (DB)      │  │   (Cache)   │  │   (DB)      │            │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘            │
│          │                │                │                   │
└──────────┼────────────────┼────────────────┼───────────────────┘
           │                │                │
           ▼                ▼                ▼
     ┌──────────┐     ┌──────────┐     ┌──────────┐
     │  Import  │     │  Search  │     │ Evaluate │
     │  Module  │     │  Module  │     │  Module  │
     └──────────┘     └──────────┘     └──────────┘
                            │
                            ▼
                      ┌──────────┐
                      │ Session  │
                      │ Context  │
                      └──────────┘
```

---

## 5. 搜索模块 (Search Module)

### 5.1 职责

- 根据 JobContext 或自然语言执行搜索
- 支持多轮、渐进式筛选
- 透明化搜索过程和推理逻辑
- 提供相似候选人搜索

### 5.2 搜索场景

| 场景 | 用户意图 | 示例 |
|------|---------|------|
| **精确搜索** | 明确知道要什么 | "北京，5年Python，30万以内" |
| **模糊探索** | 不确定要什么 | "我们组缺人，看看有什么合适的" |
| **相似搜索** | 找类似的人 | "这个人不错，有没有类似的" |
| **条件细化** | 逐步筛选 | "刚才那些人里，有没有大厂背景的" |

### 5.3 Agent Skills 设计

#### 5.3.1 核心搜索能力

```yaml
search_candidates:
  description: 搜索候选人
  input:
    - query: string              # 自然语言查询
    - job_context?: JobContext   # 可选，职位上下文
    - filters?: SearchFilters    # 可选，结构化筛选条件
  output:
    - candidates: Candidate[]    # 候选人列表
    - search_process: SearchStep[] # 搜索过程说明
    - suggestions?: string[]     # 搜索建议
  behavior:
    - 理解用户意图，不仅是关键词匹配
    - 推理泛化（产品经理 → PM, Product Manager...）
    - 多维度搜索（技能、经历、公司、项目）
    - 解释搜索逻辑

find_similar:
  description: 找相似候选人
  input:
    - candidate_id: number       # 参考候选人
    - aspects?: string[]         # 哪些方面相似（技能/经历/背景）
  output:
    - candidates: Candidate[]
    - similarity_explanation: string

browse_candidates:
  description: 浏览式探索
  input:
    - rough_filters?: object     # 粗筛条件
    - page?: number
    - page_size?: number
  output:
    - candidates: Candidate[]
    - total: number
```

#### 5.3.2 筛选能力

```yaml
refine_results:
  description: 在已有结果中继续筛选
  input:
    - session_id: string         # 上一轮搜索的 session
    - additional_criteria: string # 新增条件（自然语言）
  output:
    - candidates: Candidate[]
    - refinement_explanation: string
  example: "刚才那些人里，有没有在北京的"

exclude_candidates:
  description: 排除特定条件
  input:
    - session_id: string
    - exclusion_criteria: string
  output:
    - candidates: Candidate[]
  example: "排除掉期望薪资超过50万的"
```

#### 5.3.3 交互能力

```yaml
clarify_requirements:
  description: 当条件模糊时，主动询问
  trigger: 搜索条件不明确
  behavior:
    - 识别模糊点
    - 生成澄清问题
    - 提供选项供用户选择
  example:
    用户: "找个技术好的"
    Agent: "技术好具体指什么？后端/前端/算法？有特定技术栈要求吗？"

suggest_alternatives:
  description: 当结果不理想时，建议替代方案
  trigger: 结果为空或数量过少
  behavior:
    - 分析为什么没结果
    - 建议放宽的条件
    - 提供替代搜索方案
  example: "北京没有符合条件的，上海有3个类似的，要看吗？"

explain_reasoning:
  description: 解释搜索/推荐逻辑
  input:
    - candidate_id?: number      # 解释为什么推荐这个人
    - search_decision?: string   # 解释搜索决策
  output:
    - explanation: string
```

### 5.4 接口设计

根据路由策略，搜索模块提供不同路径的接口：

#### 5.4.1 Full Path 接口（自然语言搜索）

```
POST /api/v1/search/natural
  路径：Full Path (上下文→服务→基础设施)
  描述：自然语言搜索，经过完整的语义理解和业务处理
  输入：{
    query: string,
    job_context_id?: string,     // 关联职位上下文
    session_id?: string          // 继续上一轮搜索
  }
  输出：{
    session_id: string,
    candidates: Candidate[],
    search_process: SearchStep[],  // 搜索过程
    reasoning: string,             // 推理说明
    suggestions?: string[]         // 建议
  }

POST /api/v1/search/refine
  路径：Full Path
  描述：继续筛选（需要上下文累积）
  输入：{
    session_id: string,
    criteria: string              // 新增条件
  }
  输出：同上
```

#### 5.4.2 Direct Path 接口（简单搜索）

```
POST /api/v1/search/keywords
  路径：Direct Path (直达基础设施)
  描述：简单关键词搜索，不经过语义解析
  输入：{
    keywords: string[],           // 关键词列表
    filters?: {                   // 结构化筛选条件
      cities?: string[],
      min_experience?: number,
      max_experience?: number,
      min_salary?: number,
      max_salary?: number,
      skills?: string[]
    },
    page?: number,
    page_size?: number
  }
  输出：{
    candidates: Candidate[],
    total: number
  }

GET /api/v1/candidates/{id}
  路径：Direct Path
  描述：获取候选人详情
  输出：Candidate
```

#### 5.4.3 Semantic Path 接口（语义搜索）

```
POST /api/v1/search/similar/{candidate_id}
  路径：Semantic Path (上下文→基础设施)
  描述：找相似候选人，需要语义理解但不需要复杂业务逻辑
  输入：{
    aspects?: string[]            // 哪些方面相似
  }
  输出：{
    candidates: Candidate[],
    explanation: string
  }
```

#### 5.4.4 路径选择参数

所有搜索接口都支持显式指定路径：

```
POST /api/v1/search/natural
{
  "query": "Python 北京",
  "routing": {
    "path": "direct",            // 显式指定使用 Direct Path
    "reason": "关键词明确，无需语义解析"
  }
}
```

| routing.path | 说明 |
|--------------|------|
| `auto` | 系统自动决策（默认） |
| `full` | 强制走完整路径 |
| `direct` | 强制直达数据层 |
| `semantic` | 只走语义层 |
| `service` | 只走服务层 |

### 5.5 搜索过程透明化

```typescript
interface SearchStep {
  step_number: number
  action: string                  // "扩展关键词" | "执行搜索" | "筛选结果"
  detail: string                  // 具体做了什么
  result_count?: number           // 这一步找到多少人
}

// 示例
{
  "search_process": [
    { "step_number": 1, "action": "理解意图", "detail": "用户想找有大模型经验的产品经理" },
    { "step_number": 2, "action": "扩展关键词", "detail": "产品经理 → PM, Product Manager, 产品设计" },
    { "step_number": 3, "action": "扩展关键词", "detail": "大模型 → LLM, GPT, AIGC, 生成式AI" },
    { "step_number": 4, "action": "执行搜索", "detail": "搜索 [产品经理, PM, 大模型, LLM]", "result_count": 5 },
    { "step_number": 5, "action": "执行搜索", "detail": "搜索 [AI产品, AIGC产品]", "result_count": 3 },
    { "step_number": 6, "action": "合并去重", "detail": "合并结果，去除重复", "result_count": 7 }
  ]
}
```

---

## 6. 评估模块 (Evaluation Module)

### 6.1 职责

- 对比候选人与职位要求
- 分析候选人的优势和 Gap
- 多候选人横向对比

### 6.2 Agent Skills 设计

```yaml
analyze_candidate:
  description: 深度分析单个候选人
  input:
    - candidate_id: number
    - job_context_id?: string    # 可选，结合职位分析
  output:
    - highlights: string[]       # 亮点
    - concerns: string[]         # 潜在问题
    - fit_analysis?: string      # 与职位的匹配分析（如有职位上下文）

compare_candidates:
  description: 对比多个候选人
  input:
    - candidate_ids: number[]
    - dimensions?: string[]      # 对比维度
    - job_context_id?: string
  output:
    - comparison_table: object   # 对比表格
    - analysis: string           # 分析结论
    - recommendation?: string    # 推荐意见

match_to_job:
  description: 评估候选人与职位的匹配
  input:
    - candidate_id: number
    - job_context_id: string
  output:
    - fit_summary: string        # 匹配总结（不是分数）
    - strengths: string[]        # 匹配的点
    - gaps: string[]             # 不匹配的点
    - overall_assessment: string # 整体评价
```

### 6.3 接口设计

```
POST /api/v1/evaluate/analyze/{candidate_id}
  描述：分析单个候选人
  输入：{ job_context_id?: string }
  输出：CandidateAnalysis

POST /api/v1/evaluate/compare
  描述：对比多个候选人
  输入：{
    candidate_ids: number[],
    job_context_id?: string,
    dimensions?: string[]
  }
  输出：ComparisonResult

POST /api/v1/evaluate/match
  描述：评估匹配度
  输入：{
    candidate_id: number,
    job_context_id: string
  }
  输出：MatchAnalysis
```

---

## 7. 数据模型

### 7.1 候选人 (Candidate)

```typescript
interface Candidate {
  id: number
  name: string
  phone?: string
  email?: string

  // 当前状态
  current_company?: string
  current_title?: string
  city?: string

  // 经验和薪资
  years_of_experience?: number
  expected_salary?: number

  // 技能和背景
  skills?: string[]
  education?: string
  certifications?: string[]

  // 简介
  summary?: string
  highlights?: string[]

  // 元数据
  imported_by?: string           // 谁导入的
  source?: string                // 来源渠道
  created_at: string
  updated_at: string
}
```

### 7.2 搜索会话 (Search Session)

```typescript
interface SearchSession {
  id: string
  job_context_id?: string        // 关联的职位

  // 搜索历史
  queries: Array<{
    query: string
    timestamp: string
    result_count: number
  }>

  // 当前状态
  current_filters: object
  current_results: number[]      // 候选人 ID 列表

  // 上下文
  created_at: string
  updated_at: string
}
```

---

## 8. 给人用 vs 给 Agent 用

| 维度 | 给人用 | 给 Agent 用 |
|------|-------|------------|
| **输入** | 自然语言为主 | 结构化 + 自然语言 |
| **输出** | 可视化 + 解释性文字 | JSON + 元数据 |
| **交互** | 支持追问和反馈 | 支持工具调用链 |
| **记忆** | Session 级别 | 可持久化偏好 |
| **确认** | 重要操作需确认 | 可配置自主执行 |
| **错误处理** | 友好提示 | 结构化错误码 |
| **路由选择** | 系统自动决策 | 可显式指定路径 |
| **性能优化** | 默认完整路径 | 可选择 Direct Path |

---

## 9. 未来扩展

### 9.1 短期

- [ ] 实现基础搜索 Skills
- [ ] 实现职位上下文解析
- [ ] 搜索过程可视化

### 9.2 中期

- [ ] 多轮对话支持
- [ ] 搜索偏好学习
- [ ] 候选人推荐

### 9.3 长期

- [ ] 跨人才库联合搜索
- [ ] 基于历史招聘的智能推荐
- [ ] 候选人画像自动更新

---

## 附录

### A. 搜索关键词扩展示例

| 原始词 | 扩展词 |
|--------|--------|
| 产品经理 | PM, Product Manager, 产品设计, 产品运营, 产品负责人 |
| 后端开发 | Backend, 服务端, Java开发, Go开发, 后端工程师 |
| 大模型 | LLM, GPT, AIGC, 生成式AI, 大语言模型, NLP |
| 带团队 | 技术管理, Tech Lead, 团队负责人, 管理经验 |

### B. 评估维度参考

| 维度 | 说明 |
|------|------|
| 技术匹配度 | 技能栈是否符合要求 |
| 经验匹配度 | 年限和相关经验 |
| 背景匹配度 | 公司背景、行业经验 |
| 成长潜力 | 学习能力、发展轨迹 |
| 稳定性 | 跳槽频率、求职动机 |
| 薪资匹配度 | 期望薪资与预算 |

### C. 版本历史

| 版本 | 日期 | 变更说明 |
|------|------|----------|
| v0.1 | 2024-02 | 初始版本 |
| v0.2 | 2024-02 | 增加候选人知识库四层架构 |
| v0.3 | 2024-02 | 增加"按需走层"路由策略，更新接口设计 |
| v0.4 | 2024-02 | 新增 Section 2.5 工程挑战与解决方案：加密方案、延迟优化、层级冲突处理 |
