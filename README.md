# pikdirect

[![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-managed-6C47FF.svg)](https://docs.astral.sh/uv/)
[![CLI](https://img.shields.io/badge/interface-CLI-2ea44f.svg)](#-usage)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

Resolve direct download URLs from PikPak share links with a small CLI.

`pikdirect` logs into your PikPak account, temporarily saves the shared content to your PikPak Cloud Drive, resolves the
direct download URL for each file, and can optionally delete the saved copy right after that.

It supports both single-file and shared-folder links. The tool only resolves URLs. It does not download the files
itself.

## ✨ What It Does

- log in with your PikPak username and password
- save and reuse a local auth session in `.pikdirect-auth.json`
- auto-refresh the session when possible
- resolve direct URLs for single files or whole shared folders
- optionally delete the temporary saved copy after URL resolution

## 🚀 Quick Start

Recommended setup:

```bash
git clone https://github.com/gordonhwc/pikdirect.git
cd pikdirect
uv sync
```

Then run:

```bash
uv run pikdirect \
  --username "you@example.com" \
  "https://mypikpak.com/s/your-share-id"
```

If you omit `--password`, `pikdirect` will prompt for it securely.

If PikPak requires captcha verification, `pikdirect` prints a challenge URL and waits for the callback URL from the
browser verification flow.

## 🧭 Usage

```bash
uv run pikdirect \
  --username "you@example.com" \
  --password "your-password" \
  "https://mypikpak.com/s/your-share-id"
```

Show the CLI help:

```bash
uv run pikdirect --help
```

Keep the saved copy in your drive instead of deleting it:

```bash
uv run pikdirect \
  --username "you@example.com" \
  --no-delete \
  "https://mypikpak.com/s/your-share-id"
```

## 📝 Output

- single file share: prints the direct URL
- shared folder: prints one line per file as `relative_path<TAB>direct_url`

When `--delete` is enabled, the resolved URLs may stop working after the temporary saved copy is removed.

## 🔐 Captcha Verification

When the CLI prints a PikPak captcha challenge URL:

1. Open the challenge URL in a browser.
2. Open DevTools and switch to the Network tab before completing verification.
3. Complete the verification in the browser.
4. In Network, filter for `xlaccsdk01://`.
5. Select the callback request, usually the only result, then right-click it and select `Copy` > `Copy URL`.
6. Paste that callback URL back into the `pikdirect` prompt.

## 🔐 Auth Session

By default, `pikdirect` stores its local auth state in:

```text
.pikdirect-auth.json
```

The session file is local-only and should not be committed.

## ⚠️ Notes

- This project uses non-public PikPak API behavior
- PikPak may change its web or API flow at any time
- The project is not affiliated with PikPak

## 📄 License

Released under the [MIT License](LICENSE).

## 🙏 References

This project was developed with implementation ideas and reverse-engineering references from:

- [AksharDP/pikpak-go](https://github.com/akshardp/pikpak-go)
- [AlistGo/alist](https://github.com/AlistGo/alist)
