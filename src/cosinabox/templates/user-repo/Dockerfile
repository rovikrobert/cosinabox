# Prebuilt base with Python 3.11 + cosinabox[google] already installed.
# Floating major.minor tag — you get patch updates on redeploy, minor
# bumps require opting in (`:0.2`). For reproducible builds, pin a full
# version: `FROM ghcr.io/rovikrobert/cosinabox-runtime:0.1.2`.
FROM ghcr.io/rovikrobert/cosinabox-runtime:0.1

WORKDIR /app

# Resolve the user-repo's pyproject pin on top of the baked install.
# `--upgrade-strategy eager` is critical: without it, pip's default
# (only-if-needed) sees that the baked cosinabox version satisfies the
# pin (e.g. 0.1.2 satisfies >=0.1,<0.2) and skips the upgrade, even
# when the floating :0.1 image has been retagged to a newer patch.
# Railway's docker layer cache holds the resolved base-image digest
# across redeploys, so without this flag a deploy can stay frozen on
# an older patch indefinitely. Eager forces pip to resolve cosinabox
# (and its deps) against PyPI on every build.
COPY pyproject.toml /app/
RUN pip install --no-cache-dir --upgrade --upgrade-strategy eager -e .

COPY . /app

CMD ["python", "main.py"]
