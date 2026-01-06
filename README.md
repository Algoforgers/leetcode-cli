# leetcli

Small terminal LeetCode problem fetcher in Python.

## Usage

```bash
lc search "two sum"
lc get 1
lc get "All Possible Full Binary Trees"
lc open 1
lc get 1 --open-images
lc get 1 --imgcat
lc get 1 --mcat
```

## Install globally with pipx

```bash
brew install pipx
pipx ensurepath
pipx install -e /Users/yorqinjon/Desktop/passion/leetcode-cli
```

Open a new terminal, then run:

```bash
lc search "two sum"
```

## Notes

- Cache lives in `./.leetcli-cache` by default; set `LEETCLI_CACHE_DIR` to override.
- Set `LEETCODE_SESSION` to access paid-only content.
- Uses `rich` to render formatted content; images appear as links in the terminal.
- iTerm2 inline images: set `LEETCLI_INLINE_IMAGES=1` (or auto-detected when `TERM_PROGRAM=iTerm.app`).
- iTerm2 + tmux: add `set -g allow-passthrough on` in `~/.tmux.conf` and restart tmux.
- imgcat: install via `brew install imgcat` and use `lc get 1 --imgcat` or set `LEETCLI_IMGCAT=1`.
- mcat: install from `https://github.com/Skardyy/mcat` and use `lc get 1 --mcat` or set `LEETCLI_MCAT=1`.
