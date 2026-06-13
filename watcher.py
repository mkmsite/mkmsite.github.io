import os, json, shutil, time, subprocess
from datetime import date

INBOX = r"C:\VAULT"
VAULT = r"C:\Users\marcu\website\mkmsite.github.io\vault"
REPO  = r"C:\Users\marcu\website\mkmsite.github.io"
INDEX = os.path.join(VAULT, "index.json")

def get_title(filepath):
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#"):
                return line.lstrip("#").strip()
            if line:
                return line
    return os.path.splitext(os.path.basename(filepath))[0].replace("-", " ").title()

def process():
    files = [f for f in os.listdir(INBOX) if f.lower().endswith(".md")]
    if not files:
        return

    with open(INDEX, encoding="utf-8") as f:
        data = json.load(f)

    added = []
    for fname in files:
        src = os.path.join(INBOX, fname)
        dst = os.path.join(VAULT, fname)

        title = get_title(src)
        shutil.copy2(src, dst)
        os.remove(src)

        if not any(d["file"] == fname for d in data["documents"]):
            data["documents"].insert(0, {
                "title": title,
                "file":  fname,
                "date":  date.today().isoformat()
            })
        added.append(fname)
        print(f"  + {fname}  →  \"{title}\"")

    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    subprocess.run(["git", "-C", REPO, "add", "vault/"], check=True)
    subprocess.run(["git", "-C", REPO, "commit", "-m", f"vault: add {', '.join(added)}"], check=True)
    subprocess.run(["git", "-C", REPO, "push"], check=True)
    print(f"  pushed — live in ~10 seconds\n")

print("Watching C:\\VAULT  (Ctrl+C to stop)\n")
while True:
    try:
        process()
    except Exception as e:
        print(f"  error: {e}")
    time.sleep(10)
