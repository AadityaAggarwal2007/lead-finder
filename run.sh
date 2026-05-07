#!/bin/bash
# LeadHunter Pro — Launch Script

# Load env vars
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Check API key
if [ "$GEMINI_API_KEY" = "YOUR_GEMINI_API_KEY_HERE" ] || [ -z "$GEMINI_API_KEY" ]; then
    echo "❌ Please set your Gemini API key in .env file"
    echo "   Get one free at: https://aistudio.google.com/apikey"
    exit 1
fi

echo "🎯 Starting LeadHunter Pro..."
echo "   Dashboard: http://localhost:8000"
echo ""

python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
