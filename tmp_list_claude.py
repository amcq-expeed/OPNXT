from pathlib import Path
base = Path(r"c:\\Users\\AdamThacker\\Projects\\OPNXT\\docs\\Claude")
for path in base.glob("*.txt"):
    print(path.name)
