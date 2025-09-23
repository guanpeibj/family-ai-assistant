#!/usr/bin/env python3
"""
FastEmbed 模型预下载脚本
用于在 Docker 构建阶段预下载模型，避免运行时下载失败
"""

import os
import sys
import glob
from pathlib import Path

def main():
    # 设置环境变量
    cache_path = "/data/fastembed_cache"
    os.environ["FASTEMBED_CACHE_PATH"] = cache_path
    
    print(f"Setting FastEmbed cache path to: {cache_path}")
    
    try:
        # 确保缓存目录存在
        Path(cache_path).mkdir(parents=True, exist_ok=True)
        
        # 导入并下载模型
        print("Importing FastEmbed...")
        from fastembed import TextEmbedding
        
        model_name = "BAAI/bge-small-zh-v1.5"
        print(f"Model name: {model_name}")
        
        # 下载模型
        model = TextEmbedding(model_name=model_name)
        
        # 测试模型是否真正可用
        print("Testing model...")
        test_embedding = list(model.embed(["测试文本"]))
        print(f"Model test successful! Embedding dimension: {len(test_embedding[0])}")
        
        # 验证缓存目录
        model_cache_dir = os.path.join(cache_path, 'models')
        if os.path.exists(model_cache_dir):
            model_files = glob.glob(os.path.join(model_cache_dir, '**', '*'), recursive=True)
            print(f"Cache directory contains {len(model_files)} files")
            
            # 列出主要文件
            for file_path in sorted(model_files)[:10]:  # 只显示前10个文件
                rel_path = os.path.relpath(file_path, cache_path)
                file_size = os.path.getsize(file_path)
                print(f"  {rel_path} ({file_size} bytes)")
        else:
            print("Warning: Model cache directory not found")
            
        print("✅ FastEmbed model pre-download completed successfully!")
        
    except Exception as e:
        print(f"❌ Model pre-download failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
