#!/bin/bash
# Launch script for Guest Database Manager Streamlit app
# Version: 2.0 with Email & Skip Features

echo "🎯 Guest Database Manager v2.0 - Email & Skip Features"
echo "📧 Email Integration | ⏭️ Skip Functionality | 📊 Enhanced Analytics"
echo

# Change to the project directory
cd "$(dirname "$0")"

# Set the database path to use the updated database
export GUEST_DB_PATH="guest_database_updated.db"

echo "🚀 Starting dashboard at http://localhost:8501"
echo "💾 Database: $GUEST_DB_PATH"
echo

# Launch the Streamlit app using the CLI
if [ -f ".venv/bin/python" ]; then
    .venv/bin/python -m guest_database_manager.cli app --port 8501
else
    python -m guest_database_manager.cli app --port 8501
fi
