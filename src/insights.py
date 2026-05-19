import json
import argparse
import re
import time
import os
import urllib.request
import urllib.error
from datetime import datetime

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL      = "qwen2.5:3b"
PROMPTS_DIR = "prompts"


def load_prompt_from_file(strategy_name: str, metrics_json_str: str) -> str:
    filename = "zero_shot.txt" if strategy_name == "A" else "few_shot.txt"
    filepath = os.path.join(PROMPTS_DIR, filename)
    
    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"Erro: O ficheiro de prompt obrigatorio nao foi encontrado em: {filepath}\n"
            f"Por favor, certifique-se de que a pasta '{PROMPTS_DIR}' contem os ficheiros "
            f"'zero_shot.txt' e 'few_shot.txt'."
        )
        
    with open(filepath, "r", encoding="utf-8") as f:
        template = f.read()
        
    if "{METRICS_JSON}" in template:
        return template.replace("{METRICS_JSON}", metrics_json_str)
    
    return f"{template}\n\nDados para analise:\n{metrics_json_str}"


def query_ollama(prompt: str, temperature: float) -> dict:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "seed": 42
        }
    }
    payload["format"] = "json"

    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            res_body = json.loads(response.read().decode("utf-8"))
            text_out = res_body.get("response", "").strip()
            
            text_out = re.sub(r"^```json\s*", "", text_out, flags=re.IGNORECASE)
            text_out = re.sub(r"\s*```$", "", text_out, flags=re.IGNORECASE)
            
            try:
                return json.loads(text_out)
            except json.JSONDecodeError:
                match = re.search(r'(\{.*})', text_out, re.DOTALL)
                if match:
                    cleaned_json = match.group(1)
                    return json.loads(cleaned_json)
                else:
                    raise json.JSONDecodeError("Nenhum bloco de chaves encontrado.", text_out, 0)
            
    except urllib.error.URLError as e:
        print(f"  [Erro Ollama] Nao foi possivel ligar ao Ollama: {e}")
        return {}
    except json.JSONDecodeError:
        print("  [Erro LLM] O modelo gerou texto invalido ou corrompeu a estrutura JSON.")
        print(f"  [Debug Texto Retornado]: {text_out}")
        return {}


def mock_evaluate_metrics(insights_data: dict) -> dict:
    insights = insights_data.get("insights", [])
    if not insights:
        return {"specificity": 0.0, "actionability": 0.0, "overall": 0.0}

    spec_scores = []
    act_scores  = []

    for item in insights:
        obs = str(item.get("observacao", "")).lower()
        rec = str(item.get("recomendacao", "")).lower()

        has_number = any(char.isdigit() for char in obs)
        has_zone   = "z_" in obs or "zona" in obs
        s_score    = 1.0 if (has_number and has_zone) else (0.5 if (has_number or has_zone) else 0.2)
        spec_scores.append(s_score)

        has_action = any(v in rec for v in ["alocar", "reforcar", "instalar", "mudar", "testar", "verificar", "ajustar", "abrir"])
        has_detail = len(rec.split()) > 6
        a_score    = 1.0 if (has_action and has_detail) else (0.6 if (has_action or has_detail) else 0.3)
        act_scores.append(a_score)

    sa = round(sum(spec_scores) / len(spec_scores), 2)
    sb = round(sum(act_scores) / len(act_scores), 2)
    
    return {
        "specificity": sa,
        "actionability": sb,
        "overall": round((sa + sb) / 2, 2)
    }


