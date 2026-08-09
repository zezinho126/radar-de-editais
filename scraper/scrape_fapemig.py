"""
Scraper de chamadas da FAPEMIG.

Diferente do CNPq, o site da FAPEMIG (fapemig.br) é uma aplicação Nuxt/Vue:
o HTML inicial vem quase vazio e a lista de chamadas é montada em JavaScript
depois de uma chamada interna à API (algo como /api/calls/...). Por isso
usamos Playwright (navegador headless) para renderizar a página de verdade
antes de extrair o conteúdo — requests+bs4 não é suficiente aqui.

Estratégia de extração: em vez de depender de nomes de classes CSS (que
tendem a mudar em builds do Nuxt e quebrar o scraper silenciosamente),
extraímos o TEXTO já renderizado da página e cortamos em blocos usando o
padrão fixo que a FAPEMIG repete em cada card:

    "Aberta · <Linha de fomento> · <Público-alvo> · <Área(s)> ·
     Data início de submissão · DD de mmm. de AAAA ·
     Data fim de submissão · DD de mmm. de AAAA ·
     Resultado (Previsto) DD de mmm. de AAAA (prev.) ·
     Valor (R$) R$ X milhões · Saiba Mais"

Esse padrão textual é mais estável entre atualizações do site do que os
seletores CSS. Se a FAPEMIG mudar a redação, ajuste as regexes abaixo.

Requer: playwright (e `playwright install chromium` uma vez).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import sync_playwright

LISTING_URL = "https://fapemig.br/oportunidades/chamadas-e-editais"

MONTHS_PT = {
    "jan": "01", "fev": "02", "mar": "03", "abr": "04", "mai": "05", "jun": "06",
    "jul": "07", "ago": "08", "set": "09", "out": "10", "nov": "11", "dez": "12",
}

# Ex.: "13 de jul. de 2026" -> 13/07/2026
DATE_PT_RE = re.compile(r"(\d{1,2})\s*de\s*([a-zç]{3})\.?\s*de\s*(\d{4})", re.IGNORECASE)


@dataclass
class RawEdital:
    fonte: str
    titulo: str
    url: str
    descricao: str = ""
    status: Optional[str] = None
    linha_fomento: Optional[str] = None
    publico_alvo: Optional[str] = None
    valor: Optional[str] = None
    inscricao_inicio: Optional[str] = None
    inscricao_fim: Optional[str] = None
    resultado_previsto: Optional[str] = None
    documentos: list[str] = field(default_factory=list)


def _to_iso_br_date(raw: str) -> Optional[str]:
    m = DATE_PT_RE.search(raw)
    if not m:
        return None
    day, month_pt, year = m.groups()
    month = MONTHS_PT.get(month_pt.lower()[:3])
    if not month:
        return None
    return f"{int(day):02d}/{month}/{year}"


def _click_tab_abertas(page) -> None:
    """Clica na aba/filtro 'Abertas' se ela existir, para já carregar só as chamadas abertas."""
    for text in ["Abertas", "Aberta"]:
        try:
            locator = page.get_by_text(text, exact=False).first
            if locator.count() if hasattr(locator, "count") else False:
                locator.click(timeout=3000)
                page.wait_for_timeout(1500)
                return
        except Exception:
            continue


def scrape_fapemig(headless: bool = True, timeout_ms: int = 30000) -> list[RawEdital]:
    results: list[RawEdital] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(user_agent="CaptaEditais/1.0 scraper de editais publicos")
        page.goto(LISTING_URL, timeout=timeout_ms, wait_until="networkidle")

        _click_tab_abertas(page)
        page.wait_for_timeout(2000)  # margem para o Nuxt terminar de montar os cards

        # Pega os links de cada chamada (para título + URL) e o texto completo da página
        # (para os metadados, via regex, já que os cards não têm um seletor CSS estável).
        cards = page.locator("a[href*='/oportunidades/chamadas-e-editais/']")
        count = cards.count()

        seen_hrefs: set[str] = set()
        for i in range(count):
            el = cards.nth(i)
            href = el.get_attribute("href") or ""
            title = (el.inner_text() or "").strip()
            if not href or not title or href.rstrip("/").endswith("chamadas-e-editais"):
                continue
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)

            # Sobe até um container "de card" pegando um ancestral razoável e lê o texto dele.
            try:
                block_text = el.locator(
                    "xpath=ancestor::*[self::article or self::div][1]"
                ).inner_text(timeout=2000)
            except Exception:
                block_text = title

            status = "Aberta" if re.search(r"\bAberta\b", block_text) else (
                "Encerrada" if re.search(r"\bEncerrada\b", block_text) else None
            )

            linha = re.search(r"Linha de fomento:\s*([^\n]+)", block_text)
            publico = re.search(r"Público[- ]alvo:\s*([^\n]+)", block_text)
            valor = re.search(r"Valor\s*\(R\$\)\s*([^\n·]+)", block_text) or re.search(
                r"Valor da chamada:\s*([^\n]+)", block_text
            )

            start_m = re.search(r"(?:Data início de submissão|Lançamento da chamada)\D*(\d{1,2}\s*de\s*[a-zç]{3}\.?\s*de\s*\d{4})", block_text, re.IGNORECASE)
            end_m = re.search(r"(?:Data fim de submissão|Limite para submissão)\D*(\d{1,2}\s*de\s*[a-zç]{3}\.?\s*de\s*\d{4})", block_text, re.IGNORECASE)
            result_m = re.search(r"Divulgação do Resultado\D*(\d{1,2}\s*de\s*[a-zç]{3}\.?\s*de\s*\d{4})", block_text, re.IGNORECASE)

            full_url = href if href.startswith("http") else f"https://fapemig.br{href}"

            results.append(
                RawEdital(
                    fonte="FAPEMIG",
                    titulo=title,
                    url=full_url,
                    descricao=block_text[:600],
                    status=status,
                    linha_fomento=linha.group(1).strip() if linha else None,
                    publico_alvo=publico.group(1).strip() if publico else None,
                    valor=valor.group(1).strip() if valor else None,
                    inscricao_inicio=_to_iso_br_date(start_m.group(1)) if start_m else None,
                    inscricao_fim=_to_iso_br_date(end_m.group(1)) if end_m else None,
                    resultado_previsto=_to_iso_br_date(result_m.group(1)) if result_m else None,
                )
            )

        browser.close()

    # Mantém só as que conseguimos identificar como abertas (ou sem status detectado,
    # para não perder itens quando o texto vier em formato inesperado).
    return [r for r in results if r.status != "Encerrada"]


if __name__ == "__main__":
    import json

    editais = scrape_fapemig(headless=True)
    print(f"{len(editais)} chamadas da FAPEMIG encontradas (abertas).")
    print(json.dumps([e.__dict__ for e in editais], ensure_ascii=False, indent=2)[:3000])
