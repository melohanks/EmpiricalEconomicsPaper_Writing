class BaseSkill:
    """
    原子技能/工具的基类。
    所有原子化、可服用、无状态的技能（如特定网站爬取、特定格式保存、LLM特定任务调用）均需继承此类。
    """
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    def execute(self, *args, **kwargs):
        """
        执行具体技能动作。
        子类重写此方法。不应当在技能内部维护全局运行状态。
        """
        raise NotImplementedError("每个技能必须实现 execute 方法")
