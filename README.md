# Job Bot

A CLI tool that scrapes job listings from LinkedIn, Indeed, Handshake, and accounting firm sites, scores them against your profile, and emails you a daily digest of matches.

## Features

- Scrapes LinkedIn, Indeed, Handshake, and Big 4 / regional accounting firm career pages
- Scores each job 0–100 based on title match, seniority, location, and major fit
- Filters out roles requiring 3+ years experience, active CPA license, or early start dates
- Emails a ranked digest of matches after each run
- Interactive terminal dashboard to review, save, or reject listings
- Persists all jobs in a local SQLite database

## Setup

```bash
git clone https://github.com/victormartin1313/job-bot.git
cd job-bot
pip install -r requirements.txt
cp config.example.yaml config.yaml
python3 main.py setup
```

The setup wizard will walk you through your profile, job preferences, email credentials, and platform logins.

## Usage

```bash
python3 main.py discover   # scrape all sources, score jobs, send email digest
python3 main.py review     # browse and triage the discovery queue
python3 main.py saved      # list jobs you saved with URLs
python3 main.py status     # show counts by status
```

## Configuration

Copy `config.example.yaml` to `config.yaml` and fill in your details. The file is gitignored so your credentials stay local.

| Field | Description |
|---|---|
| `profile.name` | Your name |
| `preferences.roles` | Job titles to target |
| `preferences.locations` | Target cities |
| `preferences.min_score` | Minimum score to include in digest (0–100) |
| `email.smtp_*` | SMTP credentials for sending the digest |
| `platforms.linkedin_*` | LinkedIn credentials for scraping |
