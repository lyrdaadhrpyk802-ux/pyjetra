#!/data/data/com.termux/files/usr/bin/env bash
# ============================================================
#  publish.sh - publish pyjetra v2.0.6 to PyPI and GitHub
#  Run from the project root on Termux:
#     cd /storage/emulated/0/pyjetra-merged
#     bash publish.sh
# ============================================================
set -e

PROJECT_DIR="/storage/emulated/0/pyjetra-merged"
cd "$PROJECT_DIR"

VERSION="2.0.7"

echo "=========================================="
echo "  pyjetra v${VERSION} - publish pipeline"
echo "=========================================="

# ---------- 0. Pre-flight checks ----------
echo
echo "[0/6] Pre-flight checks..."
command -v python >/dev/null 2>&1 || { echo "FAIL: python not found"; exit 1; }
command -v git    >/dev/null 2>&1 || { echo "FAIL: git not found";    exit 1; }

if [ -z "$PYPI_API_TOKEN" ]; then
    echo "FAIL: PYPI_API_TOKEN env var is not set."
    echo "      Get one at: https://pypi.org/manage/account/token/"
    echo "      Scope: 'Entire account' or just the 'pyjetra' project."
    echo "      Then:  export PYPI_API_TOKEN='pypi-xxxxxxxxxxxxxxxx'"
    exit 1
fi

# ---------- 1. Cleanup artifacts that must NOT ship ----------
echo
echo "[1/6] Cleaning build artifacts..."
rm -rf build dist *.egg-info pyjetra.egg-info
rm -rf .pytest_cache .mypy_cache .ruff_cache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete

# Remove leftover .bak files in data/ (they are gitignored but may exist on disk)
rm -f data/*.bak data/*.bak_* 2>/dev/null || true

# Remove the stray typed.py if it exists (PEP 561 only needs py.typed)
rm -f pyjetra/botapi/typed.py 2>/dev/null || true

# ---------- 2. Apply the small cleanups (idempotent) ----------
echo
echo "[2/6] Applying cleanups..."

# 2a. Add py.typed to botapi if missing (PEP 561 marker)
if [ ! -f pyjetra/botapi/py.typed ]; then
    : > pyjetra/botapi/py.typed
    echo "    + created pyjetra/botapi/py.typed"
fi

# 2b. Move live test scripts (they need a real bot token, not unit tests)
mkdir -p examples_live
for f in test_sync test_async test_advanced_buttons test_registration_fsm test_error_handling; do
    if [ -f "tests/botapi/$f.py" ]; then
        mv "tests/botapi/$f.py" "examples_live/$f.py"
        echo "    + moved tests/botapi/$f.py -> examples_live/$f.py"
    fi
done

# ---------- 3. Run tests ----------
echo
echo "[3/6] Running offline test suite..."
python -m pip install --quiet pytest
python -m pytest tests/botapi/ --tb=short

# ---------- 4. Build sdist + wheel ----------
echo
echo "[4/6] Building package..."
python -m pip install --quiet build twine
rm -rf build dist *.egg-info
python -m build --no-isolation --wheel
python -m twine check dist/*

echo
echo "    Built artifacts:"
ls -la dist/

# ---------- 5. Upload to PyPI ----------
echo
echo "[5/6] Uploading to PyPI..."
python -m twine upload --skip-existing \
    --username __token__ \
    --password "$PYPI_API_TOKEN" \
    --non-interactive \
    dist/*

echo
echo "    PyPI page: https://pypi.org/project/pyjetra/"

# ---------- 6. Commit, tag and push to GitHub ----------
echo
echo "[6/6] Committing and pushing to GitHub..."
git add -A
git status --short

# Commit only if there are staged changes
if ! git diff --cached --quiet; then
    git commit -m "Release v${VERSION}

- Bump version to ${VERSION} in pyproject.toml and all __init__/dev_info
- Add pyjetra/botapi/py.typed (PEP 561 marker)
- Remove stray pyjetra/botapi/typed.py
- Move live test scripts to examples_live/
- Fix misleading inputChatUploadedPhoto comment
- Expand .gitignore for build/test artifacts
"
fi

# Tag the release (force re-create if it already exists locally)
git tag -d "v${VERSION}" 2>/dev/null || true
git tag -a "v${VERSION}" -m "Release v${VERSION}"

# Push main and tags
git push origin main
git push origin "v${VERSION}"

echo
echo "=========================================="
echo "  DONE!"
echo "  PyPI:   https://pypi.org/project/pyjetra/"
echo "  GitHub: https://github.com/lyrdaadhrpyk802-ux/pyjetra"
echo "  Tag:    v${VERSION}"
echo "=========================================="
echo
echo "Verify the install from a clean shell:"
echo "  pip install 'pyjetra[all]'"
echo "  python -c 'import pyjetra; print(pyjetra.__version__)'"