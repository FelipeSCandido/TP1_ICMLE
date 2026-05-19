# TP1 — From Raw Detections to Real Intelligence

**LIACD 2025/2026 — Interacção com Modelos de Larga Escala** 

Pipeline de reconstrução de trajetórias e retail intelligence a partir de eventos anónimos de visão computacional.

---

## Estrutura do Projecto

```text
tp1/
├── README.md
├── requirements.txt
├── data/
│   ├── events.csv          ← Dataset de treino (250.000 eventos)
│   └── zones.json          ← Mapa de zonas com adjacências e walk times
├── src/
│   ├── stitcher.py         ← Fase 1: Reconstrução de trajetórias individuais
│   ├── analytics.py        ← Fase 2a: Pipeline analítico e cálculo de métricas
│   ├── insights.py         ← Fase 2b: LLM Insight Engine (Zero-shot vs Few-shot)
│   └── report.py           ← Fase 2c: Geração automática do relatório semanal
├── prompts/
│   ├── zero_shot.txt       ← Prompt isolado para a Estratégia A
│   └── few_shot.txt        ← Prompt isolado para a Estratégia B (Exemplos de suporte)
├── output/
│   ├── journeys.csv        ← Trajetórias estruturadas geradas pelo stitcher
│   ├── metrics.json        ← Métricas determinísticas consolidadas
│   ├── insights.json       ← Insights gerados pela LLM e avaliação estatística
│   └── weekly_report.md    ← Briefing final em Markdown para o gestor da loja
└── evaluate.py             ← Harness de avaliação automática (Pipeline de Teste)

##  Pré-requisitos
O projeto foi desenhado para utilizar apenas as bibliotecas nativas da Python Standard Library (como json, csv, urllib, argparse), não exigindo obrigatoriamente gestores de pacotes externos se optar por esta via. Caso use pacotes como Pandas, utilize o requirements.txt.

- Python 3.9+
- Ollama instalado e ativo em ambiente local.
# Descarregar o modelo otimizado utilizado no motor de insights
ollama pull qwen2.5:3b

## Execução do Pipeline Completo
O pipeline pode ser executado passo a passo ou via harness de avaliação automática.
# 1. Reconstruir trajetórias a partir dos eventos brutos
python src/stitcher.py --input data/events.csv --output output/journeys.csv

# 2. Calcular métricas estatísticas agregadas
python src/analytics.py --input output/journeys.csv --output output/metrics.json

# 3. Gerar insights estratégicos via LLM (Ollama) utilizando ambas as abordagens
python src/insights.py --input output/metrics.json --output output/insights.json --strategy both

# 4. Compilar o relatório Markdown final para o gestor
python src/report.py --input output/insights.json --output output/weekly_report.md

Para validar o pipeline sob as condições rigorosas de teste automático, execute:
python evaluate.py --data data/events.csv --output evaluation_report.json

## Configuração do Modelo LLM e Otimizações de Engenharia
- Modelo Utilizado: qwen2.5:3b   

- Endpoint API: http://localhost:11434/api/generate   

- Temperatura de Operação: 0.3 (Exploração controlada em desenvolvimento)

- Temperatura de Avaliação: 0.0 (Forçada automaticamente via evaluate.py para assegurar reprodutibilidade total)

## Engenharia de Contexto e Proteção de Memória
Modelos compactos locais (como o de 3B parâmetros) são altamente suscetíveis a falhas de segmentação ou truncagem quando submetidos a payloads extensos de dados brutos. No src/insights.py, foi implementado um filtro dinâmico de contexto:
- Remove listagens temporais exaustivas (como métricas horárias massivas). 
- Agrega as sequências mais frequentes limitando ao Top 5. 
- Garante que apenas dados agregados e de alto valor de análise entram na janela de contexto, permitindo que o modelo corra sem quebras estruturais e de forma célere.

## Desacoplamento de Prompts
Para maximizar a manutenibilidade do código e cumprir as boas práticas de Engenharia de Prompts, os templates foram completamente extraídos do código fonte:  
- prompts/zero_shot.txt: Focado em regras rígidas de formatação de esquema e injeção direta de dados (Estratégia A).  
- prompts/few_shot.txt: Inclui exemplos contrastantes com demonstrações explícitas de respostas ideais versus respostas incompletas (Estratégia B).

## Notas Técnicas de Arquitetura
Algoritmo de Stitching (src/stitcher.py)
- Mecânica: Algoritmo ganancioso com scoring de afinidade multicritério.
- Restrições Implementadas: Consistência temporal , plausibilidade espacial , consistência demográfica (voto maioritário para contornar ruídos de classificação da visão computacional) e validação estrutural de entrada/permanência/saída.  
- Complexidade Temporal: O(E * T) onde T é o número de trajetórias simultâneas ativas na loja. Conclui o processamento do dataset completo em escassos segundos, contornando a ineficiência de abordagens quadráticas
O(n^2). 

## Separação Rígida de Conceitos
A inteligência artificial nunca interage diretamente com ficheiros brutos (como CSVs). Toda a computação pesada e agregação estatística matemática é tratada de forma determinística em Python puro (src/analytics.py). A LLM atua estritamente como uma camada cognitiva de síntese e recomendação operacional, garantindo total auditabilidade dos dados numéricos apresentados no relatório final.