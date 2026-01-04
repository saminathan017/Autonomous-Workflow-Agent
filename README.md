# 🤖 Autonomous Workflow Agent: Email → Sheets → AI Report

A production-ready autonomous workflow system that integrates Gmail API, Google Sheets API, and OpenAI to create an intelligent email processing pipeline.

## 🎯 Features

- **Email Processing**: Automatically fetches emails from Gmail using read-only API access
- **Data Extraction**: Parses and structures email information (subject, sender, body, date)
- **Google Sheets Integration**: Writes data to Google Sheets with idempotent operations
- **AI-Powered Reports**: Generates intelligent summaries and insights using OpenAI
- **Workflow State Management**: Tracks execution history in SQLite database
- **RESTful API**: FastAPI backend with comprehensive endpoints
- **Modern Frontend**: Clean, responsive UI for workflow management
- **Cost Controls**: Built-in rate limiting and token caps for OpenAI API

## 🏗️ Architecture

```
autonomous_workflow_agent/
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── config.py               # Configuration management
│   ├── api/
│   │   └── routes.py           # API endpoints
│   ├── auth/
│   │   └── google_oauth.py     # Google OAuth 2.0 flow
│   ├── ai/
│   │   └── openai_client.py    # OpenAI client wrapper
│   ├── workflows/
│   │   ├── engine.py           # Workflow orchestrator
│   │   ├── state_store.py      # SQLite persistence
│   │   ├── models.py           # Pydantic data models
│   │   └── tasks/
│   │       ├── gmail_reader.py # Gmail API integration
│   │       ├── sheets_writer.py# Sheets API integration
│   │       └── report_builder.py# AI report generation
│   ├── frontend/
│   │   ├── index.html          # UI
│   │   ├── app.js              # Frontend logic
│   │   └── styles.css          # Styling
│   └── utils/
│       └── logging.py          # Logging utilities
├── scripts/
│   ├── init_db.py              # Database initialization
│   └── run_once.py             # Manual workflow trigger
├── data/
│   ├── state.db                # SQLite database
│   └── reports/                # Generated reports
├── requirements.txt
├── .env.example
└── README.md
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Google Cloud Project with Gmail API and Sheets API enabled
- OpenAI API key
- Google OAuth credentials (`credentials.json`)

### Installation

1. **Clone the repository**
   ```bash
   cd autonomous_workflow_agent
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and configuration
   ```

5. **Set up Google OAuth**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing
   - Enable Gmail API and Google Sheets API
   - Create OAuth 2.0 credentials (Desktop app)
   - Download `credentials.json` to project root
   - Create a Google Sheet and copy its ID to `.env`

6. **Initialize database**
   ```bash
   python scripts/init_db.py
   ```

### Running the Application

**Start the server:**
```bash
cd autonomous_workflow_agent
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Access the application:**
- Frontend: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/api/health

**Manual workflow execution:**
```bash
python scripts/run_once.py
```

