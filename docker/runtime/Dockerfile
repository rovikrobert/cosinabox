# cosinabox/runtime — prebuilt base image with Python 3.11 + cosinabox[google].
#
# Build: docker buildx build -t ghcr.io/rovikrobert/cosinabox-runtime:dev .
# Published by the release workflow on every non-prerelease v*.*.* tag.
#
# Usage from a user-repo:
#   FROM ghcr.io/rovikrobert/cosinabox-runtime:0.1
#   COPY . /app
#   CMD ["python", "main.py"]

FROM python:3.11-slim

# The version to install. The release workflow passes the exact
# cosinabox version being tagged; local dev/CI builds can override.
ARG COSINABOX_VERSION=

# Install a specific cosinabox release from PyPI with the [google] extra.
# Other extras (attio, fireflies, search, consult) can be layered by the
# user-repo's Dockerfile with a cheap `RUN pip install cosinabox[...]`.
RUN if [ -n "$COSINABOX_VERSION" ]; then \
      pip install --no-cache-dir "cosinabox[google]==$COSINABOX_VERSION"; \
    else \
      pip install --no-cache-dir "cosinabox[google]"; \
    fi

WORKDIR /app

# user-repo is expected to provide main.py and config files. The
# default CMD mirrors the user-repo template's entry point.
CMD ["python", "main.py"]
