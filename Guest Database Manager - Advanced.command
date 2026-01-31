#!/bin/bash

# Guest Database Manager - Advanced Interactive Launcher
# This script provides an interactive menu for CLI, app, and maintenance tasks

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

print_header() {
    echo -e "${BLUE}$1${NC}"
}

print_menu() {
    echo -e "${CYAN}$1${NC}"
}

print_success() {
    echo -e "${GREEN}$1${NC}"
}

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Function to check dependencies
check_dependencies() {
    print_status "Checking dependencies..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed or not in PATH"
        return 1
    fi
    
    # Check Hatch
    if ! command -v hatch &> /dev/null; then
        print_warning "Hatch is not installed. Installing..."
        pip3 install hatch
        if [ $? -ne 0 ]; then
            print_error "Failed to install Hatch"
            return 1
        fi
    fi
    
    print_success "✓ All dependencies are available"
    return 0
}

# Function to find an available port
find_available_port() {
    local start_port=$1
    local max_attempts=50
    local current_port=$start_port
    
    while [ $current_port -lt $((start_port + max_attempts)) ]; do
        if ! lsof -i :$current_port >/dev/null 2>&1; then
            echo $current_port
            return 0
        fi
        current_port=$((current_port + 1))
    done
    
    echo $start_port
}

# Function to launch the web app
launch_web_app() {
    print_header "=========================================="
    print_header "   Launching Web Application             "
    print_header "=========================================="
    echo
    
    if ! check_dependencies; then
        return 1
    fi
    
    # Find available port
    AVAILABLE_PORT=$(find_available_port 8501)
    print_status "Using port: $AVAILABLE_PORT"
    
    # Set up environment
    print_status "Setting up Python environment..."
    if [ ! -d ".hatch/envs/default" ]; then
        print_status "Creating Hatch environment..."
        hatch env create
    fi
    
    print_status "Launching Streamlit application..."
    echo
    print_header "The web interface will open automatically"
    print_header "Press Ctrl+C to stop the application"
    echo
    
    hatch run streamlit run src/guest_database_manager/app.py --server.port=$AVAILABLE_PORT --server.headless=false --browser.gatherUsageStats=false
}

# Function to launch CLI
launch_cli() {
    print_header "=========================================="
    print_header "   Command Line Interface                "
    print_header "=========================================="
    echo
    
    if ! check_dependencies; then
        return 1
    fi
    
    # Set up environment
    if [ ! -d ".hatch/envs/default" ]; then
        print_status "Creating Hatch environment..."
        hatch env create
    fi
    
    print_status "Available CLI commands:"
    echo
    hatch run python -m guest_database_manager.cli --help
    echo
    
    while true; do
        echo
        print_menu "Enter CLI command (or 'back' to return to main menu):"
        read -p "> " cli_command
        
        if [ "$cli_command" = "back" ] || [ "$cli_command" = "exit" ]; then
            break
        fi
        
        if [ -n "$cli_command" ]; then
            echo
            hatch run python -m guest_database_manager.cli $cli_command
        fi
    done
}

# Function to run maintenance tasks
run_maintenance() {
    print_header "=========================================="
    print_header "   Maintenance Tasks                     "
    print_header "=========================================="
    echo
    
    if ! check_dependencies; then
        return 1
    fi
    
    while true; do
        echo
        print_menu "Select a maintenance task:"
        print_menu "1) Update dependencies"
        print_menu "2) Run code formatting (Black)"
        print_menu "3) Run linting (Ruff)"
        print_menu "4) Run tests"
        print_menu "5) Clean up environments"
        print_menu "6) Rebuild environment"
        print_menu "7) Show environment info"
        print_menu "8) Back to main menu"
        echo
        read -p "Enter choice (1-8): " maintenance_choice
        
        case $maintenance_choice in
            1)
                print_status "Updating dependencies..."
                hatch env create --force
                ;;
            2)
                print_status "Running code formatting..."
                hatch run lint:format
                ;;
            3)
                print_status "Running linting..."
                hatch run lint:check
                ;;
            4)
                print_status "Running tests..."
                hatch run test
                ;;
            5)
                print_status "Cleaning up environments..."
                hatch env prune
                ;;
            6)
                print_status "Rebuilding environment..."
                hatch env remove default
                hatch env create
                ;;
            7)
                print_status "Environment information:"
                hatch env show
                ;;
            8|back|exit)
                break
                ;;
            *)
                print_warning "Invalid choice. Please select 1-8."
                ;;
        esac
    done
}

# Function to show project info
show_project_info() {
    print_header "=========================================="
    print_header "   Project Information                   "
    print_header "=========================================="
    echo
    
    print_status "Project Directory: $SCRIPT_DIR"
    print_status "Python Version: $(python3 --version 2>/dev/null || echo 'Not found')"
    print_status "Hatch Version: $(hatch --version 2>/dev/null || echo 'Not found')"
    echo
    
    if [ -f "pyproject.toml" ]; then
        print_status "Project Configuration:"
        echo "Name: $(grep '^name' pyproject.toml | cut -d'"' -f2)"
        echo "Description: $(grep '^description' pyproject.toml | cut -d'"' -f2)"
        echo
    fi
    
    if [ -d ".hatch/envs/default" ]; then
        print_success "✓ Hatch environment is set up"
    else
        print_warning "! Hatch environment needs to be created"
    fi
    
    if [ -f "guest_database_updated.db" ]; then
        print_success "✓ Database file exists"
    else
        print_warning "! Database file will be created on first run"
    fi
    
    echo
    print_status "Press Enter to continue..."
    read
}

# Main menu loop
main_menu() {
    while true; do
        clear
        print_header "=========================================="
        print_header "   Guest Database Manager - Advanced    "
        print_header "=========================================="
        echo
        print_menu "Select an option:"
        print_menu "1) Launch Web Application (Streamlit)"
        print_menu "2) Command Line Interface (CLI)"
        print_menu "3) Maintenance Tasks"
        print_menu "4) Project Information"
        print_menu "5) Exit"
        echo
        read -p "Enter choice (1-5): " choice
        
        case $choice in
            1)
                launch_web_app
                echo
                print_status "Press Enter to continue..."
                read
                ;;
            2)
                launch_cli
                ;;
            3)
                run_maintenance
                ;;
            4)
                show_project_info
                ;;
            5|exit|quit)
                print_success "Thank you for using Guest Database Manager!"
                exit 0
                ;;
            *)
                print_warning "Invalid choice. Please select 1-5."
                sleep 2
                ;;
        esac
    done
}

# Start the main menu
main_menu
