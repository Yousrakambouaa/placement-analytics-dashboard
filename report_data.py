import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


REPORT_COLUMNS = (
    "day",
    "placement",
    "app",
    "creative",
    "impression",
    "unique_impression",
    "click",
    "unique_click",
    "install",
    "placement_daily_users",
)
REPORT_NUMBER_COLUMNS = REPORT_COLUMNS[4:]
APP_COLUMNS = ("app", "asin", "gameLink", "land_creatives", "port_creatives")


class DataValidationError(ValueError):
    """Raised when a reeequired data fiile has an innvalid structure.."""


@dataclass(frozen=True)
class ReportData:
    apps: list[dict[str, Any]]
    daily_rows: list[dict[str, Any]]
    placement_configs: dict[str, list[dict[str, Any]]]
    placement_testing: dict[str, bool]
    names: dict[str, list[str]]
    warnings: list[str]


def _require_columns(
    actual_columns: list[str] | None,
    required_columns: tuple[str, ...],
    filename: str,
) -> None:
    columns = set(actual_columns or [])
    missing = [column for column in required_columns if column not in columns]
    if missing:
        raise DataValidationError(
            f"{filename} is missing required columns: {', '.join(missing)}"
        )


def _split_creatives(value: str, filename: str, row_number: int) -> list[str]:
    if not value.strip():
        return []
    creatives = [creative.strip() for creative in value.split(",")]
    if any(not creative for creative in creatives):
        raise DataValidationError(
            f"{filename}, row {row_number} contains an empty creative name"
        )
    return creatives


def load_advertised_apps(data_folder: Path) -> list[dict[str, Any]]:
    filename = "advertised_data.csv"
    path = data_folder / filename
    try:
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            _require_columns(reader.fieldnames, APP_COLUMNS, filename)
            apps = []
            seen_asins: set[str] = set()
            seen_apps: set[str] = set()

            for row_number, row in enumerate(reader, start=2):
                app = (row.get("app") or "").strip()
                asin = (row.get("asin") or "").strip()
                if not app or not asin:
                    raise DataValidationError(
                        f"{filename}, row {row_number} requires app and asin"
                    )
                if app in seen_apps or asin in seen_asins:
                    raise DataValidationError(
                        f"{filename}, row {row_number} duplicates app or asin"
                    )
                seen_apps.add(app)
                seen_asins.add(asin)
                apps.append(
                    {
                        "app": app,
                        "asin": asin,
                        "gameLink": (row.get("gameLink") or "").strip(),
                        "land_creatives": _split_creatives(
                            row.get("land_creatives") or "", filename, row_number
                        ),
                        "port_creatives": _split_creatives(
                            row.get("port_creatives") or "", filename, row_number
                        ),
                    }
                )
    except OSError as error:
        raise DataValidationError(f"Could not read {filename}: {error}") from error

    return apps


def load_daily_rows(data_folder: Path) -> list[dict[str, Any]]:
    filename = "daily_report_300_rows.csv"
    path = data_folder / filename
    try:
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            _require_columns(reader.fieldnames, REPORT_COLUMNS, filename)
            rows = []
            seen_keys: set[tuple[str, str, str, str]] = set()

            for row_number, row in enumerate(reader, start=2):
                try:
                    report_day = date.fromisoformat((row.get("day") or "").strip())
                except ValueError as error:
                    raise DataValidationError(
                        f"{filename}, row {row_number} has an invalid day"
                    ) from error

                placement = (row.get("placement") or "").strip()
                app = (row.get("app") or "").strip()
                creative = (row.get("creative") or "").strip()
                if not placement or not app or not creative:
                    raise DataValidationError(
                        f"{filename}, row {row_number} requires placement, app, and creative"
                    )

                key = (report_day.isoformat(), placement, app, creative)
                if key in seen_keys:
                    raise DataValidationError(
                        f"{filename}, row {row_number} duplicates "
                        "day, placement, app, and creative"
                    )
                seen_keys.add(key)

                parsed_row: dict[str, Any] = {
                    "day": report_day,
                    "placement": placement,
                    "app": app,
                    "creative": creative,
                }
                for column in REPORT_NUMBER_COLUMNS:
                    try:
                        parsed_row[column] = int(row.get(column) or "")
                    except ValueError as error:
                        raise DataValidationError(
                            f"{filename}, row {row_number} has an invalid "
                            f"number in {column}"
                        ) from error
                    if parsed_row[column] < 0:
                        raise DataValidationError(
                            f"{filename}, row {row_number} has a negative {column}"
                        )
                rows.append(parsed_row)
    except OSError as error:
        raise DataValidationError(f"Could not read {filename}: {error}") from error

    return rows


