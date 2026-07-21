# Releasing BrainMemory-MCP to PyPI

This project ships as the PyPI distribution **`brainmemory-mcp`** and installs a
console script of the same name. The package metadata lives in `pyproject.toml`
(PEP 621) and the version is single-sourced from
`src/brainmemory_mcp/__init__.py` (`__version__`).

## 1. One-time PyPI setup (Trusted Publishing — recommended)

No API tokens or passwords are stored in the repo. Publishing uses PyPI
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) via GitHub OIDC.

1. Create the project on PyPI (first release can also be uploaded manually, see
   below) or pre-register a **pending publisher**:
   PyPI → *Your projects* → *Publishing* → **Add a pending publisher**.
2. Fill in:
   - **PyPI Project Name:** `brainmemory-mcp`
   - **Owner:** `venturo` (GitHub org/user)
   - **Repository:** `BrainMemory-MCP`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
3. In GitHub → *Settings → Environments*, create an environment named `pypi`
   (optionally add required reviewers for a manual approval gate).

After that, the `.github/workflows/publish.yml` workflow uploads to PyPI
automatically — no secrets required.

## 2. Cut a release

1. Bump the version in `src/brainmemory_mcp/__init__.py`:
   ```python
   __version__ = "0.2.0"
   ```
2. Update `docs/changelog/2026/...` and `NOTE.md`.
3. Commit, tag, and push:
   ```bash
   git commit -am "release: v0.2.0"
   git tag v0.2.0
   git push origin main --tags
   ```
4. Create a GitHub Release for the tag (or rely on the tag push). The
   **Publish to PyPI** workflow builds the sdist + wheel, runs `twine check`,
   and publishes to PyPI.

## 3. Manual build & upload (fallback / first release)

If you prefer to publish by hand (e.g. the very first upload before Trusted
Publishing is wired up):

```bash
# Clean previous artifacts
rm -rf dist build src/*.egg-info

# Build in an isolated environment
python3 -m pip install --upgrade build twine
python3 -m build            # -> dist/*.tar.gz and dist/*.whl
python3 -m twine check dist/*

# Upload to TestPyPI first (optional but recommended)
python3 -m twine upload --repository testpypi dist/*

# Upload to the real PyPI
python3 -m twine upload dist/*
```

You will need a PyPI API token for manual uploads:
create one at <https://pypi.org/manage/account/token/> and use
`__token__` as the username.

## 4. Verify the published package

```bash
python3 -m pip install brainmemory-mcp
brainmemory-mcp --version
```

## Checklist

- [ ] `__version__` bumped
- [ ] Changelog + `NOTE.md` updated
- [ ] `python -m build` + `twine check dist/*` pass locally
- [ ] Tag `vX.Y.Z` pushed / GitHub Release published
- [ ] Package visible at <https://pypi.org/project/brainmemory-mcp/>
