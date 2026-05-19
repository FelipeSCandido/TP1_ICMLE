import csv
import json
import argparse
from datetime import datetime
from collections import defaultdict, deque
 
# -- Parametros ----------------------------------------------------------------
MAX_GAP_SECONDS = 900    # 15 minutos -- janela de inactividade maxima
MIN_WALK_SEC    = 2      # minimo de walk entre zonas nao adjacentes
SCORE_THRESHOLD = 0.10   # score minimo para associar a trajectoria existente
 
# Zonas de entrada (sempre iniciam nova trajectoria)
ENTRY_ZONES   = {"Z_E1", "Z_E2"}
# Zonas de saida genuina (fecham trajectoria definitivamente)
EXIT_FINAL    = {"Z_CK"}
# Zonas de caixa (sinalizam que visita esta a terminar)
CHECKOUT      = {"Z_C1", "Z_C2", "Z_C3"}
# Todas as zonas de saida possivel (para metrica de completude)
EXIT_ZONES    = {"Z_E1", "Z_E2", "Z_CK"}
 
AGE_RANGES = ["child", "teenager", "young_adult", "adult", "middle_aged", "senior"]
AGE_IDX    = {a: i for i, a in enumerate(AGE_RANGES)}
 
GENDER_COMPAT = {
    ("M", "M"): 1.0, ("F", "F"): 1.0,
    ("M", "F"): 0.0, ("F", "M"): 0.0,
}
 
 
def age_compat(a1, a2):
    if a1 not in AGE_IDX or a2 not in AGE_IDX:
        return 0.5
    d = abs(AGE_IDX[a1] - AGE_IDX[a2])
    return max(0.0, 1.0 - d * 0.35)
 
 
def load_zone_graph(zones_path):
    try:
        with open(zones_path) as f:
            data = json.load(f)
        return {z: info.get("walk_seconds", {}) for z, info in data["zones"].items()}
    except Exception:
        return {}
 
 
def min_walk(zone_a, zone_b, graph):
    if zone_a == zone_b:
        return 0
    t = graph.get(zone_a, {}).get(zone_b)
    return t if t is not None else MIN_WALK_SEC
 
 
class Trajectory:
    __slots__ = ["pid", "zones", "current_zone", "zone_entry", "zone_exit",
                 "gender", "age_range", "gender_votes", "age_votes",
                 "closed", "visited_interior"]
 
    def __init__(self, pid):
        self.pid              = pid
        self.zones            = []
        self.current_zone     = None
        self.zone_entry       = None
        self.zone_exit        = None
        self.gender           = None
        self.age_range        = None
        self.gender_votes     = defaultdict(int)
        self.age_votes        = defaultdict(int)
        self.closed           = False
        # Flag: visitou pelo menos uma zona interior (nao Z_E)?
        # Necessario para distinguir "a sair" de "a entrar" em Z_E
        self.visited_interior = False
 
    def last_exit_time(self):
        if self.zone_exit:
            return self.zone_exit
        if self.zones:
            return self.zones[-1].get("exit_time") or self.zones[-1]["entry_time"]
        return None
 
    def update_attrs(self, gender, age_range):
        self.gender_votes[gender] += 1
        self.age_votes[age_range] += 1
        self.gender    = max(self.gender_votes, key=self.gender_votes.get)
        self.age_range = max(self.age_votes,    key=self.age_votes.get)
 
    def score_match(self, zone, ts, gender, age_range, graph):
        if self.closed:
            return 0.0
        last_exit = self.last_exit_time()
        if last_exit is None:
            return 0.0
 
        gap = (ts - last_exit).total_seconds()
 
        # -- Rejeicoes hard ----------------------------------------------------
        if gap < 0 or gap > MAX_GAP_SECONDS:
            return 0.0
 
        walk = min_walk(self.current_zone or zone, zone, graph)
        if gap < walk * 0.4:          # margem de 40% para imprecisao de timestamps
            return 0.0
 
        # -- Score temporal ----------------------------------------------------
        score_time = max(0.05, 1.0 - gap / MAX_GAP_SECONDS)
 
        # -- Score de atributos (peso dominante) -------------------------------
        g_score    = GENDER_COMPAT.get((self.gender, gender), 0.5) if self.gender else 0.7
        a_score    = age_compat(self.age_range, age_range) if self.age_range else 0.7
        score_attr = 0.6 * g_score + 0.4 * a_score
 
        # -- Bonus de adjacencia -----------------------------------------------
        last_zone  = self.current_zone or (self.zones[-1]["zone_id"] if self.zones else None)
        adj        = zone in graph.get(last_zone, {}) if last_zone else False
        same_zone  = (last_zone == zone)
        adj_bonus  = 0.20 if same_zone else (0.10 if adj else 0.0)
 
        # Ponderacao: atributos dominam para evitar confundir pessoas diferentes
        return 0.40 * score_time + 0.45 * score_attr + adj_bonus
 
 
