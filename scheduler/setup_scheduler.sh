#!/bin/bash
# ============================================================
#  Job AutoPilot — Mac/Linux Cron Setup
#  Runs the job search automation every night at 11:00 PM
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_CMD=$(which python3 || which python)

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ Python not found. Install Python 3.10+ first."
    exit 1
fi

echo "📍 Project directory: $SCRIPT_DIR"
echo "🐍 Python: $PYTHON_CMD"
echo ""

# Create the cron entry (runs at 11 PM every day)
CRON_ENTRY="0 23 * * * cd $SCRIPT_DIR && $PYTHON_CMD src/main.py >> output/logs/cron.log 2>&1"

# Check if already exists
EXISTING=$(crontab -l 2>/dev/null | grep "job-autopilot\|JobAutoPilot\|src/main.py")

if [ -n "$EXISTING" ]; then
    echo "⚠️  Existing Job AutoPilot cron entry found:"
    echo "   $EXISTING"
    echo ""
    read -p "Replace it? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi
    # Remove existing entry
    crontab -l 2>/dev/null | grep -v "src/main.py" | crontab -
fi

# Add new cron entry
(crontab -l 2>/dev/null; echo "# Job AutoPilot — overnight job search"; echo "$CRON_ENTRY") | crontab -

echo "✅ Cron job created!"
echo ""
echo "Schedule: Every night at 11:00 PM"
echo "Log file: $SCRIPT_DIR/output/logs/cron.log"
echo ""
echo "To view your cron jobs:  crontab -l"
echo "To remove:               crontab -l | grep -v 'src/main.py' | crontab -"
echo "To run now:              cd $SCRIPT_DIR && $PYTHON_CMD src/main.py"
echo ""

# macOS: Grant terminal automation permissions reminder
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "📌 macOS Note:"
    echo "   Go to System Settings → Privacy & Security → Automation"
    echo "   and allow Terminal to control Chrome."
fi
