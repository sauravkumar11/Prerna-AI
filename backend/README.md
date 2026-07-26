# Prerna AI Desktop Assistant

A production-quality Windows AI desktop assistant with natural voice, Gemini intelligence, and desktop automation for 20+ tools.

## Quick Start

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Backend runs on `http://localhost:8000`.

### Frontend
```bash
cd frontend/react
npm install
npm start       # Electron desktop app
# or
npm run dev     # Browser only at localhost:5173
```

### Environment
Create `backend/.env`:
```
GEMINI_API_KEY=your_key_here
ELEVENLABS_API_KEY=your_key_here   # optional
GEMINI_MODEL=gemini-2.5-flash       # optional override
```

## Usage

Say **"Hey Prerna"** to wake her, then speak your command.

Examples:
- `"Hey Prerna, open YouTube"`
- `"Hey Prerna, search Google for best pizza near me"`
- `"Hey Prerna, take a screenshot"`
- `"Hey Prerna, open camera and click pictures"`
- `"Hey Prerna, set alarm for 7:00"`
- `"Hey Prerna, Papa ko WhatsApp karo"`

## Requirements
- Windows 10/11
- Python 3.10+
- Node.js 18+
- Gemini API key (free at aistudio.google.com)
