from __future__ import annotations

import hashlib

SEVERITY_ORDER = ("CRITICAL", "ERROR", "WARNING")

TECHNICAL_DETAIL_FIELDS = ("item", "sub_item", "validation_type", "expected_value", "got_value")


def _technical_details(data: dict | None) -> dict:
    if not data:
        return {}
    return {
        field: data[field]
        for field in TECHNICAL_DETAIL_FIELDS
        if data.get(field) not in (None, "")
    }


def _occurrence_key(*parts: str) -> str:
    """Chave estavel por ocorrencia, usada pelo relatorio HTML para lembrar
    (via localStorage do navegador) quais itens ja foram marcados como corrigidos."""
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


def _group_by_message(rows: list[dict], severity: str, category: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        message = row.get("message") or ""
        groups.setdefault(message, []).append(row)
    problems = []
    for message, message_rows in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        occurrences = [
            {
                "key": _occurrence_key(severity, category, message, row.get("advise") or "", str(index)),
                "advise": row.get("advise"),
                "details": _technical_details(row.get("data")),
            }
            for index, row in enumerate(message_rows)
        ]
        problems.append({"message": message, "count": len(occurrences), "occurrences": occurrences})
    return problems


def _group_by_category(rows: list[dict]) -> dict[str, list[dict]]:
    categories: dict[str, list[dict]] = {}
    for row in rows:
        category = row.get("subject") or ""
        categories.setdefault(category, []).append(row)
    return categories


def build_grouped_report(rows: list[dict]) -> list[dict]:
    """Agrupa ocorrencias de validacao por gravidade, categoria e mensagem.

    Gravidades seguem ordem fixa (CRITICAL, ERROR, WARNING); categorias dentro de
    cada gravidade ficam em ordem alfabetica; dentro de uma categoria, ocorrencias
    com a mesma mensagem de problema sao agrupadas juntas (mais frequentes primeiro),
    para nao repetir o mesmo texto uma vez por ocorrencia. Cada ocorrencia recebe uma
    chave estavel (``key``) usada pelo relatorio HTML para persistir, no navegador,
    quais itens ja foram marcados como corrigidos.
    """
    by_severity: dict[str, list[dict]] = {}
    for row in rows:
        by_severity.setdefault(row.get("status") or "", []).append(row)

    ordered_severities = [severity for severity in SEVERITY_ORDER if severity in by_severity]
    ordered_severities += sorted(set(by_severity) - set(SEVERITY_ORDER))

    report = []
    for severity in ordered_severities:
        categories = _group_by_category(by_severity[severity])
        category_groups = [
            {
                "name": name,
                "count": len(category_rows),
                "problems": _group_by_message(category_rows, severity, name),
            }
            for name, category_rows in sorted(categories.items())
        ]
        report.append(
            {
                "severity": severity,
                "count": sum(group["count"] for group in category_groups),
                "categories": category_groups,
            }
        )
    return report