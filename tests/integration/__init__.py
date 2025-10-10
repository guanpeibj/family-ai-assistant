"""
FAA 集成测试套件

这个包包含FAA的端到端集成测试，验证实际使用场景。
测试遵循三个核心原则：
1. 以readme.MD的最终目标为导向
2. 以AI驱动设计理念为核心（AI决策、工程简化、能力自动进化）
3. 简洁、直接和稳定地实现

测试组织：
- P0: 核心必测功能（40个用例）
- P1: 重要功能（40个用例）
- P2: 增强功能（36个用例）

运行方式：
    python tests/integration/run_tests.py --priority P0
    python tests/integration/run_tests.py --priority P1
    python tests/integration/run_tests.py --all
"""

__version__ = "1.0.0"

