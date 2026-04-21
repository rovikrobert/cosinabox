# Prebuilt base with Python 3.11 + cosinabox[google] already installed.
# Floating major.minor tag — you get patch updates on redeploy, minor
# bumps require opting in (`:0.2`). For reproducible builds, pin a full
# version: `FROM ghcr.io/rovikrobert/cosinabox-runtime:0.1.2`.
FROM ghcr.io/rovikrobert/cosinabox-runtime:0.1

WORKDIR /app

# Resolve the user-repo's pyproject pin on top of the baked install.
# No-op when the pin is compatible with the image (fastest case);
# otherwise pip pulls what's needed. Also where extras like [attio]
# or [fireflies] get layered in.
COPY pyproject.toml /app/
RUN pip install --no-cache-dir -e .

COPY . /app

CMD ["python", "main.py"]
