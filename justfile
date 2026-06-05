set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# One-time setup after cloning: install deps, approve .envrc (macOS/Linux), and install git hooks
setup: _setup-direnv
    uv sync
    uv run prek install --hook-type pre-commit --hook-type pre-push --hook-type post-checkout --overwrite

[unix]
_setup-direnv:
    #!/usr/bin/env sh
    if ! command -v direnv >/dev/null 2>&1; then
        echo ""
        echo "Note: direnv not found (optional — install it for automatic environment activation on cd)."
        echo "  macOS:  brew install direnv"
        echo "  Linux:  sudo apt install direnv"
        echo "  Then add the shell hook: https://direnv.net/docs/hook.html"
        echo ""
    else
        grep -q 'direnv hook' ~/.zshrc 2>/dev/null || grep -q 'direnv hook' ~/.bashrc 2>/dev/null || {
            echo ""
            echo "Note: direnv is installed but not hooked into your shell."
            echo "Add one of the following (as appropriate) to your shell rc file and restart your shell:"
            echo "  ~/.zshrc:   eval \"\$(direnv hook zsh)\""
            echo "  ~/.bashrc:  eval \"\$(direnv hook bash)\""
            echo "  See: https://direnv.net/docs/hook.html"
            echo ""
        }
        direnv allow . || {
            echo ""
            echo "Warning: 'direnv allow .' failed — run it manually after checking your .envrc."
            echo ""
        }
    fi

[windows]
_setup-direnv:
    @echo "Note: direnv is not available on Windows — skipping."

# Format Python code with ruff
fmt:
    uv run ruff format .

# Lint Python code with ruff
lint:
    uv run ruff check .

# Type-check with mypy
typecheck:
    uv run mypy .

# Run test suite
test:
    uv run pytest -v

# Run all quality checks in CI order: format → lint → typecheck → test
check: fmt lint typecheck test

# Configure GitLab project settings: pipeline must succeed before merge, delete branch after merge, squash on by default
configure-gitlab remote:
    #!/usr/bin/env sh
    set -eu
    if ! command -v glab >/dev/null 2>&1; then
        echo "Error: glab not found. Install with: brew install glab && glab auth login"
        exit 1
    fi
    REMOTE_URL=$(git remote get-url {{remote}})
    REMOTE_URL="${REMOTE_URL%.git}"
    case "$REMOTE_URL" in
        http://*|https://*)
            PROJECT=$(echo "$REMOTE_URL" | cut -d/ -f4-)
            ;;
        *)
            PROJECT=$(echo "$REMOTE_URL" | cut -d: -f2)
            ;;
    esac
    ENCODED=$(printf '%s' "$PROJECT" | sed 's|/|%2F|g')
    glab api "projects/$ENCODED" --method PUT \
        --field only_allow_merge_if_pipeline_succeeds=true \
        --field remove_source_branch_after_merge=true \
        --field squash_option=default_on > /dev/null
    echo "Done: GitLab settings updated for $PROJECT"
