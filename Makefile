.PHONY: install download build test

install:
	uv sync --dev

download:
	@mkdir -p data/pdfs
	curl -L https://vsnr.org/wp-content/uploads/2021/11/NION-1.pdf -o data/pdfs/grammar.pdf
	curl -L https://vsnr.org/wp-content/uploads/2021/11/NION-Glossary-2011.pdf -o data/pdfs/glossary.pdf
	curl -L https://vsnr.org/wp-content/uploads/2021/11/NION-II-2011.pdf -o data/pdfs/reader.pdf

build:
	uv run nion-build

test:
	uv run pytest
