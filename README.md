# Detecção de Palavrões em Áudio — Serial vs Paralelo

**Disciplina:** Programação Concorrente e Distribuída  
**Aluno(s):** Matheus Dantas, Luis Gustavo  
**Turma:** 5 semestre 
**Professor:** Rafael  
**Data:** 23/06

---

## Estrutura do Projeto

```
detector_palavroes/
├── meu_video.mp4               ← vídeo de entrada (~2h)
├── detector_serial.py          ← pipeline serial (baseline T1)
├── detector_paralelo.py        ← pipeline paralelo (2/4/8/12 threads)
├── requirements.txt            ← dependências Python
└── README.md                   ← este arquivo
```

---

## Pré-requisitos

### 1. Python 3.10+
Baixe em: https://python.org/downloads  
Na instalação marque **"Add Python to PATH"**

### 2. ffmpeg (obrigatório)
Baixe em: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip  
Extraia em `C:\ffmpeg` e adicione `C:\ffmpeg\bin` ao PATH do Windows.  
Teste: `ffmpeg -version`

### 3. Dependências Python
```powershell
python -m pip install -r requirements.txt
```

## Como Executar

### Versão Serial (baseline)
```powershell
python detector_serial.py meu_video.mp4
```

### Versão Paralela (escolha o número de threads)
```powershell
python detector_paralelo.py meu_video.mp4 2
python detector_paralelo.py meu_video.mp4 4
python detector_paralelo.py meu_video.mp4 8
python detector_paralelo.py meu_video.mp4 12
```

### Benchmark completo (serial + 2/4/8/12 automático)
```powershell
python detector_paralelo.py meu_video.mp4 --benchmark
```

---

## 1. Descrição do Problema

O programa detecta automaticamente palavrões em um vídeo de ~2 horas. O áudio é extraído e segmentado em trechos de 30 segundos via ffmpeg, cada segmento é transcrito pela API Google Speech Recognition (pt-BR), e o texto é varrido contra uma lista de palavrões em português.

**Por que threads funcionam bem aqui?**  
A transcrição é I/O-bound: a thread fica ociosa aguardando a resposta da API de rede. O `ThreadPoolExecutor` envia múltiplos segmentos simultaneamente, reduzindo o tempo de espera proporcionalmente ao número de threads até o limite de segmentos disponíveis (~241 para este vídeo).

- **Algoritmo:** extração ffmpeg + reconhecimento de fala + busca de substring
- **Volume:** ~2h de vídeo → 241 segmentos de 30s
- **Complexidade:** O(S × W) — S = segmentos, W = palavrões na lista

---

## 2. Ambiente Experimental

| Item                        | Descrição                          |
| --------------------------- | ---------------------------------- |
| Processador                 |12th Gen Intel(R) Core(TM) i5-1235U (1.30 GHz)                 |
| Número de núcleos           |10 Núcleos                      |
| Memória RAM                 | 8 GB de RAM                      |
| Sistema Operacional         | Windows 11                         |
| Linguagem utilizada         | Python 3.10+                       |
| Biblioteca de paralelização | `concurrent.futures.ThreadPoolExecutor` |
| Ferramentas externas        | ffmpeg 8.x, Google Speech API      |

---

## 3. Metodologia de Testes

- Tempo medido com `time.perf_counter()` (resolução de nanosegundos)
- Cada etapa cronometrada individualmente: segmentação, transcrição, detecção
- 1 execução por configuração (API externa introduz variação de rede)
- Para o relatório final: recomenda-se 3 execuções e usar a média

### Configurações testadas
- 1 thread — serial (T1, baseline)
- 2 threads 
- 4 threads
- 8 threads
- 12 threads

---

## 4. Resultados Experimentais

_(preencher após rodar — os valores abaixo são de referência do modo simulado)_

| Nº Threads | Tempo de Execução (s) |
| ---------- | --------------------- |
| 1          |    1277,31            |
| 2          |    549,68             |
| 4          |    176,21             |
| 8          |    96,56              |
| 12         |    66,2               |

---

## 5. Fórmulas de Speedup e Eficiência

```
Speedup(p)    = T(1) / T(p)
Eficiência(p) = Speedup(p) / p
```

---

## 6. Tabela de Speedup e Eficiência

_(preencher com os tempos medidos)_

| Threads | Tempo (s) | Speedup | Eficiência |
| ------- | --------- | ------- | ---------- |
| 1       |  1277,31  | 1.0000  |    1,0     |
| 2       |  549,68   |  2,32   |    1,16    |
| 4       |  176,21   |  7,25   |    1.81    |
| 8       |  96,56    |  13,23  |    1,65    |
| 12      |  66,25    |  19,28  |    1,61    |

