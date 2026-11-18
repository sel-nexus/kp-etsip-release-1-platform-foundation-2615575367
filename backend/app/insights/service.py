"""Compute dashboard metrics and prepare scoped report exports."""

import csv
import io
from fastapi import HTTPException
from app.admin.service import csv_value
from app.core.seed import ROLE_PERMISSIONS
from app.insights.repository import InsightsRepository

APPLICATION_FIELDS = ["name", "portfolioName", "productArea", "criticality", "tier", "lifecycleStatus", "applicationHealthScore", "qualityScore", "automationCoverage", "unitTestCoverage", "openDefects", "openCriticalDefects", "riskLevel"]
PORTFOLIO_FIELDS = ["name", "owner", "productArea", "applicationCount", "qualityScore", "status"]


async def authorize(repo: InsightsRepository, user: dict, permission: str) -> None:
    """Enforce both the role ceiling and the live permission setting."""
    role = user.get("role", "")
    if permission not in ROLE_PERMISSIONS.get(role, []) or permission not in await repo.permissions(role):
        raise HTTPException(403, "Permission denied")


def average(rows: list[dict], key: str) -> int | None:
    """Return a half-up integer average, or null when there are no values."""
    values = [row[key] for row in rows if row.get(key) is not None]
    return (2 * sum(values) + len(values)) // (2 * len(values)) if values else None


def summarize(portfolios: list[dict], applications: list[dict]) -> tuple[dict, list[dict], list[dict]]:
    """Compute the specified metrics and report rows from the same selection."""
    grouped: dict[str, list[dict]] = {str(p["_id"]): [] for p in portfolios}
    names = {str(p["_id"]): p["name"] for p in portfolios}
    for app in applications:
        if app["portfolioId"] in grouped:
            grouped[app["portfolioId"]].append(app)
    portfolio_rows = []
    for p in portfolios:
        identifier = str(p["_id"])
        apps = grouped[identifier]
        portfolio_rows.append({"id": identifier, "name": p["name"], "owner": p.get("owner", ""),
            "productArea": p.get("productArea", ""), "status": p.get("status", ""),
            "applicationCount": len(apps), "qualityScore": average(apps, "qualityScore"),
            "applicationsAtRisk": sum(a.get("riskLevel") == "High" for a in apps)})
    app_rows = [{**{k: v for k, v in a.items() if k != "_id"}, "id": str(a["_id"]),
                 "portfolioName": names.get(a["portfolioId"], "Unavailable")} for a in applications]
    metrics = {"enterpriseQualityScore": average(applications, "qualityScore"),
        "applicationHealthScore": average(applications, "applicationHealthScore"),
        "automationMaturityScore": average(applications, "automationCoverage"),
        "openCriticalDefects": sum(a.get("openCriticalDefects", 0) for a in applications),
        "applicationsAtRisk": sum(a.get("riskLevel") == "High" for a in applications),
        "totalApplications": len(applications), "totalPortfolios": len(portfolios), "portfolios": portfolio_rows}
    return metrics, portfolio_rows, app_rows


async def read_inventory(repo: InsightsRepository, user: dict, portfolio: str | None, area: str | None, risk: str | None) -> tuple[dict, list[dict], list[dict]]:
    """Authorize a read and calculate its shared filtered data set."""
    await authorize(repo, user, "view")
    return summarize(*await repo.inventory(user, portfolio, area, risk))


async def export(repo: InsightsRepository, user: dict, kind: str, portfolio: str | None, area: str | None, risk: str | None) -> str:
    """Generate a complete formula-safe CSV and audit the successful export."""
    await authorize(repo, user, "view")
    await authorize(repo, user, "export")
    _, portfolios, applications = summarize(*await repo.inventory(user, portfolio, area, risk))
    fields, rows = (APPLICATION_FIELDS, applications) if kind == "application" else (PORTFOLIO_FIELDS, portfolios)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(fields)
    for row in rows:
        writer.writerow([csv_value(row.get(key)) for key in fields])
    await repo.audit_export(user, kind)
    return output.getvalue()