def load_names(data_folder: Path) -> dict[str, list[str]]:
    filename = "used_data_names.json"
    path = data_folder / filename
    try:
        with path.open("r", encoding="utf-8") as file:
            names = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise DataValidationError(f"Could not read {filename}: {error}") from error

    if not isinstance(names, dict):
        raise DataValidationError(f"{filename} must contain an object")

    result: dict[str, list[str]] = {}
    for category in ("placements", "apps", "creatives"):
        values = names.get(category)
        if not isinstance(values, list) or not all(
            isinstance(value, str) and value.strip() for value in values
        ):
            raise DataValidationError(
                f"{filename} category '{category}' must be a list of names"
            )
        result[category] = [value.strip() for value in values]
    return result


def _load_placement_file(
    path: Path,
) -> tuple[list[dict[str, Any]], bool]:
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise DataValidationError(f"Could not read {path.name}: {error}") from error

    if isinstance(value, dict):
        value = value.get("ads")

    if not isinstance(value, list) or not all(
        isinstance(ad, dict) for ad in value
    ):
        raise DataValidationError(
            f"{path.name} must contain a JSON array of advertisement objects"
        )
    return value, False


def load_placement_configs(
    data_folder: Path,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bool]]:
    configs: dict[str, list[dict[str, Any]]] = {}
    testing_states: dict[str, bool] = {}

    for path in sorted(data_folder.glob("*.json")):
        if path.name == "used_data_names.json":
            continue
        placement_name = path.stem
        if placement_name in configs:
            raise DataValidationError(
                f"Duplicate placement configuration: {placement_name}"
            )
        ads, is_testing = _load_placement_file(path)
        configs[placement_name] = ads
        testing_states[placement_name] = is_testing
    return configs, testing_states


def validate_relationships(
    apps: list[dict[str, Any]],
    daily_rows: list[dict[str, Any]],
    placement_configs: dict[str, list[dict[str, Any]]],
    names: dict[str, list[str]],
) -> list[str]:
    warnings: list[str] = []
    app_by_name = {app["app"]: app for app in apps}
    app_by_asin = {app["asin"]: app for app in apps}
    report_placements = {row["placement"] for row in daily_rows}
    report_apps = {row["app"] for row in daily_rows}
    report_creatives = {row["creative"] for row in daily_rows}

    for app in sorted(report_apps - app_by_name.keys()):
        warnings.append(f"Report app is missing from advertised_data.csv: {app}")

    for row in daily_rows:
        app = app_by_name.get(row["app"])
        if app is not None:
            known_creatives = set(app["land_creatives"]) | set(app["port_creatives"])
            if row["creative"] not in known_creatives:
                warnings.append(
                    f"Report creative is not listed for {row['app']}: {row['creative']}"
                )

    for placement in sorted(set(placement_configs) - report_placements):
        warnings.append(
            f"Placement JSON has no matching report rows yet: {placement}"
        )
    for placement in sorted(report_placements - set(placement_configs)):
        warnings.append(
            f"Report placement has no JSON configuration yet: {placement}"
        )

    for placement, ads in placement_configs.items():
        for index, ad in enumerate(ads, start=1):
            asin = str(ad.get("asin", "")).strip()
            if asin and asin not in app_by_asin:
                warnings.append(
                    f"{placement}.json advertisement {index} has unknown asin: {asin}"
                )

    for category in ("placements", "apps", "creatives"):
        actual = {
            "placements": report_placements,
            "apps": report_apps,
            "creatives": report_creatives,
        }[category]
        missing = sorted(actual - set(names[category]))
        if missing:
            warnings.append(
                f"Manifest category '{category}' is missing: {', '.join(missing)}"
            )

    return sorted(set(warnings))


