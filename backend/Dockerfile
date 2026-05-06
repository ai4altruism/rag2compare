FROM python:3.12-slim

WORKDIR /app

# System libraries Docling and PyMuPDF need at runtime. The slim base
# omits the X11 / GL / fontconfig stack, which the layout-analysis
# pipeline tries to load and dies with `libxcb.so.1: cannot open shared
# object file` on the first parse.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libxcb1 \
        libxext6 \
        libsm6 \
        libxrender1 \
        libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/
COPY scripts/ scripts/

# Install dependencies
RUN uv pip install --system --no-cache .

# Create data directory
RUN mkdir -p /app/data/uploads

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
