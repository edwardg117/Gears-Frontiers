import os
import re
import secrets

file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quests", "chapters", "challenges.snbt")

if not os.path.exists(file_path):
    print(f"Error: File not found: {file_path}")
    exit(1)

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

used_ids = set()

def unique_hex_id():
    while True:
        hex_id = secrets.token_hex(8).upper()
        if hex_id not in used_ids:
            used_ids.add(hex_id)
            return hex_id

new_content = re.sub(r'"REPLACEME"', lambda _: f'"{unique_hex_id()}"', content)

with open(file_path, "w", encoding="utf-8", newline="") as f:
    f.write(new_content)

print(f"Done! Replaced {len(used_ids)} occurrence(s) with unique 16-digit hex IDs.")

