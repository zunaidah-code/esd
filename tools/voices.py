"""Generate narration & dialogue with offline TTS (espeak-ng + MBROLA).
Male (Hakim / narrator): mb-id1 (Indonesian, closest male voice to Malay).
Female (lecturer): mb-ma1 (Malay female).
English terms are respelled phonetically so they read naturally."""
import subprocess, os, wave, json

OUT = "/home/user/esd/build/audio"
os.makedirs(OUT, exist_ok=True)

LINES = {
    # key: (voice, speed, pitch, text-for-tts, caption text)
    "s01": ("m", "Edyukeisyen for Sasteinebel Diveloupmen, atau i, es, di, melengkapkan kita untuk bertindak demi alam, ekonomi, dan masyarakat.",
            "Education for Sustainable Development, atau ESD, melengkapkan kita untuk bertindak demi alam, ekonomi dan masyarakat."),
    "s02": ("m", "Sistems tingking. Melihat bagaimana setiap bahagian saling berkait, dan mempengaruhi.",
            "Systems thinking: melihat bagaimana setiap bahagian saling berkait dan mempengaruhi."),
    "s03": ("m", "Kritikel tingking. Mempersoal dakwaan, andaian, dan bukti, sebelum mempercayainya.",
            "Critical thinking: mempersoal dakwaan, andaian dan bukti sebelum mempercayainya."),
    "s04": ("m", "Entisipetori. Membayangkan pelbagai masa depan, dan menilai akibat tindakan hari ini.",
            "Anticipatory: membayangkan pelbagai masa depan dan menilai akibat tindakan hari ini."),
    "s05": ("m", "Normetif. Memahami nilai dan keadilan, di sebalik setiap keputusan.",
            "Normative: memahami nilai dan keadilan di sebalik setiap keputusan."),
    "s06": ("m", "Self aweernes. Menyedari peranan, nilai, dan tabiat diri sendiri.",
            "Self-awareness: menyedari peranan, nilai dan tabiat diri sendiri."),
    "s07": ("m", "Stratijik. Merancang tindakan berperingkat, untuk mencapai perubahan.",
            "Strategic: merancang tindakan berperingkat untuk mencapai perubahan."),
    "s08": ("m", "Kolaboreisyen. Belajar dan bertindak bersama, pihak yang berbeza.",
            "Collaboration: belajar dan bertindak bersama pihak yang berbeza."),
    "s09": ("m", "Intigreitid problem solving. Menggabungkan semua kompetensi, untuk penyelesaian menyeluruh.",
            "Integrated problem-solving: menggabungkan semua kompetensi untuk penyelesaian menyeluruh."),
    "s10": ("m", "Lapan kompetensi. Satu perubahan.",
            "Lapan kompetensi. Satu perubahan."),
    "s11": ("m", "Kognitif skils dalam em, kiu, ef, dipetakan kepada kritikel tingking, lalu dinilai melalui laporan kajian kes.",
            "Cognitive Skills dalam MQF dipetakan kepada Critical Thinking, lalu dinilai melalui laporan kajian kes."),
    "s12": ("m", "Rubrik menilai tahap. Daripada menerima dakwaan tanpa soal, hingga menilai pelbagai bukti, dan bias.",
            "Rubrik menilai tahap: daripada menerima dakwaan tanpa soal, hingga menilai pelbagai bukti dan bias."),
    "s13": ("m", "Jika ramai di tahap rendah, pensyarah menambah baik pengajaran, kemudian memantau semula. Itulah, si, kiu, ai.",
            "Jika ramai di tahap rendah, pensyarah menambah baik pengajaran, kemudian memantau semula. Itulah CQI."),
    "s14": ("m", "Doktor, i, es, di, bukan subjek tambahan. Ia cara belajar, untuk bertindak demi masa depan yang lestari.",
            "Dr., ESD bukan subjek tambahan. Ia cara belajar untuk bertindak demi masa depan yang lestari."),
    "s15a": ("f", "Apa peranan saya?", "Apa peranan saya?"),
    "s15b": ("m", "Jadi fasilitator, guna isu sebenar, selaraskan pentaksiran, dan jadi teladan.",
             "Jadi fasilitator, guna isu sebenar, selaraskan pentaksiran, dan jadi teladan."),
}
VOICE = {"m": ["-v", "mb-id1", "-s", "162", "-p", "50", "-a", "180"],
         "f": ["-v", "mb-ma1", "-s", "140", "-p", "58", "-a", "180"]}

meta = {}
for k, (v, tts, cap) in LINES.items():
    raw = f"{OUT}/{k}_raw.wav"
    subprocess.run(["espeak-ng", *VOICE[v], "-w", raw, tts], check=True,
                   stderr=subprocess.DEVNULL)
    with wave.open(raw) as w:
        meta[k] = {"voice": v, "dur": w.getnframes() / w.getframerate(), "rate": w.getframerate(), "caption": cap}
    print(k, round(meta[k]["dur"], 2))
json.dump(meta, open(f"{OUT}/meta.json", "w"), indent=1)
