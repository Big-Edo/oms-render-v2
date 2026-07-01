"""
OMS Carousel Render Server v3
- /render → ZIP з 7 PNG (для Telegram)
- /render_urls → JSON з публічними URL (для Instagram)
- /slides/<filename> → роздає PNG файли
"""

from flask import Flask, request, jsonify, send_file, url_for
from PIL import Image, ImageDraw, ImageFont
import json, os, io, zipfile, textwrap, re, urllib.request, uuid, time, threading, sys

app = Flask(__name__)

# ── Тимчасове сховище PNG ────────────────────────────────
SLIDES_DIR = "/tmp/oms_slides"
os.makedirs(SLIDES_DIR, exist_ok=True)

# ── Кольори OMS ──────────────────────────────────────────
BG      = (18, 14, 9)
RED     = (204, 0, 0)
GOLD    = (212, 168, 83)
CREAM   = (245, 242, 232)
GRAY    = (122, 112, 104)
BORDER  = (46, 42, 36)

# ── Розміри ──────────────────────────────────────────────
W, H     = 1080, 1350
PAD      = 60
BAR      = 8

# ── Шрифти ───────────────────────────────────────────────
FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")

def log(msg):
    """Проста функція логування, яка одразу вилітає в Railway Deploy Logs"""
    print(f"[LOG] {msg}", flush=True)

def load_font(name, size):
    paths = {
        "bold":    os.path.join(FONT_DIR, "CyrBold.ttf"),
        "regular": os.path.join(FONT_DIR, "CyrRegular.ttf"),
    }
    try:
        return ImageFont.truetype(paths.get(name, paths["regular"]), size)
    except Exception:
        return ImageFont.load_default()

def draw_wrapped(draw, text, x, y, font, fill, max_width, line_spacing=10):
    words = text.replace("\n", " \n ").split(" ")
    lines, current = [], ""
    for word in words:
        if word == "\n":
            lines.append(current.strip())
            current = ""
            continue
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    cur_y = y
    for line in lines:
        draw.text((x, cur_y), line, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), line, font=font)
        cur_y += (bbox[3] - bbox[1]) + line_spacing
    return cur_y

