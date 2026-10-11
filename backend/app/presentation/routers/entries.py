"""Router des écritures comptables : consultation, correction, validation,
exports Excel/CSV/PDF."""
import csv
import io
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.application.use_cases import (
    CorrectEntryUseCase, UseCaseError, ValidateEntryUseCase,
)
from app.core.dependencies import get_current_user
from app.domain.entities import JournalEntry, Role, User
from app.infrastructure.db.database import get_db
from app.infrastructure.db.repositories import (
    MySQLAccountRepository, MySQLAuditRepository, MySQLCompanyRepository,
    MySQLEntryRepository, MySQLInvoiceRepository,
)
from app.presentation.schemas import (
    BatchValidateItem, BatchValidateRequest, BatchValidateResult,
    CorrectEntryRequest, EntryLineOut, EntryOut, PaginatedEntries,
)

router = APIRouter(prefix="/api/entries", tags=["Écritures comptables"])


def _to_out(entry: JournalEntry) -> EntryOut:
    return EntryOut(
        id=entry.id, invoice_id=entry.invoice_id, entry_date=entry.entry_date,
        label=entry.label, status=entry.status.value,
        confidence_score=entry.confidence_score, rule_code=entry.rule_code,
        validated_at=entry.validated_at, currency=entry.currency,
        original_currency=entry.original_currency, original_amount=entry.original_amount,
        exchange_rate=entry.exchange_rate,
        total_debit=entry.total_debit(), total_credit=entry.total_credit(),
        lines=[EntryLineOut(id=l.id, account_code=l.account_code, label=l.label,
                            debit=l.debit, credit=l.credit,
                            account_confidence=l.account_confidence,
                            suggested_by_ml=l.suggested_by_ml)
               for l in entry.lines])


def _check_access(entry: JournalEntry, user: User) -> None:
    if user.role != Role.ADMIN and entry.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Écriture introuvable")


