# FAA 项目 Makefile - 便捷命令集合

.PHONY: help dev-setup dev-up dev-down dev-logs dev-restart prod-up prod-down prod-logs clean

# 默认目标：显示帮助
help:
	@echo "=========================================="
	@echo "   FAA 项目便捷命令"
	@echo "=========================================="
	@echo ""
	@echo "开发环境："
	@echo "  make dev-setup    配置开发环境（创建 override 文件）"
	@echo "  make dev-up       启动开发环境"
	@echo "  make dev-down     停止开发环境"
	@echo "  make dev-logs     查看开发环境日志"
	@echo "  make dev-restart  重启开发环境"
	@echo "  make dev-shell    进入 API 容器"
	@echo ""
	@echo "生产环境："
	@echo "  make prod-up      启动生产环境（无 override）"
	@echo "  make prod-down    停止生产环境"
	@echo "  make prod-logs    查看生产环境日志"
	@echo "  make prod-build   重新构建生产镜像"
	@echo ""
	@echo "其他："
	@echo "  make clean        清理容器和镜像"
	@echo "  make ps           查看服务状态"
	@echo "  make backup       备份数据"
	@echo ""

# ========== 开发环境 ==========

dev-setup:
	@echo "配置开发环境..."
	@bash scripts/dev-setup.sh

dev-up:
	@echo "启动开发环境（使用 docker-compose.override.yml）..."
	docker-compose up -d
	@echo "✓ 开发环境已启动"
	@echo "  API: http://localhost:8001"
	@echo "  MCP: http://localhost:9000"

dev-down:
	@echo "停止开发环境..."
	docker-compose down

dev-logs:
	docker-compose logs -f

dev-restart:
	@echo "重启开发环境..."
	docker-compose restart

dev-shell:
	@echo "进入 API 容器..."
	docker-compose exec faa-api bash

# ========== 生产环境 ==========

prod-up:
	@echo "启动生产环境（仅使用 docker-compose.yml）..."
	@if [ -f "docker-compose.override.yml" ]; then \
		echo "⚠️  警告: 发现 docker-compose.override.yml"; \
		echo "   生产环境应删除此文件以使用纯生产配置"; \
		echo "   是否继续? (y/N)"; \
		read confirm && [ "$$confirm" = "y" ] || exit 1; \
	fi
	docker-compose up -d
	@echo "✓ 生产环境已启动"

prod-down:
	docker-compose down

prod-logs:
	docker-compose logs -f

prod-build:
	@echo "重新构建生产镜像（无缓存）..."
	docker-compose build --no-cache

# ========== 其他命令 ==========

ps:
	docker-compose ps

clean:
	@echo "清理容器和镜像..."
	docker-compose down -v
	docker system prune -f

backup:
	@echo "执行备份..."
	@bash scripts/backup_volumes.sh

# ========== 显式指定文件的命令 ==========

# 使用开发配置
dev-explicit:
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 使用生产配置（显式指定只用 yml）
prod-explicit:
	docker-compose -f docker-compose.yml up -d

