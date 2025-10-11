"""
版本信息追踪器

用于在测试报告中记录完整的版本信息，以便对比不同版本的测试结果
"""

import sys
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
import yaml

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.core.config import settings


class VersionTracker:
    """版本信息追踪器"""
    
    @staticmethod
    def get_version_info() -> Dict[str, Any]:
        """
        获取完整的版本信息
        
        Returns:
            包含所有版本信息的字典
        """
        version_info = {
            "test_timestamp": datetime.now().isoformat(),
            "test_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            
            # 主项目LLM配置
            "llm": {
                "provider": settings.AI_PROVIDER,
                "model": settings.OPENAI_MODEL if settings.AI_PROVIDER == "openai_compatible" else settings.ANTHROPIC_MODEL,
                "base_url": getattr(settings, "OPENAI_BASE_URL", None),
                "embedding_provider": getattr(settings, "EMBED_PROVIDER", "local_fastembed"),
                "embedding_model": VersionTracker._get_embedding_model(),
            },
            
            # 测试评估器LLM配置（独立配置，默认gpt-4o-mini）
            "evaluator_llm": {
                "provider": "openai",
                "model": "gpt-4o-mini",  # 成本低、速度快、评估能力足够
                "base_url": "https://api.openai.com/v1",
                "purpose": "AI评估AI的理解和体验"
            },
            
            # Prompts版本
            "prompts": VersionTracker._get_prompts_version(),
            
            # 环境信息
            "environment": {
                "app_env": settings.APP_ENV,
                "debug": settings.DEBUG,
            }
        }
        
        return version_info
    
    @staticmethod
    def _get_embedding_model() -> str:
        """获取embedding模型名称"""
        embed_provider = getattr(settings, "EMBED_PROVIDER", "local_fastembed")
        
        if embed_provider == "local_fastembed":
            return getattr(settings, "FASTEMBED_MODEL", "BAAI/bge-small-zh-v1.5")
        else:
            return getattr(settings, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    
    @staticmethod
    def _get_prompts_version() -> Dict[str, str]:
        """
        获取Prompts版本信息
        
        Returns:
            包含版本号和文件路径的字典
        """
        prompts_file = project_root / "prompts" / "family_assistant_prompts.yaml"
        
        try:
            with open(prompts_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            return {
                "version": data.get("version", "unknown"),
                "current_profile": data.get("current", "unknown"),
                "file_path": str(prompts_file.relative_to(project_root)),
            }
        except Exception as e:
            return {
                "version": "error",
                "error": str(e),
                "file_path": str(prompts_file.relative_to(project_root)),
            }
    
    @staticmethod
    def format_version_summary(version_info: Dict[str, Any]) -> str:
        """
        格式化版本信息为人类可读的摘要
        
        Args:
            version_info: 版本信息字典
            
        Returns:
            格式化的字符串
        """
        lines = []
        lines.append("=" * 80)
        lines.append("版本信息")
        lines.append("=" * 80)
        lines.append(f"测试时间: {version_info['test_date']}")
        lines.append("")
        
        # 主LLM
        llm = version_info['llm']
        lines.append(f"主项目LLM:")
        lines.append(f"  提供商: {llm['provider']}")
        lines.append(f"  模型: {llm['model']}")
        if llm.get('base_url'):
            lines.append(f"  Base URL: {llm['base_url']}")
        lines.append(f"  Embedding: {llm['embedding_provider']} / {llm['embedding_model']}")
        lines.append("")
        
        # 评估器LLM
        eval_llm = version_info['evaluator_llm']
        lines.append(f"测试评估器LLM:")
        lines.append(f"  模型: {eval_llm['model']}")
        lines.append(f"  用途: {eval_llm['purpose']}")
        lines.append("")
        
        # Prompts
        prompts = version_info['prompts']
        lines.append(f"Prompts:")
        lines.append(f"  版本: {prompts['version']}")
        lines.append(f"  当前Profile: {prompts['current_profile']}")
        lines.append(f"  文件: {prompts['file_path']}")
        lines.append("")
        
        lines.append("=" * 80)
        
        return "\n".join(lines)


def main():
    """测试版本追踪器"""
    tracker = VersionTracker()
    version_info = tracker.get_version_info()
    
    print(tracker.format_version_summary(version_info))
    
    # 打印JSON格式
    import json
    print("\nJSON格式:")
    print(json.dumps(version_info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

