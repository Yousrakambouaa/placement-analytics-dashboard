import json
from datetime import date
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for

from report_data import (
    DataValidationError,
    aggregate_app_creatives,
    aggregate_apps,
    aggregate_placements,
    load_report_data,
    summarize_placements,
)

app = Flask(__name__)

DATA_FOLDER = Path(__file__).parent / "data"


def placement_detail_redirect(filename: str):
    query = {}
    for key in ("page", "from_day", "to_day", "ad_status", "performance_view"):
        value = request.form.get(key, "").strip()
        if value:
            query[key] = value
    return redirect(url_for("placement_detail", filename=filename, **query))

def parse_date_range() -> tuple[date | None, date | None, str, str, str | None]:
    from_day_text = request.args.get("from_day", "").strip()
    to_day_text = request.args.get("to_day", "").strip()

    from_day = None
    to_day = None

    try:
        if from_day_text:
            from_day = date.fromisoformat(from_day_text)

        if to_day_text:
            to_day = date.fromisoformat(to_day_text)
    except ValueError:
        return (
            None,
            None,
            from_day_text,
            to_day_text,
            "Please select valid dates.",
        )

    if from_day and to_day and from_day > to_day:
        return (
            None,
            None,
            from_day_text,
            to_day_text,
            "The start date cannot be after the end date.",
        )

    return (
        from_day,
        to_day,
        from_day_text,
        to_day_text,
        None,
    )


def json_table_columns(rows: list[dict]) -> list[str]:
    columns = []

    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns

def display_value(value) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    if value is None:
        return "" # empty stringggg---
    return str(value)


def advertisement_from_catalog(
    apps: list[dict],
    app_name: str,
    creative: str,
) -> dict | None:
    app = next((item for item in apps if item["app"] == app_name), None)
    if app is None:
        return None

    known_creatives = set(app["land_creatives"]) | set(app["port_creatives"])
    if creative not in known_creatives:
        return None

    return {
        "asin": app["asin"],
        "gameId": f"{app_name}_{creative}",
        "gameLink": app["gameLink"],
        "videoUrl": (
            "https://test.reboundize.com/videoads/"
            f"{creative}?json={app_name}.json&asin={app['asin']}"
            f"&package={app_name}"
        ),
        "isTested": False,
    }


def placement_ads(placement_data):
    if isinstance(placement_data, list):
        return placement_data
    if isinstance(placement_data, dict) and isinstance(
        placement_data.get("ads"), list
    ):
        return placement_data["ads"]
    abort(400, description="Invalid placement JSON structure.")


def save_placement_data(json_file, placement_data, error_message):
    try:
        with json_file.open("w", encoding="utf-8") as file:
            json.dump(placement_data, file, indent=2)
            file.write("\n")
    except OSError:
        abort(500, description=error_message)


@app.route("/")
def home():
    return render_template("home.html")

@app.route("/apps")
def apps_page():
    try:
        report_data = load_report_data(DATA_FOLDER)
    except DataValidationError as error:
        return render_template(
            "apps.html",
            apps=[],
            available_days=[],
            from_day="",
            to_day="",
            error=str(error),
        )

    available_days = sorted(
        {
            row["day"]
            for row in report_data.daily_rows
        }
    )
    from_day, to_day, from_day_text, to_day_text, error = (
        parse_date_range()
    )

    app_rows = [
        row
        for row in report_data.daily_rows
        if (
            error is None
            and (from_day is None or row["day"] >= from_day)
            and (to_day is None or row["day"] <= to_day)
        )
    ]

    app_metrics = aggregate_apps(
        app_rows,
        report_data.apps,
    )

    return render_template(
        "apps.html",
        apps=app_metrics,
        available_days=available_days,
        from_day=from_day_text,
        to_day=to_day_text,
        error=error,
    )


