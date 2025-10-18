# FAA Scope驱动架构 - 方案B4实现总结

> **核心理念**：默认全家范围，AI决定scope，零硬编码

## 🎯 设计原则

### 之前的问题
- ❌ 硬编码类型列表（`FAMILY_SHARED_TYPES`, `GLOBAL_DATA_TYPES`）
- ❌ 工程层预设业务逻辑（哪些是家庭数据，哪些是个人数据）
- ❌ 硬编码人称映射（"儿子" → son, "妻子" → mother）
- ❌ 新增成员或数据类型需要改代码

### 新方案
- ✅ AI识别scope（family | thread | personal）
- ✅ AI解析人称为具体名字（"儿子" → "Jack"）
- ✅ 默认全家范围，明确指定才按人过滤
- ✅ 完全数据驱动，零硬编码

---

## 🏗️ 架构设计

### scope三种类型

#### 1. family（默认，90%的情况）
**特征**：
- 查询所有家庭成员的数据
- 包括family_default（家庭共享配置）
- 不限制thread_id（跨对话线程）

**user_id处理**：
```python
user_id = ['family_default', 'dad', 'mom', 'daughter_1', ...]
```

**示例问题**：
- "本月预算是多少" ✅
- "这个月花了多少钱" ✅
- "今年有什么计划" ✅
- "孩子们的身高变化" ✅

#### 2. personal（明确指定某人）
**特征**：
- 只查询特定成员的数据
- 必须配合person或person_key字段
- 不限制thread_id

**user_id处理**：
```python
# AI输出：person_key="son_1" 或 person="Jack"
user_id = resolve_person_to_user_id(person_or_key)
# 结果：单个user_id
```

**示例问题**：
- "我这个月的花费" → person="我"
- "Jack的身高记录" → person="Jack"
- "儿子的花费" → AI解析为 person_key="son_1"

#### 3. thread（罕见，上下文引用）
**特征**：
- 仅限当前对话线程
- 当前用户 + thread_id过滤
- 用于上下文回溯

**user_id处理**：
```python
user_id = current_user_id
filters['thread_id'] = thread_id
```

**示例问题**：
- "刚才说的那个金额"
- "你刚提到的预算"

---

## 💻 实现细节

### 1. AI引擎层（src/ai_engine.py）

#### person解析函数（极简，无硬编码）
```python:494:547:src/ai_engine.py
def _resolve_person_to_user_id(
    self,
    person_or_key: str,
    current_user_id: str,
    household_context: Dict[str, Any]
) -> Optional[str]:
    """极简查找：只负责从household中匹配，不做任何映射"""
    
    # 1. 特殊情况："我" → 当前用户
    if person_or_key in ['我', '我的']:
        return current_user_id
    
    # 2. 匹配member_key
    members_index = household_context.get('members_index', {})
    if person_or_key in members_index:
        user_ids = members_index[person_or_key].get('user_ids', [])
        return user_ids[0] if user_ids else None
    
    # 3. 匹配display_name
    for member in household_context.get('members', []):
        if member.get('display_name', '').lower() == person_or_key.lower():
            user_ids = member.get('user_ids', [])
            return user_ids[0] if user_ids else None
    
    return None  # AI应该输出更明确的标识
```

**关键**：
- 只有"我"是硬编码（无法从household推断）
- 其他全部从household context查找
- 找不到返回None并记录warning

#### scope驱动的user_id处理
```python:684:756:src/ai_engine.py
# 从AI的understanding中获取scope和person
scope = understanding.get('entities', {}).get('scope', 'family')
person = understanding.get('entities', {}).get('person')

if scope == 'family':
    # 默认：所有家庭user_ids，不限thread_id
    args['user_id'] = all_family_user_ids
    
elif scope == 'thread':
    # 线程：当前用户 + thread_id
    args['user_id'] = user_id
    args['filters']['thread_id'] = thread_id
    
elif scope == 'personal':
    # 个人：解析person为user_id
    person_key = understanding.get('entities', {}).get('person_key')
    person_identifier = person_key if person_key else person
    args['user_id'] = _resolve_person_to_user_id(person_identifier, ...)
```

### 2. MCP层（mcp-server/generic_mcp_server.py）

