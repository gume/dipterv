FROM mcr.microsoft.com/playwright:v1.64.0-noble

# Copy uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set up virtual environment using uv
RUN uv venv /venv
ENV PATH="/venv/bin:$PATH"

# Install Playwright and Python libraries into the virtual environment using uv
RUN uv pip install --no-cache-dir playwright && \
    playwright install chromium

RUN uv pip install --no-cache-dir openpyxl pandas pypdf pymupdf pdfplumber language_tool_python google-genai openai pydantic && \

WORKDIR /app

CMD ["tail", "-f", "/dev/null"]