def main():
    ap = argparse.ArgumentParser(description="Gera insights com LLM a partir de metrics.json usando ficheiros de prompt externos.")
    ap.add_argument("--input",       default="output/metrics.json")
    ap.add_argument("--output",      default="output/insights.json")
    ap.add_argument("--strategy",    default="both", choices=["A", "B", "both"])
    ap.add_argument("--temperature", type=float, default=0.3)
    args = ap.parse_args()

    print(f"[insights] input={args.input}  output={args.output}  modelo={MODEL}")

    current_temp = args.temperature
    if "evaluate.py" in "".join(os.sys.argv):
        print("[insights] Detetada execucao via Harness de Avaliacao. Forcando temperature = 0")
        current_temp = 0.0

    with open(args.input, "r", encoding="utf-8") as f:
        metrics_data = json.load(f)

    filtered_metrics = {}
    
    if "loja_geral" in metrics_data:
        filtered_metrics["loja_geral"] = metrics_data["loja_geral"]
    elif "metrics" in metrics_data and "loja" in metrics_data["metrics"]:
         filtered_metrics["loja_geral"] = metrics_data["metrics"]["loja"]
         
    if "sequencias_frequentes" in metrics_data:
        filtered_metrics["top_sequencias"] = dict(list(metrics_data["sequencias_frequentes"].items())[:5])
        
    if "funil_cliente" in metrics_data:
        filtered_metrics["funil_cliente"] = metrics_data["funil_cliente"]
    elif "funil" in metrics_data:
        filtered_metrics["funil_cliente"] = metrics_data["funil"]

    if "anomalias" in metrics_data:
        filtered_metrics["anomalias_detetadas"] = metrics_data["anomalias"]
    elif "deteção_anomalias" in metrics_data:
        filtered_metrics["anomalias_detetadas"] = metrics_data["deteção_anomalias"]

    if not filtered_metrics:
        filtered_metrics = {k: v for k, v in metrics_data.items() if "hora" not in k and "dia" not in k}

    metrics_json_str = json.dumps(filtered_metrics, ensure_ascii=False)

    results = {
        "metadata": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": MODEL,
            "temperature": current_temp,
            "strategies_run": []
        }
    }

    best_insights = None
    sa, sb = {}, {}

    if args.strategy in ["A", "both"]:
        print("  Executando Estrategia A (Zero-shot)...", flush=True)
        results["metadata"]["strategies_run"].append("A")
        try:
            prompt_a = load_prompt_from_file("A", metrics_json_str)
            res_a = query_ollama(prompt_a, current_temp)
            if res_a:
                sa = mock_evaluate_metrics(res_a)
                results["zero_shot"] = {
                    "insights": res_a.get("insights", []),
                    "resumo_executivo": res_a.get("resumo_executivo", []),
                    "evaluation": sa
                }
                best_insights = res_a
        except Exception as e:
            print(f"  [Erro Estrategia A] {e}")

    if args.strategy in ["B", "both"]:
        print("  Executando Estrategia B (Few-shot)...", flush=True)
        results["metadata"]["strategies_run"].append("B")
        try:
            prompt_b = load_prompt_from_file("B", metrics_json_str)
            res_b = query_ollama(prompt_b, current_temp)
            if res_b:
                sb = mock_evaluate_metrics(res_b)
                results["few_shot"] = {
                    "insights": res_b.get("insights", []),
                    "resumo_executivo": res_b.get("resumo_executivo", []),
                    "evaluation": sb
                }
                best_insights = res_b
        except Exception as e:
            print(f"  [Erro Estrategia B] {e}")

    if args.strategy == "both" and sa and sb:
        results["comparison"] = {
            "winner": "B (Few-shot)" if sb.get("overall", 0) >= sa.get("overall", 0) else "A (Zero-shot)",
            "zero_shot_scores": sa,
            "few_shot_scores":  sb,
            "delta_specificity": round(sb.get("specificity", 0) - sa.get("specificity", 0), 3),
            "delta_actionability": round(sb.get("actionability", 0) - sa.get("actionability", 0), 3),
        }
        print(f"  Comparacao concluida. Vencedor: {results['comparison']['winner']}", flush=True)

    if best_insights:
        results["insights"]         = best_insights.get("insights", [])
        results["resumo_executivo"] = best_insights.get("resumo_executivo", [])

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"  [Sucesso] insights.json guardado com {len(results.get('insights', []))} insights principais.")


if __name__ == "__main__":
    main()