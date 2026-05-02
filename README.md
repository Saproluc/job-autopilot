# 🤖 Job AutoPilot — Claude-Powered Overnight Job Search Automation

> Upload your resume once. Wake up to 50 pre-filled job applications waiting for your final click.

---

## ✨ What It Does

**Job AutoPilot** is an open-source Python tool that runs overnight and automates your entire job search pipeline using the Claude API:

| Step | What Happens |
|------|-------------|
| 🔍 **Search** | Scans LinkedIn, Indeed, and Glassdoor for matching roles |
| 📄 **Tailor** | Rewrites your resume per job with ATS-optimized keywords |
| ✉️ **Draft** | Generates a custom cover letter for each application |
| 🌐 **Fill** | Opens Chrome tabs and auto-fills every application form |
| ⏸️ **Pause** | Leaves forms open for your final review before submitting |
| 💾 **Save** | Stores all resumes/cover letters locally in `/output` |

**Daily limit: 50 applications** — so you never get flagged as a bot.

---

## 🧰 Requirements

- **Python 3.10+**
- **Google Chrome** (latest)
- **Claude API key** — [Get one at console.anthropic.com](https://console.anthropic.com)
- **Claude Pro subscription** recommended for higher rate limits
- Windows, macOS, or Linux

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/job-autopilot.git
cd job-autopilot
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

Then edit `config/config.yaml` with your job preferences and personal info.

### 3. Upload Your Resume

Place your resume PDF at:
```
config/base_resume.pdf
```

### 4. Run It

**Manually:**
```bash
python src/main.py
```

**Overnight (Windows Task Scheduler):**
```bash
scheduler\setup_scheduler.bat
```

**Overnight (Mac/Linux cron):**
```bash
bash scheduler/setup_scheduler.sh
```

---

## ⚙️ Configuration (`config/config.yaml`)

```yaml
personal:
  full_name: "John Smith"
  email: "john@email.com"
  phone: "555-123-4567"
  location: "Worcester, MA"
  linkedin: "linkedin.com/in/johnsmith"
  github: "github.com/johnsmith"
  portfolio: ""

job_search:
  titles:
    - "Cloud Engineer"
    - "DevOps Engineer"
    - "Business Analyst"
    - "IT Analyst"
  locations:
    - "Remote"
    - "Boston, MA"
    - "New York, NY"
  keywords:
    - "AWS"
    - "Azure"
    - "Python"
    - "E-Verify"
  exclude_keywords:
    - "Senior 10+"
    - "Director"
    - "clearance required"
  experience_level: "mid"      # entry / mid / senior
  job_type: "full_time"        # full_time / contract / part_time
  sponsorship_required: true   # filters for visa sponsorship willing employers
  daily_limit: 50

platforms:
  linkedin: true
  indeed: true
  glassdoor: true
  dice: true

browser:
  headless: false        # false = you can see Chrome working
  slow_mo: 500           # ms between actions (politeness delay)
  tab_pause_seconds: 3   # pause before moving to next tab

output:
  resumes_dir: "output/resumes"
  cover_letters_dir: "output/cover_letters"
  logs_dir: "output/logs"
  applications_db: "output/applications.json"
```

---

## 📁 Project Structure

```
job-autopilot/
├── README.md
├── requirements.txt
├── .env.example
├── config/
│   ├── config.yaml          ← Your preferences
│   └── base_resume.pdf      ← Your master resume (you add this)
├── src/
│   ├── main.py              ← Orchestrator / entry point
│   ├── job_searcher.py      ← Finds jobs on job boards
│   ├── resume_builder.py    ← Claude-powered ATS resume tailor
│   ├── cover_letter_gen.py  ← Claude-powered cover letter writer
│   ├── form_filler.py       ← Playwright browser automation
│   └── tracker.py           ← Daily limit + application log
├── prompts/
│   ├── resume_system.txt    ← System prompt for resume rewriting
│   └── cover_letter.txt     ← System prompt for cover letters
├── output/
│   ├── resumes/             ← Tailored resumes saved here
│   ├── cover_letters/       ← Cover letters saved here
│   ├── logs/                ← Run logs
│   └── applications.json    ← Master application tracker
└── scheduler/
    ├── setup_scheduler.bat  ← Windows Task Scheduler setup
    └── setup_scheduler.sh   ← Mac/Linux cron setup
```

---

## 🔒 Privacy & Security

- Your API key lives only in `.env` (gitignored)
- **Never submit** — the tool always leaves forms open for your review
- Resume and cover letter files stay on your local machine
- No data is sent anywhere except Anthropic's API

---

## 📊 Application Tracker

Every run appends to `output/applications.json`:

```json
{
  "date": "2026-04-28",
  "company": "Acme Corp",
  "title": "Cloud Engineer",
  "platform": "LinkedIn",
  "url": "https://linkedin.com/jobs/...",
  "status": "form_filled_awaiting_submit",
  "resume_file": "output/resumes/acme_cloud_engineer_2026-04-28.pdf",
  "cover_letter_file": "output/cover_letters/acme_cloud_engineer_2026-04-28.txt"
}
```

---

## ⚠️ Responsible Use

- **Always review before submitting** — the tool pauses and waits for you
- Respect platform ToS — use slow_mo and daily limits to stay under radar
- Do not use for spam — quality over quantity
- This tool is for your personal job search only

---

## 🤝 Contributing

PRs welcome! See `docs/CONTRIBUTING.md`.

---

## 📄 License

MIT License — free for personal and commercial use.
