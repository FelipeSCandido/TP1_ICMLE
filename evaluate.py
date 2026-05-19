import csv
import json
import argparse
import subprocess
import sys
import os
import re
import time
from datetime import datetime
from collections import defaultdict


STITCHER  = "src/stitcher.py"
ANALYTICS = "src/analytics.py"
INSIGHTS  = "src/insights.py"
REPORT    = "src/report.py"
ZONES_FILE = "data/zones.json"

ENTRY_ZONES   = {"Z_E1", "Z_E2"}
EXIT_ZONES    = {"Z_E1", "Z_E2", "Z_CK"}
CHECKOUT      = {"Z_C1", "Z_C2", "Z_C3"}



def run_step(cmd, label):
    print(f"\n[evaluate] → {label}")
    t0  = time.time()
    ret = subprocess.run([sys.executable] + cmd, capture_output=True, text=True)
    elapsed = round(time.time() - t0, 1)
    if ret.returncode != 0:
        print(f"  ERRO ({elapsed}s):\n{ret.stderr[-1000:]}")
        return False, elapsed, ret.stderr
    print(f"  OK ({elapsed}s)")
    return True, elapsed, ret.stdout



def eval_stitching(journeys_path: str, events_path: str) -> dict:
    
    journeys = []
    with open(journeys_path, newline="", encoding="utf-8") as f:
        journeys = list(csv.DictReader(f))

    # Carregar eventos originais
    events = []
    with open(events_path, newline="", encoding="utf-8") as f:
        events = list(csv.DictReader(f))

    n_events = len(events)

    # Agrupar por pessoa
    person_zones = defaultdict(list)
    for r in journeys:
        person_zones[r["person_id"]].append(r)

    n_persons = len(person_zones)

    inconsistent = 0
    for pid, rlist in person_zones.items():
        sorted_r = sorted(rlist, key=lambda r: r["entry_time"])
        for i in range(len(sorted_r) - 1):
            exit_i  = sorted_r[i]["exit_time"]
            entry_n = sorted_r[i+1]["entry_time"]
            if exit_i > entry_n:
                inconsistent += 1
                break
    consistency = 1.0 - inconsistent / max(n_persons, 1)

  
    n_entry_events = sum(1 for e in events if e["event_type"] == "entry")
    n_assigned     = len(journeys)   
    coverage = min(1.0, n_assigned / max(n_entry_events, 1))

    complete = 0
    for pid, rlist in person_zones.items():
        sorted_r = sorted(rlist, key=lambda r: r["entry_time"])
        starts_ok = sorted_r[0]["zone_id"] in ENTRY_ZONES if sorted_r else False
        ends_ok   = sorted_r[-1]["zone_id"] in EXIT_ZONES if sorted_r else False
        if starts_ok and ends_ok:
            complete += 1
    completeness = complete / max(n_persons, 1)

    gaps = []
    for pid, rlist in person_zones.items():
        sorted_r = sorted(rlist, key=lambda r: r["entry_time"])
        for i in range(len(sorted_r) - 1):
            try:
                exit_i  = datetime.strptime(sorted_r[i]["exit_time"],  "%Y-%m-%d %H:%M:%S")
                entry_n = datetime.strptime(sorted_r[i+1]["entry_time"], "%Y-%m-%d %H:%M:%S")
                gap = (entry_n - exit_i).total_seconds()
                if 0 <= gap <= 300:
                    gaps.append(gap)
            except Exception:
                pass

    gap_mean = round(sum(gaps) / len(gaps), 1) if gaps else 0
    gap_p50  = sorted(gaps)[len(gaps)//2] if gaps else 0
    gap_p95  = sorted(gaps)[int(len(gaps)*0.95)] if gaps else 0

    return {
        "n_events_original":    n_events,
        "n_trajectories":       n_persons,
        "consistency":          round(consistency, 4),
        "coverage":             round(coverage, 4),
        "completeness":         round(completeness, 4),
        "temporal_plausibility": {
            "n_gaps_measured":  len(gaps),
            "gap_mean_s":       gap_mean,
            "gap_median_s":     gap_p50,
            "gap_p95_s":        gap_p95,
            "plausible":        gap_mean < 120 and gap_p95 < 300,
        },
        "pass": consistency >= 0.95 and coverage >= 0.70 and completeness >= 0.50,
    }



def eval_anomaly_detection(insights_path: str,
                            known_anomalies: list = None) -> dict:
    
    with open(insights_path, encoding="utf-8") as f:
        insights_data = json.load(f)

    all_insights = insights_data.get("insights", [])
    anomaly_ins  = [i for i in all_insights if i.get("categoria") == "anomalia"]

    if not known_anomalies:
        return {
            "note": "Nenhuma anomalia conhecida fornecida. "
                    "Forneça --known-anomalies para avaliação completa.",
            "n_anomaly_insights": len(anomaly_ins),
        }

    detected = 0
    for ka in known_anomalies:
        zone = ka.get("zone", "")
        hour = str(ka.get("hour", ""))
        found = any(
            zone in i.get("observacao", "") or zone in i.get("titulo", "")
            for i in anomaly_ins
        )
        if found:
            detected += 1

    return {
        "n_known_anomalies":   len(known_anomalies),
        "n_detected":          detected,
        "detection_rate":      round(detected / max(len(known_anomalies), 1), 3),
        "n_anomaly_insights":  len(anomaly_ins),
    }



def eval_numerical_accuracy(insights_path: str, metrics_path: str) -> dict:
    
    with open(insights_path, encoding="utf-8") as f:
        insights_data = json.load(f)
    with open(metrics_path, encoding="utf-8") as f:
        metrics_str = f.read()

    all_insights = insights_data.get("insights", [])

    verified = 0
    total_nums = 0
    for i in all_insights:
        obs = i.get("observacao", "")
        numbers = re.findall(r'\b\d+[\.,]?\d*\b', obs)
        for num in numbers:
            total_nums += 1
            num_clean = num.replace(",", ".")
            if num_clean in metrics_str or num in metrics_str:
                verified += 1

    accuracy = round(verified / max(total_nums, 1), 3)
    return {
        "total_numbers_cited": total_nums,
        "verified_in_metrics": verified,
        "numerical_accuracy":  accuracy,
        "pass": accuracy >= 0.70,
    }



def eval_hallucination(insights_path: str, metrics_path: str) -> dict:
    
    with open(insights_path, encoding="utf-8") as f:
        insights_data = json.load(f)
    with open(metrics_path, encoding="utf-8") as f:
        metrics = json.load(f)

    valid_zones = set(metrics.get("zone_metrics", {}).keys())
    all_insights = insights_data.get("insights", [])

    zone_pattern = re.compile(r'Z_[A-Z]+\d*')
    total_mentions = 0
    valid_mentions = 0

    for i in all_insights:
        text = " ".join([
            i.get("titulo", ""),
            i.get("observacao", ""),
            i.get("implicacao", ""),
            i.get("recomendacao", ""),
        ])
        mentions = zone_pattern.findall(text)
        for m in mentions:
            total_mentions += 1
            if m in valid_zones:
                valid_mentions += 1

    score = round(valid_mentions / max(total_mentions, 1), 3)
    return {
        "zone_mentions_total":  total_mentions,
        "zone_mentions_valid":  valid_mentions,
        "hallucination_score":  score,    
        "pass": score >= 0.85,
    }



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data",   required=True, help="CSV de validação")
    ap.add_argument("--output", default="evaluation_report.json")
    ap.add_argument("--known-anomalies", default=None,
                    help="JSON com lista de anomalias conhecidas: "
                         '[{"zone":"Z_N4","hour":16}]')
    ap.add_argument("--skip-llm", action="store_true",
                    help="Salta a geração de insights (testa apenas stitching)")
    args = ap.parse_args()

    known_anomalies = None
    if args.known_anomalies:
        known_anomalies = json.loads(args.known_anomalies)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report    = {"timestamp": timestamp, "input_data": args.data, "steps": {}}

    val_journeys = "output/val_journeys.csv"
    val_metrics  = "output/val_metrics.json"
    val_insights = "output/val_insights.json"
    val_report   = "output/val_report.md"

    ok, elapsed, log = run_step(
        [STITCHER, "--input", args.data, "--zones", ZONES_FILE,
         "--output", val_journeys],
        "stitcher.py"
    )
    report["steps"]["stitcher"] = {"success": ok, "elapsed_s": elapsed}
    if not ok:
        report["error"] = "Falha no stitcher"
        _write(report, args.output)
        return

    ok, elapsed, log = run_step(
        [ANALYTICS, "--input", val_journeys, "--output", val_metrics],
        "analytics.py"
    )
    report["steps"]["analytics"] = {"success": ok, "elapsed_s": elapsed}
    if not ok:
        report["error"] = "Falha no analytics"
        _write(report, args.output)
        return

    print("\n[evaluate] A calcular métricas de stitching...")
    stitching_metrics = eval_stitching(val_journeys, args.data)
    report["stitching"] = stitching_metrics
    print(f"  Consistência:  {stitching_metrics['consistency']:.1%}")
    print(f"  Cobertura:     {stitching_metrics['coverage']:.1%}")
    print(f"  Completude:    {stitching_metrics['completeness']:.1%}")
    print(f"  Gap médio:     {stitching_metrics['temporal_plausibility']['gap_mean_s']}s")

    if args.skip_llm:
        _write(report, args.output)
        print(f"\n[evaluate] ✓ Relatório escrito em {args.output}")
        return

    ok, elapsed, log = run_step(
        [INSIGHTS, "--input", val_metrics, "--output", val_insights,
         "--strategy", "both", "--temperature", "0"],
        "insights.py (temperature=0 para reprodutibilidade)"
    )
    report["steps"]["insights"] = {"success": ok, "elapsed_s": elapsed}
    if not ok:
        report["error"] = "Falha nos insights"
        _write(report, args.output)
        return

    ok, elapsed, log = run_step(
        [REPORT, "--input", val_insights, "--output", val_report],
        "report.py"
    )
    report["steps"]["report"] = {"success": ok, "elapsed_s": elapsed}

    print("\n[evaluate] A calcular métricas de qualidade dos insights...")

    report["anomaly_detection"] = eval_anomaly_detection(val_insights, known_anomalies)
    print(f"  Deteção anomalias: {report['anomaly_detection']}")

    report["numerical_accuracy"] = eval_numerical_accuracy(val_insights, val_metrics)
    print(f"  Precisão numérica: {report['numerical_accuracy']['numerical_accuracy']:.1%}")

    report["hallucination"] = eval_hallucination(val_insights, val_metrics)
    print(f"  Anti-alucinação:   {report['hallucination']['hallucination_score']:.1%}")

    passes = [
        stitching_metrics.get("pass", False),
        report["numerical_accuracy"].get("pass", False),
        report["hallucination"].get("pass", False),
    ]
    report["summary"] = {
        "all_steps_ok": all(s.get("success", False) for s in report["steps"].values()),
        "stitching_pass": stitching_metrics.get("pass", False),
        "llm_quality_pass": all(passes[1:]),
        "overall_pass": all(passes),
    }

    _write(report, args.output)
    print(f"\n[evaluate] ✓ Relatório de avaliação escrito em {args.output}")
    _print_summary(report)


def _write(report, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def _print_summary(report):
    print("\n" + "="*60)
    print("SUMÁRIO DE AVALIAÇÃO")
    print("="*60)
    s = report.get("stitching", {})
    print(f"  Consistência:       {s.get('consistency', 0):.1%}  "
          f"{'✅' if s.get('consistency', 0) >= 0.95 else '❌'}")
    print(f"  Cobertura:          {s.get('coverage', 0):.1%}  "
          f"{'✅' if s.get('coverage', 0) >= 0.70 else '❌'}")
    print(f"  Completude:         {s.get('completeness', 0):.1%}  "
          f"{'✅' if s.get('completeness', 0) >= 0.50 else '❌'}")
    na = report.get("numerical_accuracy", {})
    print(f"  Precisão numérica:  {na.get('numerical_accuracy', 0):.1%}  "
          f"{'✅' if na.get('pass') else '❌'}")
    ha = report.get("hallucination", {})
    print(f"  Anti-alucinação:    {ha.get('hallucination_score', 0):.1%}  "
          f"{'✅' if ha.get('pass') else '❌'}")
    print("="*60)
    overall = report.get("summary", {}).get("overall_pass", False)
    print(f"  RESULTADO GLOBAL:   {'✅ PASS' if overall else '⚠️  PARCIAL'}")
    print("="*60)


if __name__ == "__main__":
    main()
