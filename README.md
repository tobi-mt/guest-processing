# Guest Database Manager

A modern, comprehensive web application for managing guest data from CSV/Excel files with database persistence and visualization, built with Streamlit and Hatch.

## 🌟 Features

- **📁 File Upload**: Support for CSV and Excel files with robust encoding detection
- **🗄️ Database Storage**: SQLite database with automatic schema management
- **👥 Guest Management**: Interactive table with search, filtering, and pagination
- **📧 Email Integration**: Send customizable acceptance/rejection emails to guests
- **📊 Analytics**: Beautiful charts and visualizations using Plotly
- **🔄 Status Tracking**: Mark guests as processed/unprocessed with timestamp tracking
- **🧹 Data Cleaning**: Automatic data validation and cleaning
- **🖥️ Modern UI**: Responsive Streamlit interface with Bootstrap styling
- **⚡ CLI Support**: Command-line interface for automation and batch operations

## 📧 Email Functionality

The Guest Database Manager now includes comprehensive email functionality:

### ✅ **Accept Guest Email**
- Send personalized acceptance emails to approved guests
- Customizable message with professional template
- Automatic guest status update to "Accepted"
- Email preview before sending

### ❌ **Reject Guest Email**  
- Send polite rejection emails with optional custom message
- Professional template maintaining positive tone
- Automatic guest status update to "Rejected"
- Email preview before sending

### ⏭️ **Skip Guest (No Email)**
- Mark guest as processed without sending any notification
- Optional reason tracking for internal records
- Guest status updated to "Skipped"
- No email sent to maintain privacy/reduce communication

### ⚙️ **Email Configuration**
- **Supported Providers**: Gmail, Outlook/Hotmail, Yahoo, and custom SMTP
- **Security**: App Password support for enhanced security
- **Templates**: Professional, customizable email templates
- **Tracking**: Email status and timestamp logging

### 🛡️ **Email Security Notes**
- **Gmail**: Use App Passwords instead of regular passwords
- **Outlook**: Supports both regular passwords and App Passwords
- **Yahoo**: Requires App Passwords for security
- **Custom SMTP**: Full support for any SMTP provider

### 📝 **Email Workflow**
1. Configure SMTP settings in the sidebar
2. Click "Accept", "Reject", or "Skip" for any guest
3. **Accept/Reject**: Add optional custom message and preview email
4. **Skip**: Add optional reason for your records (no email sent)
5. Send email (Accept/Reject) or confirm skip, and automatically update guest status

## 🚀 Quick Start

### Easy Launch (Recommended)

**For macOS users:**
- Double-click `Guest Database Manager.command` to launch the application
- For advanced features, double-click `Guest Database Manager - Advanced.command`

**For Windows users:**
- Double-click `Guest Database Manager.bat` to launch the application

**The launchers will:**
- ✅ Automatically check and install dependencies
- ✅ Find an available port (starting from 8501)
- ✅ Set up the Python environment
- ✅ Launch the web interface in your browser

### Manual Installation

```bash
# Install using pip
pip install guest-database-manager

# Or install from source
git clone <repository-url>
cd guest-database-manager
pip install -e .
```

## 🎯 Quick Start (Executable Files)

**For the easiest experience, just double-click one of these files:**

### macOS Users
- **`Guest Database Manager.command`** - Terminal-based launcher
- **`Guest Database Manager.app`** - Native macOS app bundle

### Windows Users  
- **`Guest Database Manager.bat`** - Windows batch file

### All Platforms
- **`launch_app.sh`** - Cross-platform shell script

These executables will:
- ✅ Automatically detect and use your Python environment
- ✅ Install dependencies if needed
- ✅ Launch the dashboard at http://localhost:8501
- ✅ Open your browser automatically
- ✅ Provide colored status messages

## 🖥️ Manual Launch Options

### Run the Web Application

```bash
# Launch Streamlit app (default command)
guest-manager

# Or explicitly run the app
guest-manager app

# Specify custom host and port
guest-manager app --host 0.0.0.0 --port 8502
```

### Command Line Usage

```bash
# Import data from a file
guest-manager import data.csv

# Show database statistics
guest-manager stats

# Clean the database
guest-manager clean
```

## 🏗️ Project Structure

```
guest-database-manager/
├── src/
│   └── guest_database_manager/
│       ├── __init__.py          # Package initialization
│       ├── __about__.py         # Version information
│       ├── app.py               # Streamlit web application
│       ├── database.py          # Main database interface (refactored)
│       ├── constants.py         # Configuration constants and column mappings
│       ├── data_mapper.py       # Data cleaning, validation, and transformation
│       ├── file_reader.py       # CSV and Excel file reading with encoding detection
│       ├── schema_manager.py    # Database schema creation and management
│       ├── email_manager.py     # Email functionality
│       ├── config_manager.py    # Configuration management
│       ├── msforms_importer.py  # Microsoft Forms import support
│       └── cli.py               # Command-line interface
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Test configuration
│   └── test_database.py         # Database tests
├── pyproject.toml               # Hatch configuration
└── README.md                    # This file
```

## 📊 Data Format

The application expects CSV/Excel files with the following columns (case-sensitive):

### Required Columns
- `Name` or `Full name`: Guest name (uses Full name if Name is empty)
- `Email`: Primary email address (if anonymous, uses Email1 instead)

