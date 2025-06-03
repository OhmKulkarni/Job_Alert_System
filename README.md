# 🚀 Job Alert System

An intelligent, automated job search and notification system that finds relevant job opportunities and delivers personalized email digests with AI-powered summaries and relevance scoring.

## 📋 Table of Contents

- [Features](#-features)
- [System Architecture](#-system-architecture)
- [Prerequisites](#-prerequisites)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Project Structure](#-project-structure)
- [How It Works](#-how-it-works)
- [Customization](#-customization)
- [Troubleshooting](#-troubleshooting)
- [Technologies Used](#-technologies-used)
- [Contributing](#-contributing)

## ✨ Features

- **🔍 Intelligent Job Search**: Uses Serper.dev API to search for jobs across multiple keywords and locations
- **🧠 AI-Powered Summarization**: Integrates with Mistral LLM to create structured job summaries
- **📊 Relevance Scoring**: Advanced algorithm scores job relevance based on keyword matching
- **🚫 Duplicate Detection**: Smart deduplication prevents duplicate job listings
- **📧 Beautiful Email Alerts**: Modern, responsive HTML email templates with color-coded relevance scores
- **⚙️ Flexible Configuration**: YAML-based configuration for easy customization
- **📝 Comprehensive Logging**: Detailed logging for monitoring and debugging

## 🏗️ System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Job Search    │    │   AI Summary     │    │  Email Digest   │
│  (Serper API)   │───▶│  (Mistral LLM)   │───▶│   (SMTP/HTML)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Relevance Scorer│    │  Deduplication   │    │  Configuration  │
│   & Filtering   │    │    Manager       │    │   Management    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🔧 Prerequisites

Before running the Job Alert System, ensure you have the following:

### Software Requirements
- **Python 3.8+**
- **Ollama** (for running Mistral LLM locally)
- **Gmail Account** (or other SMTP-compatible email service)

### API Keys & Services
- **Serper.dev API Key** - [Get it here](https://serper.dev/)
- **Email App Password** - [Gmail Setup Guide](https://support.google.com/accounts/answer/185833)

## 📦 Installation

### 1. Clone the Repository
```bash
git clone https://github.com/OhmKulkarni/Job_Alert_System
cd Job_Alert_System
```

### 2. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 3. Install and Setup Ollama
```bash
# Install Ollama (macOS)
curl -fsSL https://ollama.ai/install.sh | sh

# Or visit https://ollama.ai for other platforms

# Pull Mistral model
ollama pull mistral:7b

# Start Ollama service
ollama serve
```

### 4. Verify Ollama Installation
```bash
# Test if Mistral is working
curl http://localhost:11434/api/generate -d '{
  "model": "mistral:7b",
  "prompt": "Hello world",
  "stream": false
}'
```

## ⚙️ Configuration

### 1. Environment Variables (.env)

Create a `.env` file in the project root:

```env
# LLM Configuration
MODEL=mistral:7b

# Serper API Configuration
SERPER_API_KEY=your_serper_api_key_here

# Email Configuration
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USER=your_email@gmail.com
EMAIL_PASS=your_app_password_here
EMAIL_TO=recipient@gmail.com
```

### 2. Job Search Configuration (config/job_alert.yaml)

```yaml
name: Job Alert for User
keywords:
  - "Entry Level Jobs"
  - "Freelance Jobs" 
  - "Python developer"
  - "Remote AI jobs"
locations:
  - "Remote"
  - "Irvine"
recipient_email: your_email@gmail.com
frequency: daily
max_results: 10
last_sent: null
```

### 3. AI Prompts Configuration (config/prompts.yaml)

The system includes pre-configured prompts for the AI summarization. You can customize these in `config/prompts.yaml`.

### 4. Getting API Keys

#### Serper.dev API Key:
1. Visit [serper.dev](https://serper.dev/)
2. Sign up for a free account
3. Navigate to your dashboard
4. Copy your API key
5. Add it to your `.env` file

#### Gmail App Password:
1. Enable 2-Factor Authentication on your Gmail account
2. Go to [Google Account settings](https://myaccount.google.com/)
3. Navigate to Security → 2-Step Verification → App Passwords
4. Generate a new app password for "Mail"
5. Use this password in your `.env` file (not your regular Gmail password)

## 🚀 Usage

### Basic Usage

1. **Start Ollama** (if not already running):
   ```bash
   ollama serve
   ```

2. **Run the Job Alert System**:
   ```bash
   python main.py
   ```

### What Happens:

1. **🔍 Job Search**: System searches for jobs using your configured keywords and locations
2. **📊 Scoring**: Each job gets a relevance score (0-100%) based on keyword matching
3. **🚫 Deduplication**: Duplicate jobs are filtered out using advanced hashing
4. **🧠 AI Summary**: Mistral LLM creates structured summaries of job listings
5. **📧 Email Delivery**: You receive a beautiful HTML email digest with:
   - Color-coded relevance scores
   - Job details and descriptions
   - Direct application links
   - Search statistics

### Sample Output

The system will output logs like:
```
[2024-12-19 10:30:15] INFO - Starting Job Alert System
[2024-12-19 10:30:16] INFO - Loading configuration files...
[2024-12-19 10:30:17] INFO - Job search completed. Found 8 job listings
[2024-12-19 10:30:25] INFO - LLM summarization completed
[2024-12-19 10:30:26] INFO - ✅ Email sent to your_email@gmail.com
```

## 📁 Project Structure

```
job-alert-system/
├── main.py                     # Main application entry point
├── requirements.txt            # Python dependencies
├── .env                       # Environment variables (create this)
├── README.md                  # This file
│
├── config/
│   ├── job_alert.yaml         # Job search configuration
│   └── prompts.yaml           # AI prompt templates
│
├── tools/
│   ├── serper_job_search_tool.py      # Job search functionality
│   ├── llm_sumarizer_tool.py          # AI summarization
│   ├── html_email_formatter.py        # Email template engine
│   ├── email_sender_tool.py           # Email delivery
│   ├── job_relevance_scorer.py        # Relevance scoring algorithm
│   └── job_deduplication.py           # Duplicate detection
│
└── utils/
    └── logger.py              # Logging configuration
```

## 🔄 How It Works

### 1. Job Search Process
- Uses Serper.dev API to search Google for job listings
- Searches across multiple keyword-location combinations
- Extracts job title, company, location, description, and URL

### 2. Relevance Scoring Algorithm
```python
# Scoring weights:
- Job Title Match: 3.0x weight
- Company Match: 1.5x weight  
- Description Match: 1.0x weight
- Location Match: 0.5x weight

# Score calculation:
- Exact keyword match: 2.0x bonus
- Partial keyword match: Proportional scoring
- Final score: Normalized to 0-100%
```

### 3. Deduplication Strategy
- Creates MD5 hash from normalized title + company + location
- Filters out exact duplicates
- Maintains seen job registry during search session

### 4. AI Summarization
- Sends job data to local Mistral LLM
- Structures response as JSON with job details
- Fallback to simple formatting if AI parsing fails

### 5. Email Generation
- Creates responsive HTML email template
- Color-codes jobs by relevance score:
  - 🟢 Green (75%+): High relevance
  - 🟠 Orange (50-74%): Medium relevance  
  - 🔴 Red (25-49%): Low relevance
  - ⚪ Gray (<25%): Very low relevance

## 🎨 Customization

### Adding New Keywords/Locations
Edit `config/job_alert.yaml`:
```yaml
keywords:
  - "Data Scientist"
  - "Machine Learning Engineer"
  - "Your Custom Keywords"
locations:
  - "San Francisco"
  - "New York"
  - "Your Preferred Locations"
```

### Customizing Email Templates
Modify `tools/html_email_formatter.py` to change:
- Email styling and colors
- Layout and structure
- Additional job information display

### Adjusting Relevance Scoring
Edit `tools/job_relevance_scorer.py` to modify:
- Keyword matching algorithms
- Field importance weights
- Scoring thresholds

### Changing AI Prompts
Update `config/prompts.yaml` to customize:
- AI summarization style
- Output format requirements
- Additional instructions for the LLM

## 🐛 Troubleshooting

### Common Issues

#### 1. "SERPER_API_KEY not found"
- Verify your `.env` file exists and contains the correct API key
- Check that the `.env` file is in the project root directory

#### 2. "Error communicating with Mistral API"
- Ensure Ollama is running: `ollama serve`
- Verify Mistral model is installed: `ollama list`
- Check if port 11434 is available

#### 3. "Failed to send email"
- Verify Gmail app password (not regular password)
- Check if 2FA is enabled on your Gmail account
- Ensure SMTP settings are correct

#### 4. "Configuration file not found"
- Verify `config/job_alert.yaml` and `config/prompts.yaml` exist
- Check file paths and permissions

### Debug Mode
Add more verbose logging by modifying `utils/logger.py`:
```python
logging.basicConfig(level=logging.DEBUG)
```

## 🛠️ Technologies Used

- **Python 3.8+** - Core programming language
- **CrewAI Tools** - Framework for building AI tools
- **Serper.dev API** - Google search API for job listings
- **Ollama + Mistral 7B** - Local LLM for AI summarization
- **SMTP/Email** - Email delivery system
- **YAML** - Configuration management
- **HTML/CSS** - Email template styling
- **Logging** - System monitoring and debugging

## 🤝 Contributing

This is a college project, but suggestions for improvements are welcome:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/improvement`)
3. Commit your changes (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature/improvement`)
5. Create a Pull Request

## 📄 License

This project is created for educational purposes as part of a college assignment.

## 🙏 Acknowledgments

- **Serper.dev** for providing job search API
- **Ollama Team** for local LLM infrastructure
- **Mistral AI** for the language model
- **CrewAI** for the tool framework

---

**Built with claude.ai for automated job hunting and learning AI integration**