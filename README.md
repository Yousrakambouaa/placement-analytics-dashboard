# Reboundize Placement Analytics Dashboard

A Flask web dashboard for exploring advertising placement performance. The app
loads the included CSV and JSON data files, then presents performance metrics
by placement, advertised app, and creative.

## Features

- Browse placement performance with date, app, creative, and status filters.
- View detailed placement configuration and advertisement data.
- Compare advertised apps and their creative performance.
- Review impressions, clicks, installs, daily users, CTR, and install rate.
- Validate the supplied CSV and JSON data before displaying it.

## Project structure

```text
.
├── app.py                 # Flask routes and application entry point
├── report_data.py         # Data loading, validation, and aggregation
├── data/                  # Local data files (not committed)
├── templates/             # Jinja HTML templates
├── static/                # CSS and JavaScript assets
└── requirements.txt       # Python dependencies
```

## Requirements

- Python 3.10 or newer
- Flask 3.1.3

## Run locally

1. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Start the application:

   ```powershell
   python app.py
   ```

4. Open <http://127.0.0.1:5000> in your browser.

The development server runs with Flask debug mode enabled by the current
application entry point. Do not use this development server as a production
deployment server.

## Data

The dashboard reads these files from `data/`:

- `daily_report_300_rows.csv` for daily performance metrics.
- `advertised_data.csv` for app and creative metadata.
- Placement JSON files for advertisement configuration.
- `used_data_names.json` for display names used by the dashboard.

The data directory is intentionally excluded from Git because it may contain
company or other confidential information. Copy authorized data files into
`data/` locally before starting the application. Do not upload company data to
GitHub unless your company has explicitly approved the repository, its
visibility, and the files being shared.

The expected files are:

- `daily_report_300_rows.csv`
- `advertised_data.csv`
- `used_data_names.json`
- One or more placement JSON files

The CSV and JSON structures are validated in `report_data.py`.

## GitHub

This project is already connected to its GitHub repository. Keep company data
out of Git: files in `data/` are intentionally ignored, while the application
code and templates are tracked.