@router.get("", response_model=PaginatedEntries, summary="Lister les écritures")
def list_entries(status: str | None = Query(default=None),
                 page: int = Query(default=1, ge=1),
                 size: int = Query(default=20, ge=1, le=100),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scope = None if user.role == Role.ADMIN else user.company_id
    items, total = MySQLEntryRepository(db).list_paginated(status, page, size, scope)
    return PaginatedEntries(items=[_to_out(e) for e in items],
                            total=total, page=page, size=size)


@router.get("/by-invoice/{invoice_id}", response_model=list[EntryOut],
            summary="Écritures d'une facture")
def entries_of_invoice(invoice_id: int, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    invoice = MySQLInvoiceRepository(db).get_by_id(invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    if user.role != Role.ADMIN and invoice.company_id != user.company_id:
        raise HTTPException(status_code=404, detail="Facture introuvable")
    return [_to_out(e) for e in MySQLEntryRepository(db).list_by_invoice(invoice_id)]


@router.get("/{entry_id}", response_model=EntryOut, summary="Détail d'une écriture")
def get_entry(entry_id: int, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    entry = MySQLEntryRepository(db).get_by_id(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Écriture introuvable")
    _check_access(entry, user)
    return _to_out(entry)


@router.put("/{entry_id}", response_model=EntryOut,
            summary="Corriger une écriture proposée (historisé pour le ML)")
def correct_entry(entry_id: int, payload: CorrectEntryRequest,
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    existing = MySQLEntryRepository(db).get_by_id(entry_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Écriture introuvable")
    _check_access(existing, user)
    try:
        entry = CorrectEntryUseCase(
            MySQLEntryRepository(db), MySQLAccountRepository(db),
            MySQLAuditRepository(db)).execute(
            entry_id, user.id,
            [c.model_dump() for c in payload.corrections])
    except UseCaseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _to_out(entry)


@router.post("/{entry_id}/validate", response_model=EntryOut,
             summary="Validation définitive (équilibre re-vérifié)")
def validate_entry(entry_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    existing = MySQLEntryRepository(db).get_by_id(entry_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Écriture introuvable")
    _check_access(existing, user)
    try:
        entry = ValidateEntryUseCase(
            MySQLEntryRepository(db), MySQLInvoiceRepository(db),
            MySQLAuditRepository(db)).execute(entry_id, user.id)
    except UseCaseError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _to_out(entry)


@router.post("/validate-batch", response_model=BatchValidateResult,
             summary="Valider plusieurs écritures (chacune contrôlée séparément)")
def validate_batch(payload: BatchValidateRequest, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Une écriture déséquilibrée ou déjà validée n'empêche pas les autres :
    chaque écriture passe par le même cas d'usage que la validation unitaire
    (équilibre re-vérifié, audit) et le résultat est rendu écriture par écriture."""
    entries = MySQLEntryRepository(db)
    use_case = ValidateEntryUseCase(entries, MySQLInvoiceRepository(db), MySQLAuditRepository(db))
    results = []
    for entry_id in dict.fromkeys(payload.entry_ids):  # dédoublonne en gardant l'ordre
        existing = entries.get_by_id(entry_id)
        if existing is None or (user.role != Role.ADMIN and existing.company_id != user.company_id):
            results.append(BatchValidateItem(id=entry_id, ok=False, error="Écriture introuvable"))
            continue
        try:
            use_case.execute(entry_id, user.id)
            results.append(BatchValidateItem(id=entry_id, ok=True))
        except UseCaseError as exc:
            results.append(BatchValidateItem(id=entry_id, ok=False, error=str(exc)))
    validated = sum(1 for r in results if r.ok)
    return BatchValidateResult(validated=validated, failed=len(results) - validated, results=results)


_EXPORT_HEADERS = ["N°", "Date", "Libellé", "Compte", "Libellé ligne",
                   "Débit", "Crédit", "Statut", "Devise", "Montant d'origine",
                   "Devise d'origine", "Taux"]


def _export_rows(db: Session, company_id: int | None) -> list[list]:
    """Aplatit les écritures validées en lignes exportables — logique
    commune aux exports Excel, CSV et PDF pour éviter toute divergence
    entre formats."""
    entries, _total = MySQLEntryRepository(db).list_paginated(
        "VALIDATED", 1, 10_000, company_id)
    rows = []
    for entry in entries:
        for line in entry.lines:
            rows.append([entry.id, entry.entry_date.isoformat(), entry.label,
                        line.account_code, line.label, float(line.debit),
                        float(line.credit), entry.status.value, entry.currency,
                        float(entry.original_amount) if entry.original_amount is not None else "",
                        entry.original_currency or "",
                        float(entry.exchange_rate) if entry.exchange_rate is not None else ""])
    return rows


@router.get("/export/excel", summary="Export Excel des écritures validées")
def export_excel(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from openpyxl import Workbook

    scope = None if user.role == Role.ADMIN else user.company_id
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Journal des achats"
    sheet.append(_EXPORT_HEADERS)
    for row in _export_rows(db, scope):
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=journal_achats.xlsx"})


@router.get("/export/csv", summary="Export CSV des écritures validées")
def export_csv(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scope = None if user.role == Role.ADMIN else user.company_id
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")  # ';' : compatible Excel FR (virgule décimale)
    writer.writerow(_EXPORT_HEADERS)
    for row in _export_rows(db, scope):
        writer.writerow(row)
    # BOM UTF-8 : Excel n'affiche correctement les accents d'un CSV sans lui
    encoded = ("﻿" + buffer.getvalue()).encode("utf-8")
    return StreamingResponse(
        io.BytesIO(encoded), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=journal_achats.csv"})


def _company_currency(db: Session, company_id: int | None) -> str:
    if company_id is None:
        return "MGA"
    company = MySQLCompanyRepository(db).get_by_id(company_id)
    return company.base_currency if company else "MGA"


def _company_label(db: Session, company_id: int | None) -> str:
    """Nom de l'entreprise affiché en tête du journal. Sans périmètre
    (administrateur global), le journal couvre toutes les entreprises."""
    if company_id is None:
        return "Toutes les entreprises"
    company = MySQLCompanyRepository(db).get_by_id(company_id)
    return company.name if company else "—"


def _format_amount(value: float) -> str:
    """Sans décimales si le montant est un nombre entier (convention du
    journal papier malgache), sinon deux décimales — toujours espace comme
    séparateur de milliers."""
    text = f"{value:,.0f}" if value == round(value) else f"{value:,.2f}"
    return text.replace(",", " ")


def _origin_text(entry: JournalEntry) -> str:
    """« 1 000 EUR × 4 950 » : montant d'origine et taux, pour qu'un contrôleur
    retrouve le calcul d'une écriture convertie."""
    if entry.original_currency is None or entry.original_amount is None:
        return ""
    rate = f"{entry.exchange_rate:f}".rstrip("0").rstrip(".") if entry.exchange_rate else "?"
    return (f"{_format_amount(float(entry.original_amount))} {entry.original_currency}"
            f" × {_format_amount(float(rate)) if rate != '?' else rate}")


def _pdf_journal_rows(db: Session, company_id: int | None) -> list[list]:
    """Lignes du journal au format du modèle papier : une ligne par
    imputation, avec le numéro de pièce (numéro de facture) plutôt que
    l'identifiant interne de l'écriture."""
    entries, _total = MySQLEntryRepository(db).list_paginated(
        "VALIDATED", 1, 10_000, company_id)
    invoice_repo = MySQLInvoiceRepository(db)
    invoice_cache: dict[int, str] = {}
    rows = []
    for entry in entries:
        if entry.invoice_id not in invoice_cache:
            invoice = invoice_repo.get_by_id(entry.invoice_id)
            invoice_cache[entry.invoice_id] = (
                invoice.invoice_number if invoice and invoice.invoice_number
                else f"FAC-{entry.invoice_id:03d}")
        piece = invoice_cache[entry.invoice_id]
        origin = _origin_text(entry)
        for index, line in enumerate(entry.lines):
            rows.append([entry.entry_date, piece, line.account_code, line.label,
                        float(line.debit), float(line.credit),
                        origin if index == 0 else "", entry.currency])
    return rows


@router.get("/export/pdf", summary="Export PDF des écritures validées")
def export_pdf(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    from app.core.config import get_settings

    settings = get_settings()
    scope = None if user.role == Role.ADMIN else user.company_id
    rows = _pdf_journal_rows(db, scope)
    company_label = _company_label(db, scope)
    currencies = sorted({r[7] for r in rows})
    # Devise du journal : celle des écritures (une seule par entreprise) ; un
    # administrateur plateforme qui exporte plusieurs entreprises peut en voir plusieurs.
    if currencies:
        journal_currency = currencies[0] if len(currencies) == 1 else "/".join(currencies)
    else:
        journal_currency = _company_currency(db, scope)

    HEADER_BG = colors.HexColor("#D9D9D9")
    ROW_ALT_BG = colors.HexColor("#F2F2F2")
    TOTAL_BG = colors.HexColor("#BFBFBF")
    GRID_COLOR = colors.HexColor("#999999")
    PIECE_COLOR = colors.HexColor("#1F4E79")

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "JournalTitle", parent=styles["Title"], fontSize=18, spaceAfter=2)
    subtitle_style = ParagraphStyle(
        "JournalSubtitle", parent=styles["Normal"], alignment=1,
        textColor=colors.HexColor("#444444"))
    footer_style = ParagraphStyle(
        "JournalFooter", parent=styles["Normal"], fontSize=8,
        textColor=colors.HexColor("#444444"))
    cell_style = ParagraphStyle("JournalCell", parent=styles["Normal"], fontSize=8, leading=10)

    if rows:
        period_start = min(r[0] for r in rows).strftime("%d/%m/%Y")
        period_end = max(r[0] for r in rows).strftime("%d/%m/%Y")
        periode = period_start if period_start == period_end else f"{period_start} – {period_end}"
    else:
        periode = "—"

    elements = [
        Paragraph("JOURNAL COMPTABLE", title_style),
        Paragraph("Journal des achats et opérations diverses — écritures validées",
                  subtitle_style),
        Spacer(1, 0.5 * cm),
    ]

    info_table = Table(
        [["Entreprise", Paragraph(xml_escape(company_label),
                                      ParagraphStyle("CompanyCell", parent=cell_style,
                                                     fontSize=9, leading=11)), "Période", periode],
         ["Journal", "ACH", "Devise", journal_currency]],
        colWidths=[2.6 * cm, 6.4 * cm, 2.6 * cm, 4.9 * cm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), HEADER_BG),
        ("BACKGROUND", (2, 0), (2, -1), HEADER_BG),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID_COLOR),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.6 * cm))

    headers = ["Date", "N° pièce", "Compte", "Libellé",
               f"Débit ({journal_currency})", f"Crédit ({journal_currency})"]
    total_debit = sum(r[4] for r in rows)
    total_credit = sum(r[5] for r in rows)
    # Bug réel corrigé : Paragraph() interprète son texte comme du XML léger
    # (balises <b>, <br/>...) ; un libellé contenant un '<' non échappé (ex.
    # nom de fournisseur issu d'un texte OCR corrompu, "SARL<brlsLot...")
    # casse le parseur ReportLab avec "unclosed tags" et fait échouer tout
    # l'export PDF (500). On échappe donc systématiquement le texte libre.
    table_data = [headers] + [
        [r[0].strftime("%d/%m/%Y"), r[1], r[2], Paragraph(
            xml_escape(r[3]) + (f'<br/><font size="7" color="#555555">{xml_escape(r[6])}</font>'
                                 if r[6] else ""), cell_style),
         _format_amount(r[4]) if r[4] else "", _format_amount(r[5]) if r[5] else ""]
        for r in rows
    ] + [["TOTAL JOURNAL", "", "", "", _format_amount(total_debit), _format_amount(total_credit)]]

    # Largeur utile = largeur A4 - marges gauche/droite (21 - 1,8*2 = 17,4 cm)
    col_widths = [2.1 * cm, 2.1 * cm, 1.8 * cm, 6.4 * cm, 2.5 * cm, 2.5 * cm]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    last_row = len(table_data) - 1
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (4, 1), (5, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID_COLOR),
        ("ROWBACKGROUNDS", (0, 1), (-1, last_row - 1), [colors.white, ROW_ALT_BG]),
        ("TEXTCOLOR", (0, 1), (1, last_row - 1), PIECE_COLOR),
        ("SPAN", (0, last_row), (3, last_row)),
        ("BACKGROUND", (0, last_row), (-1, last_row), TOTAL_BG),
        ("FONTNAME", (0, last_row), (-1, last_row), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    table.setStyle(TableStyle(style))
    elements.append(table)
    elements.append(Spacer(1, 0.4 * cm))

    if rows:
        elements.append(Paragraph(
            "Contrôle : Total Débit = Total Crédit. Écritures validées par le comptable, "
            "générées automatiquement par le système à partir des factures traitées.",
            footer_style))
    else:
        elements.append(Paragraph("Aucune écriture validée à ce jour.", styles["Normal"]))

    document.build(elements)
    buffer.seek(0)
    return StreamingResponse(
        buffer, media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=journal_comptable.pdf"})
