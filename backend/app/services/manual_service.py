from io import BytesIO
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import null
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.config import get_settings
from app.models import Boletim, BoletimSecao, Resultado, CandidatoVoto
from app.services.duplicate_checker import lock_scope, check_sections, scope
from app.services.file_hash import calculate_sha256
from app.services.preview_service import create_preview, recover_preview
from app.services.storage_service import StorageError


def photos_preview(files):
    if not 1 <= len(files) <= 10:
        raise HTTPException(422, "Envie entre 1 e 10 fotos, na ordem do boletim.")
    limit = get_settings().max_pdf_size_mb * 1024 * 1024
    images = []
    size = 0
    pixels = 0
    try:
        for file in files:
            raw = file.file.read(limit + 1)
            size += len(raw)
            if size > limit:
                raise HTTPException(413, "As fotos excedem o tamanho máximo permitido.")
            with Image.open(BytesIO(raw)) as source:
                if source.format not in ("JPEG", "PNG", "WEBP"):
                    raise HTTPException(415, "Envie fotos JPEG, PNG ou WebP.")
                if source.width * source.height > 25000000:
                    raise HTTPException(413, "Foto muito grande. Reduza a resolução.")
                pixels += source.width * source.height
                if pixels > 60000000:
                    raise HTTPException(
                        413, "As fotos somadas têm resolução muito alta. Reduza as imagens."
                    )
                img = ImageOps.exif_transpose(source).convert("RGB")
                img.thumbnail((2400, 6000))
                images.append(img)
        output = BytesIO()
        images[0].save(output, format="PDF", save_all=True, append_images=images[1:])
        pdf = output.getvalue()
        if len(pdf) > limit:
            raise HTTPException(413, "O PDF das fotos excede o limite permitido.")
        return {"foto_token": create_preview(pdf, "fotos-bu.pdf"), "paginas": len(images)}
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Foto inválida. Envie uma imagem legível do BU.") from exc
    finally:
        for img in images:
            img.close()


def save_manual(body, db, storage):
    pdf = recover_preview(body.foto_token)[0] if body.foto_token else None
    bulletin_id = uuid4()
    file_hash = calculate_sha256(str(bulletin_id).encode())
    bucket = get_settings().supabase_storage_bucket
    path = f"manual/{bulletin_id}/fotos.pdf" if pdf else ""
    uploaded = False
    try:
        with db.begin():
            lock_scope(db, body, file_hash)
            check_sections(db, body)
            b = Boletim(
                id=bulletin_id,
                origem="MANUAL",
                eleicao_descricao=body.eleicao.descricao,
                eleicao_data=body.eleicao.data,
                eleicao_turno=body.eleicao.turno,
                municipio_codigo=body.municipio.codigo,
                municipio_nome=body.municipio.nome,
                zona=body.zona,
                secao=body.secao,
                quantidade_secoes_agregadas=len(body.secoes_agregadas),
                arquivo_nome_original="Digitação manual",
                arquivo_hash=file_hash,
                storage_bucket="",
                storage_path="",
                evidencia_bucket=bucket if pdf else None,
                evidencia_path=path or None,
            )
            b.secoes = [
                BoletimSecao(
                    numero_secao=n,
                    secao_chave=str(int(n)),
                    tipo="PRINCIPAL" if i == 0 else "AGREGADA",
                    **scope(body),
                )
                for i, n in enumerate([body.secao, *body.secoes_agregadas])
            ]
            for office in sorted({c.cargo for c in body.candidatos}):
                b.resultados.append(
                    Resultado(
                        cargo=office,
                        votos_nominais=None,
                        votos_legenda=null(),
                        brancos=None,
                        nulos=None,
                        total_apurado=None,
                        candidatos=[
                            CandidatoVoto(
                                numero_candidato=c.numero, nome_candidato=c.nome, votos=c.votos
                            )
                            for c in body.candidatos
                            if c.cargo == office
                        ],
                    )
                )
            db.add(b)
            db.flush()
            if pdf:
                storage.upload(bucket, path, pdf)
                uploaded = True
        return {"id": bulletin_id, "detail": "Lançamento manual parcial salvo."}
    except (SQLAlchemyError, StorageError) as exc:
        db.close()
        if uploaded:
            from app.services.importacao_service import _recover_upload

            existing_id = _recover_upload(db, body, file_hash, bucket, path, storage)
            if existing_id:
                return {"id": existing_id, "detail": "Lançamento manual parcial salvo."}
        if isinstance(exc, IntegrityError):
            raise HTTPException(409, "Esta seção já foi cadastrada.") from exc
        if isinstance(exc, StorageError):
            raise HTTPException(
                502, "Falha ao guardar as fotos. O lançamento não foi salvo."
            ) from exc
        raise HTTPException(
            503, "Falha no banco. Consulte a listagem antes de tentar novamente."
        ) from exc
