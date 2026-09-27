# ESD — Bandar Kertas Lestari (animated video)

**Output:** `output/ESD_Bandar_Kertas_Lestari_16x9.mp4` (16:9, 1280×720, 25 fps, ~2 min 16 s)
plus an optional subtitle file `output/ESD_Bandar_Kertas_Lestari.srt` (not burned into the video).

The video follows the 15 scenes in `assets/scene_esd.docx` / `assets/scene_to_screen.docx`:
title card → ESD → the 7 competencies, with the river turning from grey to cyan section by section →
integrated problem-solving → living river → MQF mapping → rubric → CQI → conclusion → the lecturer's role.

| Item | How it is made |
|---|---|
| Visuals | Paper-craft town drawn in code; characters cut out of the storyboard images (IS-Net matting); storyboard panels used as scrapbook photos |
| Narration / dialogue | Offline TTS: espeak-ng + MBROLA (`id1` male voice for Hakim/narrator, `ma1` Malay female voice for the lecturer) |
| Lip-sync | Scenes 14–15: Hakim's and the lecturer's jaw/mouth are warped each frame from the loudness envelope of their own voice lines |
| Music | Original cheerful track composed & synthesised in `tools/music.py` (no samples → royalty-free) |
| SFX | Synthesised paper, marker, pop, chime and water sounds |

## Rebuild

```bash
sudo apt-get install espeak-ng mbrola mbrola-id1 mbrola-ma1 fonts-comic-neue fonts-roboto
pip install numpy scipy pillow imageio-ffmpeg onnxruntime
cd tools
python3 voices.py        # build/audio/*.wav
python3 render.py        # build/esd_video.mp4 + .srt
python3 render.py --sheet sheet.png   # contact sheet preview
```
(`cutout.py` re-extracts the character cut-outs; needs `isnet-general-use.onnx` from the rembg releases.)

---

# Selepas Pinggan Ditinggalkan (animated video)

**Output:** `output/Selepas_Pinggan_Ditinggalkan_16x9.mp4` (16:9, 1280×720, 25 fps, 5 min 54 s, captions burned in)
plus `output/Selepas_Pinggan_Ditinggalkan.srt`.

Follows the 12-scene brief in `assets/pinggan/prompt_claude_esd.docx`: title → 12 scenes (8 ESD competencies
tracked at the top right, lecturer/CQI segment in scene 11) → final reflection question → credits.

| Item | How it is made |
|---|---|
| Visuals | The approved storyboard panels (`assets/pinggan/storyboard.webp`) with Ken Burns camera moves, plus animated infographics drawn in code (system map, imagined-scenario triptych labelled "Senario bayangan", criteria board, pilot responsibility sheet, CQI loop) |
| Characters | Face badges cut from `assets/pinggan/characters.webp`; the active speaker's badge pulses with their voice |
| Voices | Offline TTS espeak-ng + MBROLA, a separate pitch/speed per character (Amir, Ju, Sara, Kak Lina, narrator) |
| Music / SFX | Original cheerful track synthesised by `tools/music.py`, synthesised cafeteria ambience — royalty-free |

No statistics, baselines or official mappings are invented; the credits say that the examples are illustrative.

```bash
cd tools
python3 pinggan_voices.py          # build/pg/audio/*.wav
python3 pinggan.py                 # build/pg/pinggan.mp4 + .srt
python3 pinggan.py --sheet s.png   # contact-sheet preview
```
