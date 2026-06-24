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
| 1          |                       |
| 2          |                       |
| 4          |                       |
| 8          |                       |
| 12         |                       |

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
| 1       |           | 1.0000  | 1.0000     |
| 2       |           |         |            |
| 4       |           |         |            |
| 8       |           |         |            |
| 12      |           |         |            |

---

## 10. Análise dos Resultados

_(preencher após obter os dados reais)_

Pontos a discutir:
- O speedup foi próximo do ideal até qual configuração?
- Em qual ponto a eficiência começou a cair expressivamente?
- O número de segmentos (241) é maior que 12 threads, então todas as threads têm trabalho — o que favorece boa eficiência até 12T.
- A parte serial (segmentação no disco, overhead do ffmpeg) limita o speedup máximo (Lei de Amdahl).

---

## 11. Conclusão

_(preencher após os experimentos)_

Sugestões de pontos a comentar:
- Qual configuração de threads apresentou melhor custo-benefício?
- O paralelismo trouxe ganho significativo considerando o volume de dados?
- Melhorias possíveis: API de transcrição em lote, processamento de segmentos maiores, uso de ProcessPoolExecutor para contornar o GIL em cargas CPU-bound.
