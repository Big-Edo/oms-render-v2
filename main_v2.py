"""
OMS Carousel Render Server v2
Flask API: приймає JSON від Make.com → повертає 7 PNG як ZIP
Підтримує фонові зображення через image_url
"""

from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import json, os, io, zipfile, textwrap, re, urllib.request

app = Flask(__name__)

# ── Кольори OMS ──────────────────────────────────────────
BG      = (18, 14, 9)
RED     = (204, 0, 0)
GOLD    = (212, 168, 83)
CREAM   = (245, 242, 232)
GRAY    = (122, 112, 104)
BORDER  = (46, 42, 36)
BLACK   = (0, 0, 0)

# ── Розміри ──────────────────────────────────────────────
W, H     = 1080, 1350
PAD      = 60
BAR      = 8

# ── Шрифти ───────────────────────────────────────────────
FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")

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
    """Завантажує зображення з URL"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            return Image.open(io.BytesIO(r.read())).convert("RGBA")
    except Exception:
        return None

def make_gradient_overlay(size, start_alpha=0, end_alpha=230, from_bottom=True):
    """Створює градієнтний оверлей"""
    w, h = size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    pixels = overlay.load()
    for y in range(h):
        if from_bottom:
            t = y / h  # 0 вгорі, 1 внизу
            alpha = int(start_alpha + (end_alpha - start_alpha) * t)
        else:
            t = 1 - y / h
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

    # ── Базовий фон ──────────────────────────────────────
    img = Image.new("RGB", (W, H), BG)

    # ── Фонове зображення ────────────────────────────────
    if image_url:
        bg_img = fetch_image(image_url)
        if bg_img:
            # Масштабуємо cover
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
            # Кроп по центру
            left = (new_w - W) // 2
            top = (new_h - H) // 2
            bg_img = bg_img.crop((left, top, left + W, top + H))
            img.paste(bg_img, (0, 0))

            # Градієнт: прозорий вгорі, темний знизу
            gradient = make_gradient_overlay((W, H), start_alpha=80, end_alpha=240)
            img_rgba = img.convert("RGBA")
            img_rgba = Image.alpha_composite(img_rgba, gradient)
            img = img_rgba.convert("RGB")
    else:
        # Без фото — темний фон з текстурою
        draw_bg = ImageDraw.Draw(img)
        # Легка текстура — вертикальний градієнт
        for y in range(H):
            alpha = int(18 + (y / H) * 10)
            draw_bg.line([(0, y), (W, y)], fill=(alpha, int(alpha*0.8), int(alpha*0.5)))

    draw = ImageDraw.Draw(img)

    # ── Верхня червона смуга ─────────────────────────────
    draw.rectangle([(0, 0), (W, BAR)], fill=RED)

    # ── Хедер ────────────────────────────────────────────
    f_meta = load_font("regular", 26)
    draw.text((PAD, BAR + 18), "ЄДИНИЙ РОЗУМ  ·  @one_mind_lab", font=f_meta, fill=GRAY)
    num_text = f"{n:02d}/{total:02d}"
    bbox_n = draw.textbbox((0, 0), num_text, font=f_meta)
    draw.text((W - PAD - (bbox_n[2] - bbox_n[0]), BAR + 18), num_text, font=f_meta, fill=GRAY)

    # ── Контент — позиціонуємо знизу ────────────────────
    # Рахуємо висоту контенту знизу вгору
    BOTTOM_MARGIN = 80  # відступ від низу до навігації
    DOT_ZONE = 50
    content_bottom = H - BAR - BOTTOM_MARGIN - DOT_ZONE

    # Спочатку рахуємо висоту тексту (знизу вгору)
    f_nav = load_font("bold", 28)
    f_devise = load_font("bold", 30)
    f_body = load_font("regular", 36)
    f_title = load_font("bold", 72)
    f_tag = load_font("bold", 28)

    # Будуємо контент знизу вгору
    y = content_bottom

    # Девіз
    devise_height = 0
    if devise:
        lines = []
        words = devise.split(" ")
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            bbox = draw.textbbox((0, 0), test, font=f_devise)
            if bbox[2] - bbox[0] <= W - PAD * 2 - 16:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        devise_height = len(lines) * (draw.textbbox((0,0),"A",font=f_devise)[3] + 10) + 20

    # Body висота
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
    body_height = len(body_lines) * (draw.textbbox((0,0),"A",font=f_body)[3] + 10) + 20 if body_lines else 0

    # Title висота
    title_wrapped = textwrap.wrap(title, width=16)
    title_lh = draw.textbbox((0,0),"A",font=f_title)[3] + 8
    title_height = len(title_wrapped) * title_lh + 24

    # Tag висота
    tag_height = (draw.textbbox((0,0),"A",font=f_tag)[3] + 16) if tag else 0

    # Загальна висота контенту
    total_content = tag_height + title_height + 12 + body_height + devise_height + 16

    # Початок контенту (можна підняти якщо контент не вміщується)
    content_top = max(200, content_bottom - total_content)
    y = content_top

    # ── Тег ──────────────────────────────────────────────
    if tag:
        draw.rectangle([(PAD, y + 4), (PAD + 4, y + 30)], fill=RED)
        draw.text((PAD + 14, y), tag, font=f_tag, fill=RED)
        bbox_t = draw.textbbox((0, 0), tag, font=f_tag)
        y += (bbox_t[3] - bbox_t[1]) + 16

    # ── Заголовок ────────────────────────────────────────
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

    y += 12

    # ── Розділювач ───────────────────────────────────────
    draw.rectangle([(PAD, y), (W - PAD, y + 2)], fill=(80, 70, 60))
    y += 14

    # ── Тіло ─────────────────────────────────────────────
    if body:
        y = draw_wrapped(draw, body, PAD, y, f_body, CREAM, W - PAD * 2, 10)
        y += 12

    # ── Девіз ────────────────────────────────────────────
    if devise:
        draw.rectangle([(PAD, y), (PAD + 4, y + 28)], fill=GOLD)
        y = draw_wrapped(draw, devise, PAD + 14, y, f_devise, GOLD, W - PAD * 2 - 14, 8)
        y += 10

    # ── Нижня зона ───────────────────────────────────────
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

    # ── Нижня червона смуга ──────────────────────────────
    draw.rectangle([(0, H - BAR), (W, H)], fill=RED)

    return img


@app.route("/render", methods=["POST"])
def render():
    try:
        raw = request.get_data(as_text=True)
        raw = re.sub(r'^```[a-zA-Z]*\s*', '', raw.strip())
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()
        data = json.loads(raw)
    except Exception as e:
        return jsonify({"error": f"JSON parse error: {e}"}), 400

    slides = data.get("slides", [])
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
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="oms_carousel.zip"
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "OMS Render Server v2"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
