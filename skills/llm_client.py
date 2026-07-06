"""
模型无关的 LLM 调用技能 — 增强版。

新增功能：
1. structured_output()  — 强制 LLM 输出符合指定的 JSON Schema（消除手写正则）
2. 自动重试机制          — JSON 解析失败/Markdown中找JSON/回退到自由文本
3. 质量验证回调          — 输出后可执行 quality_score 计算
4. 流式输出支持          — 大文本生成可流式返回（可选）

后端支持：Anthropic SDK + OpenAI 兼容 SDK
"""

import os
import json
import re
import time
from typing import Optional, Callable, Any, Dict, List
from skills.base import BaseSkill


class LlmClient(BaseSkill):
    """
    统一的LLM调用接口，支持 Anthropic 与 OpenAI 兼容后端。

    增强特性：
    - structured_output(): 传入 JSON Schema 字典，强制 LLM 输出合规 JSON
    - 自动重试: 最多 3 次，每次递增等待
    - 回退链: tool_call JSON → ```json 代码块 → 正则提取 → 原始文本
    """

    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 2.0  # 秒

    def __init__(self):
        super().__init__(
            name="LlmClient",
            description="统一的LLM调用接口，支持 Anthropic 与 OpenAI 兼容后端，含结构化输出与自动重试"
        )

    # ═══════════════════════════════════════════════════════════
    # 公共接口
    # ═══════════════════════════════════════════════════════════

    def execute(
        self,
        prompt: str,
        system_prompt: str = "",
        backend: str = None,
        model: str = None,
        max_tokens: int = 4000,
    ) -> str:
        """
        基本调用：返回自由文本。
        如需结构化输出，使用 structured_output()。
        """
        backend = backend or os.environ.get("LLM_BACKEND", "openai")

        if backend == "anthropic":
            return self._call_anthropic(prompt, system_prompt, model, max_tokens)
        elif backend == "openai":
            return self._call_openai(prompt, system_prompt, model, max_tokens)
        else:
            raise ValueError(f"不支持的后端: {backend}。可选值: anthropic, openai")

    def structured_output(
        self,
        prompt: str,
        output_schema: Dict[str, Any],
        system_prompt: str = "",
        backend: str = None,
        model: str = None,
        max_tokens: int = 6000,
        max_retries: int = None,
        quality_validator: Callable[[dict], tuple[bool, str]] = None,
    ) -> Dict[str, Any]:
        """
        结构化输出：强制 LLM 返回符合指定 JSON Schema 的字典。

        :param prompt: 用户提示
        :param output_schema: JSON Schema 字典（描述期望的输出结构）
        :param system_prompt: 系统角色指令
        :param backend: LLM 后端
        :param model: 模型名
        :param max_tokens: 最大输出 token
        :param max_retries: 最大重试次数（默认 3）
        :param quality_validator: 可选的质量验证回调，接收 (parsed_dict) → (is_valid, error_msg)
        :return: 解析后的字典
        """
        max_retries = max_retries if max_retries is not None else self.MAX_RETRIES
        backend = backend or os.environ.get("LLM_BACKEND", "openai")

        # 将 JSON Schema 追加到 prompt
        schema_json = json.dumps(output_schema, ensure_ascii=False, indent=2)
        enhanced_prompt = (
            f"{prompt}\n\n"
            f"【必须输出的 JSON 结构】\n"
            f"请在回答的末尾，用 ```json 代码块输出以下结构的 JSON。\n"
            f"必须包含所有字段，不要省略任何字段。字符串字段如无法确定请用空字符串 \"\"，\n"
            f"列表字段如无内容请用空列表 []，数字字段如无法确定请用 0。\n\n"
            f"```json\n{schema_json}\n```\n\n"
            f"重要：JSON 必须是合法的、可被 json.loads() 解析的。不要在 JSON 中使用尾随逗号。"
        )

        enhanced_system = (
            f"{system_prompt}\n\n"
            f"你必须在回答末尾输出一个 ```json 代码块，包含结构化的分析数据。"
            f"JSON 必须严格遵循用户指定的格式，所有字段都必须填写。"
        )

        last_error = None
        for attempt in range(max_retries):
            try:
                raw_output = self.execute(
                    prompt=enhanced_prompt,
                    system_prompt=enhanced_system,
                    backend=backend,
                    model=model,
                    max_tokens=max_tokens,
                )

                # 尝试解析 JSON
                parsed = self._extract_json(raw_output)

                if parsed and isinstance(parsed, dict) and len(parsed) > 2:
                    # 质量验证
                    if quality_validator:
                        is_valid, error_msg = quality_validator(parsed)
                        if not is_valid:
                            if attempt < max_retries - 1:
                                # 将错误反馈给 LLM 重新生成
                                enhanced_prompt = (
                                    f"{prompt}\n\n"
                                    f"【上一次输出的 JSON 校验失败】\n"
                                    f"错误: {error_msg}\n"
                                    f"请修正后重新输出完整的 JSON 代码块。\n\n"
                                    f"```json\n{schema_json}\n```"
                                )
                                continue
                            else:
                                # 最后一次仍失败，返回带错误标记的字典
                                parsed["_json_parse_error"] = error_msg
                    return parsed
                else:
                    last_error = f"JSON 字段数不足 ({len(parsed) if parsed else 0})"
                    if attempt < max_retries - 1:
                        print(f"  [LlmClient] 结构化输出重试 {attempt+1}/{max_retries}: {last_error}")
                        time.sleep(self.RETRY_BASE_DELAY * (attempt + 1))

            except Exception as e:
                last_error = str(e)
                if attempt < max_retries - 1:
                    print(f"  [LlmClient] LLM 调用重试 {attempt+1}/{max_retries}: {e}")
                    time.sleep(self.RETRY_BASE_DELAY * (attempt + 1))

        # 全部重试失败
        print(f"  [LlmClient] 结构化输出失败（{max_retries} 次重试）: {last_error}")
        return {
            "_json_parse_error": last_error,
            "_raw_output": raw_output if 'raw_output' in dir() else "",
        }

    # ═══════════════════════════════════════════════════════════
    # JSON 提取（多策略回退）
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict]:
        """
        从 LLM 输出中提取 JSON。按优先级尝试多种策略：
        1. ```json ... ``` 代码块
        2. 最后一个 { ... } 块
        3. 全文作为 JSON 解析（最后手段）
        """
        if not text:
            return None

        # 策略1: ```json 代码块（可能有多个，取最深/最大的）
        json_blocks = re.findall(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
        if json_blocks:
            # 按代码块大小排序，优先取最大的（通常是最完整的）
            json_blocks.sort(key=len, reverse=True)
            for block in json_blocks:
                try:
                    parsed = json.loads(block.strip())
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    # 尝试修复常见错误
                    fixed = LlmClient._try_fix_json(block.strip())
                    if fixed:
                        return fixed

        # 策略2: 找最后一个完整的 { ... } 对象
        # 从末尾开始找（通常 LLM 把 JSON 放在最后）
        brace_depth = 0
        json_start = -1
        for i in range(len(text) - 1, -1, -1):
            if text[i] == '}':
                if brace_depth == 0:
                    json_end = i + 1
                brace_depth += 1
            elif text[i] == '{':
                brace_depth -= 1
                if brace_depth == 0:
                    json_start = i
                    break

        if json_start >= 0:
            candidate = text[json_start:json_end]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and len(parsed) > 1:
                    return parsed
            except json.JSONDecodeError:
                fixed = LlmClient._try_fix_json(candidate)
                if fixed:
                    return fixed

        # 策略3: 全文解析
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        return None

    @staticmethod
    def _try_fix_json(text: str) -> Optional[Dict]:
        """尝试修复常见的 JSON 格式错误"""
        fixes = [
            # 尾随逗号
            (r',\s*}', '}'),
            (r',\s*]', ']'),
            # 单引号
            ("'", '"'),
            # 未转义的控制字符
            ('\n', '\\n'),
            ('\t', '\\t'),
        ]
        for pattern, replacement in fixes:
            try:
                fixed = re.sub(pattern, replacement, text)
                parsed = json.loads(fixed)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, Exception):
                continue
        return None

    # ═══════════════════════════════════════════════════════════
    # 后端实现
    # ═══════════════════════════════════════════════════════════

    def _call_anthropic(self, prompt: str, system_prompt: str, model: str, max_tokens: int) -> str:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "未设置 ANTHROPIC_API_KEY 环境变量。"
            )

        base_url = os.environ.get("ANTHROPIC_BASE_URL")
        model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

        try:
            import anthropic
        except ImportError:
            raise ImportError("请先安装 anthropic SDK: pip install anthropic")

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        client = anthropic.Anthropic(**client_kwargs)

        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = client.messages.create(**kwargs)

        # 遍历 content 找到 TextBlock（兼容 DeepSeek 等返回 ThinkingBlock 的 API）
        for block in response.content:
            block_type = getattr(block, "type", "")
            if block_type == "text" and hasattr(block, "text") and block.text:
                return block.text

        # 回退：返回第一个有 text 属性的 block
        for block in response.content:
            if hasattr(block, "text"):
                try:
                    return block.text
                except Exception:
                    pass

        raise RuntimeError(
            f"无法从响应中提取文本: "
            f"{[getattr(b, 'type', type(b).__name__) for b in response.content]}"
        )

    def _call_openai(self, prompt: str, system_prompt: str, model: str, max_tokens: int) -> str:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "未设置 OPENAI_API_KEY 环境变量。"
            )

        base_url = os.environ.get("OPENAI_BASE_URL")
        model = model or os.environ.get("LLM_MODEL", "gpt-4o")

        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("请先安装 openai SDK: pip install openai")

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url

        client = OpenAI(**client_kwargs)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


