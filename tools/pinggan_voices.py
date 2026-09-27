"""Dialogue & narration for "Selepas Pinggan Ditinggalkan" with offline TTS (espeak-ng + MBROLA).
Female voices use mb-ma1 (Malay), male voices mb-id1 (closest male voice to Malay);
each character gets its own pitch / speed. English terms are respelled phonetically."""
import subprocess, os, wave, json

OUT = "/home/user/esd/build/pg/audio"
os.makedirs(OUT, exist_ok=True)

VOICE = {  # speaker: espeak-ng args
    "amir": ["-v", "mb-id1", "-s", "156", "-p", "62", "-a", "180"],
    "amir_q": ["-v", "mb-id1", "-s", "138", "-p", "52", "-a", "150"],   # quiet, reflective
    "ju":   ["-v", "mb-ma1", "-s", "138", "-p", "55", "-a", "180"],
    "sara": ["-v", "mb-ma1", "-s", "150", "-p", "74", "-a", "180"],
    "lina": ["-v", "mb-ma1", "-s", "132", "-p", "44", "-a", "170"],
    "nar":  ["-v", "mb-id1", "-s", "146", "-p", "40", "-a", "180"],
}
NAME = {"amir": "Amir", "amir_q": "Amir", "ju": "Ju", "sara": "Sara", "lina": "Kak Lina", "nar": ""}

