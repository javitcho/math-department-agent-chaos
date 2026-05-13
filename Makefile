PYTHON     = python3
AGENTS_DIR = math-agents
WEB_DIR    = $(AGENTS_DIR)/web

.PHONY: serve server web install web-install

# Start both backend (uvicorn) and frontend (Vite) in parallel
serve: server web

server:
	cd $(AGENTS_DIR) && $(PYTHON) main.py --serve --no-open

web:
	cd $(WEB_DIR) && npm run dev

# Install all dependencies
install: pip-install web-install

pip-install:
	pip install -r $(AGENTS_DIR)/requirements.txt

web-install:
	cd $(WEB_DIR) && npm install
