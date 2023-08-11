ARG PYTHON_VERSION

FROM python:${PYTHON_VERSION}-bookworm

ARG TEST_AUTH_TOKEN
ARG TEST_CACHE_NAME

ENV TEST_AUTH_TOKEN=${TEST_AUTH_TOKEN}
ENV TEST_CACHE_NAME=${TEST_CACHE_NAME}

RUN apt-get update && apt-get install -y \
    curl git \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sL https://install.python-poetry.org | python - -y --version 1.3.1 \
    && mkdir /root/app

WORKDIR /root/app
RUN git clone https://github.com/vpolikarpov-akvelon/client-sdk-python.git /root/app

RUN ls -l && /root/.local/bin/poetry config virtualenvs.in-project true && /root/.local/bin/poetry install
RUN if [ "${PYTHON_VERSION}" = "3.7" ]; then /root/.local/bin/poetry run mypy src tests; fi

RUN /root/.local/bin/poetry run flake8 src tests \
    && /root/.local/bin/poetry run black src tests --check --diff \
    && /root/.local/bin/poetry run isort . --check --diff

RUN /root/.local/bin/poetry run pytest -v -p no:sugar tests/momento/cache_client/test_control.py
