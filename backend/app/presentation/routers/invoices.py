"""Router des factures : upload (202 + pipeline en tâche de fond),
consultation, résultat OCR, entités extraites, image source, rejet."""
from datetime import date
from decimal import Decimal

from fastapi import (APIRouter, BackgroundTasks, Depends, File, HTTPException,
                     Query, UploadFile)
from fastapi.responses import Response
from sqlalchemy.orm import Session, sessionmaker

from app.application.pipeline import ProcessInvoicePipelineUseCase
from app.application.use_cases import (
    DeleteInvoiceUseCase, InvoiceNotDeletableError, RejectInvoiceUseCase, UploadInvoiceUseCase,
    UseCaseError,
)
from app.core.dependencies import get_current_user
from app.domain.entities import InvoiceStatus, Role, User
from app.infrastructure.db.database import get_db
from app.infrastructure.db.repositories import (
    MySQLAccountRepository, MySQLAuditRepository, MySQLCompanyRepository,
    MySQLChartRepository, MySQLEntryRepository, MySQLExchangeRateRepository, MySQLInvoiceRepository,
    MySQLRuleRepository, MySQLSupplierRepository,
)
from app.infrastructure.nlp.extractor import HybridExtractor
from app.infrastructure.storage.local_storage import LocalFileStorage
from app.presentation.schemas import (
    ExtractedEntityOut, InvoiceOut, InvoiceRateUpdate, OcrResultOut, PaginatedInvoices,
    RejectRequest,
)

router = APIRouter(prefix="/api/invoices", tags=["Factures"])


def _to_out(invoice, supplier_name: str | None = None,
           company_name: str | None = None, duplicate_of: int | None = None) -> InvoiceOut:
    return InvoiceOut(
        id=invoice.id, company_id=invoice.company_id, company_name=company_name,
        original_filename=invoice.original_filename,
        status=invoice.status.value,
        current_step=invoice.current_step.value if invoice.current_step else None,
        document_type=invoice.document_type.value,
        supplier_id=invoice.supplier_id,
        supplier_name=supplier_name, language=invoice.language,
        invoice_number=invoice.invoice_number, invoice_date=invoice.invoice_date,
        total_ht=invoice.total_ht, total_vat=invoice.total_vat,
        total_ttc=invoice.total_ttc, currency=invoice.currency,
        exchange_rate=invoice.exchange_rate,
        arithmetic_ok=invoice.arithmetic_ok, error_message=invoice.error_message,
        duplicate_of=duplicate_of)


def _check_access(invoice, user: User) -> None:
    """404 (pas 403) si la facture n'appartient pas à l'entreprise de
    l'appelant — ne pas confirmer l'existence d'une facture d'une autre
    entreprise par simple énumération d'ID. L'ADMIN global voit tout."""
    if user.role != Role.ADMIN and invoice.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Facture introuvable")


