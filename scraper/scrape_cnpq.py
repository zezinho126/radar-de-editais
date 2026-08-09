"""
Scraper de chamadas públicas do CNPq.

O site do CNPq (gov.br/cnpq) roda em Plone e devolve HTML já renderizado
no servidor, então dá pra raspar com requests + BeautifulSoup, sem navegador.

Páginas usadas:
  - Abertas para submissão:  /pt-br/chamadas/abertas-para-submissao
  - (Opcional) Em análise:   /pt-br/chamadas/analise-em-andamento

Cada chamada aparece como um bloco iniciado por um <h2><a>Título</a></h2>,
seguido de parágrafo(s) de descrição e uma linha "Inscrições: DD/MM/AAAA a DD/MM/AAAA"
(o texto exato varia: "Inscrições:", "INSCRIÇÕES:", "Recebimento das propostas:" etc,
por isso usamos uma lista de padrões).

Saída: lista de dicts no formato intermediário (ver normalize.py).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.gov.br/cnpq/pt-br/chamadas/abertas-para-submissao"
HEADERS = {
    "User-Agent": "CaptaEditais/1.0 (+https://github.com/SEU_USUARIO/SEU_REPO) scraper de editais publicos"
}
REQUEST_TIMEOUT = 30

# Padrões de data de inscrição observados nas páginas do CNPq.
DATE_RANGE_PATTERNS = [
    re.compile(r"(?:Inscri[cç][oõ]es|Recebimento das propostas)[^:]*:\s*(\d{2}/\d{2}/\d{2,4})\s*a\s*(\d{2}/\d{2}/\d{2,4})", re.IGNORECASE),
]
PUBLISHED_PATTERN = re.compile(r"Publicado em (\d{2}/\d{2}/\d{4})")


@dataclass
class RawEdital:
    fonte: str
    titulo: str
    url: str
    descricao: str = ""
    publicado_em: Optional[str] = None
    inscricao_inicio: Optional[str] = None
    inscricao_fim: Optional[str] = None
    documentos: list[str] = field(default_factory=list)


def _extract_date_range(text: str) -> tuple[Optional[str], Optional[str]]:
    for pattern in DATE_RANGE_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1), m.group(2)
    return None, None


def _fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def _parse_listing(soup: BeautifulSoup) -> list[RawEdital]:
    results: list[RawEdital] = []

    # Cada chamada é um <h2> com um <a> dentro, dentro da área de conteúdo principal.
    headings = soup.select("h2 a[href]")

    for h2_link in headings:
        title = h2_link.get_text(strip=True)
        href = h2_link.get("href", "")
        if not title or "/chamadas/" not in href:
            continue

        # Sobe até o container do card/artigo (heurística: primeiro ancestral
        # que contenha bastante texto e o link "Inscrições"/"Publicado em").
        container = h2_link.find_parent(["article", "div", "li"])
        block_text = container.get_text(" ", strip=True) if container else h2_link.get_text(" ", strip=True)

        # Se o container escolhido for grande demais (ex.: pegou a página toda),
        # caímos para pegar só os próximos elementos-irmãos até o próximo h2.
        if container is None or len(block_text) > 4000:
            block_text = _text_until_next_heading(h2_link)

        published = PUBLISHED_PATTERN.search(block_text)
        start, end = _extract_date_range(block_text)

        # Descrição: pega o primeiro parágrafo "de verdade" (>40 caracteres)
        # depois do título, ignorando linhas de compartilhamento/data.
        description = _first_meaningful_paragraph(block_text, title)

        # Documentos/anexos: links próximos que terminam em pdf/doc/docx/xls/xlsx
        documentos = []
        if container is not None:
            for a in container.select("a[href]"):
                link_href = a.get("href", "")
                if re.search(r"\.(pdf|docx?|xlsx?)(\?|$)", link_href, re.IGNORECASE):
                    documentos.append(link_href)

        results.append(
            RawEdital(
                fonte="CNPq",
                titulo=title,
                url=href if href.startswith("http") else f"https://www.gov.br{href}",
                descricao=description,
                publicado_em=published.group(1) if published else None,
                inscricao_inicio=start,
                inscricao_fim=end,
                documentos=documentos[:5],
            )
        )

    return results


def _text_until_next_heading(h2_link) -> str:
    """Concatena o texto dos elementos seguintes até encontrar o próximo <h2>."""
    parts = [h2_link.get_text(" ", strip=True)]
    node = h2_link.find_parent(["h2"]) or h2_link
    sib = node.find_next_sibling()
    steps = 0
    while sib is not None and steps < 12:
        if sib.name == "h2":
            break
        parts.append(sib.get_text(" ", strip=True))
        sib = sib.find_next_sibling()
        steps += 1
    return " ".join(p for p in parts if p)


def _first_meaningful_paragraph(block_text: str, title: str) -> str:
    # Remove o próprio título do início do texto, se repetido.
    text = block_text.replace(title, "", 1).strip()
    # Corta a partir de padrões de rodapé de card que não interessam.
    for marker in ["Compartilhe:", "Publicado em"]:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx] if idx > 60 else text[idx + len(marker):]
    text = text.strip(" ·-")
    return text[:600]


def scrape_cnpq(max_pages: int = 3, delay_seconds: float = 1.0) -> list[RawEdital]:
    """Raspa a listagem de chamadas abertas do CNPq, seguindo paginação ("Próximo »")."""
    all_results: list[RawEdital] = []
    seen_urls: set[str] = set()
    url = BASE_URL

    for _ in range(max_pages):
        soup = _fetch(url)
        page_results = _parse_listing(soup)

        new_count = 0
        for r in page_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                all_results.append(r)
                new_count += 1

        if new_count == 0:
            break

        next_link = soup.find("a", string=re.compile("Próximo", re.IGNORECASE))
        if not next_link or not next_link.get("href"):
            break
        next_href = next_link["href"]
        url = next_href if next_href.startswith("http") else f"https://www.gov.br{next_href}"
        time.sleep(delay_seconds)

    return all_results


if __name__ == "__main__":
    import json

    editais = scrape_cnpq()
    print(f"{len(editais)} chamadas do CNPq encontradas.")
    print(json.dumps([e.__dict__ for e in editais], ensure_ascii=False, indent=2)[:3000])
