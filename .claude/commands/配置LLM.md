请帮助用户配置 LLM API。

## 配置方式

用户可以在 Claude Code 中直接输入 API Key，或者使用命令行向导。

### 方式一：使用命令行向导（推荐）

告诉用户运行以下命令：
```bash
python scripts/config_wizard.py
```
然后按提示选择后端、输入 Key。

也可以快速配置（DeepSeek 默认）：
```bash
python scripts/config_wizard.py --quick
```

查看当前配置：
```bash
python scripts/config_wizard.py --check
```

### 方式二：手动编辑 .env

1. 复制 `.env.example` → `.env`
2. 编辑 `.env`，填入 Key

### 配置内容

- `LLM_BACKEND`: `anthropic` 或 `openai`
- `ANTHROPIC_API_KEY`: DeepSeek 或 Anthropic 的 API Key
- `ANTHROPIC_BASE_URL`: API 端点（DeepSeek 默认 `https://api.deepseek.com/anthropic`）
- `ANTHROPIC_MODEL`: 模型名（推荐 `deepseek-v4-pro`）
- `OPENAI_API_KEY`: OpenAI 兼容的 API Key（备选）
- `OPENAI_BASE_URL`: OpenAI 兼容端点
- `LLM_MODEL`: OpenAI 兼容的模型名

### 安全说明

`.env` 文件已在 `.gitignore` 中，不会被上传到 Git。
API Key 仅保存在本地 `.env` 文件中。
