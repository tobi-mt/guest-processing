#!/bin/bash

# Guest Database Manager - macOS Launcher
# This script launches the Guest Database Manager Streamlit application

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_header() {
    echo -e "${BLUE}$1${NC}"
}

print_feature() {
    echo -e "${PURPLE}   ✓${NC} $1"
}

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

clear
print_header "============================================================"
print_header "           🎯 Guest Database Manager v2.0                   "
print_header "       Advanced Guest Management & Email Campaign Tool      "
print_header "============================================================"
echo

print_status "Initializing Guest Database Manager..."
print_status "Project directory: $SCRIPT_DIR"
echo

print_header "📋 Enhanced Features:"
print_feature "Duplicate-proof import system"
print_feature "Smart email column detection (Email, Email2, Guest's Email, etc.)"
print_feature "Advanced guest processing & email campaigns"
print_feature "Real-time statistics & visualizations"
print_feature "CSV/Excel import with robust error handling"
print_feature "Anonymous email fixing & data cleanup tools"
echo

print_status "🔍 Email Import Intelligence:"
print_status "   • Automatically detects: Email, Email2, Guest's Email, Contact Email"
print_status "   • Prevents duplicate guest creation during imports"
print_status "   • Smart email updates (anonymous → real email when available)"
print_status "   • Preserves all processing history and email campaign status"
echo

# Check if Python is available
print_status "Checking system requirements..."
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed or not in PATH"
    print_error "Please install Python 3.8 or later from https://python.org"
    read -p "Press Enter to exit..."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
print_success "Python $PYTHON_VERSION detected"

# Check if we're in a Hatch project
if [ -f "pyproject.toml" ]; then
    print_status "Hatch project detected"
    
    # Check if Hatch is available
    if ! command -v hatch &> /dev/null; then
        print_warning "Hatch is not installed. Installing Hatch..."
        pip3 install hatch
        if [ $? -ne 0 ]; then
            print_error "Failed to install Hatch"
            print_error "Please install Hatch manually: pip3 install hatch"
            read -p "Press Enter to exit..."
            exit 1
        fi
        print_success "Hatch installed successfully"
    fi
    
    HATCH_VERSION=$(hatch --version 2>/dev/null)
    print_success "Hatch $HATCH_VERSION detected"
    USE_HATCH=true
else
    print_status "Using standard Python environment"
    USE_HATCH=false
fi

# Function to find an available port
find_available_port() {
    local start_port=$1
    local max_attempts=20
    local current_port=$start_port
    
    while [ $current_port -lt $((start_port + max_attempts)) ]; do
        if ! lsof -i :$current_port >/dev/null 2>&1; then
            echo $current_port
            return 0
        fi
        current_port=$((current_port + 1))
    done
    
    # If no port found in range, return the start port anyway
    echo $start_port
}

# Find an available port starting from 8501 (Streamlit default)
AVAILABLE_PORT=$(find_available_port 8501)

if lsof -i :$AVAILABLE_PORT >/dev/null 2>&1; then
    print_warning "Port $AVAILABLE_PORT is in use. Streamlit will find another port automatically."
else
    print_status "Target port: $AVAILABLE_PORT"
fi

# Set up the environment
if [ "$USE_HATCH" = true ]; then
    print_status "Setting up Hatch environment..."
    
    if [ ! -d ".hatch" ]; then
        print_status "Creating Hatch environment for the first time..."
        hatch env create
        if [ $? -ne 0 ]; then
            print_error "Failed to create Hatch environment"
            print_error "Please check your pyproject.toml configuration"
            read -p "Press Enter to exit..."
            exit 1
        fi
        print_success "Hatch environment created"
    else
        print_status "Hatch environment exists"
    fi
    
    # Verify dependencies
    print_status "Verifying dependencies..."
    hatch env show
else
    print_status "Checking Python dependencies..."
    
    # Check if required packages are available
    python3 -c "import streamlit, pandas, plotly" 2>/dev/null
    if [ $? -ne 0 ]; then
        print_warning "Some required packages may be missing"
        print_status "Installing required packages..."
        pip3 install streamlit pandas plotly openpyxl
    fi
fi

# Check if the main app file exists
APP_FILE=""
if [ -f "src/guest_database_manager/app.py" ]; then
    APP_FILE="src/guest_database_manager/app.py"
    print_success "Found Streamlit app: $APP_FILE"
elif [ -f "app.py" ]; then
    APP_FILE="app.py"
    print_success "Found Streamlit app: $APP_FILE"
else
    print_error "Could not find app.py file"
    print_error "Expected locations:"
    print_error "  - src/guest_database_manager/app.py"
    print_error "  - app.py"
    read -p "Press Enter to exit..."
    exit 1
fi

# Check database status
print_status "Checking database status..."
if [ -f "guest_database.db" ]; then
    DB_SIZE=$(ls -lh guest_database.db | awk '{print $5}')
    print_success "Database found (${DB_SIZE})"
    
    # Quick database check
    if [ "$USE_HATCH" = true ]; then
        GUEST_COUNT=$(hatch run python -c "
from src.guest_database_manager.database import GuestDatabase
try:
    db = GuestDatabase()
    guests = db.get_all_guests()
    print(len(guests))
except Exception as e:
    print('Error')
" 2>/dev/null)
    else
        GUEST_COUNT=$(python3 -c "
from src.guest_database_manager.database import GuestDatabase
try:
    db = GuestDatabase()
    guests = db.get_all_guests()
    print(len(guests))
except Exception as e:
    print('Error')
" 2>/dev/null)
    fi
    
    if [ "$GUEST_COUNT" != "Error" ] && [ ! -z "$GUEST_COUNT" ]; then
        print_success "Database contains $GUEST_COUNT guests"
    fi
else
    print_status "Database will be created on first run"
fi

echo
print_header "🚀 Launching Guest Database Manager..."
echo
print_header "============================================================"
print_header "                   Starting Streamlit App                   "
print_header "============================================================"
print_header "📱 The web interface will open automatically in your browser"
print_header "🌐 Manual access: http://localhost:$AVAILABLE_PORT"
print_header "⚡ Features: Guest Management | Email Campaigns | Analytics"
print_header "🛑 Press Ctrl+C to stop the application"
print_header "============================================================"
echo

# Launch the Streamlit app
if [ "$USE_HATCH" = true ]; then
    print_status "Launching via Hatch environment..."
    hatch run streamlit run "$APP_FILE" --server.port $AVAILABLE_PORT --server.headless false --browser.gatherUsageStats false
else
    print_status "Launching via system Python..."
    "/Users/tobi/PycharmProjects/pythonProject/MT Guest Processing/.hatch/default/bin/python" -m streamlit run "$APP_FILE" --server.port $AVAILABLE_PORT --server.headless false --browser.gatherUsageStats false
fi

# Check exit status
EXIT_CODE=$?

echo
if [ $EXIT_CODE -eq 0 ]; then
    print_success "Guest Database Manager stopped gracefully"
else
    print_warning "Guest Database Manager stopped with exit code: $EXIT_CODE"
fi

print_header "============================================================"
print_status "Thank you for using Guest Database Manager! 🎯"
print_status "Your guest data and email campaigns are safely stored."
print_header "============================================================"
echo

# Keep the terminal open on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    read -p "Press Enter to close this window..."
fi