#### 支持多user_id查询
```python:143:157:mcp-server/generic_mcp_server.py
if isinstance(user_id, list):
    # 多用户查询
    user_ids = [self._normalize_user_id(uid) for uid in user_id]
    multi_user_mode = True
else:
    # 单用户查询
    uid = self._normalize_user_id(user_id)
    user_ids = [uid]
    multi_user_mode = False

# SQL查询
WHERE user_id = ANY($1::uuid[])
params = [user_ids]
```

### 3. Prompt层（prompts/family_assistant_prompts.yaml）

#### scope识别指南
```yaml:659:760:prompts/family_assistant_prompts.yaml
scope_identification_guide: |
  ### 核心原则
  默认 = 家庭全局范围（family）
  
  ### scope="family"（默认，90%）
  - "这个月花了多少钱？" → family
  - "本月预算是？" → family
  - "孩子们的身高变化" → family（多人）
  
  ### scope="personal"（明确指定）
  - "我这个月的花费" → personal, person="我"
  - "儿子的身高曲线" → personal, person_key="son_1"
  
  ### scope="thread"（罕见）
  - "刚才说的那个金额" → thread
```

#### person识别（AI的职责）
```yaml
AI负责将人称代词解析为具体的成员名字或member_key

识别步骤：
1. 从household context获取成员信息
2. 解析人称：
   - "儿子" → 查找relationship="son" → person_key="son_1"
   - "大女儿" → person_key="daughter_1" 或 person="Hannah"
   - "Peter" → person="Peter"
   - "我" → person="我"（引擎处理）

输出优先级：
- 首选：person_key="son_1"（最准确）
- 备选：person="Jack"（display_name）
- 兜底：person="我"

不应该出现：
- ❌ person="儿子"（应解析为具体名字）
- ❌ person="孩子"（模糊，应澄清）
```

---

## 📊 测试结果

### 测试1：所有家庭成员都能查到预算
```bash
# dad查询
curl -X POST http://localhost:8001/message \
  -d '{"content": "本月预算", "user_id": "dad"}'
✅ 返回：11,500元

# mom查询（相同数据）
curl -X POST http://localhost:8001/message \
  -d '{"content": "本月预算", "user_id": "mom"}'
✅ 返回：11,500元

# daughter_1查询（相同数据）
curl -X POST http://localhost:8001/message \
  -d '{"content": "本月预算", "user_id": "daughter_1"}'
✅ 返回：11,500元
```

### 测试2：默认全家范围
```bash
# 查询时使用全家user_ids
user_id = [
  '9715cb3e-9d7c-5bbd-b811-2a681a5a033d',  # family_default
  'b8e6969e-e626-5bca-a027-b0aa1d28adf4',  # dad
  'd772a402-ebc6-52f1-a378-a95ae740b4dd',  # mom
  'f51a9aab-6f45-5e12-9dd7-91f71b1f32fb'   # daughter_1
]
```

---

## 🔄 数据流

### 用户问："本月预算是多少"

```
1. AI分析
   └→ scope=family（默认，没有人称代词）
   └→ person=null

2. 引擎处理
   └→ scope=family → user_id=[family_default, dad, mom, ...]
   └→ 不添加thread_id

3. MCP查询
   └→ WHERE user_id = ANY($1::uuid[])
   └→ 查到family_default下的预算

4. 返回结果
   └→ ✅ 所有家庭成员都能查到
```

### 用户问："我这个月的花费"

```
1. AI分析
   └→ scope=personal（"我"明确指定）
   └→ person="我"

2. 引擎处理
   └→ scope=personal → person="我" → user_id=current_user_id
   └→ 不添加thread_id

3. MCP查询
   └→ WHERE user_id = ANY($1::uuid[])  # 单个user_id
   └→ 只查当前用户的数据

4. 返回结果
   └→ ✅ 只包含当前用户的花费
```

---

## 🎁 优势总结

| 方面 | 旧方案 | 新方案（B4） |
|-----|--------|-------------|
| **类型判断** | 硬编码FAMILY_SHARED_TYPES | AI识别scope |
| **人称解析** | 硬编码relation_mapping | AI查household解析 |
| **默认行为** | 按数据类型区分 | 统一默认family |
| **扩展性** | 新类型/成员需改代码 | 无需改代码 |
| **符合理念** | ❌ 工程预设 | ✅ AI决定 |
| **代码行数** | 更多硬编码 | 极简查找 |

