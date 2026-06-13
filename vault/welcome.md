# Welcome to the Vault

This is your personal document vault, powered by Claude Dispatch.

Documents saved here by Dispatch appear on this site within seconds of a push — no redeployment needed.

## How documents get here

Set up a Dispatch shortcut called **"save to vault"** with this instruction:

> Write the content to a `.md` file inside `C:\Users\marcu\website\mkmsite.github.io\vault\`, add an entry for it in `vault\index.json` (title, file name, today's date), then run `git add . && git commit -m "vault: new doc" && git push` in that directory.

After Dispatch runs that, the document appears here within ~10 seconds.

## Document format

Dispatch should write standard markdown. Everything renders cleanly — headings, code blocks, tables, lists, blockquotes.

```python
# Example code block
def hello():
    return "renders great"
```

| Column A | Column B |
|----------|----------|
| Value 1  | Value 2  |

## Notes

- The password is session-based — closing the tab locks the vault again
- Documents are fetched live from GitHub, so they update the moment a push lands
- Share the passphrase with anyone who should have read access
