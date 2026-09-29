import pymupdf


def extract_text_from_pdf(file_bytes: bytes) -> str:
    if not file_bytes.startswith(b"%PDF-"):
        raise ValueError("PDF inválido.")
    try:
        with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
            if doc.needs_pass:
                raise ValueError("PDF protegido por senha. Envie um PDF sem senha.")
            if len(doc) > 100:
                raise ValueError("O PDF excede o limite de 100 páginas.")
            pages = []
            size = 0
            for page in doc:
                page_text = page.get_text(sort=True)
                size += len(page_text) + 1
                if size > 2000000:
                    raise ValueError("O texto do PDF excede o limite permitido.")
                pages.append(page_text)
            text = "\n".join(pages)
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise ValueError("PDF inválido ou falha na leitura do arquivo.") from exc
    if not text.strip():
        raise ValueError("Não foi possível extrair texto deste PDF.")
    return text
