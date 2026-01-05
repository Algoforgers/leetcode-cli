# leetcli

Small terminal LeetCode problem fetcher in Python.

## Usage

```bash
lc search "two sum"
lc get 1
lc get "All Possible Full Binary Trees"
lc open 1
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
