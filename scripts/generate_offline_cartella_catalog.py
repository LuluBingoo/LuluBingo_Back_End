from pathlib import Path
import json
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from games.offline_cartellas import get_offline_cartella_catalog


OUTPUT_PATH = PROJECT_ROOT / "OFFLINE_CARTELLA_CATALOG.md"
JSON_OUTPUT_PATH = PROJECT_ROOT / "OFFLINE_CARTELLA_CATALOG.json"
FRONTEND_OUTPUT_PATH = (
    PROJECT_ROOT.parent
    / "LuluBingo_Front_End"
    / "src"
    / "data"
    / "offlineCartellas.ts"
)


def _build_catalog_dict(
    catalog: tuple[tuple[int, ...], ...],
) -> dict[str, list[int]]:
    return {str(idx): list(board) for idx, board in enumerate(catalog, start=1)}


def _write_backend_json(catalog_dict: dict[str, list[int]]) -> None:
    JSON_OUTPUT_PATH.write_text(
        json.dumps(catalog_dict, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_frontend_ts(catalog_dict: dict[str, list[int]]) -> None:
    if not FRONTEND_OUTPUT_PATH.parent.exists():
        return

    content = (
        "// Generated from LuluBingo_Back_End/OFFLINE_CARTELLA_CATALOG.json.\n"
        "// Do not edit manually; regenerate from the backend script.\n\n"
        "export const OFFLINE_CARTELLA_CATALOG: Record<string, number[]> = "
        + json.dumps(catalog_dict, indent=2)
        + ";\n\n"
        + "export const getOfflineCartellaBoard = (cartellaNumber: string | number): number[] | undefined => {\n"
        + "  return OFFLINE_CARTELLA_CATALOG[String(cartellaNumber)];\n"
        + "};\n"
    )
    FRONTEND_OUTPUT_PATH.write_text(content, encoding="utf-8")


def main() -> None:
    catalog = get_offline_cartella_catalog()
    catalog_dict = _build_catalog_dict(catalog)
    lines = [
        "# Offline Cartella Catalog (1-200)",
        "",
        "These are the fixed offline cartellas used for every offline-mode game.",
        "Each cartella is 5x5 with a FREE center and 24 unique numbers randomly chosen from 1 to 75.",
        "",
        "Synced files:",
        "- Backend generator source: `games/offline_cartellas.py`",
        "- Backend catalog data: `OFFLINE_CARTELLA_CATALOG.json`",
        "- Frontend mirror data: `../LuluBingo_Front_End/src/data/offlineCartellas.ts`",
        "",
        "Regenerate all synced files by running `scripts/generate_offline_cartella_catalog.py`.",
        "",
    ]

    for idx, board in enumerate(catalog, start=1):
        lines.append(f"## Cartella {idx}")
        lines.append("")
        lines.append("| 1 | 2 | 3 | 4 | 5 |")
        lines.append("|---|---|---|---|---|")
        for row in range(5):
            row_values: list[str] = []
            for col in range(5):
                value = board[col * 5 + row]
                row_values.append("FREE" if value == 0 else str(value))
            lines.append("| " + " | ".join(row_values) + " |")
        lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    _write_backend_json(catalog_dict)
    _write_frontend_ts(catalog_dict)
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Wrote {JSON_OUTPUT_PATH}")
    if FRONTEND_OUTPUT_PATH.parent.exists():
        print(f"Wrote {FRONTEND_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