---

## 📚 相关文件

### 修改的文件
1. **src/ai_engine.py**
   - `_resolve_person_to_user_id()`: 极简版本（52行 → 25行）
   - `resolve_context_requests()`: 移除GLOBAL_DATA_TYPES
   - `_prepare_tool_arguments()`: 基于scope处理

2. **mcp-server/generic_mcp_server.py**
   - `_search()`: 支持user_id列表
   - SQL: `WHERE user_id = ANY($1::uuid[])`

3. **prompts/family_assistant_prompts.yaml**
   - 新增：`scope_identification_guide`
   - 更新：`context_requests_examples`
   - 指导AI识别scope和解析person

4. **.env**
   - 新增：`FAMILY_SHARED_USER_IDS='["family_default"]'`

---

## 🚀 使用指南

### 对用户
所有家庭成员问相同问题，得到相同答案：
```
dad问：  "本月预算是多少" → 11,500元
mom问：  "本月预算是多少" → 11,500元（相同）
孩子问： "本月预算是多少" → 11,500元（相同）
```

指定某人时，只查该人数据：
```
"我这个月的花费" → 只查当前用户
"儿子的身高" → 只查儿子（AI解析为Jack）
```

### 对开发者
无需关心数据类型，AI自动决定：
- 新增数据类型 → 无需改代码
- 新增家庭成员 → 无需改代码
- 调整查询逻辑 → 修改Prompt即可

---

## 🔮 未来演进

### AI能力提升自动带来的改进
1. **更准确的scope识别**
   - 模型升级 → 理解"我们家"vs"我的"更准确
   
2. **更智能的person解析**
   - 上下文学习 → 知道"老大"是谁
   - 对话历史 → 记住用户习惯称呼

3. **更细粒度的范围控制**
   - AI可能自创：scope="couple"（夫妻）
   - scope="children"（所有孩子）
   - 完全由AI决定，无需改代码

### Prompt优化方向
```yaml
# 未来可能的扩展（不改代码）
scope_custom_examples: |
  - "我和老婆的花费" → scope=custom, person_keys=["dad","mom"]
  - "孩子们的开支" → scope=custom, person_keys=["daughter_1","son_1"]
```

---

## ✅ 验证清单

- [x] dad、mom、daughter_1都能查到预算
- [x] 查询使用全家user_ids列表
- [x] MCP支持WHERE user_id = ANY($1)
- [x] 移除所有GLOBAL_DATA_TYPES硬编码
- [x] person解析函数极简化（无relation_mapping）
- [x] Prompt增加scope识别指导
- [x] 环境变量配置FAMILY_SHARED_USER_IDS

---

## 🎓 经验总结

### 设计教训
1. **思考"谁决定"**：业务逻辑应该由AI决定，不是工程代码
2. **避免"预设"**：不要假设哪些是全局数据、哪些是个人数据
3. **拥抱数据**：从household context学习，不硬编码映射表
4. **保持极简**：引擎只做查找，不做映射/推理/判断

### FAA核心理念体现
- ✅ **AI驱动**：scope由AI识别，不是代码判断
- ✅ **数据驱动**：person从household解析，不是硬编码映射
- ✅ **能力进化**：AI模型升级自动提升识别准确度
- ✅ **零预设**：默认行为统一（family），特殊情况由AI决定

---

## 📝 配置要求

### 环境变量
```bash
# .env
FAMILY_SHARED_USER_IDS='["family_default"]'
```

### 初始化数据
```bash
# 预算和类目配置存储在family_default下
docker-compose exec faa-api python scripts/init_budget_data.py
```

---

## 🐛 调试日志

### 关键日志点
```python
# scope识别
"tool_args.scope_family"      # 默认全家范围
"tool_args.scope_personal"    # 个人范围
"tool_args.scope_thread"      # 线程范围

# person解析
"person_resolution.failed"    # AI输出的person无法匹配

# 上下文
"context.using_family_scope"  # context_requests使用全家
```

### 排查问题
1. 查不到数据 → 检查family_scope.user_ids是否包含所有成员
2. person解析失败 → 检查AI是否输出了具体名字
3. scope不正确 → 检查Prompt指导是否清晰

---

**日期**: 2025-10-17  
**版本**: FAA v2.1 - Scope驱动架构

