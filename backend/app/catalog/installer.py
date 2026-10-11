"""Installe (ou complète) les plans comptables du catalogue en base.

Idempotent : relancer ne crée aucun doublon. Les comptes et règles déjà présents
sont conservés tels quels ; seuls les manquants sont ajoutés (un administrateur ou
une mise à jour du catalogue peut donc compléter un plan sans écraser l'existant)."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import pcg_fr
from app.infrastructure.db import models as m

logger = logging.getLogger(__name__)

# Plans fournis par le catalogue. Le PCG malgache est créé par les scripts SQL
# (schema.sql / seed_accounts.sql / migration 004) : il n'est pas réinstallé ici.
CATALOG = [pcg_fr.DEFINITION]


def keywords_for_chart(chart_code: str | None) -> dict[str, list[str]] | None:
    """Mots-clés d'affinage propres à un plan (None = ceux du plan malgache, par défaut)."""
    for definition in CATALOG:
        if definition["code"] == chart_code:
            return definition.get("keywords")
    return None


def install_chart(db: Session, definition: dict) -> dict[str, int]:
    chart = db.scalar(select(m.ChartModel).where(m.ChartModel.code == definition["code"]))
    created_chart = chart is None
    if chart is None:
        chart = m.ChartModel(code=definition["code"], name=definition["name"],
                             country=definition.get("country"), version=definition.get("version"),
                             description=definition.get("description"))
        db.add(chart)
        db.flush()

    existing = set(db.scalars(select(m.AccountModel.code).where(m.AccountModel.chart_id == chart.id)).all())
    added_accounts = 0
    for account in definition["accounts"]():
        if account["code"] in existing:
            continue
        db.add(m.AccountModel(chart_id=chart.id, **account))
        added_accounts += 1

    existing_rules = set(db.scalars(select(m.AccountingRuleModel.code)).all())
    added_rules = 0
    for rule in definition["rules"]:
        if rule["code"] in existing_rules:
            continue
        db.add(m.AccountingRuleModel(chart_id=chart.id, **rule))
        added_rules += 1

    db.commit()
    return {"chart_created": int(created_chart), "accounts_added": added_accounts, "rules_added": added_rules}


def install_catalog(db: Session) -> dict[str, dict[str, int]]:
    report = {}
    for definition in CATALOG:
        report[definition["code"]] = install_chart(db, definition)
        logger.info("Plan %s : %s", definition["code"], report[definition["code"]])
    return report
