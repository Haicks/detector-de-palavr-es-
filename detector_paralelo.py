"""
PROGRAMAÇÃO CONCORRENTE E DISTRIBUÍDA
Detecção PARALELA de Palavrões em Áudio
Usa ThreadPoolExecutor para paralelizar segmentação, transcrição e detecção.
Configurações: 2, 4, 8 e 12 threads.

Usa ffmpeg via subprocess — não depende de pydub.
Requer: pip install SpeechRecognition
Requer: ffmpeg instalado e no PATH do sistema.
"""

import time
import subprocess
import os
import sys
import json
import tempfile
import shutil
import threading
import concurrent.futures
import speech_recognition as sr

# ─────────────────────────────────────────────
# LISTA DE PALAVRÕES (PT-BR)
# ─────────────────────────────────────────────
PALAVROES = [
    "porra", "merda", "caralho", "puta", "viado", "otário", "idiota",
    "imbecil", "cuzão", "buceta", "pau", "cu", "foder", "fodido", "foda",
    "arrombado", "babaca", "bosta", "desgraça", "droga", "filha da puta",
    "filho da puta", "inferno", "maldito", "mierda", "puta merda",
    "vai se foder", "vai tomar no cu", "bossal", "cagão", "vagabundo",
    "vadia", "piranha", "safado", "safada", "canalha", "lixo", "inútil",
]

_print_lock = threading.Lock()

def tprint(*args, **kwargs):
    """Print thread-safe."""
    with _print_lock:
        print(*args, **kwargs)


# ─────────────────────────────────────────────
# UTILITÁRIOS
# ─────────────────────────────────────────────

def verificar_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("ERRO: ffmpeg não encontrado no PATH.")
        print("Instale em https://ffmpeg.org/download.html e adicione ao PATH.")
        sys.exit(1)


def obter_duracao(caminho: str) -> float:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", caminho
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    return float(json.loads(out)["format"]["duration"])


def extrair_segmento_worker(args: tuple) -> tuple:
    """
    Worker de segmentação paralela:
    extrai + converte um trecho do vídeo para WAV mono 16kHz via ffmpeg.
    Retorna (indice, caminho_wav, inicio_s) ou None em caso de erro.
    """
    indice, caminho_entrada, inicio, duracao_seg, caminho_saida = args
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(inicio),
        "-t",  str(duracao_seg),
        "-i",  caminho_entrada,
        "-ac", "1",
        "-ar", "16000",
        "-vn",
        "-f", "wav",
        caminho_saida
    ]
    resultado = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    if resultado.returncode == 0 and os.path.exists(caminho_saida) \
            and os.path.getsize(caminho_saida) > 44:
        return (indice, caminho_saida, inicio)
    return None


def transcrever_worker(args: tuple) -> tuple:
    """Worker de transcrição paralela via Google Speech Recognition."""
    indice, caminho, inicio_seg = args
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(caminho) as fonte:
            audio_data = recognizer.record(fonte)
        texto = recognizer.recognize_google(audio_data, language="pt-BR")
    except sr.UnknownValueError:
        texto = ""
    except sr.RequestError as e:
        texto = ""
        tprint(f"    [ERRO API] seg {indice}: {e}")
    except Exception as e:
        texto = ""
        tprint(f"    [ERRO] seg {indice}: {e}")

    preview = f'"{texto[:55]}..."' if len(texto) > 55 else f'"{texto}"'
    tprint(f"  seg {indice:03d} @ {inicio_seg:.0f}s  {preview}")
    return indice, texto, inicio_seg


def detectar_worker(args: tuple) -> list:
    """Worker de detecção paralela: busca palavrões no texto de um segmento."""
    indice, texto, inicio_seg = args
    texto_lower = texto.lower()
    ocorrencias = []
    for palavrao in PALAVROES:
        if palavrao in texto_lower:
            ocorrencias.append({
                "palavrao": palavrao,
                "timestamp_aprox_s": round(inicio_seg, 2),
                "contexto": texto[:120]
            })
    return ocorrencias


# ─────────────────────────────────────────────
# PIPELINE PARALELO PRINCIPAL
# ─────────────────────────────────────────────

