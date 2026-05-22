"""可选代码生成（类型桩与薄封装）。"""

from entpy.codegen.stubgen import generate_stubs
from entpy.codegen.thin import generate_thin_wrappers

__all__ = ["generate_stubs", "generate_thin_wrappers"]
