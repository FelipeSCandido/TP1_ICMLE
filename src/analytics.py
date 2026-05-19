import csv
import json
import argparse
import math
from datetime import datetime
from collections import defaultdict, Counter

CHECKOUT_ZONES = {"Z_C1", "Z_C2", "Z_C3"}
EXIT_ZONES     = {"Z_E1", "Z_E2", "Z_CK"}
ENTRY_ZONES    = {"Z_E1", "Z_E2"}
SECTION_ZONES  = {f"Z_S{i}" for i in range(1, 8)}
NAV_ZONES      = {f"Z_N{i}" for i in range(1, 11)}


def safe_mean(lst):
    return round(sum(lst) / len(lst), 2) if lst else 0.0


def safe_std(lst):
    if len(lst) < 2:
        return 0.0
    m = sum(lst) / len(lst)
    return round(math.sqrt(sum((x - m) ** 2 for x in lst) / len(lst)), 2)


def load_journeys(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def compute(journeys_path):
    print("  A ler journeys.csv...", flush=True)
    rows = load_journeys(journeys_path)
    print(f"  {len(rows):,} linhas carregadas", flush=True)

    person_zones   = defaultdict(list)   
    person_dates   = defaultdict(set)
    person_gender  = {}
    person_age     = {}
    zone_traffic   = defaultdict(int)    
    zone_dwells    = defaultdict(list)   
    zone_lingers   = defaultdict(int)    
    traffic_dhz    = defaultdict(int)    
    person_seq     = defaultdict(list)   
    person_reached_checkout = set()
    person_reached_ck       = set()
    demo_hour_gender = defaultdict(lambda: defaultdict(int))  
    demo_hour_age    = defaultdict(lambda: defaultdict(int))  
    dwell_gender_zone = defaultdict(lambda: defaultdict(list))  
    dwell_age_zone    = defaultdict(lambda: defaultdict(list))  

    print("  A calcular metricas...", flush=True)
    for r in rows:
        pid   = r["person_id"]
        zone  = r["zone_id"]
        date  = r["visit_date"]
        hour  = int(r["hour_of_day"])
        dwell = int(r["dwell_s"])
        gender = r["gender"]
        age    = r["age_range"]

        person_zones[pid].append(r)
        person_dates[pid].add(date)
        person_gender[pid] = gender
        person_age[pid]    = age
        zone_traffic[zone] += 1
        traffic_dhz[(date, hour, zone)] += 1

        if dwell > 0:
            zone_dwells[zone].append(dwell)
            zone_lingers[zone] += 1

        person_seq[pid].append(zone)

        if zone in CHECKOUT_ZONES:
            person_reached_checkout.add(pid)
        if zone == "Z_CK":
            person_reached_ck.add(pid)

        demo_hour_gender[hour][gender] += 1
        demo_hour_age[hour][age]       += 1

        if dwell > 0:
            dwell_gender_zone[gender][zone].append(dwell)
            dwell_age_zone[age][zone].append(dwell)

    all_persons  = set(person_zones.keys())
    n_persons    = len(all_persons)
    all_dates    = sorted(set(r["visit_date"] for r in rows))
    n_days       = len(all_dates)

    visitors_by_day  = defaultdict(set)
    visitors_by_hour = defaultdict(set)
    visit_duration   = {}   

    for pid, rlist in person_zones.items():
        for r in rlist:
            visitors_by_day[r["visit_date"]].add(pid)
            visitors_by_hour[int(r["hour_of_day"])].add(pid)

        times = [datetime.strptime(r["entry_time"], "%Y-%m-%d %H:%M:%S") for r in rlist]
        exits = [datetime.strptime(r["exit_time"],  "%Y-%m-%d %H:%M:%S") for r in rlist]
        if times and exits:
            visit_duration[pid] = (max(exits) - min(times)).total_seconds()

    visitors_day_count  = {d: len(s) for d, s in visitors_by_day.items()}
    visitors_hour_count = {h: len(s) for h, s in visitors_by_hour.items()}
    avg_visit_duration  = safe_mean(list(visit_duration.values()))

    traffic = {
        "total_visitors_week":    n_persons,
        "visitors_by_day":        {d: visitors_day_count.get(d, 0) for d in all_dates},
        "visitors_by_hour":       {str(h): visitors_hour_count.get(h, 0) for h in range(9, 21)},
        "avg_visit_duration_s":   avg_visit_duration,
        "avg_visit_duration_min": round(avg_visit_duration / 60, 1),
        "busiest_day":            max(visitors_day_count, key=visitors_day_count.get, default=""),
        "quietest_day":           min(visitors_day_count, key=visitors_day_count.get, default=""),
        "peak_hour":              max(visitors_hour_count, key=visitors_hour_count.get, default=0),
    }

    zone_metrics = {}
    for zone in sorted(zone_traffic.keys()):
        total  = zone_traffic[zone]
        dwells = zone_dwells[zone]
        linger = zone_lingers[zone]
        zone_metrics[zone] = {
            "total_entries":       total,
            "avg_dwell_s":         safe_mean(dwells),
            "std_dwell_s":         safe_std(dwells),
            "stop_rate":           round(linger / total, 3) if total else 0.0,
            "visitors_with_linger": linger,
        }

    seq_counter = Counter()
    for pid, seq in person_seq.items():
        if len(seq) >= 2:
            for i in range(len(seq) - 1):
                seq_counter[(seq[i], seq[i+1])] += 1
    top_sequences = [{"from": a, "to": b, "count": c} for (a, b), c in seq_counter.most_common(10)]

    entered = {pid for pid, rlist in person_zones.items() if any(r["zone_id"] in ENTRY_ZONES for r in rlist)}
    reached_nav      = {pid for pid, rlist in person_zones.items() if any(r["zone_id"] in NAV_ZONES for r in rlist)}
    reached_section  = {pid for pid, rlist in person_zones.items() if any(r["zone_id"] in SECTION_ZONES for r in rlist)}

    funnel = {
        "entered":              len(entered),
        "reached_navigation":   len(reached_nav & entered),
        "reached_product":      len(reached_section & entered),
        "reached_checkout":     len(person_reached_checkout & entered),
        "reached_exit_ck":      len(person_reached_ck & entered),
        "checkout_rate":        round(len(person_reached_checkout & entered) / max(len(entered), 1), 3),
        "conversion_rate":      round(len(person_reached_ck & entered) / max(len(entered), 1), 3),
    }

    no_checkout = all_persons - person_reached_checkout
    nc_gender = Counter(person_gender[p] for p in no_checkout if p in person_gender)
    nc_age    = Counter(person_age[p]    for p in no_checkout if p in person_age)
    funnel["non_buyers_gender_dist"] = dict(nc_gender)
    funnel["non_buyers_age_dist"]    = dict(nc_age)

    demographics = {
        "gender_by_hour": {str(h): dict(demo_hour_gender[h]) for h in range(9, 21)},
        "age_by_hour":    {str(h): dict(demo_hour_age[h])    for h in range(9, 21)},
        "overall_gender": dict(Counter(person_gender.values())),
        "overall_age":    dict(Counter(person_age.values())),
        "avg_dwell_by_gender_zone": {g: {z: safe_mean(dwells) for z, dwells in zdict.items()} for g, zdict in dwell_gender_zone.items()},
        "avg_dwell_by_age_zone": {a: {z: safe_mean(dwells) for z, dwells in zdict.items()} for a, zdict in dwell_age_zone.items()},
    }

    dates_sorted = all_dates
    baseline_dates = dates_sorted[:-1] if len(dates_sorted) >= 2 else dates_sorted
    test_date      = dates_sorted[-1]  if len(dates_sorted) >= 1 else None

    baseline = defaultdict(list)
    for (date, hour, zone), count in traffic_dhz.items():
        if date in baseline_dates:
            baseline[(hour, zone)].append(count)

    anomalies = []
    if test_date:
        for (hour, zone), counts in baseline.items():
            mu  = safe_mean(counts)
            std = safe_std(counts)
            actual = traffic_dhz.get((test_date, hour, zone), 0)
            if std > 0:
                z_score = (actual - mu) / std
                if abs(z_score) > 2.0:
                    anomalies.append({
                        "zone":      zone,
                        "hour":      hour,
                        "date":      test_date,
                        "z_score":   round(z_score, 2),
                        "actual":    actual,
                        "expected":  round(mu, 1),
                        "std":       round(std, 2),
                        "direction": "acima" if z_score > 0 else "abaixo",
                    })

    anomalies.sort(key=lambda x: abs(x["z_score"]), reverse=True)

    overlap_count = 0
    for pid, rlist in person_zones.items():
        sorted_r = sorted(rlist, key=lambda r: r["entry_time"])
        for i in range(len(sorted_r) - 1):
            if sorted_r[i]["exit_time"] > sorted_r[i+1]["entry_time"]:
                overlap_count += 1
                break
    consistency = round(1.0 - overlap_count / max(n_persons, 1), 4)

    stitching_quality = {
        "total_trajectories":   n_persons,
        "total_zones_visited":  len(rows),
        "consistency_rate":     consistency,
        "avg_zones_per_person": round(len(rows) / max(n_persons, 1), 2),
    }

    metrics = {
        "metadata": {
            "generated_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "period_start":  all_dates[0]  if all_dates else "",
            "period_end":    all_dates[-1] if all_dates else "",
            "n_days":        n_days,
            "test_date":     test_date,
            "baseline_days": baseline_dates,
        },
        "traffic":           traffic,
        "zone_metrics":      zone_metrics,
        "top_zone_sequences": top_sequences,
        "funnel":            funnel,
        "demographics":      demographics,
        "anomalies":         anomalies[:20],   
        "stitching_quality": stitching_quality,
    }
    return metrics


def main():
    ap = argparse.ArgumentParser(description="Calcula metricas a partir de journeys.csv")
    ap.add_argument("--input",  default="output/journeys.csv")
    ap.add_argument("--output", default="output/metrics.json")
    args = ap.parse_args()

    print(f"[analytics] input={args.input}  output={args.output}")
    metrics = compute(args.input)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    print(f"[analytics] OK - metrics.json escrito -- {len(metrics['anomalies'])} anomalias detectadas")


if __name__ == "__main__":
    main()