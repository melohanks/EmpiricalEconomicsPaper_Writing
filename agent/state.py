import os
import json

class StateManager:
    """
    负责加载与暂存科研写作流程中，各阶段共享状态参数的序列化管理器。
    """
    def __init__(self, state_file_path: str = "workspace/state.json"):
        self.state_file_path = state_file_path
        os.makedirs(os.path.dirname(self.state_file_path), exist_ok=True)

    def load_state(self) -> dict:
        """
        读取现有状态，如不存在则返回空 dict
        """
        if not os.path.exists(self.state_file_path):
            return {}
        try:
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[StateManager] 加载历史运行状态异常: {e}")
            return {}

    def save_state(self, context: dict):
        """
        保存当前的 Agent 运行状态字典，排除冗余大型载荷。
        """
        # 对 context 中的超大变量（如抓取到的整站 HTML/大型原始列表）进行清洗后保存，节约空间。
        serializable = {k: v for k, v in context.items() if not k.startswith("_") and k != "raw_papers"}
        try:
            with open(self.state_file_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[StateManager] 保存运行状态失败: {e}")