## 📋 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | *Required* |
| `OPENAI_MODEL` | OpenAI model to use | `gpt-4o-mini` |
| `OPENAI_MAX_TOKENS` | Max tokens per request | `800` |
| `OPENAI_TIMEOUT_SECONDS` | Request timeout | `20` |
| `OPENAI_MAX_CALLS_PER_RUN` | Max API calls per workflow | `5` |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | *Required* |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | *Required* |
| `GOOGLE_SHEET_ID` | Target Google Sheet ID | *Required* |
| `APP_HOST` | Application host | `0.0.0.0` |
| `APP_PORT` | Application port | `8000` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DATABASE_PATH` | SQLite database path | `data/state.db` |
| `WORKFLOW_MAX_RETRIES` | Max retries per step | `3` |
| `WORKFLOW_RETRY_DELAY_SECONDS` | Retry delay | `5` |

### Cost Safety

The system includes built-in cost controls:
- **Rate Limiting**: Maximum 5 OpenAI API calls per workflow run
- **Token Caps**: Maximum 800 tokens per request
- **Timeout Enforcement**: 20-second timeout per request
- **Graceful Fallbacks**: Continues workflow even if AI calls fail

## 🔌 API Endpoints

### Workflow Management

- `POST /api/run` - Trigger workflow execution
  ```json
  {
    "max_emails": 10,
    "generate_report": true
  }
  ```

- `GET /api/runs` - List workflow runs
  - Query params: `limit` (default: 50), `status` (optional)

- `GET /api/runs/{run_id}` - Get specific run details

- `GET /api/health` - Health check

- `POST /api/schedule` - Schedule recurring workflows (planned)

## 🔄 Workflow Steps

1. **Fetch Emails**: Retrieves emails from Gmail using read-only API
2. **Write to Sheets**: Writes structured data to Google Sheets (idempotent)
3. **Generate Report**: Creates AI-powered summary and insights
4. **Save Artifacts**: Persists report to disk and updates database

Each step includes:
- Automatic retry logic (3 attempts with 5-second delay)
- Error handling and logging
- Status tracking in database

## 🎨 Frontend Features

- **Workflow Trigger**: Configure and run workflows
- **Run History**: View past executions with status
- **Run Details**: Inspect step-by-step execution logs
- **Responsive Design**: Works on desktop and mobile
- **Dark Mode**: Modern, eye-friendly interface

## 🧪 Testing

### Manual Testing

1. **Database initialization:**
   ```bash
   python scripts/init_db.py
   sqlite3 data/state.db ".schema"
   ```

2. **Server startup:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   curl http://localhost:8000/api/health
   ```

3. **OAuth flow:**
   - Visit http://localhost:8000
   - Complete Google OAuth
   - Verify `token.json` is created

4. **End-to-end workflow:**
   ```bash
   python scripts/run_once.py
   ```

## 🔒 Security Best Practices

- **No Hardcoded Secrets**: All credentials via environment variables
- **Read-Only Gmail Access**: Minimal required permissions
- **Token Persistence**: Secure OAuth token storage
- **API Rate Limiting**: Prevents cost overruns
- **Error Logging**: Comprehensive audit trail

## 📊 Database Schema

### `workflow_runs` Table
- `run_id` (TEXT, PRIMARY KEY)
- `status` (TEXT)
- `started_at` (TEXT)
- `completed_at` (TEXT)
- `error_message` (TEXT)
- `emails_processed` (INTEGER)
- `report_path` (TEXT)

### `step_logs` Table
- `id` (INTEGER, PRIMARY KEY)
- `run_id` (TEXT, FOREIGN KEY)
- `step_name` (TEXT)
- `status` (TEXT)
- `started_at` (TEXT)
- `completed_at` (TEXT)
- `error_message` (TEXT)
- `retry_count` (INTEGER)
- `metadata` (TEXT)

## 🎓 Resume Bullets

- Architected and deployed a production-ready autonomous workflow system integrating Gmail API, Google Sheets API, and OpenAI for intelligent email processing
- Implemented cost-aware AI integration with rate limiting (5 calls/run), token caps (800 max), and graceful fallbacks to prevent API cost overruns
- Built RESTful FastAPI backend with SQLite persistence, OAuth 2.0 authentication, and comprehensive error handling with automatic retry logic
- Designed idempotent data pipeline ensuring duplicate-free Google Sheets updates and maintaining complete workflow execution history
- Created responsive frontend with real-time workflow monitoring, execution history, and detailed step-level logging

## 🛠️ Tech Stack

- **Backend**: Python 3.11, FastAPI, Pydantic, SQLite
- **AI**: OpenAI API (GPT-4o-mini)
- **Google APIs**: Gmail API (read-only), Sheets API (write)
- **Auth**: Google OAuth 2.0
- **Frontend**: HTML, CSS, Vanilla JavaScript
- **Utilities**: APScheduler, python-dotenv, aiofiles

## 📝 License

This project is for demonstration and educational purposes.

## Author

Saminathan

## 🤝 Contributing

This is a portfolio project. Feel free to fork and adapt for your own use.

## 📧 Contact

For questions or feedback, please open an issue.

---

**Built with ❤️ as a demonstration of production-ready agentic AI systems**
