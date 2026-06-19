#!/usr/bin/env python3
"""
OpenAPI 文档生成脚本 — 从 FastAPI app 导出 openapi.json

用法:
    python scripts/generate_api_docs.py
    python scripts/generate_api_docs.py --output docs/api/openapi.json

输出:
    - docs/api/openapi.json  (OpenAPI 3.1 spec)
    - 控制台打印端点统计

CI 集成:
    python scripts/generate_api_docs.py --check  # 验证 spec 是否最新
"""

import json
import os
import sys
from pathlib import Path

# 确保项目根目录可导入
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)


def get_openapi_spec() -> dict:
    """从 FastAPI app 提取 OpenAPI spec。"""
    from backend.main import app

    return app.openapi()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate OpenAPI documentation")
    parser.add_argument(
        "--output",
        "-o",
        default="docs/api/openapi.json",
        help="Output file path (default: docs/api/openapi.json)",
    )
    parser.add_argument(
        "--check", action="store_true", help="Check if existing spec is up-to-date (for CI)"
    )
    args = parser.parse_args()

    spec = get_openapi_spec()
    output_path = PROJECT_ROOT / args.output

    if args.check:
        # CI 模式：对比现有 spec
        if not output_path.exists():
            print(f"❌ Spec file not found: {output_path}")
            print("   Run: python scripts/generate_api_docs.py")
            sys.exit(1)
        existing = json.loads(output_path.read_text())
        if existing == spec:
            print("✅ OpenAPI spec is up-to-date")
            sys.exit(0)
        else:
            print("❌ OpenAPI spec is outdated!")
            print("   Run: python scripts/generate_api_docs.py")
            # 打印差异摘要
            new_paths = set(spec.get("paths", {}).keys()) - set(existing.get("paths", {}).keys())
            removed_paths = set(existing.get("paths", {}).keys()) - set(
                spec.get("paths", {}).keys()
            )
            if new_paths:
                print(f"   New endpoints: {new_paths}")
            if removed_paths:
                print(f"   Removed endpoints: {removed_paths}")
            sys.exit(1)

    # 生成模式
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n")

    # 打印统计
    paths = spec.get("paths", {})
    total_endpoints = sum(len(methods) for methods in paths.values())
    tags = spec.get("tags", [])

    print(f"✅ OpenAPI spec generated: {output_path}")
    print(f"   Title: {spec['info']['title']}")
    print(f"   Version: {spec['info']['version']}")
    print(f"   Endpoints: {total_endpoints}")
    print(f"   Tags: {len(tags)}")
    print(f"   Paths: {len(paths)}")
    print()
    print("   Swagger UI: http://127.0.0.1:8765/docs")
    print("   ReDoc:      http://127.0.0.1:8765/redoc")


if __name__ == "__main__":
    main()
