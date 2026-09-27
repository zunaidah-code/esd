"""Extract character cut-outs (RGBA) from the storyboard images using the IS-Net model."""
import sys, numpy as np, onnxruntime as ort
from PIL import Image

MODEL = sys.argv[1] if len(sys.argv) > 1 else "isnet-general-use.onnx"
A = "/home/user/esd/assets/"
JOBS = {
    # name: (source, crop box (l, t, r, b), bottom trim in source px or None)
    "hakim_stand":  ("scene08_collaboration.jpg", (770, 70, 950, 630), None),
    "hakim_kneel":  ("scene06_storyboard.jpg", (190, 20, 345, 255), None),
    "hakim_hall":   ("scene15_storyboard.jpg", (55, 40, 330, 384), 336),
    "lecturer":     ("scene15_storyboard.jpg", (325, 70, 640, 384), 336),
    "group":        ("scene08_collaboration.jpg", (390, 80, 950, 630), None),
}

sess = ort.InferenceSession(A + "../tools/" + MODEL if not MODEL.startswith("/") else MODEL)

def matte(img):
    x = np.asarray(img.convert("RGB").resize((1024, 1024), Image.BILINEAR), np.float32) / 255.0
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / 1.0
    x = x.transpose(2, 0, 1)[None]
    y = sess.run(None, {sess.get_inputs()[0].name: x})[0][0, 0]
    y = (y - y.min()) / (y.max() - y.min() + 1e-8)
    m = Image.fromarray((y * 255).astype(np.uint8)).resize(img.size, Image.LANCZOS)
    return m

for name, (src, box, trim) in JOBS.items():
    im = Image.open(A + src).convert("RGB")
    crop = im.crop(box)
    m = matte(crop)
    a = np.asarray(m, np.float32)
    a = np.clip((a - 115) * 255.0 / 110.0, 0, 255).astype(np.uint8)
    if trim:
        a[trim - box[1]:, :] = 0
    out = crop.convert("RGBA"); out.putalpha(Image.fromarray(a))
    out = out.crop(out.getbbox())
    out.save(A + "cutouts/%s.png" % name)
    print(name, out.size)
