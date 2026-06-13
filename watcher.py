import os, json, shutil, time, subprocess
from datetime import date

INBOX = r"C:\VAULT"
VAULT = r"C:\Users\marcu\website\mkmsite.github.io\vault"
REPO  = r"C:\Users\marcu\website\mkmsite.github.io"
INDEX = os.path.join(VAULT, "index.json")

TEXT_EXTS = {'.md', '.txt', '.py', '.js', '.ts', '.json', '.sql',
             '.html', '.css', '.sh', '.bash', '.yaml', '.yml',
             '.toml', '.r', '.java', '.c', '.cpp', '.go', '.rs',
             '.xml', '.rb', '.php', '.csv', '.env', '.ini', '.cfg'}

def get_title(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in TEXT_EXTS:
        try:
            with open(filepath, encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#'):
                        return line.lstrip('#').strip()
                    if line:
                        return line[:80]
        except Exception:
            pass
    base = os.path.splitext(os.path.basename(filepath))[0]
    return base.replace('-', ' ').replace('_', ' ').title()

def process():
    files = [
        f for f in os.listdir(INBOX)
        if not f.startswith('.') and os.path.isfile(os.path.join(INBOX, f))
    ]
    if not files:
        return

    with open(INDEX, encoding='utf-8') as f:
        data = json.load(f)

    added = []
    for fname in files:
        src = os.path.join(INBOX, fname)
        dst = os.path.join(VAULT, fname)

        title = get_title(src)
        shutil.copy2(src, dst)
        os.remove(src)

        existing = next((d for d in data['documents'] if d['file'] == fname), None)
        if existing:
            existing['title'] = title
            existing['date']  = date.today().isoformat()
        else:
            data['documents'].insert(0, {
                'title': title,
                'file':  fname,
                'date':  date.today().isoformat(),
            })

        added.append(fname)
        print(f"  + {fname}  →  \"{title}\"")

    with open(INDEX, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

    subprocess.run(['git', '-C', REPO, 'add', 'vault/'], check=True)
    subprocess.run(['git', '-C', REPO, 'commit', '-m', f'vault: {", ".join(added)}'], check=True)
    subprocess.run(['git', '-C', REPO, 'push'], check=True)
    print(f"  pushed — live in ~10s\n")

print(f"Watching C:\\VAULT for any file type  (Ctrl+C to stop)\n")
while True:
    try:
        process()
    except Exception as e:
        print(f"  error: {e}")
    time.sleep(10)
