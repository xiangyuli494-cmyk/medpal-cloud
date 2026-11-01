# 便捷入口。Windows 下没有 make 时用 tools/dev.sh。
PY ?= python
export PYTHONIOENCODING := utf-8

.PHONY: help install seed api test lint check pr eval all clean

help:
	@echo "make install  - 装依赖(含 dev)"
	@echo "make seed     - 灌合成样本与本体种子"
	@echo "make api      - 起 API (http://127.0.0.1:8000)"
	@echo "make test     - pytest"
	@echo "make lint     - ruff check"
	@echo "make check    - 边界 + 禁用语检查"
	@echo "make pr       - 提交前自检: lint + check + test（约 20 秒）"
	@echo "make eval     - 跑评测"
	@echo "make all      - lint + check + test + eval"

install:
	$(PY) -m pip install -e ".[dev]"

seed:
	$(PY) -m app.seed

api:
	$(PY) -m uvicorn app.main:app --reload --port 8000

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check .

check:
	$(PY) tools/check_boundaries.py
	$(PY) tools/check_guard_words.py

pr: lint check test

eval:
	$(PY) eval/run_eval.py

all: lint check test eval

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