### Optional Columns
- `Start time`: Form submission start time
- `Completion time`: Form submission completion time
- `Email1`: Secondary email (used as primary if Email is anonymous)
- `Do you have a website?`: Website availability question
- `Website`: Personal/professional website
- `Do you have social media handles?`: Social media availability question
- `Kindly list your active social media handles?`: Social media information
- `A brief overview of your personal and professional background`: Background info
- `What is your current profession, and what led you to this career path?`: Profession
- `What motivates or inspires you in your work and life?`: Motivation
- `What life experiences or pivotal moments have shaped who you are today?`: Life experiences
- `What are your core values or guiding principles?`: Core values
- `Do you follow a specific faith, spiritual practice, or philosophical tradition?`: Faith practice
- `Do you believe your beliefs and values align with the themes of soulful conversations?`: Belief alignment
- `Do you have a favourite quote or philosophy that guides your life?`: Favorite quote
- `What topics or themes are you most passionate about discussing?`: Passionate topics
- `What message or takeaway would you like to leave with our listeners?`: Message takeaway
- `Have you been a guest on podcasts or spoken at events before?`: Podcast experience
- `Is there anything else you'd like us to know about you?`: Additional info
- `Are you following us on podcast platforms and social media?`: Following status

## 🛠️ Development

### Prerequisites

- Python 3.12+
- Hatch (for development)

### Setup Development Environment

```bash
# Install Hatch
pip install hatch

# Create development environment
hatch env create

# Install dependencies in development mode
hatch env run pip install -e .

# Run tests
hatch run test

# Run linting
hatch run lint:all

# Format code
hatch run lint:fmt
```

### Running Tests

```bash
# Run all tests
hatch run test

# Run with coverage
hatch run test-cov

# Generate coverage report
hatch run cov-report
```

### Code Quality

```bash
# Run all linting checks
hatch run lint:all

# Format code
hatch run lint:fmt

# Type checking
hatch run lint:typing

# Style checking only
hatch run lint:style
```

## 📁 Database Schema

The SQLite database contains a single `guests` table with the following structure:

```sql
CREATE TABLE guests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    full_name TEXT,
    email TEXT,
    email1 TEXT,
    start_time TEXT,
    completion_time TEXT,
    has_website TEXT,
    website TEXT,
    has_social_media TEXT,
    social_media TEXT,
    background TEXT,
    profession TEXT,
    motivation TEXT,
    life_experiences TEXT,
    core_values TEXT,
    faith_practice TEXT,
    beliefs_align TEXT,
    favorite_quote TEXT,
    passionate_topics TEXT,
    message_takeaway TEXT,
    podcast_experience TEXT,
    additional_info TEXT,
    following_status TEXT,
    is_processed BOOLEAN DEFAULT 0,
    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    date_processed TIMESTAMP,
    original_file_name TEXT,
    UNIQUE(name, email, full_name)
);
```

## 🔧 Configuration

### Environment Variables

- `GUEST_DB_PATH`: Path to the SQLite database file (default: `guest_database.db`)

### Streamlit Configuration

The application can be configured using Streamlit's standard configuration options:

```toml
# .streamlit/config.toml
[server]
port = 8501
address = "localhost"

[theme]
primaryColor = "#FF6B6B"
backgroundColor = "#FFFFFF"
secondaryBackgroundColor = "#F0F2F6"
textColor = "#262730"
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting (`hatch run test && hatch run lint:all`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🔗 Dependencies

- **streamlit**: Web application framework
- **pandas**: Data manipulation and analysis
- **plotly**: Interactive visualizations
- **openpyxl**: Excel file reading
- **xlrd**: Legacy Excel file support

## 🆘 Support

If you encounter any issues or have questions:

1. Check the [Issues](https://github.com/your-username/guest-database-manager/issues) page
2. Create a new issue with detailed information
3. Provide sample data (anonymized) if applicable

## 🛠️ Development Quick Start

```bash
# Clone and set up
git clone <your-repo-url>
cd guest-database-manager

# Install for development
make dev-install
# or manually: pip install -e .[dev]

# Run the app
make run
# or: python -m guest_database_manager.cli app

# Run tests
make test

# Check code quality
make lint

# Format code
make format
```

## 🔄 Changelog

### v0.2.0 (January 2026) - Major Refactoring
- **Database Module Refactored**: Split monolithic 593-line module into 5 modular components
  - `constants.py` - Configuration constants and column mappings
  - `data_mapper.py` - Data cleaning, validation, and transformation
  - `file_reader.py` - CSV and Excel file reading with encoding detection
  - `schema_manager.py` - Database schema creation and management
  - `database.py` - Simplified main interface (283 lines, 52% reduction)
- **Improved Code Quality**: Better separation of concerns and maintainability
- **Backward Compatibility**: All existing code continues to work without changes
- **All Tests Passing**: 7/7 tests passing with updated expectations
- **Comprehensive Documentation**: New documentation for refactored architecture
- **Email Features**: Accept, reject, and skip guest emails with customizable templates
- **Email Configuration**: Support for Gmail, Outlook, Yahoo, and custom SMTP
- **Status Preservation**: Processing status is never overwritten on updates
- **Enhanced Error Handling**: More specific error messages and better logging

### v0.1.0 (Initial Release)
- Complete rewrite using Hatch project structure
- Streamlit-based web interface
- Robust CSV/Excel parsing with encoding detection
- Interactive guest management with search and filtering
- Analytics dashboard with Plotly visualizations
- Command-line interface for automation
- Comprehensive test suite
- Type hints and documentation
