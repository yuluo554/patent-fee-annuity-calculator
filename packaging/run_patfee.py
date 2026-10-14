"""PyInstaller 入口启动器：绝对导入调 patfee.cli.main。

cli.py 内部使用相对导入，作为 Analysis 入口脚本时没有父包上下文
（``attempted relative import with no known parent package``），故经本
启动器以包成员方式触发（CLI 与 GUI 两个 exe 共用同一 main）。
"""

import sys

from patfee.cli import main

if __name__ == "__main__":
    sys.exit(main())
