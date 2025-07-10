# 阿福隐私数据设置指南

## 快速开始

### 1. 首次设置（仅需一次）
```bash
# 复制模板文件
cp family_private_data_template.json family_private_data.json

# 编辑你的私有数据
nano family_private_data.json  # 或使用你喜欢的编辑器
```

### 2. 填写真实信息
在 `family_private_data.json` 中：
- 将所有 `[占位符]` 替换为真实信息
- 删除不需要的字段
- 根据需要添加更多信息

### 3. 运行初始化
```bash
# 使用Docker
docker-compose run --rm faa-api python scripts/init_family_data.py

# 或直接运行
python scripts/init_family_data.py
```

## 隐私保护机制

### ✅ 安全措施
- `family_private_data.json` 已在 `.gitignore` 中
- 不会被git跟踪或提交
- 只存在于你的本地环境

### ❌ 注意事项
- **永远不要**手动将 `family_private_data.json` 添加到git
- **永远不要**在公开场合分享此文件
- **定期备份**你的私有数据到安全位置

## 文件结构示例

```json
{
  "username": "my_family",
  "threema_id": "ABCD1234",
  
  "family_members": [
    {
      "content": "家庭成员：爸爸张三，1985年出生...",
      "ai_understanding": {
        "person": "爸爸",
        "name": "张三",
        "birth_year": 1985
      }
    }
  ],
  
  "important_info": [
    {
      "content": "家庭住址：北京市朝阳区xx小区",
      "ai_understanding": {
        "type": "address",
        "address": "北京市朝阳区xx小区"
      }
    }
  ]
}
```

## 更新数据

当家庭信息发生变化时：
1. 编辑 `family_private_data.json`
2. 重新运行初始化脚本
3. 阿福会立即使用更新后的信息

## 多环境管理

如果你有多个环境（开发/生产）：
- `family_private_data.dev.json` - 开发环境
- `family_private_data.prod.json` - 生产环境
- 在 `.env` 中设置 `FAMILY_DATA_ENV=dev` 或 `prod`

## 故障排除

### 问题：找不到家庭数据
- 确认 `family_private_data.json` 在项目根目录
- 检查文件名拼写是否正确
- 确认JSON格式是否有效

### 问题：数据没有更新
- 重新运行初始化脚本
- 检查是否有数据库连接问题
- 查看脚本输出的错误信息

## 备份建议

定期备份你的私有数据：
```bash
# 创建备份
cp family_private_data.json backup/family_data_$(date +%Y%m%d).json

# 加密备份（可选）
tar -czf - family_private_data.json | openssl enc -e -aes256 > family_backup.enc
```

记住：**隐私数据的安全是最重要的！** 