def executar_paralelo(caminho_audio: str, num_threads: int = 4,
                      duracao_seg: int = 55) -> dict:
    print("\n" + "═" * 64)
    print(f"  DETECÇÃO PARALELA DE PALAVRÕES  [{num_threads} threads]")
    print("═" * 64)

    verificar_ffmpeg()

    tempos = {}
    todas_ocorrencias = []
    todas_transcricoes = []

    pasta_tmp = tempfile.mkdtemp(prefix=f"par{num_threads}_segs_")

    try:
        # ── 1. SEGMENTAÇÃO PARALELA ──────────────────────────────────
        # Múltiplas instâncias do ffmpeg rodam ao mesmo tempo,
        # cada uma extraindo e convertendo um trecho diferente.
        print(f"\n[1/3] Segmentando com {num_threads} threads (ffmpeg paralelo)...")
        t0 = time.perf_counter()

        duracao_total = obter_duracao(caminho_audio)
        tarefas_seg = []
        i = 0
        inicio = 0.0
        while inicio < duracao_total:
            caminho_seg = os.path.join(pasta_tmp, f"seg_{i:04d}.wav")
            tarefas_seg.append((i, caminho_audio, inicio, duracao_seg, caminho_seg))
            inicio += duracao_seg
            i += 1

        # Limita ffmpeg a 4 processos simultâneos para evitar contenção de I/O no disco.
        # Acima disso o ganho é mínimo e pode distorcer os tempos de segmentação.
        max_ffmpeg = min(num_threads, 4)
        segmentos = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_ffmpeg) as ex:
            for resultado in ex.map(extrair_segmento_worker, tarefas_seg):
                if resultado is not None:
                    segmentos.append(resultado)

        segmentos.sort(key=lambda x: x[0])
        tempos["segmentacao"] = time.perf_counter() - t0
        print(f"  → {len(segmentos)} segmentos em {tempos['segmentacao']:.2f}s")

        # ── 2. TRANSCRIÇÃO PARALELA ──────────────────────────────────
        print(f"\n[2/3] Transcrevendo {len(segmentos)} segmento(s) "
              f"com {num_threads} threads...")
        t0 = time.perf_counter()

        transcricoes = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as ex:
            futuros = {ex.submit(transcrever_worker, seg): seg[0]
                       for seg in segmentos}
            for futuro in concurrent.futures.as_completed(futuros):
                try:
                    resultado = futuro.result()
                    transcricoes.append(resultado)
                except Exception as e:
                    tprint(f"  [ERRO transcrição]: {e}")

        transcricoes.sort(key=lambda x: x[0])
        todas_transcricoes = [t[1] for t in transcricoes]  # ordem cronológica garantida
        tempos["transcricao"] = time.perf_counter() - t0

        # ── 3. DETECÇÃO PARALELA ─────────────────────────────────────
        print(f"\n[3/3] Detectando palavrões com {num_threads} threads...")
        t0 = time.perf_counter()

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as ex:
            resultados_deteccao = list(ex.map(detectar_worker, transcricoes))

        for ocorrencias in resultados_deteccao:
            todas_ocorrencias.extend(ocorrencias)
            for oc in ocorrencias:
                print(f"  ⚑  \"{oc['palavrao']}\"  ~{oc['timestamp_aprox_s']}s")

        tempos["deteccao"] = time.perf_counter() - t0

    finally:
        shutil.rmtree(pasta_tmp, ignore_errors=True)

    # ── RESUMO ────────────────────────────────────────────────────────
    tempos["total_paralelo"] = sum(tempos.values())

    print("\n" + "═" * 64)
    print(f"  RESULTADOS PARALELOS [{num_threads} threads]")
    print("═" * 64)
    print(f"  Segmentos processados : {len(segmentos)}")
    print(f"  Palavrões encontrados : {len(todas_ocorrencias)}")
    print()
    print(f"  Segmentação : {tempos['segmentacao']:.4f} s")
    print(f"  Transcrição : {tempos['transcricao']:.4f} s")
    print(f"  Detecção    : {tempos['deteccao']:.6f} s")
    print(f"  {'─'*44}")
    print(f"  TOTAL PARALELO ({num_threads}T): {tempos['total_paralelo']:.4f} s")
    print("═" * 64)

    resultado_json = {
        "arquivo": caminho_audio,
        "modo": f"paralelo_{num_threads}t",
        "num_threads": num_threads,
        "duracao_seg_s": duracao_seg,
        "segmentos": len(segmentos),
        "total_palavroes": len(todas_ocorrencias),
        "ocorrencias": todas_ocorrencias,
        "tempos_s": tempos,
        "transcricao_completa": " ".join(todas_transcricoes)
    }
    saida = (os.path.splitext(caminho_audio)[0]
             + f"_resultado_paralelo_{num_threads}t.json")
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(resultado_json, f, ensure_ascii=False, indent=2)
    print(f"\n  Resultado salvo em: {saida}")
    return resultado_json


