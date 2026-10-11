"""Routers transverses : plan comptable, tableau de bord, audit,
réentraînement (Admin)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_admin
from app.domain.entities import Role, User
from app.infrastructure.db import models as m
from app.infrastructure.db.database import get_db
from app.infrastructure.db.repositories import (
    MySQLAccountRepository, MySQLAuditRepository, MySQLInvoiceRepository,
    MySQLSupplierRepository,
)
from app.presentation.routers.invoices import _to_out
from app.presentation.schemas import AccountOut, DashboardStats

router = APIRouter(prefix="/api", tags=["Référentiels & pilotage"])


@router.get("/accounts", response_model=list[AccountOut],
            summary="Plan comptable (PCG malgache 2005)")
def list_accounts(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [AccountOut(code=a.code, label=a.label, account_class=a.account_class,
                       normal_balance=a.normal_balance)
            for a in MySQLAccountRepository(db).list_active()]


@router.get("/dashboard", response_model=DashboardStats,
            summary="Statistiques du tableau de bord")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # L'ADMIN global voit l'agrégat de toutes les entreprises ; tout autre
    # rôle est cantonné à la sienne.
    scope = None if user.role == Role.ADMIN else user.company_id

    invoice_query = select(m.InvoiceModel.status, func.count(m.InvoiceModel.id))
    entry_query = select(func.count(m.JournalEntryModel.id)).where(
        m.JournalEntryModel.status == "VALIDATED")
    corrected_query = (
        select(func.count(func.distinct(m.CorrectionModel.entry_id)))
        .join(m.JournalEntryModel, m.JournalEntryModel.id == m.CorrectionModel.entry_id)
        .where(m.JournalEntryModel.status == "VALIDATED"))
    confidence_query = select(func.avg(m.JournalEntryModel.confidence_score))
    operations_query = (
        select(m.ClassificationModel.operation_type, func.count(m.ClassificationModel.id))
        .join(m.InvoiceModel, m.InvoiceModel.id == m.ClassificationModel.invoice_id))
    invoices_for_volume = select(m.InvoiceModel)
    if scope is not None:
        invoice_query = invoice_query.where(m.InvoiceModel.company_id == scope)
        entry_query = entry_query.where(m.JournalEntryModel.company_id == scope)
        corrected_query = corrected_query.where(m.JournalEntryModel.company_id == scope)
        confidence_query = confidence_query.where(m.JournalEntryModel.company_id == scope)
        operations_query = operations_query.where(m.InvoiceModel.company_id == scope)
        invoices_for_volume = invoices_for_volume.where(m.InvoiceModel.company_id == scope)

    by_status = dict(db.execute(invoice_query.group_by(m.InvoiceModel.status)).all())
    total = sum(by_status.values())

    validated_entries = db.scalar(entry_query) or 0
    corrected = db.scalar(corrected_query) or 0
    without_correction_rate = (round((validated_entries - corrected) / validated_entries, 4)
                               if validated_entries else None)
    average_confidence = db.scalar(confidence_query)

    # Répartition par type d'opération (graphique camembert du tableau de
    # bord) : une classification par facture, jointe pour ne compter que
    # les factures effectivement passées par le classifieur ML.
    operations_by_type = dict(db.execute(
        operations_query.group_by(m.ClassificationModel.operation_type)).all())

    # Volume mensuel sur les 6 derniers mois (nombre de factures + montant
    # TTC cumulé) : agrégation en Python plutôt qu'en SQL pour rester
    # compatible SQLite (tests) ET MySQL (prod), qui n'ont pas la même
    # syntaxe de troncature de date.
    monthly_buckets: dict[str, dict[str, float]] = {}
    for invoice in db.scalars(invoices_for_volume).all():
        key = invoice.uploaded_at.strftime("%Y-%m")
        bucket = monthly_buckets.setdefault(key, {"count": 0, "total_ttc": 0.0})
        bucket["count"] += 1
        amount = float(invoice.total_ttc) if invoice.total_ttc else 0.0
        # Converti dans la devise de l'entreprise quand la facture est en devise étrangère
        # (sinon des EUR et des MGA seraient additionnés tels quels).
        bucket["total_ttc"] += amount * float(invoice.exchange_rate or 1)
    monthly_volume = [
        {"month": month, "invoice_count": int(v["count"]), "total_ttc": round(v["total_ttc"], 2)}
        for month, v in sorted(monthly_buckets.items())[-6:]
    ]

    recent, _count = MySQLInvoiceRepository(db).list_paginated(None, 1, 5, scope)
    suppliers = MySQLSupplierRepository(db)
    recent_out = []
    for invoice in recent:
        name = None
        if invoice.supplier_id:
            supplier = suppliers.get_by_id(invoice.supplier_id)
            name = supplier.name if supplier else None
        recent_out.append(_to_out(invoice, name))

    return DashboardStats(
        total_invoices=total,
        pending_review=by_status.get("ENTRIES_PROPOSED", 0),
        validated=by_status.get("VALIDATED", 0),
        errors=by_status.get("ERROR", 0),
        validated_without_correction_rate=without_correction_rate,
        average_confidence=round(float(average_confidence), 4) if average_confidence else None,
        invoices_by_status=by_status, operations_by_type=operations_by_type,
        monthly_volume=monthly_volume, recent_invoices=recent_out)


@router.get("/audit", summary="Journal d'audit (Admin)")
def audit_log(page: int = Query(default=1, ge=1),
              size: int = Query(default=50, ge=1, le=200),
              _: User = Depends(require_admin), db: Session = Depends(get_db)):
    items, total = MySQLAuditRepository(db).list_paginated(page, size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.post("/ml/retrain", summary="Réentraîner le classifieur (Admin)")
def retrain_model(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.infrastructure.ml.training import retrain
    report = retrain(db)
    MySQLAuditRepository(db).log(admin.id, "MODEL_RETRAINED", "model_version", 0,
                                 new_value=report)
    return report


@router.get("/ml/versions", summary="Historique des versions de modèles (Admin)")
def model_versions(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(m.ModelVersionModel)
                      .order_by(m.ModelVersionModel.id.desc())).all()
    return [{"name": r.name, "version": r.version, "algorithm": r.algorithm,
             "accuracy": float(r.accuracy) if r.accuracy else None,
             "f1_score": float(r.f1_score) if r.f1_score else None,
             "training_samples": r.training_samples, "is_active": r.is_active,
             "trained_at": r.trained_at.isoformat()} for r in rows]