def _run_pipeline(invoice_id: int, bind) -> None:
    """Tâche de fond : le pipeline ouvre SA PROPRE session (la session de la
    requête HTTP est fermée quand la tâche s'exécute), mais liée au MÊME
    moteur que la requête d'origine — indispensable pour les tests
    (base en mémoire injectée) et cohérent en production (moteur unique)."""
    session_factory = sessionmaker(bind=bind, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        pipeline = ProcessInvoicePipelineUseCase(
            invoices=MySQLInvoiceRepository(db), entries=MySQLEntryRepository(db),
            accounts=MySQLAccountRepository(db), suppliers=MySQLSupplierRepository(db),
            rules=MySQLRuleRepository(db), extractor=HybridExtractor(),
            companies=MySQLCompanyRepository(db), rates=MySQLExchangeRateRepository(db),
            charts=MySQLChartRepository(db))
        pipeline.execute(invoice_id)
    finally:
        db.close()


@router.post("", response_model=InvoiceOut, status_code=202,
             summary="Importer une facture (PDF/JPG/PNG) — pipeline asynchrone")
async def upload_invoice(background_tasks: BackgroundTasks,
                         file: UploadFile = File(...),
                         user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    if user.company_id is None:
        raise HTTPException(status_code=403,
                            detail="Ce compte n'est rattaché à aucune entreprise")
    company = MySQLCompanyRepository(db).get_by_id(user.company_id)
    if company is None or company.chart_id is None:
        raise HTTPException(
            status_code=409,
            detail="Aucun plan comptable choisi : l'administrateur de l'entreprise doit en "
                   "choisir un (Mon profil → Plan comptable) avant d'importer des factures.")
    content = await file.read()
    try:
        invoice = UploadInvoiceUseCase(
            MySQLInvoiceRepository(db), LocalFileStorage(),
            MySQLAuditRepository(db)).execute(
            content, file.filename or "facture", file.content_type or "",
            user.id, user.company_id)
    except UseCaseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    background_tasks.add_task(_run_pipeline, invoice.id, db.get_bind())
    return _to_out(invoice)


@router.get("", response_model=PaginatedInvoices, summary="Lister les factures")
def list_invoices(status: str | None = Query(default=None),
                  page: int = Query(default=1, ge=1),
                  size: int = Query(default=20, ge=1, le=100),
                  q: str | None = Query(default=None, max_length=100,
                                        description="Fichier, fournisseur ou n° de facture"),
                  date_from: date | None = Query(default=None),
                  date_to: date | None = Query(default=None),
                  min_amount: Decimal | None = Query(default=None, ge=0),
                  max_amount: Decimal | None = Query(default=None, ge=0),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scope = None if user.role == Role.ADMIN else user.company_id
    repo = MySQLInvoiceRepository(db)
    items, total = repo.list_paginated(status, page, size, scope, search=q,
                                       date_from=date_from, date_to=date_to,
                                       min_amount=min_amount, max_amount=max_amount)
    suppliers = MySQLSupplierRepository(db)
    companies = MySQLCompanyRepository(db)
    out = []
    for invoice in items:
        name = None
        if invoice.supplier_id:
            supplier = suppliers.get_by_id(invoice.supplier_id)
            name = supplier.name if supplier else None
        company_name = None
        if user.role == Role.ADMIN and invoice.company_id:
            company = companies.get_by_id(invoice.company_id)
            company_name = company.name if company else None
        out.append(_to_out(invoice, name, company_name, repo.find_duplicate_id(invoice)))
    return PaginatedInvoices(items=out, total=total, page=page, size=size)


@router.get("/{invoice_id}", response_model=InvoiceOut, summary="Détail d'une facture")
def get_invoice(invoice_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    invoice = MySQLInvoiceRepository(db).get_by_id(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    _check_access(invoice, user)
    name = None
    if invoice.supplier_id:
        supplier = MySQLSupplierRepository(db).get_by_id(invoice.supplier_id)
        name = supplier.name if supplier else None
    return _to_out(invoice, name, duplicate_of=MySQLInvoiceRepository(db).find_duplicate_id(invoice))


@router.get("/{invoice_id}/file", summary="Fichier source de la facture")
def get_invoice_file(invoice_id: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    invoice = MySQLInvoiceRepository(db).get_by_id(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    _check_access(invoice, user)
    content = LocalFileStorage().read(invoice.storage_path)
    return Response(content=content, media_type=invoice.mime_type)


@router.get("/{invoice_id}/ocr", response_model=OcrResultOut,
            summary="Résultat OCR brut (texte + blocs + confiances)")
def get_ocr(invoice_id: int, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    invoice = MySQLInvoiceRepository(db).get_by_id(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    _check_access(invoice, user)
    result = MySQLInvoiceRepository(db).get_ocr_result(invoice_id)
    if result is None:
        raise HTTPException(status_code=404, detail="OCR non encore disponible")
    return OcrResultOut(**result)


@router.get("/{invoice_id}/entities", response_model=list[ExtractedEntityOut],
            summary="Entités extraites (avec traçabilité)")
def get_entities(invoice_id: int, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    invoice = MySQLInvoiceRepository(db).get_by_id(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    _check_access(invoice, user)
    return [ExtractedEntityOut(**e)
            for e in MySQLInvoiceRepository(db).get_entities(invoice_id)]


_PIPELINE_RUNNING_STATUSES = {"UPLOADED", "PREPROCESSING", "OCR_DONE", "ANALYZED"}


@router.post("/{invoice_id}/reprocess", status_code=202,
             summary="Relancer le pipeline IA")
def reprocess(invoice_id: int, background_tasks: BackgroundTasks,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    invoice = MySQLInvoiceRepository(db).get_by_id(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    _check_access(invoice, user)
    if invoice.status.value == "VALIDATED":
        raise HTTPException(status_code=409,
                            detail="Facture validée : elle ne peut plus être retraitée.")
    if invoice.status.value in _PIPELINE_RUNNING_STATUSES:
        # Bug réel corrigé : sans ce garde-fou, un second clic (ou un appel
        # API concurrent) démarre un second _run_pipeline sur LA MÊME
        # facture ; les deux tâches de fond écrivent alors current_step/
        # status en s'entrelaçant de façon non déterministe (l'une peut
        # écraser la progression de l'autre), et le widget de suivi affiche
        # une étape qui oscille au lieu de progresser.
        raise HTTPException(status_code=409,
                            detail="Le pipeline est déjà en cours de traitement pour cette facture.")
    # Statut « en cours » posé tout de suite, avant la tâche de fond : sinon un
    # sondage immédiat voit encore l'ancien statut ERROR (final) et cesse de
    # suivre le traitement, qui paraît alors bloqué alors qu'il vient de repartir.
    invoice.status = InvoiceStatus.UPLOADED
    invoice.current_step = None
    invoice.error_message = None
    MySQLInvoiceRepository(db).update(invoice)
    background_tasks.add_task(_run_pipeline, invoice_id, db.get_bind())
    return {"detail": "Pipeline relancé"}


@router.put("/{invoice_id}/exchange-rate", response_model=InvoiceOut,
            summary="Fixer le taux de change de cette facture (devise étrangère)")
def set_exchange_rate(invoice_id: int, payload: InvoiceRateUpdate,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    repo = MySQLInvoiceRepository(db)
    invoice = repo.get_by_id(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    _check_access(invoice, user)
    company = MySQLCompanyRepository(db).get_by_id(invoice.company_id)
    base = company.base_currency if company else "MGA"
    if invoice.currency == base:
        raise HTTPException(status_code=422,
                            detail=f"Cette facture est déjà en {base} : aucun taux à appliquer.")
    if invoice.status.value in _PIPELINE_RUNNING_STATUSES:
        raise HTTPException(status_code=409, detail="Le pipeline est en cours de traitement.")
    if invoice.status.value == "VALIDATED":
        raise HTTPException(status_code=409,
                            detail="Écriture déjà validée : le taux ne peut plus être modifié.")
    invoice.exchange_rate = payload.rate
    repo.update(invoice)
    if payload.save_for_company and user.role in (Role.ADMIN, Role.ENTREPRISE_ADMIN):
        MySQLExchangeRateRepository(db).upsert(
            invoice.company_id, invoice.currency, payload.rate, invoice.invoice_date or date.today())
    MySQLAuditRepository(db).log(user.id, "INVOICE_RATE_SET", "invoice", invoice_id,
                                 new_value={"currency": invoice.currency, "rate": str(payload.rate)})
    return _to_out(invoice)


@router.delete("/{invoice_id}", status_code=204,
               summary="Supprimer une facture non validée (avec ses écritures proposées)")
def delete_invoice(invoice_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    existing = MySQLInvoiceRepository(db).get_by_id(invoice_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    _check_access(existing, user)
    try:
        DeleteInvoiceUseCase(
            MySQLInvoiceRepository(db), MySQLEntryRepository(db), LocalFileStorage(),
            MySQLAuditRepository(db)).execute(invoice_id, user.id)
    except InvoiceNotDeletableError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except UseCaseError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return Response(status_code=204)


@router.post("/{invoice_id}/reject", response_model=InvoiceOut,
             summary="Rejeter une facture")
def reject(invoice_id: int, payload: RejectRequest,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = MySQLInvoiceRepository(db).get_by_id(invoice_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    _check_access(existing, user)
    try:
        invoice = RejectInvoiceUseCase(
            MySQLInvoiceRepository(db), MySQLAuditRepository(db)).execute(
            invoice_id, user.id, payload.reason)
    except UseCaseError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _to_out(invoice)
