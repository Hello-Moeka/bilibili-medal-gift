import os
import sys
import pytest

# 让测试能 import src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_log_file(tmp_path):
    """提供一个临时 sent_log.json 路径，测试间互不干扰。"""
    return str(tmp_path / "sent_log.json")