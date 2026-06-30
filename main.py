"""
OMS Carousel Render Server
Flask API: приймає JSON від Make.com → повертає 7 PNG як ZIP
"""

from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont
import json, os, io, zipfile, textwrap, re

app = Flask(__name__)

# ── Кольори OMS ──────────────────────────────────────────
BG      = (18, 14, 9)
RED     = (204, 0, 0)
GOLD    = (212, 168, 83)
CREAM   = (245, 242, 232)
GRAY    = (122, 112, 104)
BORDER  = (46, 42, 36)

# ── Розміри слайду ───────────────────────────────────────
W, H     = 1080, 1350
PAD      = 64
BAR      = 8
HEADER_H = 90

# ── Шляхи до шрифтів ────────────────────────────────────
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

def draw_wrapped(draw, text, x, y, font, fill, max_width, line_spacing=8):
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

def render_slide(slide: dict, total: int) -> Image.Image:
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    n      = slide.get("n", 1)
    tag    = slide.get("tag", "").upper()
    title  = slide.get("title", "").upper()
    accent = slide.get("accent", "").upper()
    body   = slide.get("body", "")
    devise = slide.get("devise", "")
    nav    = slide.get("nav", "ДАЛІ →")

    # Верхня червона смуга
    draw.rectangle([(0, 0), (W, BAR)], fill=RED)

    # Хедер
    f_meta = load_font("regular", 26)
    draw.text((PAD, BAR + 18), "ЄДИНИЙ РОЗУМ  ·  @one_mind_lab", font=f_meta, fill=GRAY)
    num_text = f"{n:02d}/{total:02d}"
    bbox_n = draw.textbbox((0, 0), num_text, font=f_meta)
    draw.text((W - PAD - (bbox_n[2] - bbox_n[0]), BAR + 18), num_text, font=f_meta, fill=GRAY)

    # Тег
    y = HEADER_H + BAR + 24
    if tag:
        f_tag = load_font("bold", 28)
        draw.rectangle([(PAD, y + 4), (PAD + 4, y + 32)], fill=RED)
        draw.text((PAD + 16, y), tag, font=f_tag, fill=RED)
        bbox_t = draw.textbbox((0, 0), tag, font=f_tag)
        y += (bbox_t[3] - bbox_t[1]) + 24

    # Заголовок
    f_title = load_font("bold", 88)
    title_lines = textwrap.wrap(title, width=14)
    for line in title_lines:
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
    y += 20

    # Розділювач
    draw.rectangle([(PAD, y), (W - PAD, y + 2)], fill=BORDER)
    y += 18

    # Тіло
    f_body = load_font("regular", 34)
    y = draw_wrapped(draw, body, PAD, y, f_body, CREAM, W - PAD * 2, 10)
    y += 20

    # Девіз
    if devise:
        draw.rectangle([(PAD, y), (PAD + 4, y + 32)], fill=GOLD)
        f_devise = load_font("bold", 28)
        y = draw_wrapped(draw, devise, PAD + 16, y, f_devise, GOLD, W - PAD * 2 - 16, 6)
        y += 16

    # Прогрес-точки
    dot_y  = H - BAR - 50
    dot_r  = 7
    dot_gap = 22
    for i in range(total):
        color = GOLD if i == n - 1 else BORDER
        draw.ellipse(
            [(PAD + i * dot_gap, dot_y - dot_r),
             (PAD + i * dot_gap + dot_r * 2, dot_y + dot_r)],
            fill=color
        )

    # Навігація
    f_nav = load_font("bold", 28)
    bbox_nav = draw.textbbox((0, 0), nav, font=f_nav)
    nav_color = RED if n == total else GOLD
    draw.text((W - PAD - (bbox_nav[2] - bbox_nav[0]), dot_y - 10), nav, font=f_nav, fill=nav_color)

    # Нижня червона смуга
    draw.rectangle([(0, H - BAR), (W, H)], fill=RED)

    return img


@app.route("/render", methods=["POST"])
def render():
    try:
        raw = request.get_data(as_text=True)
        # Очищаємо будь-які markdown fences
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
    return jsonify({"status": "ok", "service": "OMS Render Server"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
