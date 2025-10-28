FROM node:lts AS js

WORKDIR /js-app
COPY wallet-connect ./
RUN npm install
RUN npm run build


FROM python:3.13-bookworm AS runtime

# Set working directory
WORKDIR /app

# Install Poetry
RUN pip install --no-cache-dir poetry

# Configure Poetry to not create virtual environments (we'll use the system Python in the container)
RUN poetry config virtualenvs.create false

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies using Poetry (production dependencies only)
# Using --no-root to avoid installing the project itself since package-mode is false
RUN poetry install --no-interaction --no-ansi

# Copy application code
COPY app/ ./app/
COPY boot.sh run.py ./
COPY retry_worker.py retry_transactions.py entrypoint.sh manage.py run_migrations.py ./
COPY extract-wagmi-script.sh ./app/
COPY merge-css.py ./app/

# Copy migrations folder if it exists (for version-controlled migrations)
# Using wildcard pattern so build doesn't fail if migrations/ doesn't exist
COPY migrations/ ./migrations/

COPY env.sh /docker-entrypoint.d/env.sh
RUN chmod +x /docker-entrypoint.d/env.sh

# Copy javascript resources from wallet connect build
COPY --from=js /js-app/static ./app/static
RUN ./app/extract-wagmi-script.sh ./app/static/index.html ./app/templates/layouts/base.html
RUN rm ./app/static/index.html
RUN rm ./app/extract-wagmi-script.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port (default to 8000, can be overridden)
EXPOSE 8000

# Make scripts executable
RUN chmod +x boot.sh entrypoint.sh retry_worker.py retry_transactions.py

ENTRYPOINT ["/docker-entrypoint.d/env.sh"]
# Default to running web service, can be overridden with: docker run image worker
CMD ["./entrypoint.sh", "web"]