@app.route("/apps/<app_name>")
def app_detail(app_name):
    try:
        report_data = load_report_data(DATA_FOLDER)
    except DataValidationError:
        abort(404)

    app_data = next(
        (
            app
            for app in report_data.apps
            if app["app"] == app_name
        ),
        None,
    )

    if app_data is None:
        abort(404)

    available_days = sorted(
        {
            row["day"]
            for row in report_data.daily_rows
            if row["app"] == app_name
        }
    )

    from_day, to_day, from_day_text, to_day_text, error = (
        parse_date_range()
    )

    app_rows = [
        row
        for row in report_data.daily_rows
        if (
            row["app"] == app_name
            and (
                error is None
                and (from_day is None or row["day"] >= from_day)
                and (to_day is None or row["day"] <= to_day)
            )
        )
    ]

    creative_metrics = aggregate_app_creatives(
        app_rows,
        report_data.apps,
    )

    page_size = 10
    page_text = request.args.get("page", "1").strip()
    try:
        page = max(1, int(page_text))
    except ValueError:
        page = 1

    total_pages = max(
        1,
        (len(creative_metrics) + page_size - 1) // page_size,
    )
    page = min(page, total_pages)
    page_start = (page - 1) * page_size
    paginated_creative_metrics = creative_metrics[
        page_start:page_start + page_size
    ]

    return render_template(
        "app_detail.html",
        app=app_data,
        creative_metrics=paginated_creative_metrics,
        page=page,
        total_pages=total_pages,
        available_days=available_days,
        from_day=from_day_text,
        to_day=to_day_text,
        error=error,
    )


@app.route("/placements")
def placements():
    page_size = 10
    try:
        report_data = load_report_data(DATA_FOLDER)
    except DataValidationError as error:
        return render_template(
            "placements.html",
            placements=[],
            summary=summarize_placements([]),
            available_days=[],
            available_apps=[],
            available_creatives=[],
            from_day="",
            to_day="",
            page=1,
            total_pages=1,
            placement_json_names=set(),
            error=str(error),
        )

    available_days = sorted(
        {
            row["day"]
            for row in report_data.daily_rows
        }
    )

    available_apps = sorted(
        {
            row["app"]
            for row in report_data.daily_rows
        }
    )


    from_day, to_day, from_day_text, to_day_text, error = (
        parse_date_range()
    )
    selected_app = request.args.get("app", "").strip() or None
    selected_creative = request.args.get("creative", "").strip() or None


    if selected_app:
        available_creatives = sorted(
            {
                row["creative"]
                for row in report_data.daily_rows
                if row["app"] == selected_app
            }
        )
    else:
        available_creatives = sorted(
            {
                row["creative"]
                for row in report_data.daily_rows
            }
        )

    if (
        selected_creative
        and selected_creative not in available_creatives
    ):
        error = "The selected creative is not available for this app."


    if error:
        placement_metrics = []
    else:
        placement_rows = [
            row
            for row in report_data.daily_rows
            if (
                (from_day is None or row["day"] >= from_day)
                and (to_day is None or row["day"] <= to_day)
            )
        ]

        placement_metrics = aggregate_placements(
            placement_rows,
            selected_app=selected_app,
            selected_creative=selected_creative,
            apps=report_data.apps,
        )

    summary = summarize_placements(placement_metrics)
    placement_json_names = set(report_data.placement_configs)
    page_text = request.args.get("page", "1").strip()

    try:
        page = max(1, int(page_text))
    except ValueError:
        page = 1

    total_pages = max(
        1,
        (len(placement_metrics) + page_size - 1) // page_size,
    )
    page = min(page, total_pages)
    page_start = (page - 1) * page_size
    page_placements = placement_metrics[
        page_start:page_start + page_size
    ]

    return render_template(
        "placements.html",
        placements=page_placements,
        summary=summary,
        available_days=available_days,
        available_apps=available_apps,
        available_creatives=available_creatives,
        from_day=from_day_text,
        to_day=to_day_text,
        selected_app=selected_app or "",
        selected_creative=selected_creative or "",
        placement_json_names=placement_json_names,
        placement_testing=report_data.placement_testing,
        page=page,
        total_pages=total_pages,
        error=error,
    )


@app.post("/placements/<placement_name>/ads/<int:ad_index>/is-tested")
def update_ad_testing(placement_name, ad_index):
    json_file = DATA_FOLDER / f"{placement_name}.json"

    if (
        json_file.parent != DATA_FOLDER
        or not json_file.is_file()
    ):
        abort(404)

    testing_values = request.form.getlist("isTested")
    if not testing_values or any(
        value not in {"true", "false"} for value in testing_values
    ):
        abort(400, description="Testing must be true or false.")

    is_testing = "true" in testing_values

    try:
        with json_file.open("r", encoding="utf-8") as file:
            placement_data = json.load(file)
    except (OSError, json.JSONDecodeError):
        abort(404)

    ads = placement_ads(placement_data)

    if ad_index < 0 or ad_index >= len(ads):
        abort(404)

    ads[ad_index]["isTested"] = is_testing
    ads[ad_index].pop("testing", None)
    ads[ad_index].pop("enabled", None)
    save_placement_data(
        json_file,
        placement_data,
        "Could not save testing status.",
    )

    return placement_detail_redirect(json_file.name)