def fetch_image(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            return Image.open(io.BytesIO(r.read())).convert("RGBA")
    except Exception as e:
        log(f"fetch_image FAILED for {url}: {e}")
        return None

def make_gradient(size, start_alpha=80, end_alpha=240):
    w, h = size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pixels = overlay.load()
    for y in range(h):
        t = y / h
        alpha = int(start_alpha + (end_alpha - start_alpha) * t)
        for x in range(w):
            pixels[x, y] = (0, 0, 0, alpha)
    return overlay

def render_slide(slide: dict, total: int) -> Image.Image:
    n      = slide.get("n", 1)
    tag    = slide.get("tag", "").upper()
    title  = slide.get("title", "").upper()
    accent = slide.get("accent", "").upper()
    body   = slide.get("body", "")
    devise = slide.get("devise", "")
    nav    = slide.get("nav", "ДАЛІ →")
    image_url = slide.get("image_url", "")

    img = Image.new("RGB", (W, H), BG)

    if image_url:
        bg_img = fetch_image(image_url)
        if bg_img:
            bg_img = bg_img.convert("RGB")
            img_ratio = W / H
            bg_ratio = bg_img.width / bg_img.height
            if bg_ratio > img_ratio:
                new_h = H
                new_w = int(H * bg_ratio)
            else:
                new_w = W
                new_h = int(W / bg_ratio)
            bg_img = bg_img.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - W) // 2
            top = (new_h - H) // 2
            bg_img = bg_img.crop((left, top, left + W, top + H))
            img.paste(bg_img, (0, 0))
            gradient = make_gradient((W, H))
            img_rgba = img.convert("RGBA")
            img_rgba = Image.alpha_composite(img_rgba, gradient)
            img = img_rgba.convert("RGB")

    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (W, BAR)], fill=RED)

    f_meta = load_font("regular", 26)
    draw.text((PAD, BAR + 18), "ЄДИНИЙ РОЗУМ  ·  @one_mind_lab", font=f_meta, fill=GRAY)
    num_text = f"{n:02d}/{total:02d}"
    bbox_n = draw.textbbox((0, 0), num_text, font=f_meta)
    draw.text((W - PAD - (bbox_n[2] - bbox_n[0]), BAR + 18), num_text, font=f_meta, fill=GRAY)

    f_tag   = load_font("bold", 28)
    f_title = load_font("bold", 72)
    f_body  = load_font("regular", 36)
    f_devise = load_font("bold", 30)
    f_nav   = load_font("bold", 28)

    title_wrapped = textwrap.wrap(title, width=16)
    title_lh = f_title.getbbox("A")[3] + 8
    title_height = len(title_wrapped) * title_lh + 24
    tag_height = (f_tag.getbbox("A")[3] + 16) if tag else 0

    body_lines = []
    if body:
        for raw_line in body.split("\n"):
            words = raw_line.split(" ")
            current = ""
            for word in words:
                test = (current + " " + word).strip()
                bbox = draw.textbbox((0, 0), test, font=f_body)
                if bbox[2] - bbox[0] <= W - PAD * 2:
                    current = test
                else:
                    if current:
                        body_lines.append(current)
                    current = word
            if current:
                body_lines.append(current)
    body_height = len(body_lines) * (f_body.getbbox("A")[3] + 10) + 20 if body_lines else 0

    devise_lines = []
    if devise:
        words = devise.split(" ")
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            bbox = draw.textbbox((0, 0), test, font=f_devise)
            if bbox[2] - bbox[0] <= W - PAD * 2 - 14:
                current = test
            else:
                if current:
                    devise_lines.append(current)
                current = word
        if current:
            devise_lines.append(current)
    devise_height = len(devise_lines) * (f_devise.getbbox("A")[3] + 10) + 20 if devise_lines else 0

    total_content = tag_height + title_height + 14 + body_height + devise_height + 16
    dot_zone = 60
    content_bottom = H - BAR - dot_zone - 20
    content_top = max(200, content_bottom - total_content)
    y = content_top

    if tag:
        draw.rectangle([(PAD, y + 4), (PAD + 4, y + 30)], fill=RED)
        draw.text((PAD + 14, y), tag, font=f_tag, fill=RED)
        bbox_t = draw.textbbox((0, 0), tag, font=f_tag)
        y += (bbox_t[3] - bbox_t[1]) + 16

    for line in title_wrapped:
        if accent and accent in line:
            parts = line.split(accent)
            cur_x = PAD
            for i, part in enumerate(parts):
                if part:
                    draw.text((cur_x, y), part, font=f_title, fill=CREAM)
                    bbox_p = draw.textbbox((0, 0), part, font=f_title)
                    cur_x += bbox_p[2] - bbox_p[0]
                if i < len(parts) - 1:
                    draw.text((cur_x, y), accent, font=f_title, fill=GOLD)
                    bbox_a = draw.textbbox((0, 0), accent, font=f_title)
                    cur_x += bbox_a[2] - bbox_a[0]
        else:
            draw.text((PAD, y), line, font=f_title, fill=CREAM)
        bbox_l = draw.textbbox((0, 0), line, font=f_title)
        y += (bbox_l[3] - bbox_l[1]) + 8
    y += 14

    draw.rectangle([(PAD, y), (W - PAD, y + 2)], fill=(80, 70, 60))
    y += 14

    if body:
        y = draw_wrapped(draw, body, PAD, y, f_body, CREAM, W - PAD * 2, 10)
        y += 12

    if devise:
        draw.rectangle([(PAD, y), (PAD + 4, y + 28)], fill=GOLD)
        y = draw_wrapped(draw, devise, PAD + 14, y, f_devise, GOLD, W - PAD * 2 - 14, 8)
        y += 10

    dot_y = H - BAR - 44
    dot_r = 6
    dot_gap = 20
    for i in range(total):
        color = GOLD if i == n - 1 else (60, 55, 48)
        draw.ellipse(
            [(PAD + i * dot_gap, dot_y - dot_r),
             (PAD + i * dot_gap + dot_r * 2, dot_y + dot_r)],
            fill=color
        )

    bbox_nav = draw.textbbox((0, 0), nav, font=f_nav)
    nav_color = RED if n == total else GOLD
    draw.text((W - PAD - (bbox_nav[2] - bbox_nav[0]), dot_y - 12), nav, font=f_nav, fill=nav_color)
    draw.rectangle([(0, H - BAR), (W, H)], fill=RED)

    return img

