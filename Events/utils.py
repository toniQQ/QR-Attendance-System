import io
import socket

import qrcode
from django.http import HttpResponse

LAN_PORT = 8000


def _local_ip():
    ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        pass
    return ip


def local_base_url(port=LAN_PORT):
    """Return the base URL used for QR codes and share links.

    When ``SITE_BASE_URL`` is configured (production), it wins. Otherwise
    fall back to the LAN IP + port used for offline/college-LAN hosting.
    """
    from django.conf import settings

    configured = getattr(settings, "SITE_BASE_URL", "")
    if configured:
        return configured.rstrip("/")
    return f"http://{_local_ip()}:{port}"


def checkin_url(event):
    return f"{local_base_url()}/events/{event.slug}/register/"


def qr_png_response(url, fill_color="#000000"):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return HttpResponse(buffer.getvalue(), content_type="image/png")


def dominant_colors(fp, limit=3):
    """Return up to `limit` dominant hex colors from an image (Pillow).

    Skips near-white and near-black so a white/transparent background does
    not become the theme color. Reads from a file path or file object.
    """
    from PIL import Image

    img = Image.open(fp).convert("RGBA")
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    bg.alpha_composite(img)
    img = bg.convert("RGB")
    img.thumbnail((64, 64))
    quantized = img.quantize(colors=16, method=Image.MEDIANCUT).convert("RGB")
    ranked = sorted(
        quantized.getcolors(maxcolors=100_000), key=lambda item: -item[0]
    )
    hexes = []
    for _, (r, g, b) in ranked:
        if max(r, g, b) >= 245 and min(r, g, b) >= 210:
            continue  # near-white background
        if max(r, g, b) < 18:
            continue  # near-black
        hexes.append(f"#{r:02x}{g:02x}{b:02x}")
        if len(hexes) >= limit:
            break
    return hexes


def darken(hex_color, factor=0.5):
    """Return `hex_color` scaled by `factor` (0 = black, 1 = unchanged)."""
    hex_color = hex_color.lstrip("#")
    rgb = [int(hex_color[i : i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(c * factor):02x}" for c in rgb)