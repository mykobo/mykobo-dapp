FROM node:lts AS js

WORKDIR /js-app
COPY wallet-connect ./
RUN npm install
RUN npm run build


FROM python:3.13-alpine3.21 AS runtime

# Set working directory
WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Copy application code
COPY app/ ./app/
COPY boot.sh run.py ./
COPY extract-wagmi-script.sh ./app/

# Copy javascript resources from wallet connect build
COPY --from=js /js-app/static ./app/static
RUN ./app/extract-wagmi-script.sh ./app/static/index.html ./app/templates/base.html
RUN rm ./app/static/index.html
RUN rm ./app/extract-wagmi-script.sh

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Expose port (default to 8000, can be overridden)
EXPOSE 8000

# Make boot.sh executable
RUN chmod +x boot.sh

# Run the application
CMD ["./boot.sh"]
