"""
费用类目配置服务 - 管理家庭费用分类体系

设计理念：
1. 配置单一来源（family_private_data.json）
2. 启动时加载到内存，运行时快速访问
3. 支持热重载（配置更新后重启生效）
4. 格式化为AI友好的详细描述
"""
import json
import os
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger(__name__)


class ExpenseCategoriesService:
    """费用类目配置服务"""
    
    def __init__(self):
        self._config: Optional[Dict[str, Any]] = None
        self._categories: List[Dict[str, Any]] = []
        self._load_from_file()
    
    def _load_from_file(self):
        """从配置文件加载费用类目定义"""
        try:
            # 尝试加载私有配置
            config_paths = [
                'family_private_data.json',
                'family_data_example.json'
            ]
            
            config_data = None
            used_path = None
            
            for path in config_paths:
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                        used_path = path
                        break
            
            if not config_data:
                logger.warning("expense_categories.config_not_found")
                self._use_empty_config()
                return
            
            # 提取费用类目配置
            expense_config = config_data.get('expense_categories_budget', {})
            
            if not expense_config:
                logger.warning("expense_categories.empty_config", path=used_path)
                self._use_empty_config()
                return
            
            self._config = expense_config
            self._categories = expense_config.get('monthly_categories_budget', [])
            
            logger.info(
                "expense_categories.loaded",
                path=used_path,
                categories_count=len(self._categories),
                categories=[c.get('category_name') for c in self._categories[:5]]
            )
            
        except Exception as e:
            logger.error("expense_categories.load_failed", error=str(e))
            self._use_empty_config()
    
    def _use_empty_config(self):
        """使用空配置作为fallback"""
        self._config = {
            'monthly_budget_total': 0,
            'monthly_categories_budget': []
        }
        self._categories = []
    
    def get_categories_context(self) -> Dict[str, Any]:
        """获取类目配置上下文（用于存储和AI理解）"""
        return {
            'total_budget': self._config.get('monthly_budget_total', 0),
            'categories': self._categories,
            'formatted_description': self._format_for_storage()
        }
    
    def _format_for_storage(self) -> str:
        """格式化为详细的存储文本（用于写入memories）"""
        if not self._categories:
            return "无费用类目配置"
        
        lines = [
            "# 家庭费用类目配置",
            "",
            f"**月度总预算**: {self._config.get('monthly_budget_total', 0)} {self._config.get('currency', 'CNY')}",
            "",
            "## 费用类目定义",
            ""
        ]
        
        for cat in self._categories:
            cat_name = cat.get('category_name', '未命名')
            aliases = cat.get('alias', [])
            budget = cat.get('budget', -1)
            description = cat.get('description', '')
            exclude = cat.get('exclude', [])
            notes = cat.get('notes', '')
            sub_cats = cat.get('sub_categories', [])
            
            # 类目标题
            lines.append(f"### {cat_name}")
            
            # 别名
            if aliases:
                lines.append(f"**别名**: {', '.join(aliases)}")
            
            # 预算
            if budget == -1:
                lines.append("**预算**: 无限制")
            else:
                lines.append(f"**预算**: {budget} 元/月")
            
            # 描述
            if description:
                lines.append(f"**描述**: {description}")
            
            # 排除项
            if exclude:
                lines.append(f"**排除**: {', '.join(exclude)}")
            
            # 备注
            if notes:
                lines.append(f"**备注**: {notes}")
            
            # 子类目
            if sub_cats:
                lines.append("")
                lines.append("**子类目**:")
                for sub in sub_cats:
                    sub_name = sub.get('sub_category_name', '')
                    sub_aliases = sub.get('alias', [])
                    sub_desc = sub.get('description', '')
                    sub_budget = sub.get('budget', -1)
                    
                    sub_line = f"  - **{sub_name}**"
                    if sub_aliases:
                        sub_line += f" (别名: {', '.join(sub_aliases)})"
                    if sub_budget != -1:
                        sub_line += f" [预算: {sub_budget}元]"
                    lines.append(sub_line)
                    
                    if sub_desc:
                        lines.append(f"    描述: {sub_desc}")
            
            lines.append("")  # 类目间空行
        
        return "\n".join(lines)
    
    def get_category_mapping_rules(self) -> str:
        """获取简化的分类映射规则（用于prompts指导）"""
        if not self._categories:
            return "暂无类目配置"
        
        lines = [
            "## 费用分类规则",
            "",
            "**原则**:",
            "1. 严格按照类目定义分类，不创造新类目",
            "2. 优先匹配别名（alias）",
            "3. 参考描述理解类目范围",
            "4. 注意排除规则（exclude）",
            "5. 使用sub_category记录细分（如果适用）",
            "",
            "**类目列表**:",
            ""
        ]
        
        for cat in self._categories:
            cat_name = cat.get('category_name', '')
            aliases = cat.get('alias', [])
            description = cat.get('description', '')
            
            # 简化显示
            cat_line = f"- **{cat_name}**"
            if aliases:
                cat_line += f" (别名: {', '.join(aliases)})"
            lines.append(cat_line)
            
            # 简短描述
            if description:
                short_desc = description[:80] + '...' if len(description) > 80 else description
                lines.append(f"  {short_desc}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def reload(self):
        """重新加载配置"""
        logger.info("expense_categories.reloading")
        self._load_from_file()


# 全局单例
expense_categories_service = ExpenseCategoriesService()

