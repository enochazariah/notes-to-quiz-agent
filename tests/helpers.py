from quizagent.pdf_input import SourceMaterial

SAMPLE_TEXT = (
    "Photosynthesis is the process plants use to turn light energy into chemical energy. "
    "It takes place inside chloroplasts, which contain the green pigment chlorophyll. "
    "Chlorophyll absorbs mostly red and blue light and reflects green light. "
    "The light reactions happen in the thylakoid membranes of the chloroplast. "
    "During the light reactions, water is split and oxygen is released as a by-product. "
    "The light reactions also produce ATP and NADPH, which store energy for the next stage. "
    "The Calvin cycle takes place in the stroma of the chloroplast. "
    "In the Calvin cycle, carbon dioxide is fixed into sugar using ATP and NADPH. "
    "The enzyme rubisco catalyses the first step of carbon fixation. "
    "Light intensity, carbon dioxide concentration and temperature are limiting factors. "
    "If any one limiting factor is in short supply the rate of photosynthesis cannot increase. "
    "Higher temperatures can denature enzymes and slow photosynthesis down sharply."
)


def sample_source(text: str = SAMPLE_TEXT) -> SourceMaterial:
    return SourceMaterial(filename="bio.pdf", page_count=1, text=text)


def make_pdf(pages: list[list[str]]) -> bytes:
    """Build a tiny valid text PDF (no extra libraries)."""
    objs: list[bytes] = []
    n = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, lines in enumerate(pages):
        content = "BT /F1 10 Tf 40 780 Td 12 TL\n"
        for line in lines:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content += f"({safe}) '\n"
        content += "ET"
        objs.append(
            (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {5 + 2 * i} 0 R "
             f"/Resources << /Font << /F1 3 0 R >> >> >>").encode())
        objs.append(f"<< /Length {len(content)} >>\nstream\n{content}\nendstream".encode())
    out = b"%PDF-1.4\n"
    offsets = []
    for idx, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{idx} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out