@app.post("/placements/<placement_name>/ads/<app_name>/<creative>/enabled")
def update_ad_enabled(placement_name, app_name, creative):
    json_file = DATA_FOLDER / f"{placement_name}.json"

    if json_file.parent != DATA_FOLDER or not json_file.is_file():
        abort(404)

    enabled_values = request.form.getlist("enabled")
    if not enabled_values or any(
        value not in {"true", "false"} for value in enabled_values
    ):
        abort(400, description="Enabled must be true or false.")

    try:
        report_data = load_report_data(DATA_FOLDER)
        with json_file.open("r", encoding="utf-8") as file:
            placement_data = json.load(file)
    except (DataValidationError, OSError, json.JSONDecodeError):
        abort(404)

    ad = advertisement_from_catalog(report_data.apps, app_name, creative)
    if ad is None:
        abort(404)

    ads = placement_ads(placement_data)
    is_enabled = "true" in enabled_values
    game_id = ad["gameId"]
    matching_index = next(
        (
            index
            for index, existing_ad in enumerate(ads)
            if existing_ad.get("gameId") == game_id
        ),
        None,
    )

    if is_enabled and matching_index is None:
        ads.append(ad)
    elif not is_enabled and matching_index is not None:
        ads.pop(matching_index)

    for existing_ad in ads:
        existing_ad.pop("enabled", None)

    save_placement_data(
        json_file,
        placement_data,
        "Could not save advertisement status.",
    )

    return placement_detail_redirect(json_file.name)


@app.post("/placements/<placement_name>/ads/add")
def add_advertisement(placement_name):
    json_file = DATA_FOLDER / f"{placement_name}.json"

    if json_file.parent != DATA_FOLDER or not json_file.is_file():
        abort(404)

    selected_ad = request.form.get("advertisement", "").strip()
    app_name, separator, creative = selected_ad.partition("|")
    if not separator or not app_name or not creative:
        abort(400, description="Please select an advertisement.")

    try:
        report_data = load_report_data(DATA_FOLDER)
        with json_file.open("r", encoding="utf-8") as file:
            placement_data = json.load(file)
    except (DataValidationError, OSError, json.JSONDecodeError):
        abort(404)

    ad = advertisement_from_catalog(report_data.apps, app_name, creative)
    if ad is None:
        abort(404)

    ads = placement_ads(placement_data)
    if any(existing_ad.get("gameId") == ad["gameId"] for existing_ad in ads):
        abort(400, description="That advertisement is already appearing.")

    ads.append(ad)
    save_placement_data(
        json_file,
        placement_data,
        "Could not add advertisement.",
    )
    return placement_detail_redirect(json_file.name)


@app.post("/placements/<placement_name>/ads/enable-all")
def enable_all_ads(placement_name):
    json_file = DATA_FOLDER / f"{placement_name}.json"

    if json_file.parent != DATA_FOLDER or not json_file.is_file():
        abort(404)

    try:
        report_data = load_report_data(DATA_FOLDER)
        with json_file.open("r", encoding="utf-8") as file:
            placement_data = json.load(file)
    except (DataValidationError, OSError, json.JSONDecodeError):
        abort(404)

    ads = placement_ads(placement_data)
    existing_game_ids = {ad.get("gameId") for ad in ads}
    for app in report_data.apps:
        creatives = app["land_creatives"] + app["port_creatives"]
        for creative in dict.fromkeys(creatives):
            ad = advertisement_from_catalog(report_data.apps, app["app"], creative)
            if ad and ad["gameId"] not in existing_game_ids:
                ads.append(ad)
                existing_game_ids.add(ad["gameId"])

    for ad in ads:
        ad.pop("enabled", None)

    save_placement_data(
        json_file,
        placement_data,
        "Could not enable advertisements.",
    )

    return redirect(
        url_for(
            "placement_detail",
            filename=json_file.name,
            ad_status="appearing",
        )
    )


