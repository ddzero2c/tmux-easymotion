.PHONY: lint test install-dev

install-dev:
	pip install -r requirements-dev.txt

lint:
	ruff check easymotion.py test_easymotion.py
	pyright easymotion.py test_easymotion.py

test:
	pytest test_easymotion.py -v

all: lint test
