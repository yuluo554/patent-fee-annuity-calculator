"""patfee —— 专利年费与费减合规计算工作台。

分层纪律（依赖方向单向向下）：

    表现层（cli / gui）
      → 编排层（calc.pipeline，唯一业务编排源）
        → 领域层（calc.* 引擎，纯 Decimal，零第三方依赖）
          → 规则层（rules.loader / rules.gate，按 scope 门控）
            → 数据层（data/ 冻结规则包与真值库）

全本地处理、零上传、零 API 依赖。
"""

__version__ = "0.2.0"

__all__ = ["__version__"]