# ─────────────────────────────────────────────
# BENCHMARK: roda serial + 2/4/8/12 e compara
# ─────────────────────────────────────────────

def executar_benchmark(caminho_audio: str, duracao_seg: int = 55):
    """Roda todas as configurações e imprime tabela de speedup/eficiência."""
    configs = [1, 2, 4, 8, 12]
    resultados = []

    for n in configs:
        if n == 1:
            # serial (importa e chama o serial)
            from detector_serial import executar_serial
            r = executar_serial(caminho_audio, duracao_seg)
            t = r["tempos_s"]["total_serial"]
        else:
            r = executar_paralelo(caminho_audio, n, duracao_seg)
            t = r["tempos_s"]["total_paralelo"]
        resultados.append({"threads": n, "tempo_s": t, "resultado": r})

    t_serial = next(r["tempo_s"] for r in resultados if r["threads"] == 1)

    print("\n" + "═" * 64)
    print("  TABELA FINAL — SPEEDUP E EFICIÊNCIA")
    print("═" * 64)
    print(f"  {'Threads':>8}  {'Tempo(s)':>10}  {'Speedup':>8}  {'Eficiência':>11}")
    print(f"  {'─'*8}  {'─'*10}  {'─'*8}  {'─'*11}")

    tabela = []
    for r in resultados:
        n  = r["threads"]
        t  = r["tempo_s"]
        sp = t_serial / t
        ef = sp / n
        tabela.append({"threads": n, "tempo_s": round(t, 4),
                        "speedup": round(sp, 4), "eficiencia": round(ef, 4)})
        print(f"  {n:>8}  {t:>10.4f}  {sp:>8.4f}  {ef:>11.4f}")

    print("═" * 64)

    bench = {
        "arquivo": caminho_audio,
        "t_serial_s": round(t_serial, 4),
        "tabela": tabela
    }
    with open("benchmark_resultado.json", "w", encoding="utf-8") as f:
        json.dump(bench, f, ensure_ascii=False, indent=2)
    print("\n  Benchmark salvo em: benchmark_resultado.json")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    arquivo  = sys.argv[1] if len(sys.argv) > 1 else "meu_video.mp4"
    flag_bench = len(sys.argv) > 2 and sys.argv[2] == "--benchmark"

    if not os.path.exists(arquivo):
        print(f"Erro: arquivo '{arquivo}' não encontrado.")
        print("Uso: python detector_paralelo.py <arquivo> [threads] [dur_seg_s]")
        print("     python detector_paralelo.py meu_video.mp4 4")
        print("     python detector_paralelo.py meu_video.mp4 --benchmark")
        sys.exit(1)

    if flag_bench:
        duracao = int(sys.argv[3]) if len(sys.argv) > 3 else 55
        executar_benchmark(arquivo, duracao)
    else:
        num_threads = int(sys.argv[2]) if len(sys.argv) > 2 else 4
        duracao     = int(sys.argv[3]) if len(sys.argv) > 3 else 55
        if num_threads not in (2, 4, 8, 12):
            print(f"Aviso: recomendado usar 2, 4, 8 ou 12 threads.")
        executar_paralelo(arquivo, num_threads, duracao)