def parse_json(raw):
    raw = re.sub(r'^```[a-zA-Z]*\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw)
    return json.loads(raw.strip())

def cleanup_old_sessions():
    """Видаляє сесії старші 2 годин"""
    while True:
        time.sleep(3600)
        now = time.time()
        try:
            for session_id in os.listdir(SLIDES_DIR):
                session_path = os.path.join(SLIDES_DIR, session_id)
                if os.path.isdir(session_path):
                    if now - os.path.getmtime(session_path) > 7200:
                        import shutil
                        shutil.rmtree(session_path)
        except Exception:
            pass

threading.Thread(target=cleanup_old_sessions, daemon=True).start()


# ── /render → ZIP для Telegram ───────────────────────────
@app.route("/render", methods=["POST"])
def render():
    try:
        raw_body = request.get_data(as_text=True)
        data = parse_json(raw_body)
    except Exception as e:
        log(f"/render JSON parse error: {e}")
        return jsonify({"error": f"JSON parse error: {e}"}), 400

    slides = data.get("slides", [])
    log(f"/render received {len(slides)} slides")
    if not slides:
        return jsonify({"error": "No slides provided"}), 400

    total = len(slides)
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for slide in slides:
            img = render_slide(slide, total)
            img_buffer = io.BytesIO()
            img.save(img_buffer, format="PNG", optimize=True)
            img_buffer.seek(0)
            filename = f"slide_{slide.get('n', 0):02d}.png"
            zf.writestr(filename, img_buffer.read())

    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype="application/zip",
                     as_attachment=True, download_name="oms_carousel.zip")


# ── /render_urls → JSON з URL для Instagram ──────────────
@app.route("/render_urls", methods=["POST"])
def render_urls():
    try:
        raw_body = request.get_data(as_text=True)
        log(f"/render_urls raw body length: {len(raw_body)} chars")
        data = parse_json(raw_body)
    except Exception as e:
        log(f"/render_urls JSON parse error: {e}")
        return jsonify({"error": f"JSON parse error: {e}"}), 400

    slides = data.get("slides", [])
    log(f"/render_urls received {len(slides)} slides")

    if not slides:
        log("/render_urls: 'slides' key missing or empty in payload")
        return jsonify({"error": "No slides provided", "received_keys": list(data.keys())}), 400

    if len(slides) < 2:
        # Instagram Carousel вимагає мінімум 2 фото — краще впасти тут
        # з чіткою помилкою, ніж мовчки віддати неповний масив у Make.
        log(f"/render_urls: only {len(slides)} slide(s) received, Instagram carousel needs >=2")
        return jsonify({
            "error": f"Only {len(slides)} slide(s) in payload, Instagram carousel requires at least 2",
            "slides_count": len(slides)
        }), 400

    # Унікальна сесія для цього запиту
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(SLIDES_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)

    total = len(slides)
    urls = []
    base_url = request.host_url.rstrip("/")
    # Railway ставить сервіс за проксі — переконуємось, що схема https,
    # навіть якщо Flask всередині бачить http (інакше Instagram може
    # відмовитись від "небезпечних" http-посилань).
    if base_url.startswith("http://"):
        base_url = "https://" + base_url[len("http://"):]

    for slide in slides:
        try:
            img = render_slide(slide, total)
            filename = f"slide_{slide.get('n', 0):02d}.png"
            filepath = os.path.join(session_dir, filename)
            img.save(filepath, format="PNG", optimize=True)
            url = f"{base_url}/slides/{session_id}/{filename}"
            urls.append(url)
        except Exception as e:
            log(f"/render_urls: failed to render slide {slide.get('n', '?')}: {e}")
            # не додаємо URL, який не існує — але продовжуємо інші слайди

    log(f"/render_urls: successfully rendered {len(urls)}/{total} slides for session {session_id}")

    if len(urls) < 2:
        return jsonify({
            "error": f"Only {len(urls)} slide(s) rendered successfully out of {total}",
            "session_id": session_id
        }), 500

    return jsonify({
        "session_id": session_id,
        "total": total,
        "urls": urls,
        "instagram_caption": data.get("instagram_caption", ""),
        "telegram_post": data.get("telegram_post", ""),
        "hashtags": data.get("hashtags", [])
    })


# ── /slides/<session>/<file> → роздає PNG ────────────────
@app.route("/slides/<session_id>/<filename>")
def serve_slide(session_id, filename):
    filepath = os.path.join(SLIDES_DIR, session_id, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    return send_file(filepath, mimetype="image/png")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "OMS Render Server v3"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
