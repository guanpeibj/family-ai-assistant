# 阿福(FAA) 家庭数据初始化指南

## 🔐 隐私保护方案

### 设计原则
- **公开配置**：通用的结构和示例可以提交到GitHub
- **私有数据**：真实的家庭信息保存在本地，永不提交
- **灵活加载**：系统自动识别并加载私有数据

### 文件说明
1. **family_data_example.json** - 示例数据文件（可提交到GitHub）
2. **family_private_data_template.json** - 私有数据模板（可提交到GitHub）
3. **family_private_data.json** - 你的真实家庭数据（绝不提交，已在.gitignore中）

### 结构要点（新增）
- `household`：声明家庭 slug、展示名称、时区等元信息。
- `family_members[*].member_key`：每个成员的稳定标识，供数据库与 AI 内部引用。
- `family_members[*].accounts`：可选账户绑定（如 Threema、Email），脚本会自动写入 `family_member_accounts` 与 `user_channels`。
- 顶层 `threema_id` 仍然兼容，会自动赋给 `role="father"` 的成员。

### 使用步骤
1. 复制 `family_private_data_template.json` 为 `family_private_data.json`
2. 在 `family_private_data.json` 中填入你的真实家庭信息
3. 运行初始化脚本：`docker-compose run --rm faa-api python scripts/init_family_data.py`
4. 系统会自动加载你的私有数据，如果没有则使用示例数据

## 核心文件关系

### 1. init_family_data.py（数据层）
- **作用**：初始化数据库中的持久化数据
- **内容**：
  - 向 `family_households / family_members / family_member_accounts` 写入结构化成员信息
  - 将详细画像写入 `memories`，供语义检索
- **特点**：AI 可以通过上下文获取成员档案（`profile`）、账号绑定与偏好信息
- **使用时机**：系统部署时运行一次，或者家庭结构发生重大变化时重跑

### 2. family_assistant_prompts.yaml（行为层）
- **作用**：定义AI的行为准则和人设
- **内容**：系统提示词、理解规则、回复风格
- **特点**：指导AI如何理解和回应
- **使用时机**：AI运行时每次加载

## 两者的协作关系

```
用户消息 → AI理解（基于prompts） → 查询数据（从init_family_data） → 生成回复
```

- prompts告诉AI"如何理解家庭成员"
- init_family_data提供"具体的家庭成员信息"
- 两者结合让AI能够个性化地服务你的家庭

## 不一致的处理原则

1. **基础信息必须一致**
   - 家庭成员的称呼（爸爸、妈妈、儿子、大女儿、二女儿）
   - 基本角色定位

2. **数据以init_family_data为准**
   - 具体的姓名、年龄、生日等
   - AI会从数据库查询最新信息

3. **行为以prompts为准**
   - AI的说话风格、回复方式
   - 理解和处理逻辑

## 丰富的初始化数据清单

### 家庭成员详细信息
- ✅ member_key（稳定 ID，避免因称呼变化导致数据错位）
- ✅ user_id（统一身份别名，所有渠道共用，可选但推荐与 member_key 一致）
- ✅ names（formal / english / nickname / preferred）
- ✅ 姓名/昵称
- ✅ 出生日期/年龄
- ✅ 身高、体重
- ✅ 血型
- ✅ 过敏信息
- ✅ 兴趣爱好
- ✅ 学校/工作信息
- ✅ 作息时间
- ✅ life_status（alive / deceased），含去世日期与纪念习惯

### 家庭基础信息
- ✅ 家庭住址
- ✅ 车辆信息（含限行日期）
- ✅ 宠物信息
- ✅ 月度预算分配
- ✅ 家庭季节性策略（`seasonal_playbook`）

### 账号与渠道
- ✅ Threema / Email / 微信等账号，可在 `accounts` 中声明
- ✅ `accounts` 未显式指定 `user_id` 时，会自动继承成员的 `user_id`
- ✅ `labels` 字段可描述该账号用途（例如“家庭群主”）
- ✅ `channel_data` 可附加额外元信息（如昵称、签名）

### 重要联系人
- ✅ 老师联系方式
- ✅ 家庭医生
- ✅ 物业电话
- ✅ 其他紧急联系人

### 日常习惯偏好
- ✅ 作息时间表
- ✅ 饮食偏好和禁忌
- ✅ 购物习惯
- ✅ 常去的地方

## 如何添加更多信息

### 1. 修改init_family_data.py添加新数据
```python
{
    "content": "儿子最喜欢的动画片是《汪汪队》",
    "ai_understanding": {
        "intent": "record_info",
        "type": "preference",
        "person": "儿子",
        "favorite_show": "汪汪队"
    }
}
```

### 2. 运行初始化脚本
```bash
docker-compose run --rm faa-api python scripts/init_family_data.py
```

### 3. 验证数据
发消息给阿福："儿子喜欢看什么动画片？"

## 推荐添加的额外信息

### 医疗健康
- 家庭成员的常用药品
- 就诊医院偏好
- 疫苗接种记录
- 体检周期

### 教育相关
- 孩子的特长班信息
- 作业时间安排
- 考试日期
- 家长会安排

### 财务相关
- 固定支出（房贷、保险等）
- 投资理财偏好
- 紧急备用金

### 社交相关
- 亲戚朋友生日
- 常见的家庭活动
- 节日庆祝方式

## 最佳实践

1. **初始化时尽量详细**
   - 信息越丰富，阿福服务越贴心
   - 包含具体数值方便统计分析

2. **定期更新数据**
   - 孩子成长数据需要定期更新
   - 新的联系人和偏好及时添加

3. **保持两个文件同步**
   - 修改家庭成员时两边都要更新
   - 使用相同的称呼体系

4. **利用AI的学习能力**
   - 初始化提供基础框架
   - 日常使用中AI会不断积累新信息
5. **维护 member_key 与账号映射**
   - member_key 一旦确认尽量保持不变，避免丢失历史上下文
   - 添加新账号时只需在 `accounts` 中追加，脚本会自动创建映射

## 示例：完整的家庭画像

通过丰富的初始化，阿福能够：

- "明天是周六，要去永辉超市买菜，记得爸爸不吃香菜"
- "大女儿思思明天7:30要上学，今天早点睡"
- "二女儿甜甜对鸡蛋过敏，买零食要注意"
- "车牌尾号8，15号限行，记得提醒"
- "妈妈通常6点起床准备早餐，设置5:50的提醒"

这样的个性化服务，正是通过详细的初始化数据实现的！ 

## AI 如何消费这些数据

- `context.household.households[*].config`：整体偏好、重要信息和联系人快速可用。
- `context.household.members_index[member_key].profile`：完整的成员档案（过敏、作息、兴趣）。
- `context.household.members_index[member_key].user_ids`：成员与账号的绑定，便于精准提醒或数据聚合。
- 所有初始化写入的 `memories` 都带有 `family_scope=true`、`household_slug` 和 `member_key`，AI 可根据意图灵活检索。
- `metadata`、`ai_playbook`、`seasonal_playbook`：为 AI 提供快速策略、语气和提醒触发条件，减少工程硬编码。
- `profile.names` 与 `profile.life_status`：帮助 AI 选择恰当称呼、尊重去世成员并生成合适的情感回应。
- 成员级 `user_id` 用于统一 API/Threema/Email 的身份；未在 `accounts` 中声明时也能通过 `/message` 使用该别名。
