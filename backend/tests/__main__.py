"""核心逻辑测试入口（零三方依赖）：cd backend && python3 -m tests"""
import sys
import unittest
from pathlib import Path

# 让 `micall.*` 可导入（src 布局）。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

suite = unittest.TestLoader().discover(
    str(Path(__file__).resolve().parent), pattern="test_*.py"
)
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
