import json
import argparse
from datetime import datetime


def fmt_date(d: str) -> str:
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return d


def fmt_duration(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    if m == 0:
        return f"{s}s"
    return f"{m}min {s}s" if s else f"{m}min"


def pct(num, denom):
    if not denom:
        return "0%"
    return f"{num/denom*100:.1f}%"


def generate_report(insights_path: str, output_path: str):
    with open(insights_path, encoding="utf-8") as f:
        data = json.load(f)

    insights = data.get("insights", [])
    resumo   = data.get("resumo_executivo", [])
    metrics  = data.get("metrics", {})

    def by_cat(cat):
        return [i for i in insights if i.get("categoria") == cat]

    ins_trafego   = by_cat("trafego")
    ins_zona      = by_cat("zona")
    ins_funil     = by_cat("funil")
    ins_anomalia  = by_cat("anomalia")
    ins_demo      = by_cat("demografico")

    all_recs = sorted(insights, key=lambda i: (
        {"imediata": 0, "esta_semana": 1, "proximo_mes": 2}.get(i.get("urgencia", "esta_semana"), 1)
    ))

    lines = []
    W = lines.append   

    W("# Relatorio Semanal de Loja")
    W("")
    W(f"> Gerado automaticamente em {datetime.now().strftime('%d/%m/%Y as %H:%M')}")
    W("")
    W("---")
    W("")

    W("## 1. Resumo Executivo")
    W("")
    if resumo:
        for bullet in resumo:
            W(f"- {bullet}")
    else:
        W("_Dados insuficientes para gerar resumo executivo._")
    W("")
    W("---")
    W("")

    W("## 2. Performance de Trafego")
    W("")
    if ins_trafego:
        for i in ins_trafego:
            W(f"### {i['titulo']}")
            W("")
            W(f"**O que os dados mostram:** {i['observacao']}")
            W("")
            W(f"**Implicacao:** {i['implicacao']}")
            W("")
            W(f"**Accao recomendada:** {i['recomendacao']}")
            W("")
    else:
        W("_Sem insights de trafego disponiveis._")
        W("")
    W("---")
    W("")

    W("## 3. Analise de Zonas")
    W("")
    if ins_zona:
        for i in ins_zona:
            urgencia_badge = {
                "imediata":    "IMEDIATA",
                "esta_semana": "Esta semana",
                "proximo_mes": "Proximo mes",
            }.get(i.get("urgencia", ""), "")
            W(f"### {i['titulo']}  `[{urgencia_badge}]`")
            W("")
            W(f"**Observacao:** {i['observacao']}")
            W("")
            W(f"**Implicacao:** {i['implicacao']}")
            W("")
            W(f"**Recomendacao:** {i['recomendacao']}")
            W("")
    else:
        W("_Sem insights de zonas disponiveis._")
        W("")
    W("---")
    W("")

    W("## 4. Funil de Clientes")
    W("")
    if ins_funil:
        for i in ins_funil:
            W(f"### {i['titulo']}")
            W("")
            W(f"**Observacao:** {i['observacao']}")
            W("")
            W(f"**Implicacao:** {i['implicacao']}")
            W("")
            W(f"**Recomendacao:** {i['recomendacao']}")
            W("")
    else:
        W("_Sem insights de funil disponiveis._")
        W("")

    if ins_demo:
        W("### Perfil Demografico")
        W("")
        for i in ins_demo:
            W(f"**{i['titulo']}:** {i['observacao']}")
            W("")
    W("---")
    W("")

    W("## 5. Anomalias da Semana")
    W("")
    if ins_anomalia:
        for i in ins_anomalia:
            W(f"### Alerta: {i['titulo']}")
            W("")
            W(f"**Descricao:** {i['observacao']}")
            W("")
            W(f"**Possivel causa / implicacao:** {i['implicacao']}")
            W("")
            W(f"**Accao recomendada:** {i['recomendacao']}")
            urgencia = i.get("urgencia", "esta_semana")
            conf     = i.get("confianca", 0)
            W(f"> Urgencia: **{urgencia}** | Confianca: **{conf:.0%}**")
            W("")
    else:
        W("Nenhuma anomalia significativa detectada esta semana.")
        W("")
    W("---")
    W("")

    W("## 6. Recomendacoes para a Proxima Semana")
    W("")
    W("Ordenadas por urgencia:")
    W("")
    seen_recs = set()
    rank = 1
    for i in all_recs:
        rec = i.get("recomendacao", "").strip()
        if not rec or rec in seen_recs:
            continue
        seen_recs.add(rec)
        urgencia = i.get("urgencia", "esta_semana")
        badge = {"imediata": "[CRITICO]", "esta_semana": "[AVISO]", "proximo_mes": "[PLANO]"}.get(urgencia, "")
        W(f"{rank}. {badge} **{i.get('titulo', '')}**")
        W(f"   {rec}")
        W("")
        rank += 1
        if rank > 6:
            break

    W("---")
    W("")
    W("*Este relatorio foi gerado automaticamente pelo sistema de Retail Intelligence.*")

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  weekly_report.md escrito -- {len(content.split())} palavras")


def main():
    ap = argparse.ArgumentParser(description="Gera relatorio semanal em Markdown")
    ap.add_argument("--input",  default="output/insights.json")
    ap.add_argument("--output", default="output/weekly_report.md")
    args = ap.parse_args()

    print(f"[report] input={args.input}  output={args.output}")
    generate_report(args.input, args.output)
    print("[report] OK")


if __name__ == "__main__":
    main()