LINES = {
    # key: (speaker, text-for-tts, caption)
    "t00":  ("nar", "Selepas pinggan ditinggalkan.", "Selepas Pinggan Ditinggalkan"),
    "s01a": ("amir", "Program tadi meriah. Tapi, banyaknya makanan yang tinggal.",
             "Program tadi meriah. Tapi… banyaknya makanan yang tinggal."),
    "s02a": ("amir", "Apa kata kita tambah tong kitar semula?", "Apa kata kita tambah tong kitar semula?"),
    "s02b": ("ju", "Kalau makanan masih dibuang, adakah masalah kita sudah selesai?",
             "Kalau makanan masih dibuang, adakah masalah kita sudah selesai?"),
    "s03n": ("nar", "Pemikiran sistem.", "Pemikiran Sistem (Systems Thinking)"),
    "s03a": ("amir", "Kita sibuk fikir tempat membuang.", "Kita sibuk fikir tempat membuang."),
    "s03b": ("amir", "Kita belum fikir, kenapa makanan itu dibuang.", "Kita belum fikir kenapa makanan itu dibuang."),
    "s04n": ("nar", "Kompetensi antisipasi.", "Kompetensi Antisipasi (Anticipatory Competency)"),
    "s04a": ("nar", "Setiap pilihan membawa kesan.", "Setiap pilihan membawa kesan."),
    "s04b": ("nar", "Apa yang mungkin berlaku? Siapa yang terkesan?", "Apa yang mungkin berlaku? Siapa yang terkesan?"),
    "s04c": ("nar", "Apakah masa depan yang kita mahu?", "Apakah masa depan yang kita mahu?"),
    "s05n": ("nar", "Kompetensi normatif.", "Kompetensi Normatif (Normative Competency)"),
    "s05a": ("sara", "Kalau semua hidangan dikecilkan?", "Kalau semua hidangan dikecilkan?"),
    "s05b": ("lina", "Ada pelajar yang perlukan lebih. Kita kena beri pilihan.",
             "Ada pelajar yang perlukan lebih. Kita kena beri pilihan."),
    "s05c": ("amir", "Harga pun kena jelas dan berpatutan.", "Harga pun kena jelas dan berpatutan."),
    "s06n": ("nar", "Kompetensi kolaborasi.", "Kompetensi Kolaborasi (Collaboration Competency)"),
    "s06a": ("ju", "Kak Lina, bahagian mana yang paling sukar dilaksanakan?",
             "Kak Lina, bahagian mana yang paling sukar dilaksanakan?"),
    "s06b": ("lina", "Waktu rehat singkat. Pilihan hidangan mesti mudah dan cepat.",
             "Waktu rehat singkat. Pilihan hidangan mesti mudah dan cepat."),
    "s07n": ("nar", "Pemikiran kritis.", "Pemikiran Kritis (Critical Thinking)"),
    "s07a": ("amir", "Pembungkus ini nampak lebih mesra alam.", "Pembungkus ini nampak lebih mesra alam."),
    "s07b": ("sara", "Apa buktinya?", "Apa buktinya?"),
    "s07c": ("sara", "Dan adakah ia mengurangkan makanan yang tidak habis?",
             "Dan adakah ia mengurangkan makanan yang tidak habis?"),
    "s08n": ("nar", "Kesedaran kendiri.", "Kesedaran Kendiri (Self-awareness)"),
    "s08a": ("amir_q", "Aku pun selalu ambil lebih daripada yang aku makan.",
             "Aku pun selalu ambil lebih daripada yang aku makan."),
    "s09n": ("nar", "Kompetensi strategik.", "Kompetensi Strategik (Strategic Competency)"),
    "s09a": ("nar", "Cadangan perlu diterjemahkan kepada tindakan.", "Cadangan perlu diterjemahkan kepada tindakan:"),
    "s09b": ("nar", "Siapa bertanggungjawab, apa sumbernya, bila diuji, dan bagaimana hasilnya dinilai.",
             "siapa bertanggungjawab, apa sumbernya, bila diuji dan bagaimana hasilnya dinilai."),
    "s10n": ("nar", "Penyelesaian masalah bersepadu.", "Penyelesaian Masalah Bersepadu (Integrated Problem-solving)"),
    "s10a": ("sara", "Kita perlu semak sisa makanan, kos, dan maklum balas bersama.",
             "Kita perlu semak sisa makanan, kos dan maklum balas bersama."),
    "s10b": ("lina", "Label ini masih mengelirukan. Boleh kita ringkaskan?",
             "Label ini masih mengelirukan. Boleh kita ringkaskan?"),
    "s11a": ("ju", "Bukan hasil projek sahaja yang dinilai.", "Bukan hasil projek sahaja yang dinilai."),
    "s11b": ("ju", "Cara kamu menggunakan bukti, mempertimbangkan kesan, dan membuat keputusan, juga penting.",
             "Cara kamu menggunakan bukti, mempertimbangkan kesan dan membuat keputusan juga penting."),
    "s11c": ("nar", "Dapatan pentaksiran membantu pensyarah mengenal pasti jurang pembelajaran,",
             "Dapatan pentaksiran membantu pensyarah mengenal pasti jurang pembelajaran,"),
    "s11d": ("nar", "menambah baik pengajaran, dan menyemak keberkesanannya.",
             "menambah baik pengajaran dan menyemak keberkesanannya."),
    "s12a": ("amir", "Sedikit dahulu, Kak Lina. Kalau perlu, saya tambah.",
             "Sedikit dahulu, Kak Lina. Kalau perlu, saya tambah."),
    "s12b": ("ju", "Pendidikan untuk pembangunan lestari bermula dengan memahami hubungan, mempertimbangkan kesan, dan bertindak bersama.",
             "Pendidikan untuk pembangunan lestari bermula dengan memahami hubungan, mempertimbangkan kesan dan bertindak bersama."),
    "s12c": ("ju", "Selepas itu, kita semak, dan tambah baik.", "Selepas itu, kita semak dan tambah baik."),
    "s12q": ("nar", "Di kampus anda, apakah satu masalah yang boleh disiasat, dan ditambah baik bersama?",
             "Di kampus anda, apakah satu masalah yang boleh disiasat dan ditambah baik bersama?"),
}

if __name__ == "__main__":
    meta = {}
    for k, (spk, tts, cap) in LINES.items():
        raw = f"{OUT}/{k}_raw.wav"
        subprocess.run(["espeak-ng", *VOICE[spk], "-w", raw, tts], check=True, stderr=subprocess.DEVNULL)
        with wave.open(raw) as w:
            meta[k] = {"speaker": spk.split("_")[0], "name": NAME[spk], "dur": w.getnframes() / w.getframerate(),
                       "caption": cap}
        print(k, round(meta[k]["dur"], 2))
    json.dump(meta, open(f"{OUT}/meta.json", "w"), indent=1)
