# Guest Database Manager Launchers

This directory contains several launcher scripts to make it easy to run the Guest Database Manager application.

## Launcher Files

### macOS Users
- **`Guest Database Manager.command`** - Simple launcher that starts the web application
  - Double-click to run
  - Automatically finds an available port
  - Sets up the Python environment if needed
  - Opens the web interface in your browser

- **`Guest Database Manager - Advanced.command`** - Interactive menu launcher
  - Double-click to run  
  - Provides options for web app, CLI, maintenance tasks, and project info
  - Useful for development and troubleshooting

### Windows Users
- **`Guest Database Manager.bat`** - Simple launcher for Windows
  - Double-click to run
  - Same functionality as the macOS .command file
  - Automatically finds an available port and sets up environment

## First-Time Setup

1. Ensure Python 3.8+ is installed on your system
2. The launchers will automatically install Hatch if it's not present
3. The first run will create the Python environment and install dependencies
4. Subsequent runs will be much faster

## Usage Tips

- **For regular use**: Use the simple launchers (`Guest Database Manager.command` or `.bat`)
- **For development**: Use the Advanced launcher for access to CLI tools and maintenance tasks
- **Port conflicts**: The launchers automatically find available ports starting from 8501
- **Email setup**: Configure your email settings in the web interface sidebar

## Troubleshooting

If you encounter issues:

1. Use the Advanced launcher and select "Project Information" to check system status
2. Try the maintenance tasks in the Advanced launcher:
   - Update dependencies
   - Rebuild environment
   - Run code formatting/linting

## Manual Running

You can also run the application manually from the terminal:

```bash
# Navigate to the project directory
cd "/path/to/MT Guest Processing"

# Run with Hatch
hatch run streamlit run src/guest_database_manager/app.py

# Or run CLI
hatch run python -m guest_database_manager.cli --help
```

## Security Note

The application uses encrypted storage for email credentials. Your email passwords are never stored in plain text.
