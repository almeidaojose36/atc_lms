#!/usr/bin/env python3
"""Voz-para-voz (ElevenLabs) dos clips regenerados em «Avatar Regenarated Clips».

Os clips foram gerados de novo com sotaque português; o Voice Changer converte bem
para português angolano quando a fonte já é português europeu. Resultado em
producao/videos/avatar-video-regenerado-voz/<ID>.mp4.
"""
import pathlib, subprocess, sys, tempfile

RAIZ = pathlib.Path(__file__).resolve().parents[2]
FONTE = RAIZ / "Avatar Regenarated Clips"
DESTINO = RAIZ / "producao" / "videos" / "avatar-video-regenerado-voz"
API = "https://api.elevenlabs.io/v1"
HELENA, MIGUEL = "JGnWZj684pcXmK2SxYIv", "FbFkkfp4Iv6U5Q1WC4C2"
# ID -> (prefixo do nome do ficheiro, apresentador)
CLIPS = {
    "H1": ("Choosing_first_course_and_learning", "H"), "H3": ("Exploring_computer_components", "H"),
    "H6": ("Presenter_explaining_online_lear", "H"), "H9": ("Video_demonstration_exercise_ins", "H"),
    "M2": ("Choosing_first_course_and_practice", "M"), "M3": ("Computer_parts_opening_lesson", "M"),
    "M4": ("Course_content_overview_and_narr", "M"), "M8": ("Narrator_explaining_computer_exe", "M"),
    "M9": ("Voice-over_recording_for_course_", "M"),
}

def run(*a): subprocess.run([str(x) for x in a], check=True)

def procurar(prefixo):
    return next(p for p in sorted(FONTE.rglob("*.mp4")) if p.name.startswith(prefixo))

if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    for cid in sys.argv[1:] or CLIPS:
        prefixo, q = CLIPS[cid]; src = procurar(prefixo); dst = DESTINO / f"{cid}.mp4"
        if dst.exists(): continue
        voz = HELENA if q == "H" else MIGUEL
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-ac", "1", "-ar", "44100", t / "o.wav")
            run("curl", "-sS", "--fail-with-body", "-o", t / "n.mp3", "-F", f"audio=@{t/'o.wav'}",
                "-F", "model_id=eleven_multilingual_sts_v2", "-F", "remove_background_noise=true", "-F", "seed=22",
                "-F", 'voice_settings={"stability":0.6,"similarity_boost":0.85}',
                f"{API}/speech-to-speech/{voz}?output_format=mp3_44100_128")
            audio = t / "n.mp3"
            if q == "H":
                run("curl", "-sS", "--fail-with-body", "-o", t / "i.mp3", "-F", f"audio=@{audio}", f"{API}/audio-isolation")
                audio = t / "i.mp3"
            run("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-shortest", dst)
        print("ok", cid, src.name, flush=True)
