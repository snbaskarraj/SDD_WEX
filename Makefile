PYTHON := $(shell command -v python3.12 || command -v python3)
PORT ?= 8000

.PHONY: setup test app ask data clean-data

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -r requirements.txt

test:
	.venv/bin/pytest -q

app:
	.venv/bin/uvicorn fleetline.api:app --app-dir src --host 127.0.0.1 --port $(PORT) --reload

ask:
	.venv/bin/python scripts/ask.py "$(Q)"

data:
	.venv/bin/python -m fleetline.generate

clean-data:
	rm -f data/*.parquet
