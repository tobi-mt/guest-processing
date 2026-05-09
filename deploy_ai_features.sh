#!/bin/bash

# 🚀 Deploy AI Features to Railway

echo "🎨 Deploying AI Features to Production..."
echo ""

# Check if we're in the right directory
if [ ! -f "web_interface.py" ]; then
    echo "❌ Error: Must run from project root directory"
    exit 1
fi

# Check for uncommitted changes
if ! git diff --quiet; then
    echo "📝 Uncommitted changes detected. Staging all files..."
    git add .
    
    echo "💬 Committing changes..."
    git commit -m "✨ Add AI features frontend integration

- Add AI buttons to guest cards (Email, Questions, Analysis)
- Add AI status indicator in dashboard
- Create modal system for displaying AI results
- Add JavaScript functions for AI API calls
- Add professional CSS styling for AI features
- Implement error handling and loading states
- Add responsive design for mobile compatibility"
    
    echo "✅ Changes committed!"
else
    echo "✅ No uncommitted changes"
fi

echo ""
echo "🚂 Pushing to Railway..."
git push origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 SUCCESS! Deployment initiated."
    echo ""
    echo "📊 Next steps:"
    echo "   1. Wait for Railway to build (check Railway dashboard)"
    echo "   2. Visit: https://guest-processing-production.up.railway.app/dashboard"
    echo "   3. Look for AI Features card showing '✅ AI Enabled'"
    echo "   4. Test AI buttons on any guest card"
    echo ""
    echo "🔗 Quick Links:"
    echo "   Dashboard: https://guest-processing-production.up.railway.app/dashboard"
    echo "   Railway: https://railway.app/dashboard"
    echo ""
    echo "📚 Documentation: AI_FRONTEND_INTEGRATION.md"
else
    echo ""
    echo "❌ Push failed. Check your git configuration and try again."
    exit 1
fi
