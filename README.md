# Fantasy Basketball Rankings

This repository is for a passion project related to fantasy basketball. I want to build out my own player rankings application using some new tools and libraries.

## Features
- 9-cat fantasy rankings (turnovers excluded)
- Volume-weighted efficiency stats
- Customizable category weights
- Nicegui dashboard

## Project Structure
- `src/` – data ingestion and ranking logic
- `app/` – dashboard application
- `data/` – cached stats (not committed)
- `notebooks/` – exploration and analysis

## Getting Started
```bash
pip install -r requirements.txt
python src/ingest.py
python app/main.py