def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
 
 
def stitch(events_path, zones_path, output_path):
    graph = load_zone_graph(zones_path)
    print(f"  Mapa de zonas: {len(graph)} zonas carregadas", flush=True)
 
    print("  A ler eventos...", flush=True)
    events = []
    with open(events_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            events.append({
                "event_id":   row["event_id"],
                "timestamp":  parse_ts(row["timestamp"]),
                "zone_id":    row["zone_id"],
                "event_type": row["event_type"],
                "duration_s": int(row["duration_s"]),
                "gender":     row["gender"],
                "age_range":  row["age_range"],
            })
    print(f"  {len(events):,} eventos lidos", flush=True)
 
    all_trajs    = {}                   # pid -> Trajectory
    open_by_zone = defaultdict(list)    # zone -> [Trajectory]  (lookup rapido)
    active_deque = deque()              # (last_exit_ts, pid) ordenado por tempo
    pid_counter  = 1
    discarded    = 0
 
    for i, ev in enumerate(events):
        if i % 50000 == 0:
            n_open = sum(1 for t in all_trajs.values() if not t.closed)
            print(f"  Progresso: {i:,}/{len(events):,} | abertas: {n_open}", flush=True)
 
        ts        = ev["timestamp"]
        zone      = ev["zone_id"]
        etype     = ev["event_type"]
        gender    = ev["gender"]
        age_range = ev["age_range"]
 
        while active_deque:
            last_ts, old_pid = active_deque[0]
            if (ts - last_ts).total_seconds() <= MAX_GAP_SECONDS:
                break
            active_deque.popleft()
            t_old = all_trajs.get(old_pid)
            if t_old and not t_old.closed:
                real_last = t_old.last_exit_time()
                if real_last and (ts - real_last).total_seconds() > MAX_GAP_SECONDS:
                    t_old.closed = True
                    cz = t_old.current_zone
                    if cz and t_old in open_by_zone[cz]:
                        open_by_zone[cz].remove(t_old)
 
        if etype == "linger":
            for t in open_by_zone[zone]:
                if not t.closed:
                    t.update_attrs(gender, age_range)
            continue
 
        if etype == "exit":
            matched = False
            for t in list(open_by_zone[zone]):
                if t.closed:
                    continue
                # Registar saida
                t.zone_exit = ts
                if t.zones:
                    last_rec = t.zones[-1]
                    if last_rec["zone_id"] == zone and last_rec["exit_time"] is None:
                        last_rec["exit_time"] = ts
                        last_rec["dwell_s"]   = int((ts - last_rec["entry_time"]).total_seconds())
                t.update_attrs(gender, age_range)
                open_by_zone[zone].remove(t)
 
                if zone in EXIT_FINAL:
                    t.closed = True
                elif zone in ENTRY_ZONES and t.visited_interior:
                    t.closed = True
                else:
                    # Manter aberta: regressar ao interior ou ainda na entrada
                    active_deque.append((ts, t.pid))
 
                matched = True
                break
 
            if not matched:
                discarded += 1
            continue
 
        
        force_new = zone in ENTRY_ZONES
 
        best_score = SCORE_THRESHOLD
        best_traj  = None
 
        if not force_new:
            # Pesquisa em todas as trajectorias activas (via deque, por recencia)
            # Complexidade: O(T_activas) ~ O(30-50) na pratica
            seen = set()
            for _, pid in reversed(active_deque):   # mais recentes primeiro
                if pid in seen:
                    continue
                seen.add(pid)
                t = all_trajs.get(pid)
                if not t or t.closed:
                    continue
                s = t.score_match(zone, ts, gender, age_range, graph)
                if s > best_score:
                    best_score = s
                    best_traj  = t
 
            # Verificar tambem trajectorias abertas na zona actual e adjacentes
            # (podem nao estar na deque se nunca tiveram exit registado)
            candidate_zones = [zone] + list(graph.get(zone, {}).keys())
            for cz in candidate_zones:
                for t in open_by_zone[cz]:
                    if t.closed or t.pid in seen:
                        continue
                    s = t.score_match(zone, ts, gender, age_range, graph)
                    if s > best_score:
                        best_score = s
                        best_traj  = t
 
        if best_traj is not None:
            # Remover do indice da zona anterior
            cz = best_traj.current_zone
            if cz and best_traj in open_by_zone[cz]:
                open_by_zone[cz].remove(best_traj)
 
            best_traj.current_zone = zone
            best_traj.zone_entry   = ts
            best_traj.zone_exit    = None
            best_traj.zones.append({
                "zone_id":    zone,
                "entry_time": ts,
                "exit_time":  None,
                "dwell_s":    0,
            })
            best_traj.update_attrs(gender, age_range)
            open_by_zone[zone].append(best_traj)
 
            # Marcar como interior se nao for zona de entrada
            if zone not in ENTRY_ZONES:
                best_traj.visited_interior = True
 
        else:
            # Nova trajectoria
            t = Trajectory(pid_counter)
            all_trajs[pid_counter] = t
            pid_counter += 1
            t.current_zone = zone
            t.zone_entry   = ts
            t.zones.append({
                "zone_id":    zone,
                "entry_time": ts,
                "exit_time":  None,
                "dwell_s":    0,
            })
            t.update_attrs(gender, age_range)
            open_by_zone[zone].append(t)
 
            if zone not in ENTRY_ZONES:
                t.visited_interior = True
 
            # Adicionar a deque apenas se nao for entry de porta
            # (entries de porta nao precisam de estar na deque para match futuro --
            #  sao sempre force_new se reaparecerem)
            if zone not in ENTRY_ZONES:
                active_deque.append((ts, t.pid))
 
    # Fechar todas as remanescentes
    for t in all_trajs.values():
        t.closed = True
 
    n_trajs = len(all_trajs)
    print(f"  Trajectorias reconstruidas: {n_trajs:,}", flush=True)
    print(f"  Eventos exit sem match:     {discarded:,}", flush=True)
 
    # -- Escrever journeys.csv -------------------------------------------------
    header = ["person_id", "zone_id", "entry_time", "exit_time",
              "dwell_s", "gender", "age_range", "visit_date", "hour_of_day"]
 
    rows_written = 0
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for t in all_trajs.values():
            pid_str = f"P_{t.pid:05d}"
            for z in t.zones:
                entry  = z["entry_time"]
                exit_t = z["exit_time"] or entry
                w.writerow([
                    pid_str,
                    z["zone_id"],
                    entry.strftime("%Y-%m-%d %H:%M:%S"),
                    exit_t.strftime("%Y-%m-%d %H:%M:%S"),
                    z["dwell_s"],
                    t.gender or "",
                    t.age_range or "",
                    entry.strftime("%Y-%m-%d"),
                    entry.hour,
                ])
                rows_written += 1
 
    print(f"  Linhas escritas: {rows_written:,}", flush=True)
    return n_trajs, rows_written
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",  default="data/events.csv")
    ap.add_argument("--zones",  default="data/zones.json")
    ap.add_argument("--output", default="output/journeys.csv")
    args = ap.parse_args()
 
    print(f"[stitcher] input={args.input}  zones={args.zones}  output={args.output}")
    n_traj, n_rows = stitch(args.input, args.zones, args.output)
    print(f"[stitcher] SUCESSO - {n_traj:,} trajectorias -> {n_rows:,} linhas")
 
 
if __name__ == "__main__":
    main()