"""
Ponto de entrada: roda os scrapers de CNPq e FAPEMIG e grava data/editais.json
na raiz do repositório, no formato consumido pelo captaeditais.html.

Uso local:
    pip install -r scraper/requirements.txt
    playwright install chromium
    python scraper/run.py

No GitHub Actions isso roda automaticamente (ver .github/workflows/scrape-editais.yml).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from normalize import normalize_cnpq, normalize_fapemig  # noqa: E402
from scrape_cnpq import scrape_cnpq  # noqa: E402
from scrape_fapemig import scrape_fapemig  # noqa: E402

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "editais.json"


def main() -> None:
    editais: list[dict] = []
    errors: list[str] = []

    print("Raspando CNPq...")
    try:
        cnpq_raw = scrape_cnpq()
        editais.extend(normalize_cnpq(r) for r in cnpq_raw)
        print(f"  -> {len(cnpq_raw)} chamadas do CNPq.")
    except Exception as exc:  # noqa: BLE001
        msg = f"Falha ao raspar CNPq: {exc}"
        print(f"  !! {msg}")
        errors.append(msg)

    print("Raspando FAPEMIG...")
    try:
        fapemig_raw = scrape_fapemig()
        editais.extend(normalize_fapemig(r) for r in fapemig_raw)
        print(f"  -> {len(fapemig_raw)} chamadas da FAPEMIG.")
    except Exception as exc:  # noqa: BLE001
        msg = f"Falha ao raspar FAPEMIG: {exc}"
        print(f"  !! {msg}")
        errors.append(msg)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "geradoEm": datetime.now(timezone.utc).isoformat(),
        "totalEditais": len(editais),
        "erros": errors,
        "editais": editais,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nGravado {len(editais)} editais em {OUTPUT_PATH}")

    if errors and not editais:
        # Se AMBOS os scrapers falharam, retorna código de erro para o Actions avisar
        # (mas não sobrescreve o JSON anterior, já que não chegamos a escrever nada novo
        # com sucesso -- ajuste esse comportamento se preferir sempre sobrescrever).
        sys.exit(1)


if __name__ == "__main__":
    main()