def load_report_data(data_folder: Path) -> ReportData:
    apps = load_advertised_apps(data_folder)
    daily_rows = load_daily_rows(data_folder)
    names = load_names(data_folder)
    placement_configs, placement_testing = load_placement_configs(data_folder)
    warnings = validate_relationships(
        apps, daily_rows, placement_configs, names
    )
    return ReportData(
        apps,
        daily_rows,
        placement_configs,
        placement_testing,
        names,
        warnings,
    )


def aggregate_placements(
    rows: list[dict[str, Any]],
    selected_day: date | None = None,
    selected_app: str | None = None,
    selected_creative: str | None = None,
    apps: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:

    """
    Aggregate report metrics by placement.

    If selected_day is provided, only rows from that date are included.
    If selected_app is provided, only rows for that app are included.
    If selected_creative is provided, only rows for that creative are included.
    If apps is provided, orientation information is calculated for each placement.
    """
    grouped: dict[str, dict[str, Any]] = {}
    daily_users: dict[str, dict[date, int]] = {}
    orientations: dict[str, set[str]] = {}

    for row in rows:
        if selected_day is not None and row["day"] != selected_day:
            continue

        if selected_app is not None and row["app"] != selected_app:
            continue

        if selected_creative is not None and row["creative"] != selected_creative:
            continue

        placement = row["placement"]

        if placement not in grouped:
            grouped[placement] = {
                "placement": placement,
                "impression": 0,
                "unique_impression": 0,
                "click": 0,
                "unique_click": 0,
                "install": 0,
                "placement_daily_users": 0,
                "orientation": "unknown",
            }
            daily_users[placement] = {}
            orientations[placement] = set()

        if apps is not None:
            orientations[placement].add(
                classify_creative_orientation(
                    apps,
                    row["app"],
                    row["creative"],
                )
            )

        grouped[placement]["impression"] += row["impression"]
        grouped[placement]["unique_impression"] += row["unique_impression"]
        grouped[placement]["click"] += row["click"]
        grouped[placement]["unique_click"] += row["unique_click"]
        grouped[placement]["install"] += row["install"]

        daily_users[placement].setdefault(
            row["day"],
            row["placement_daily_users"],
        )

    for placement, placement_days in daily_users.items():
        grouped[placement]["placement_daily_users"] = sum(
            placement_days.values()
        )

    for placement, placement_orientations in orientations.items():
        known_orientations = placement_orientations - {"unknown"}

        if len(known_orientations) == 1 and "unknown" not in placement_orientations:
            grouped[placement]["orientation"] = known_orientations.pop()
        elif len(known_orientations) > 1:
            grouped[placement]["orientation"] = "mixed"
        else:
            grouped[placement]["orientation"] = "unknown"


    for metrics in grouped.values():
        impressions = metrics["impression"]
        clicks = metrics["click"]

        metrics["ctr"] = (
            round(clicks / impressions * 100, 2)
            if impressions
            else 0
        )

        metrics["install_rate"] = (
            round(metrics["install"] / clicks * 100, 2)
            if clicks
            else 0
        )

    return sorted(
        grouped.values(),
        key=lambda metrics: metrics["placement"],
    )



def summarize_placements(
    placement_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Calculate totals for the currently filtered placement metrics.
    """
    totals = {
        "impression": 0,
        "unique_impression": 0,
        "click": 0,
        "unique_click": 0,
        "install": 0,
        "placement_daily_users": 0,
    }

    for placement in placement_metrics:
        for field in totals:
            totals[field] += placement[field]

    impressions = totals["impression"]
    clicks = totals["click"]

    totals["ctr"] = (
        round(clicks / impressions * 100, 2)
        if impressions
        else 0
    )

    totals["install_rate"] = (
        round(totals["install"] / clicks * 100, 2)
        if clicks
        else 0
    )

    totals["placement_count"] = len(placement_metrics)

    return totals


def classify_creative_orientation(
    apps: list[dict[str, Any]],
    app_name: str,
    creative: str,
) -> str:
    """
    Return the catalog orientation for an app creative.

    Possible results are landscape, portrait, both, and unknown.
    """
    app_data = next(
        (app for app in apps if app["app"] == app_name),
        None,
    )

    if app_data is None:
        return "unknown"

    in_landscape = creative in app_data["land_creatives"]
    in_portrait = creative in app_data["port_creatives"]

    if in_landscape and in_portrait:
        return "both"

    if in_landscape:
        return "landscape"

    if in_portrait:
        return "portrait"

    return "unknown"


def enrich_report_rows(
    rows: list[dict[str, Any]],
    apps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Return report rows with the creative orientation added.

    The original rows are copied and are not modified.
    """
    enriched_rows = []

    for row in rows:
        enriched_row = dict(row)
        enriched_row["orientation"] = classify_creative_orientation(
            apps,
            row["app"],
            row["creative"],
        )
        enriched_rows.append(enriched_row)

    return enriched_rows


def aggregate_app_creatives(
    rows: list[dict[str, Any]],
    apps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Aggregate performance by advertised app and creative.
    """
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        key = (row["app"], row["creative"])

        if key not in grouped:
            grouped[key] = {
                "app": row["app"],
                "creative": row["creative"],
                "orientation": classify_creative_orientation(
                    apps,
                    row["app"],
                    row["creative"],
                ),
                "impression": 0,
                "unique_impression": 0,
                "click": 0,
                "unique_click": 0,
                "install": 0,
            }

        grouped[key]["impression"] += row["impression"]
        grouped[key]["unique_impression"] += row["unique_impression"]
        grouped[key]["click"] += row["click"]
        grouped[key]["unique_click"] += row["unique_click"]
        grouped[key]["install"] += row["install"]

    for metrics in grouped.values():
        impressions = metrics["impression"]
        clicks = metrics["click"]

        metrics["ctr"] = (
            round(clicks / impressions * 100, 2)
            if impressions
            else 0
        )

        metrics["install_rate"] = (
            round(metrics["install"] / clicks * 100, 2)
            if clicks
            else 0
        )

    return sorted(
        grouped.values(),
        key=lambda metrics: (metrics["app"], metrics["creative"]),
    )


def aggregate_apps(
    rows: list[dict[str, Any]],
    apps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Aggregate existing app/creative metrics by app.
    """
    app_creative_metrics = aggregate_app_creatives(rows, apps)
    app_groups: dict[str, dict[str, Any]] = {}

    for metrics in app_creative_metrics:
        app_name = metrics["app"]

        if app_name not in app_groups:
            app_data = next(
                (
                    app
                    for app in apps
                    if app["app"] == app_name
                ),
                {},
            )

            app_groups[app_name] = {
                "app": app_name,
                "asin": app_data.get("asin", ""),
                "gameLink": app_data.get("gameLink", ""),
                "impression": 0,
                "unique_impression": 0,
                "click": 0,
                "unique_click": 0,
                "install": 0,
                "creative_count": 0,
            }

        app_groups[app_name]["impression"] += metrics["impression"]
        app_groups[app_name]["unique_impression"] += (
            metrics["unique_impression"]
        )
        app_groups[app_name]["click"] += metrics["click"]
        app_groups[app_name]["unique_click"] += metrics["unique_click"]
        app_groups[app_name]["install"] += metrics["install"]
        app_groups[app_name]["creative_count"] += 1

    for metrics in app_groups.values():
        impressions = metrics["impression"]
        clicks = metrics["click"]

        metrics["ctr"] = (
            round(clicks / impressions * 100, 2)
            if impressions
            else 0
        )

        metrics["install_rate"] = (
            round(metrics["install"] / clicks * 100, 2)
            if clicks
            else 0
        )

    return sorted(
        app_groups.values(),
        key=lambda metrics: metrics["app"],
    )