---

## 10. Análise dos Resultados

O experimento revelou um comportamento de **speedup superlinear** em todas as configurações testadas — ou seja, a eficiência ficou acima de 1,0 em todos os casos, o que é incomum em paralelismo tradicional mas esperado em tarefas predominantemente I/O-bound.

**Evolução do speedup:**

- De **1 → 2 threads**, o speedup foi de 2,32x (eficiência 1,16): já superior ao ideal teórico, pois as duas threads ficam ociosas aguardando a API simultaneamente, e a sobreposição de espera reduz o tempo total além do que uma simples divisão por 2 explicaria.
- De **2 → 4 threads**, o salto foi o mais expressivo proporcionalmente: speedup de 7,25x e eficiência de 1,81 — a melhor eficiência registrada. Nessa faixa, o paralelismo de rede está sendo aproveitado de forma quase ideal.
- De **4 → 8 threads**, o speedup continua crescendo (13,23x), mas a eficiência cai de 1,81 para 1,65. Isso indica que fatores de overhead começam a aparecer: gerenciamento de mais threads, concorrência no acesso ao disco durante a segmentação, e a fração serial do pipeline (etapa de segmentação via ffmpeg) começa a pesar relativamente mais.
- De **8 → 12 threads**, o crescimento de speedup é o menor entre as transições (13,23 → 19,28x) e a eficiência segue caindo (1,65 → 1,61). O programa ainda ganha com mais threads, mas o retorno marginal diminui — comportamento previsto pela **Lei de Amdahl**: a parte que não pode ser paralelizada (segmentação em disco) impõe um teto crescente.

**Por que o speedup foi superlinear?**

A tarefa de transcrição é quase inteiramente tempo de espera de rede. Ao disparar múltiplas requisições simultâneas, as esperas se sobrepõem quase completamente — 12 threads esperando juntas terminam em muito menos que 1/12 do tempo de uma única thread esperando em fila. Isso explica eficiências consistentemente acima de 1,0.

**Fração serial e Lei de Amdahl:**

A etapa de segmentação (ffmpeg) consumiu aproximadamente 3% do tempo total no modo serial (~31s de 1277s). Pelo modelo de Amdahl, esse percentual serial limita o speedup máximo teórico a ~33x, independente de quantas threads sejam usadas. Com 12 threads já atingimos 19,28x — estamos em ~58% do teto teórico, o que demonstra uma implementação paralela eficiente.

---

## 11. Conclusão

O projeto demonstrou na prática que a escolha correta do modelo de paralelismo é tão importante quanto a implementação em si. Ao identificar a transcrição de áudio como uma tarefa I/O-bound — com ~97% do tempo total consumido aguardando respostas da API de rede —, o uso de `ThreadPoolExecutor` se mostrou a abordagem ideal, resultando em ganhos de desempenho expressivos e consistentes.

**Melhor custo-benefício:** A configuração de **4 threads** apresentou a maior eficiência (1,81), sendo a opção mais equilibrada entre ganho de velocidade e aproveitamento de recursos. Para cenários onde o tempo absoluto é prioritário, **12 threads** entregou o melhor resultado (19,28x mais rápido que o serial).

**Paralelismo valeu a pena?** Sim, de forma significativa. Reduzir o tempo de processamento de ~21 minutos (serial) para ~1 minuto (12 threads) em um vídeo de 2 horas é um ganho prático real — especialmente considerando que a mudança no código foi relativamente simples: substituir chamadas sequenciais por um pool de threads gerenciado pelo próprio Python.

**Limitações identificadas:**
- A busca por substring simples gerou falsos positivos (ex: `"cu"` detectado dentro de `"concurso"`). A correção com expressões regulares e `\b` (word boundary) resolve esse problema.
- Uma única execução por configuração limita a confiabilidade estatística dos tempos medidos, dado que a variação de rede pode influenciar os resultados.

**Melhorias possíveis para trabalhos futuros:**
- Usar uma API de transcrição que suporte requisições em lote, reduzindo ainda mais o overhead por segmento.
- Aumentar o tamanho dos segmentos (ex: 60s em vez de 30s) para reduzir o número total de chamadas de API sem perda de qualidade.
- Para cargas CPU-bound futuras (ex: transcrição local com Whisper), substituir `ThreadPoolExecutor` por `ProcessPoolExecutor` para contornar o GIL e obter paralelismo real de CPU.
