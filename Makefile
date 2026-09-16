.PHONY: install browsers demo-app test discovery replay offline-demo

install:
	python -m pip install -e ".[dev]"

browsers:
	python -m playwright install chromium

demo-app:
	python -m app.legacy_app.app

test:
	pytest -q

discovery:
	python scripts/run_discovery.py --goal 'Look up member $${member_id} and read the current savings balance' --target http://127.0.0.1:8001 --input member_id=12345

replay:
	python scripts/run_replay.py --artifact evidence/example_capability.json --input member_id=12345

offline-demo:
	python scripts/run_offline_demo.py
