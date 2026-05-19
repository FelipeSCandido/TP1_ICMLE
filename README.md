# TP1 — From Raw Detections to Real Intelligence

## Identificação do Autor
* **Nome Completo:** Felipe Santana Cândido
* **Repositório Oficial:** [GitHub - TP1_ICMLE](https://github.com/FelipeSCandido/TP1_ICMLE.git)
* **Unidade Curricular:** Interação com Modelos em Larga Escala (LIACD)
* **Ano Letivo:** 2º Ano - 2º Semestre

---

## 🏗️ 1. Arquitetura do Sistema e Engenharia de Software

O projeto está estruturado como um pipeline sequencial e modular de processamento de dados e inteligência artificial. O fluxo foi desenhado para garantir a separação clara de responsabilidades, permitindo que cada componente funcione de forma independente e auditável.

[ data/events.csv ] (250k eventos em bruto)
│
▼
┌─────────────────┐
│   stitcher.py   │  ◄─── Fase 1: Reconstrução O(1) de Trajetórias
└────────┬────────┘
│
▼
[ output/journeys.csv ] (Trajetórias consolidadas)
│
▼
┌─────────────────┐
│  analytics.py   │  ◄─── Fase 2a: Métricas Determinísticas & Anomalias
└────────┬────────┘
│
▼
[ output/metrics.json ] (Estatísticas e desvios)
│
▼
┌─────────────────┐
│   insights.py   │  ◄─── Fase 2b: Prompting Engine (Qwen 2.5:3b via Ollama)
└────────┬────────┘
│
▼
[ output/insights.json ] (Análise qualitativa estruturada)
│
▼
┌─────────────────┐
│    report.py    │  ◄─── Fase 2c: Compilação do Briefing Executivo
└────────┬────────┘
│
▼
[ output/weekly_report.md ] (Relatório final limpo para o Gestor)

### Componentes do Repositório:
* `src/stitcher.py`: Aborda o problema de correspondência de dados brutos (*data stitching*), unificando os registos fragmentados de sensores numa sequência cronológica contínua por cliente.
* `src/analytics.py`: Engine estatística que calcula indicadores de desempenho (KPIs) da loja, taxas de conversão do funil de vendas e desvios estatísticos significativos (anomalias).
* `src/insights.py`: Módulo de inteligência que faz a curadoria de dados e interage com o LLM através de estratégias avançadas de prompting.
* `src/report.py`: Tradutor de dados que converte as estruturas JSON em relatórios executivos formatados em Markdown.
* `prompts/`: Diretoria centralizada contendo os templates de contextualização (`zero_shot.txt` e `few_shot.txt`).

---

## ⚡ 2. Discussão Técnica e Opções de Implementação

### Fase 1: Otimização Algorítmica e Resolução de Hiper-fragmentação
O processamento inicial do volume de dados (250.000 eventos) apresentava barreiras severas de desempenho e precisão. A resolução destas condicionantes seguiu duas abordagens metodológicas estritas:

1. **Arquitetura de Complexidade O(1):** A pesquisa linear iterativa em listas tradicionais do Python gerava uma saturação computacional, resultando num tempo de execução de **864.3 segundos (cerca de 14 minutos)**. O algoritmo foi reestruturado para utilizar Tabelas de Dispersão (`dict`) indexadas por zonas ativas e uma fila cronológica assente em Double-Ended Queues (`collections.deque`). Esta mutação algorítmica permitiu que as operações de inserção, pesquisa e remoção passassem a ter complexidade constante, fazendo o tempo de execução desabar para escassos **3.8 segundos**.
2. **Estratégia de Maximização de Completude:** A leitura estocástica dos sensores introduz ruído de classificação demográfica (oscilações na deteção de género e idade de uma mesma pessoa entre secções). A lógica de correspondência foi alterada para efetuar uma **busca global de candidatos ativos** em detrimento da restrição de vizinhos diretos no grafo de zonas. Adicionalmente, ajustaram-se os limiares temporais (`MAX_GAP_SECONDS = 1200`) e flexibilizou-se o peso eliminatório dos atributos demográficos. Esta tolerância ao ruído visual permitiu costurar os fragmentos dispersos causados por pontos cegos na loja, elevando a completude para o patamar verde de excelência sem introduzir sobreposições temporais (Consistência a 100%).

### Fase 2: Robustez Contextual e Mitigação de Alucinações do LLM
A operação de modelos de linguagem de menor escala em ambientes locais (como o Qwen 2.5:3b) exige uma gestão rigorosa da janela de contexto para evitar a degradação da atenção e o aparecimento de falsificações de dados (*hallucinations*).
* **Curadoria Prévia de Contexto:** Em vez de injetar a totalidade da telemetria no modelo, o script `insights.py` atua como um filtro, isolando as séries de dados críticas (top sequências de transição, anomalias com maior desvio padrão e o funil de conversão absoluto).
* **Garantia de Tipagem Símica:** Forçou-se o parâmetro `format="json"` na API nativa do Ollama. Para blindar a resiliência do sistema contra quebras de parse, implementaram-se filtros por expressões regulares (`regex`) para higienizar invólucros Markdown (` ```json `) que o modelo por vezes adiciona de forma redundante.

---

## 📊 3. Análise Comparativa de Estratégias de Prompting

O sistema foi submetido ao crivo do avaliador automático `evaluate.py`, comparando o desempenho do modelo local perante duas arquiteturas de prompt distintas:

| Métrica de Avaliação | Estratégia A (Zero-Shot) | Estratégia B (Few-Shot) |
| :--- | :---: | :---: |
| **Taxa de Anti-Alucinação** | 100.0% | 100.0% |
| **Precisão Numérica** | ~60.0% | **75.0%** |
| **Especificidade Contextual** | Genérica / Textual | **Alta (Mapeia as Zonas Reais)** |
| **Direcionamento de Ações** | Abstrato | **Prático e Aplicável** |

### Conclusões Baseadas nos Resultados Reais:
O modelo **Qwen 2.5:3b** beneficiou criticamente da **Estratégia B (Few-Shot)**. A inclusão de demonstrações exemplificativas no ficheiro `few_shot.txt` fixou o comportamento do modelo, mitigando desvios analíticos e elevando a precisão numérica para **75.0%**. O modelo aprendeu a associar os desvios estatísticos diretamente aos identificadores técnicos das zonas (ex: `Z_S3`, `Z_N2`) em vez de utilizar descrições vagas. Isto prova que a aprendizagem em contexto (*in-context learning*) é vital para dotar modelos de menor escala de capacidades de raciocínio de negócio estruturado.

---

## 🛠️ 4. Guia de Instalação e Execução

### Pré-requisitos
Garante que tens o Python 3.11 ou superior instalado, bem como o ecossistema do Ollama ativo no teu computador.

# Descarregar e iniciar o modelo local obrigatório
ollama run qwen2.5:3b

Execução Centralizada (Recomendado)
Para maior facilidade e reprodutibilidade, foi desenvolvido um script utilitário de automação na raiz do repositório. Este comando limpa o ambiente, cria as pastas necessárias, executa todas as fases do projeto sequencialmente, mede a performance cronometrada de cada script e invoca o avaliador oficial:

# Fase 1: Reconstrução das Trajetórias dos Clientes
python src/stitcher.py --input data/events.csv --output output/journeys.csv

# Fase 2a: Processamento de Métricas e Deteção de Anomalias
python src/analytics.py --input output/journeys.csv --output output/metrics.json

# Fase 2b: Ativação da IA Engine para Extração de Insights
python src/insights.py --input output/metrics.json --output output/insights.json --strategy both

# Fase 2c: Compilação do Briefing Executivo em Markdown
python src/report.py --input output/insights.json --output output/weekly_report.md

Execução do Harness de Teste do Professor
Para gerar o relatório de auditoria e validar as notas de consistência, cobertura e precisão numérica:

python evaluate.py --data data/events.csv --output evaluation_report.json
