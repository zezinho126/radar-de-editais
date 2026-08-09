"""
Converte os resultados brutos (RawEdital do CNPq e da FAPEMIG) para o mesmo
formato de objeto que o array `editais` já usa no captaeditais.html, para que
o frontend não precise mudar a lógica de filtro/score — só passa a buscar
os dados de um JSON em vez de um array fixo.

Campos esperados pelo frontend (ver findMatches() no HTML):
  nome, orgao, area, naturezas[], publicos[], instituicoes[], abrangencia,
  estados[], valorMin, valorMax, tipoRecurso, fonte, instrumento, prazo,
  taxaVedada, vedacao, fonteVedacao, url
"""
from __future__ import annotations

import re
from typing import Any


def _parse_valor_para_faixa(texto: str | None) -> tuple[int, int]:
    """Extrai um valor aproximado de um texto tipo 'R$ 10 milhões' ou 'R$ 300.000,00'.
    Como geralmente só temos o valor TOTAL da chamada (não o teto por projeto),
    usamos ele como valorMax e deixamos valorMin em 0 — ajuste manualmente
    depois se seu edital específico informa faixas por proposta."""
    if not texto:
        return 0, 0
    texto = texto.replace("\xa0", " ")
    m = re.search(r"([\d\.,]+)\s*(milh(?:ão|ões)|mil)?", texto, re.IGNORECASE)
    if not m:
        return 0, 0
    number_str, unit = m.groups()
    number_str = number_str.replace(".", "").replace(",", ".")
    try:
        value = float(number_str)
    except ValueError:
        return 0, 0
    if unit and "milh" in unit.lower():
        value *= 1_000_000
    elif unit and "mil" in unit.lower():
        value *= 1_000
    return 0, int(value)


def _to_br_date(iso_or_br: str | None) -> str:
    """Já recebemos datas em DD/MM/AAAA dos dois scrapers; só garante 4 dígitos de ano."""
    if not iso_or_br:
        return ""
    parts = iso_or_br.split("/")
    if len(parts) == 3 and len(parts[2]) == 2:
        parts[2] = "20" + parts[2]
        return "/".join(parts)
    return iso_or_br


def normalize_cnpq(raw: Any) -> dict:
    valor_min, valor_max = 0, 0  # CNPq raramente traz valor total no card da listagem
    return {
        "nome": raw.titulo,
        "orgao": "CNPq",
        "area": "Multidisciplinar / Outros",  # a listagem do CNPq não classifica por área; ajuste manualmente se quiser
        "naturezas": ["Pesquisa"],
        "publicos": ["Pesquisadores"],
        "instituicoes": ["UFLA", "IFES", "ICT", "Universidade Pública"],
        "abrangencia": "Nacional",
        "estados": [],
        "valorMin": valor_min,
        "valorMax": valor_max,
        "tipoRecurso": "Chamada pública / seleção de projetos",
        "fonte": "Governo Federal",
        "instrumento": "Termo de Outorga",
        "prazo": _to_br_date(raw.inscricao_fim) or "",
        "taxaVedada": False,
        "vedacao": "",
        "fonteVedacao": "",
        "url": raw.url,
        "_descricao": raw.descricao,
        "_publicadoEm": raw.publicado_em,
        "_inscricaoInicio": _to_br_date(raw.inscricao_inicio),
        "_documentos": raw.documentos,
    }


def normalize_fapemig(raw: Any) -> dict:
    valor_min, valor_max = _parse_valor_para_faixa(raw.valor)
    return {
        "nome": raw.titulo,
        "orgao": "FAPEMIG",
        "area": "Multidisciplinar / Outros",  # a listagem da FAPEMIG não expõe a área textualmente; ajuste manualmente
        "naturezas": ["Pesquisa"],
        "publicos": _publico_para_lista(raw.publico_alvo),
        "instituicoes": ["UFLA", "ICT", "Universidade Pública"],
        "abrangencia": "Estadual",
        "estados": ["MG"],
        "valorMin": valor_min,
        "valorMax": valor_max,
        "tipoRecurso": raw.linha_fomento or "Auxílio à pesquisa",
        "fonte": "Governo Estadual",
        "instrumento": "Termo de Outorga",
        "prazo": raw.inscricao_fim or "",
        "taxaVedada": False,
        "vedacao": "",
        "fonteVedacao": "",
        "url": raw.url,
        "_descricao": raw.descricao,
        "_inscricaoInicio": raw.inscricao_inicio,
        "_resultadoPrevisto": raw.resultado_previsto,
    }


def _publico_para_lista(texto: str | None) -> list[str]:
    if not texto:
        return ["Pesquisadores"]
    mapping = {
        "pesquisadores": "Pesquisadores",
        "ict": "Comunidade acadêmica",
        "empresas": "Empreendedores",
    }
    found = [v for k, v in mapping.items() if k in texto.lower()]
    return found or ["Pesquisadores"]
