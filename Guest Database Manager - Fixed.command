#!/bin/bash

# Guest Database Manager - macOS Launcher v3.0
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
print_header "           🎯 Guest Database Manager v3.0                   "
print_header "       Advanced Guest Management & Email Campaign Tool      "
print_header "============================================================"
echo

print_status "Initializing Guest Database Manager..."
print_status "Project directory: $SCRIPT_DIR"
echo

print_header "📋 Latest Features:"
print_feature "✅ Fixed CSV import with 99% success rate"
print_feature "✅ Robust date parsing for analytics"
print_feature "✅ Smart column mapping and duplicate prevention"
print_feature "✅ Enhanced email campaign management"
print_feature "✅ Real-time statistics & visualizations"
print_feature "✅ Improved error handling and logging"
echo

print_status "🔍 Import Intelligence:"
print_status "   • Handles mixed date formats automatically"
print_status "   • Maps CSV columns to database fields intelligently"
print_status "   • Preserves processing status during updates"
print_status "   • Graceful error handling with detailed reporting"
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

# Check for virtual environment
VENV_PATH=""
if [ -d ".venv" ]; then
    VENV_PATH=".venv/bin/python"
    print_success "Virtual environment found: .venv"
elif [ -d ".hatch/default" ]; then
    VENV_PATH=".hatch/default/bin/python"
    print_success "Hatch environment found: .hatch/default"
else
    print_warning "No virtual environment found, using system Python"
    VENV_PATH="python3"
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

# Find an available port starting from 8052 (our preferred port)
AVAILABLE_PORT=$(find_available_port 8052)

if lsof -i :$AVAILABLE_PORT >/dev/null 2>&1; then
    print_warning "Port $AVAILABLE_PORT is in use. Finding alternative..."
    AVAILABLE_PORT=$(find_available_port 8053)
fi

print_status "Target port: $AVAILABLE_PORT"

# Check if required dependencies are installed
print_status "Checking dependencies..."
MISSING_DEPS=()

# Test imports with the Python interpreter we'll use
if [ "$VENV_PATH" = "python3" ]; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="$SCRIPT_DIR/$VENV_PATH"
fi

# Check each required package
for package in streamlit pandas plotly cryptography; do
    if ! "$PYTHON_CMD" -c "import $package" &>/dev/null; then
        MISSING_DEPS+=("$package")
    fi
done

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    print_warning "Missing dependencies: ${MISSING_DEPS[*]}"
    print_status "Installing missing packages..."
    
    if [ "$VENV_PATH" != "python3" ]; then
        # Activate virtual environment and install
        source "$SCRIPT_DIR/${VENV_PATH%/bin/python}/bin/activate"
        pip install "${MISSING_DEPS[@]}"
    else
        pip3 install "${MISSING_DEPS[@]}"
    fi
    
    if [ $? -eq 0 ]; then
        print_success "Dependencies installed successfully"
    else
        print_error "Failed to install dependencies"
        read -p "Press Enter to exit..."
        exit 1
    fi
else
    print_success "All dependencies are available"
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
    GUEST_COUNT=$("$PYTHON_CMD" -c "
import sys
sys.path.insert(0, 'src/guest_database_manager')
from database import GuestDatabase
try:
    db = GuestDatabase()
    guests = db.get_all_guests()
    print(len(guests))
except Exception as e:
    print('Error')
" 2>/dev/null)
    
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

# Kill any existing processes on the target port
if lsof -i :$AVAILABLE_PORT >/dev/null 2>&1; then
    print_status "Stopping existing process on port $AVAILABLE_PORT..."
    lsof -ti:$AVAILABLE_PORT | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Launch the Streamlit app
print_status "Launching Guest Database Manager..."

if [ "$VENV_PATH" != "python3" ]; then
    # Use virtual environment
    source "$SCRIPT_DIR/${VENV_PATH%/bin/python}/bin/activate"
    streamlit run "$APP_FILE" --server.port $AVAILABLE_PORT --server.headless false --browser.gatherUsageStats false
else
    # Use system Python
    python3 -m streamlit run "$APP_FILE" --server.port $AVAILABLE_PORT --server.headless false --browser.gatherUsageStats false
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