@app.route("/placements/<filename>")
def placement_detail(filename):
    json_file = DATA_FOLDER / filename

    if (
        json_file.parent != DATA_FOLDER
        or json_file.suffix != ".json"
        or not json_file.is_file()
    ):
        abort(404)

    try:
        report_data = load_report_data(DATA_FOLDER)
    except DataValidationError:
        abort(404)

    placement_name = json_file.stem
    ads = report_data.placement_configs.get(placement_name)

    if ads is None:
        abort(404)

    placement = {
        "ads": ads,
    }


    available_days = sorted(
        {
            row["day"]
            for row in report_data.daily_rows
            if row["placement"] == placement_name
        }
    )

    from_day, to_day, from_day_text, to_day_text, detail_error = (
        parse_date_range()
    )

    placement_rows = [
        row
        for row in report_data.daily_rows
        if (
            row["placement"] == placement_name
            and (
                from_day is None
                or row["day"] >= from_day
            )
            and (
                to_day is None
                or row["day"] <= to_day
            )
        )
    ]

    placement_metrics = aggregate_placements(
        placement_rows,
        apps=report_data.apps,
    )

    placement_summary = summarize_placements(placement_metrics)

    performance_by_key = {
        (metrics["app"], metrics["creative"]): metrics
        for metrics in aggregate_app_creatives(
            placement_rows,
            report_data.apps,
        )
    }
    performance_view = request.args.get(
        "performance_view",
        "with_performance",
    ).strip()
    if performance_view not in {"all", "with_performance"}:
        performance_view = "with_performance"
    ads_by_game_id = {
        str(ad.get("gameId", "")): (ad_index, ad)
        for ad_index, ad in enumerate(ads)
    }
    app_creative_breakdown = []
    ad_testing_by_app_creative = {}
    ad_index_by_app_creative = {}
    for ad_index, ad in enumerate(ads):
        game_id = str(ad.get("gameId", ""))
        app_name, separator, creative = game_id.partition("_")
        if not separator:
            continue

        key = (app_name, creative)
        metrics = dict(
            performance_by_key.get(
                key,
                {
                    "app": app_name,
                    "creative": creative,
                    "orientation": "unknown",
                    "impression": 0,
                    "unique_impression": 0,
                    "click": 0,
                    "unique_click": 0,
                    "install": 0,
                    "ctr": 0,
                    "install_rate": 0,
                },
            )
        )
        metrics["has_performance"] = key in performance_by_key
        if performance_view == "with_performance" and not metrics["has_performance"]:
            continue

        app_creative_breakdown.append(metrics)
        display_key = f"{app_name}|{creative}"
        ad_index_by_app_creative[display_key] = ad_index

        if "isTested" in ad:
            testing_value = ad["isTested"]
            if not isinstance(testing_value, bool):
                abort(400, description="Advertisement testing must be true or false.")
            ad_testing_by_app_creative[display_key] = testing_value

    app_creative_breakdown.sort(
        key=lambda metrics: (metrics["app"], metrics["creative"])
    )
    available_advertisements = []
    for app in report_data.apps:
        for creative in dict.fromkeys(
            app["land_creatives"] + app["port_creatives"]
        ):
            game_id = f"{app['app']}_{creative}"
            if game_id not in ads_by_game_id:
                available_advertisements.append(
                    {
                        "app": app["app"],
                        "creative": creative,
                        "value": f"{app['app']}|{creative}",
                    }
                )

    all_appearing_count = len(ads_by_game_id)
    with_performance_count = sum(
        1
        for ad in ads
        if (
            (game_id := str(ad.get("gameId", ""))).partition("_")[0],
            game_id.partition("_")[2],
        ) in performance_by_key
    )

    page_size = 10
    page_text = request.args.get("page", "1").strip()
    try:
        page = max(1, int(page_text))
    except ValueError:
        page = 1

    total_pages = max(
        1,
        (len(app_creative_breakdown) + page_size - 1) // page_size,
    )
    page = min(page, total_pages)
    page_start = (page - 1) * page_size
    paginated_app_creative_breakdown = app_creative_breakdown[
        page_start:page_start + page_size
    ]

    return render_template(
        "placement_detail.html",
        filename=filename,
        placement=placement,
        placement_metrics=placement_metrics,
        placement_summary=placement_summary,
        app_creative_breakdown=paginated_app_creative_breakdown,
        ad_testing_by_app_creative=ad_testing_by_app_creative,
        ad_index_by_app_creative=ad_index_by_app_creative,
        available_advertisements=available_advertisements,
        performance_view=performance_view,
        all_appearing_count=all_appearing_count,
        with_performance_count=with_performance_count,
        page=page,
        total_pages=total_pages,
        available_days=available_days,
        from_day=from_day_text,
        to_day=to_day_text,
        detail_error=detail_error,
    )


if __name__ == "__main__":
    app.run(debug=True)