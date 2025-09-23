#!/usr/bin/env python3
"""
FAA 通用化性能监控与动态优化系统

基于核心理念：
- 数据结构泛化，查询性能专业化
- 工程固定，能力自动增长
- AI驱动决策，系统自动优化
"""
import asyncio
import asyncpg
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict
import structlog

logger = structlog.get_logger()

class FAAPerfomanceMonitor:
    """FAA 性能监控与优化系统"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool = None
    
    async def initialize(self):
        """初始化数据库连接池"""
        self.pool = await asyncpg.create_pool(self.database_url)
        
    async def close(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.close()
    
    async def analyze_query_patterns(self) -> Dict[str, Any]:
        """
        分析查询模式，识别高频查询组合
        """
        try:
            async with self.pool.acquire() as conn:
                # 分析最近30天的查询模式
                analysis = await conn.fetch("""
                    SELECT 
                        type_extracted,
                        person_extracted,
                        metric_extracted,
                        subject_extracted,
                        category_extracted,
                        COUNT(*) as query_count,
                        COUNT(DISTINCT user_id) as user_count,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value_extracted) as median_value,
                        AVG(value_extracted) as avg_value
                    FROM memories 
                    WHERE created_at >= NOW() - INTERVAL '30 days'
                      AND (type_extracted IS NOT NULL OR person_extracted IS NOT NULL)
                    GROUP BY type_extracted, person_extracted, metric_extracted, subject_extracted, category_extracted
                    HAVING COUNT(*) > 10
                    ORDER BY query_count DESC
                    LIMIT 50
                """)
                
                patterns = {}
                for row in analysis:
                    pattern_key = self._generate_pattern_key(dict(row))
                    patterns[pattern_key] = {
                        "query_count": row['query_count'],
                        "user_count": row['user_count'],
                        "data_distribution": {
                            "median_value": float(row['median_value']) if row['median_value'] else None,
                            "avg_value": float(row['avg_value']) if row['avg_value'] else None
                        },
                        "fields": {
                            "type": row['type_extracted'],
                            "person": row['person_extracted'],
                            "metric": row['metric_extracted'],
                            "subject": row['subject_extracted'],
                            "category": row['category_extracted']
                        }
                    }
                
                return {
                    "analysis_date": datetime.now().isoformat(),
                    "total_patterns": len(patterns),
                    "patterns": patterns
                }
                
        except Exception as e:
            logger.error("查询模式分析失败", error=str(e))
            return {"error": str(e)}
    
    async def suggest_optimizations(self) -> Dict[str, Any]:
        """
        基于查询模式建议优化策略
        """
        try:
            patterns = await self.analyze_query_patterns()
            if "error" in patterns:
                return patterns
            
            suggestions = []
            
            # 分析高频查询组合
            for pattern_key, pattern_data in patterns["patterns"].items():
                query_count = pattern_data["query_count"]
                fields = pattern_data["fields"]
                
                # 识别需要专用索引的查询模式
                if query_count > 100:  # 高频查询
                    index_suggestion = self._generate_index_suggestion(fields, query_count)
                    if index_suggestion:
                        suggestions.append(index_suggestion)
                
                # 识别需要专用查询函数的模式
                if query_count > 200 and pattern_data["user_count"] > 3:
                    function_suggestion = self._generate_function_suggestion(fields, pattern_data)
                    if function_suggestion:
                        suggestions.append(function_suggestion)
            
            # 分析索引使用情况
            index_analysis = await self._analyze_index_usage()
            suggestions.extend(index_analysis.get("suggestions", []))
            
            return {
                "analysis_date": datetime.now().isoformat(),
                "total_suggestions": len(suggestions),
                "suggestions": suggestions,
                "patterns_analyzed": len(patterns["patterns"]),
                "index_analysis": index_analysis
            }
            
        except Exception as e:
            logger.error("优化建议生成失败", error=str(e))
            return {"error": str(e)}
    
    async def _analyze_index_usage(self) -> Dict[str, Any]:
        """分析索引使用情况"""
        try:
            async with self.pool.acquire() as conn:
                # 获取索引使用统计
                index_stats = await conn.fetch("""
                    SELECT * FROM index_usage_analysis
                    WHERE scan_count IS NOT NULL
                    ORDER BY scan_count DESC
                """)
                
                suggestions = []
                unused_indexes = []
                high_usage_indexes = []
                
                for row in index_stats:
                    usage_level = row['usage_level']
                    index_name = row['indexname']
                    scan_count = row['scan_count']
                    
                    if usage_level == 'UNUSED':
                        unused_indexes.append({
                            "index_name": index_name,
                            "suggestion": f"考虑删除未使用的索引: {index_name}",
                            "reason": "索引从未被使用，浪费存储空间和维护成本"
                        })
                    elif usage_level == 'HIGH_USAGE':
                        high_usage_indexes.append({
                            "index_name": index_name,
                            "scan_count": scan_count,
                            "suggestion": f"高使用率索引 {index_name}，考虑进一步优化",
                            "reason": "高频使用的索引，值得投入更多优化资源"
                        })
                
                # 生成清理建议
                if len(unused_indexes) > 2:
                    suggestions.append({
                        "type": "index_cleanup",
                        "priority": "medium",
                        "action": f"删除 {len(unused_indexes)} 个未使用索引",
                        "details": unused_indexes
                    })
                
                # 生成重点优化建议
                if high_usage_indexes:
                    suggestions.append({
                        "type": "index_optimization", 
                        "priority": "high",
                        "action": f"优化 {len(high_usage_indexes)} 个高使用率索引",
                        "details": high_usage_indexes
                    })
                
                return {
                    "unused_count": len(unused_indexes),
                    "high_usage_count": len(high_usage_indexes),
                    "suggestions": suggestions
                }
                
        except Exception as e:
            logger.error("索引分析失败", error=str(e))
            return {"error": str(e), "suggestions": []}
    
    def _generate_pattern_key(self, row_data: Dict) -> str:
        """生成查询模式的唯一标识"""
        key_parts = []
        for field in ['type_extracted', 'person_extracted', 'metric_extracted', 'subject_extracted', 'category_extracted']:
            value = row_data.get(field)
            if value:
                key_parts.append(f"{field.replace('_extracted', '')}:{value}")
        return "|".join(key_parts) if key_parts else "general"
    
    def _generate_index_suggestion(self, fields: Dict, query_count: int) -> Optional[Dict]:
        """基于字段组合生成索引建议"""
        non_null_fields = {k: v for k, v in fields.items() if v is not None}
        
        if len(non_null_fields) < 2:
            return None
        
        # 生成索引名称
        field_names = list(non_null_fields.keys())
        index_name = f"idx_auto_{'_'.join(field_names)}_{hash(str(sorted(non_null_fields.items()))) % 10000}"
        
        # 生成索引创建语句
        index_columns = []
        where_conditions = []
        
        for field, value in non_null_fields.items():
            if field == 'type':
                index_columns.append("user_id")
                index_columns.append("type_extracted") 
                where_conditions.append(f"type_extracted = '{value}'")
            elif field in ['person', 'metric', 'subject', 'category']:
                index_columns.append(f"{field}_extracted")
        
        # 添加常用的排序和查询列
        index_columns.extend(["occurred_at DESC", "value_extracted"])
        
        create_statement = f"""
        CREATE INDEX CONCURRENTLY {index_name}
        ON memories ({', '.join(index_columns)})"""
        
        if where_conditions:
            create_statement += f"\nWHERE {' AND '.join(where_conditions)}"
        
        return {
            "type": "dynamic_index",
            "priority": "high" if query_count > 500 else "medium",
            "index_name": index_name,
            "create_statement": create_statement.strip() + ";",
            "reason": f"高频查询组合 (使用 {query_count} 次)，需要专用索引优化",
            "estimated_benefit": f"预计提升查询速度 10-50倍",
            "query_count": query_count
        }
    
    def _generate_function_suggestion(self, fields: Dict, pattern_data: Dict) -> Optional[Dict]:
        """基于查询模式生成专用函数建议"""
        non_null_fields = {k: v for k, v in fields.items() if v is not None}
        
        if 'type' not in non_null_fields:
            return None
        
        data_type = non_null_fields['type']
        query_count = pattern_data["query_count"]
        
        # 生成函数名称
        function_name = f"get_{data_type}_summary_by"
        if 'person' in non_null_fields:
            function_name += "_person"
        if 'metric' in non_null_fields:
            function_name += "_metric"
        if 'subject' in non_null_fields:
            function_name += "_subject"
        
        return {
            "type": "specialized_function",
            "priority": "high",
            "function_name": function_name,
            "data_type": data_type,
            "reason": f"高频专用查询 (使用 {query_count} 次)，建议创建专用优化函数",
            "estimated_benefit": "数据库端聚合，减少数据传输，提升5-10倍性能",
            "query_count": query_count,
            "user_count": pattern_data["user_count"]
        }
    
    async def apply_optimization(self, suggestion: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用优化建议
        """
        try:
            async with self.pool.acquire() as conn:
                suggestion_type = suggestion.get("type")
                
                if suggestion_type == "dynamic_index":
                    # 创建动态索引
                    create_statement = suggestion["create_statement"]
                    await conn.execute(create_statement)
                    
                    return {
                        "success": True,
                        "action": "index_created",
                        "index_name": suggestion["index_name"],
                        "message": f"成功创建索引: {suggestion['index_name']}"
                    }
                
                elif suggestion_type == "index_cleanup":
                    # 清理未使用的索引
                    cleaned_count = 0
                    for index_info in suggestion.get("details", []):
                        index_name = index_info["index_name"]
                        if not index_name.startswith("idx_memories_financial"):  # 保护核心索引
                            try:
                                await conn.execute(f"DROP INDEX IF EXISTS {index_name}")
                                cleaned_count += 1
                            except Exception as e:
                                logger.warning("索引删除失败", index=index_name, error=str(e))
                    
                    return {
                        "success": True,
                        "action": "indexes_cleaned",
                        "cleaned_count": cleaned_count,
                        "message": f"成功清理 {cleaned_count} 个未使用索引"
                    }
                
                else:
                    return {
                        "success": False,
                        "error": f"不支持的优化类型: {suggestion_type}"
                    }
                    
        except Exception as e:
            logger.error("优化应用失败", suggestion=suggestion, error=str(e))
            return {
                "success": False,
                "error": str(e)
            }
    
    async def generate_performance_report(self) -> Dict[str, Any]:
        """
        生成完整的性能报告
        """
        try:
            # 收集各种性能指标
            query_patterns = await self.analyze_query_patterns()
            optimization_suggestions = await self.suggest_optimizations()
            
            # 计算关键性能指标
            async with self.pool.acquire() as conn:
                # 数据统计
                data_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_records,
                        COUNT(DISTINCT user_id) as total_users,
                        COUNT(DISTINCT type_extracted) as data_types,
                        COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') as recent_records,
                        AVG(pg_column_size(ai_understanding)) as avg_jsonb_size
                    FROM memories
                """)
                
                # 计算列优化效果
                computed_col_usage = await conn.fetch("""
                    SELECT 
                        'type_extracted' as column_name,
                        COUNT(*) FILTER (WHERE type_extracted IS NOT NULL) as non_null_count,
                        COUNT(DISTINCT type_extracted) as distinct_values
                    FROM memories
                    UNION ALL
                    SELECT 
                        'person_extracted',
                        COUNT(*) FILTER (WHERE person_extracted IS NOT NULL),
                        COUNT(DISTINCT person_extracted)
                    FROM memories
                    UNION ALL
                    SELECT 
                        'metric_extracted',
                        COUNT(*) FILTER (WHERE metric_extracted IS NOT NULL),
                        COUNT(DISTINCT metric_extracted)
                    FROM memories
                """)
            
            computed_col_stats = {}
            for row in computed_col_usage:
                computed_col_stats[row['column_name']] = {
                    "non_null_count": row['non_null_count'],
                    "distinct_values": row['distinct_values'],
                    "utilization_rate": row['non_null_count'] / data_stats['total_records'] if data_stats['total_records'] > 0 else 0
                }
            
            return {
                "report_date": datetime.now().isoformat(),
                "summary": {
                    "total_records": data_stats['total_records'],
                    "total_users": data_stats['total_users'],
                    "data_types": data_stats['data_types'],
                    "recent_activity": data_stats['recent_records'],
                    "avg_jsonb_size_bytes": int(data_stats['avg_jsonb_size']) if data_stats['avg_jsonb_size'] else 0
                },
                "computed_columns_performance": computed_col_stats,
                "query_patterns": query_patterns,
                "optimization_suggestions": optimization_suggestions,
                "performance_score": self._calculate_performance_score(data_stats, computed_col_stats, optimization_suggestions)
            }
            
        except Exception as e:
            logger.error("性能报告生成失败", error=str(e))
            return {"error": str(e)}
    
    def _calculate_performance_score(self, data_stats: Dict, computed_col_stats: Dict, optimization_suggestions: Dict) -> Dict[str, Any]:
        """计算系统性能评分"""
        score = 100  # 基础分数
        issues = []
        
        # 数据量评估
        total_records = data_stats['total_records']
        if total_records > 100000:
            score -= 10
            issues.append("数据量较大，需要持续优化")
        
        # 计算列利用率评估
        for col_name, stats in computed_col_stats.items():
            utilization = stats['utilization_rate']
            if utilization < 0.1:  # 利用率低于10%
                score -= 5
                issues.append(f"{col_name} 利用率过低 ({utilization:.1%})")
        
        # 优化建议评估
        high_priority_suggestions = len([s for s in optimization_suggestions.get("suggestions", []) if s.get("priority") == "high"])
        score -= high_priority_suggestions * 3
        
        if high_priority_suggestions > 0:
            issues.append(f"{high_priority_suggestions} 个高优先级优化建议")
        
        return {
            "score": max(score, 0),
            "grade": self._get_performance_grade(score),
            "issues_count": len(issues),
            "issues": issues
        }
    
    def _get_performance_grade(self, score: int) -> str:
        """根据分数获取性能等级"""
        if score >= 90:
            return "A (优秀)"
        elif score >= 80:
            return "B (良好)"
        elif score >= 70:
            return "C (一般)"
        elif score >= 60:
            return "D (需改进)"
        else:
            return "F (需立即优化)"

async def main():
    """主函数 - 性能监控示例"""
    database_url = os.getenv('DATABASE_URL', 'postgresql://faa:faa@localhost:5432/family_assistant')
    
    monitor = FAAPerfomanceMonitor(database_url)
    await monitor.initialize()
    
    try:
        # 生成性能报告
        report = await monitor.generate_performance_report()
        print("=== FAA 性能监控报告 ===")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        
        # 分析优化建议
        suggestions = await monitor.suggest_optimizations()
        print("\n=== 优化建议 ===")
        for suggestion in suggestions.get("suggestions", []):
            print(f"- {suggestion.get('reason', 'N/A')}")
            if suggestion.get("priority") == "high":
                print(f"  优先级: 🔴 {suggestion['priority']}")
            else:
                print(f"  优先级: 🟡 {suggestion['priority']}")
        
    finally:
        await monitor.close()

if __name__ == "__main__":
    asyncio.run(main())