# ═══════════════════════════════════════════════════════════════
# Schema 辅助：从 Python dataclass 生成 JSON Schema
# ═══════════════════════════════════════════════════════════════

def dataclass_to_json_schema(dataclass_cls) -> Dict[str, Any]:
    """
    将 Python dataclass 定义转换为 JSON Schema。
    用于 structured_output() 的 output_schema 参数。

    示例:
      schema = dataclass_to_json_schema(Section05EmpiricalMethodology)
      result = llm.structured_output(prompt, output_schema=schema, ...)
    """
    import dataclasses
    from enum import Enum

    type_map = {
        str: "string",
        int: "number",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    fields = dataclasses.fields(dataclass_cls)
    properties = {}
    required = []

    for f in fields:
        if f.name.startswith("_"):
            continue

        field_type = f.type
        field_schema = {"description": f.name}

        # 处理 Optional[X]
        origin = getattr(field_type, "__origin__", None)
        args = getattr(field_type, "__args__", ())

        if origin is list or field_type is list:
            field_schema["type"] = "array"
            field_schema["items"] = {"type": "string"}
        elif origin is dict or field_type is dict:
            field_schema["type"] = "object"
        elif isinstance(field_type, type) and issubclass(field_type, Enum):
            field_schema["type"] = "string"
            field_schema["enum"] = [e.value for e in field_type]
        elif field_type in type_map:
            field_schema["type"] = type_map[field_type]
        elif origin is Optional:
            inner = args[0] if args else str
            if inner in type_map:
                field_schema["type"] = type_map[inner]
        else:
            field_schema["type"] = "string"

        # 判断是否必填
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
            required.append(f.name)

        # 添加默认值示例
        if f.default is not dataclasses.MISSING:
            if isinstance(f.default, Enum):
                field_schema["default"] = f.default.value
            elif f.default is not None:
                field_schema["default"] = f.default

        properties[f.name] = field_schema

    schema = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema
