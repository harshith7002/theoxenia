FROM mcr.microsoft.com/devcontainers/base:bookworm

ARG UV_VERSION=0.13.0
ENV UV_NO_MODIFY_PATH=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl --proto '=https' --tlsv1.2 -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" \
      | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh

USER vscode
WORKDIR /workspaces/theoxenia
