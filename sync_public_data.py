from pathlib import Path
import shutil


PUBLIC_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PUBLIC_DIR.parent

DATA_FILES = [
    PROJECT_DIR / "ship" / "ship_order_summary.csv",
    PROJECT_DIR / "ship" / "ship_order_targets.csv",
    PROJECT_DIR / "ship" / "ship_market_cap.csv",
]


def main():
    copied = []
    for source in DATA_FILES:
        if not source.exists():
            print(f"skip missing: {source}")
            continue
        target = PUBLIC_DIR / source.name
        shutil.copy2(source, target)
        copied.append(target.name)
        print(f"copied: {source} -> {target}")

    if not copied:
        raise SystemExit("동기화할 CSV 파일이 없습니다.")

    print("public data synced:", ", ".join(copied))


if __name__ == "__main__":
    main()
