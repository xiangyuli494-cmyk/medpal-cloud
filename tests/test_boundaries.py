"""边界检查本身就是被测试对象：它红了，架构就破了。"""

from __future__ import annotations

from pathlib import Path

from tools.check_boundaries import check as check_boundaries
from tools.check_guard_words import check as check_guard_words

REPO = Path(__file__).resolve().parents[1]


def test_core_has_no_app_or_vendor_leak():
    assert check_boundaries(REPO) == []


def test_no_guard_words_in_user_facing_copy():
    assert check_guard_words(REPO) == []
