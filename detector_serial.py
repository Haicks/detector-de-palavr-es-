"""
PROGRAMAÇÃO CONCORRENTE E DISTRIBUÍDA
Detecção SERIAL de Palavrões em Áudio
Baseline para comparação com a versão paralela.

Usa ffmpeg via subprocess — não depende de pydub para conversão/segmentação.
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

# ─────────────────────────────────────────────
# UTILITÁRIOS
# ─────────────────────────────────────────────

def verificar_ffmpeg():
    """Verifica se ffmpeg está disponível no PATH."""
    if shutil.which("ffmpeg") is None:
        print("ERRO: ffmpeg não encontrado no PATH.")
        print("Instale em https://ffmpeg.org/download.html e adicione ao PATH.")
        sys.exit(1)


def obter_duracao(caminho: str) -> float:
    """Retorna a duração do arquivo em segundos usando ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format", caminho
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
    info = json.loads(out)
    return float(info["format"]["duration"])


def extrair_segmento(caminho_entrada: str, inicio: float, duracao_seg: int,
                     caminho_saida: str) -> bool:
    """
    Extrai um trecho do áudio original diretamente com ffmpeg,
    convertendo para WAV mono 16kHz em uma única passagem.
    Muito mais rápido que converter tudo e depois segmentar.
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(inicio),
        "-t",  str(duracao_seg),
        "-i",  caminho_entrada,
        "-ac", "1",           # mono
        "-ar", "16000",       # 16 kHz (ideal para Speech Recognition)
        "-vn",                # sem vídeo
        "-f", "wav",
        caminho_saida
    ]
    resultado = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    return resultado.returncode == 0


def segmentar_audio(caminho_entrada: str, duracao_seg: int,
                    pasta_tmp: str) -> list:
    """
    Gera todos os segmentos WAV serialmente.
    Retorna lista de (indice, caminho_wav, inicio_s).
    """
    t0 = time.perf_counter()
    duracao_total = obter_duracao(caminho_entrada)
    segmentos = []
    i = 0
    inicio = 0.0
    while inicio < duracao_total:
        caminho_seg = os.path.join(pasta_tmp, f"seg_{i:04d}.wav")
        ok = extrair_segmento(caminho_entrada, inicio, duracao_seg, caminho_seg)
        if ok and os.path.exists(caminho_seg) and os.path.getsize(caminho_seg) > 44:
            segmentos.append((i, caminho_seg, inicio))
        inicio += duracao_seg
        i += 1
    t1 = time.perf_counter()
    print(f"  [segmentação] {t1 - t0:.2f}s  →  {len(segmentos)} segmento(s) "
          f"de {duracao_seg}s  (áudio total: {duracao_total:.1f}s)")
    return segmentos, t1 - t0


def transcrever_segmento(indice: int, caminho: str, inicio_seg: float) -> tuple:
    """Transcreve um único segmento com Google Speech Recognition (pt-BR)."""
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(caminho) as fonte:
            audio_data = recognizer.record(fonte)
        texto = recognizer.recognize_google(audio_data, language="pt-BR")
    except sr.UnknownValueError:
        texto = ""
    except sr.RequestError as e:
        texto = ""
        print(f"    [ERRO API] seg {indice}: {e}")
    except Exception as e:
        texto = ""
        print(f"    [ERRO] seg {indice}: {e}")
    return indice, texto, inicio_seg


def detectar_palavroes(texto: str, inicio_seg: float) -> list:
    """Varre o texto em busca de palavrões e retorna ocorrências."""
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
# PIPELINE SERIAL PRINCIPAL
# ─────────────────────────────────────────────

def executar_serial(caminho_audio: str, duracao_seg: int = 55):
    print("\n" + "═" * 60)
    print("  DETECÇÃO SERIAL DE PALAVRÕES")
    print("═" * 60)

    verificar_ffmpeg()

    tempos = {}
    todas_ocorrencias = []
    todas_transcricoes = []
    segmentos = []

    # Pasta temporária para os segmentos WAV
    pasta_tmp = tempfile.mkdtemp(prefix="serial_segs_")

    try:
        # 1. SEGMENTAÇÃO (ffmpeg extrai + converte diretamente)
        print("\n[1/3] Segmentando e convertendo áudio com ffmpeg...")
        segmentos, tempos["segmentacao"] = segmentar_audio(
            caminho_audio, duracao_seg, pasta_tmp)

        # 2. TRANSCRIÇÃO SERIAL
        print(f"\n[2/3] Transcrevendo {len(segmentos)} segmento(s) — SERIAL...")
        t0 = time.perf_counter()
        transcricoes = []
        for idx, caminho_seg, inicio in segmentos:
            t_seg = time.perf_counter()
            resultado = transcrever_segmento(idx, caminho_seg, inicio)
            transcricoes.append(resultado)
            todas_transcricoes.append(resultado[1])
            elapsed = time.perf_counter() - t_seg
            preview = f'"{resultado[1][:55]}..."' if len(resultado[1]) > 55 \
                      else f'"{resultado[1]}"'
            print(f"  seg {idx:03d} @ {inicio:.0f}s  ({elapsed:.2f}s)  {preview}")
        tempos["transcricao"] = time.perf_counter() - t0

        # 3. DETECÇÃO SERIAL
        print(f"\n[3/3] Detectando palavrões — SERIAL...")
        t0 = time.perf_counter()
        for idx, texto, inicio in transcricoes:
            ocorrencias = detectar_palavroes(texto, inicio)
            todas_ocorrencias.extend(ocorrencias)
            for oc in ocorrencias:
                print(f"  ⚑  \"{oc['palavrao']}\"  ~{oc['timestamp_aprox_s']}s")
        tempos["deteccao"] = time.perf_counter() - t0

    finally:
        shutil.rmtree(pasta_tmp, ignore_errors=True)

    # ── RESUMO ──
    tempos["total_serial"] = sum(tempos.values())

    print("\n" + "═" * 60)
    print("  RESULTADOS SERIAIS")
    print("═" * 60)
    print(f"  Segmentos processados : {len(segmentos)}")
    print(f"  Palavrões encontrados : {len(todas_ocorrencias)}")
    print()
    print(f"  Segmentação : {tempos['segmentacao']:.4f} s")
    print(f"  Transcrição : {tempos['transcricao']:.4f} s")
    print(f"  Detecção    : {tempos['deteccao']:.6f} s")
    print(f"  {'─'*40}")
    print(f"  TOTAL SERIAL: {tempos['total_serial']:.4f} s")
    print("═" * 60)

    resultado_json = {
        "arquivo": caminho_audio,
        "modo": "serial",
        "duracao_seg_s": duracao_seg,
        "segmentos": len(segmentos),
        "total_palavroes": len(todas_ocorrencias),
        "ocorrencias": todas_ocorrencias,
        "tempos_s": tempos,
        "transcricao_completa": " ".join(todas_transcricoes)
    }
    saida = os.path.splitext(caminho_audio)[0] + "_resultado_serial.json"
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(resultado_json, f, ensure_ascii=False, indent=2)
    print(f"\n  Resultado salvo em: {saida}")
    return resultado_json


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    arquivo = sys.argv[1] if len(sys.argv) > 1 else "meu_video.mp4"
    duracao = int(sys.argv[2]) if len(sys.argv) > 2 else 55

    if not os.path.exists(arquivo):
        print(f"Erro: arquivo '{arquivo}' não encontrado.")
        print("Uso: python detector_serial.py <arquivo> [duração_segmento_s]")
        sys.exit(1)

    executar_serial(arquivo, duracao)
