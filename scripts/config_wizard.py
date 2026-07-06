"""
LLM API 配置向导 — 交互式命令行工具。

用法:
  python scripts/config_wizard.py          # 交互式配置
  python scripts/config_wizard.py --quick  # 快速配置（DeepSeek 默认）
  python scripts/config_wizard.py --check  # 检查当前配置状态
"""

import os
import sys


ENV_TEMPLATE = """# 全流程科研论文写作系统 — 环境变量配置
# 由 config_wizard.py 自动生成
# 日期: {date}

# LLM 后端选择
LLM_BACKEND={backend}

# Anthropic API
ANTHROPIC_API_KEY={anthropic_key}
ANTHROPIC_BASE_URL={anthropic_url}
ANTHROPIC_MODEL={anthropic_model}

# OpenAI 兼容 API
OPENAI_API_KEY={openai_key}
OPENAI_BASE_URL={openai_url}
LLM_MODEL={openai_model}
"""


def main():
    print("=" * 60)
    print("  全流程科研论文写作系统 — LLM API 配置向导")
    print("=" * 60)
    print()

    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        check_config()
        return

    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        quick_config()
        return

    interactive_config()


def check_config():
    """检查当前配置状态"""
    print("当前 LLM 配置状态：\n")

    env_files = []
    for path in [".env", os.path.expanduser("~/.research_agent.env")]:
        if os.path.exists(path):
            env_files.append(os.path.abspath(path))

    if env_files:
        print(f"  ✓ 找到配置文件: {', '.join(env_files)}")
    else:
        print("  ✗ 未找到 .env 配置文件")
        print("    运行 python scripts/config_wizard.py 进行配置")

    backend = os.environ.get("LLM_BACKEND", "未设置")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")

    print(f"  LLM 后端: {backend}")
    print(f"  Anthropic Key: {'已设置' if anthropic_key and 'your-' not in anthropic_key else '未设置'}")
    print(f"  Anthropic URL: {os.environ.get('ANTHROPIC_BASE_URL', '未设置')}")
    print(f"  Anthropic Model: {os.environ.get('ANTHROPIC_MODEL', '未设置')}")
    print(f"  OpenAI Key: {'已设置' if openai_key and 'your-' not in openai_key else '未设置'}")

    if (anthropic_key and 'your-' not in anthropic_key) or (openai_key and 'your-' not in openai_key):
        print("\n  ✅ LLM 配置就绪，可以开始使用。")
    else:
        print("\n  ⚠️  LLM 未配置。运行 python scripts/config_wizard.py 进行配置。")


def quick_config():
    """快速配置（DeepSeek 默认）"""
    print("快速配置模式：使用 DeepSeek API（Anthropic 兼容格式）\n")

    key = input("请输入 DeepSeek API Key (从 https://platform.deepseek.com/api_keys 获取): ").strip()
    if not key:
        print("未输入 API Key，已取消。")
        return

    model = input("模型名称 [deepseek-v4-pro]: ").strip() or "deepseek-v4-pro"

    save_config(
        backend="anthropic",
        anthropic_key=key,
        anthropic_url="https://api.deepseek.com/anthropic",
        anthropic_model=model,
    )
    print("\n✅ 配置完成！")


def interactive_config():
    """交互式配置"""
    print("请选择 LLM 后端：")
    print("  1. DeepSeek API (Anthropic 兼容格式，推荐)")
    print("  2. Anthropic 官方 API")
    print("  3. OpenAI 官方 API")
    print("  4. DeepSeek API (OpenAI 兼容格式)")
    print("  5. 自定义 OpenAI 兼容 API")
    print()

    choice = input("请输入选项 (1-5) [1]: ").strip() or "1"

    if choice == "1":
        key = input("\nDeepSeek API Key: ").strip()
        model = input("模型 [deepseek-v4-pro]: ").strip() or "deepseek-v4-pro"
        save_config("anthropic", anthropic_key=key,
                    anthropic_url="https://api.deepseek.com/anthropic",
                    anthropic_model=model)

    elif choice == "2":
        key = input("\nAnthropic API Key: ").strip()
        model = input("模型 [claude-sonnet-4-6]: ").strip() or "claude-sonnet-4-6"
        save_config("anthropic", anthropic_key=key, anthropic_model=model)

    elif choice == "3":
        key = input("\nOpenAI API Key: ").strip()
        model = input("模型 [gpt-4o]: ").strip() or "gpt-4o"
        save_config("openai", openai_key=key, openai_model=model)

    elif choice == "4":
        key = input("\nDeepSeek API Key: ").strip()
        model = input("模型 [deepseek-chat]: ").strip() or "deepseek-chat"
        save_config("openai", openai_key=key,
                    openai_url="https://api.deepseek.com/v1",
                    openai_model=model)

    elif choice == "5":
        key = input("\nAPI Key: ").strip()
        url = input("Base URL: ").strip()
        model = input("模型名称: ").strip()
        save_config("openai", openai_key=key, openai_url=url, openai_model=model)

    else:
        print("无效选项。")
        return

    print("\n✅ 配置完成！现在可以运行论文分析命令了。")


def save_config(
    backend: str = "anthropic",
    anthropic_key: str = "",
    anthropic_url: str = "",
    anthropic_model: str = "",
    openai_key: str = "",
    openai_url: str = "",
    openai_model: str = "",
):
    """保存配置到 .env 文件"""
    from datetime import datetime

    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    content = ENV_TEMPLATE.format(
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        backend=backend,
        anthropic_key=anthropic_key or "",
        anthropic_url=anthropic_url or "https://api.deepseek.com/anthropic",
        anthropic_model=anthropic_model or "",
        openai_key=openai_key or "",
        openai_url=openai_url or "",
        openai_model=openai_model or "",
    )

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n  配置已保存到: {os.path.abspath(env_path)}")
    print(f"  （此文件已在 .gitignore 中，不会被提交到 Git）")


if __name__ == "__main__":
    main()
