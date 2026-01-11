# Deploying with Claude Code

This guide walks through deploying the Bunker CSV Plotter using Claude Code.

## Prerequisites

1. GitHub account (free)
2. Render.com account (free) - sign up at https://render.com

## Step-by-Step Deployment

### 1. Initialize Git Repository

Run these commands in Claude Code:

```bash
cd bunker-plotter-web
git init
git add .
git commit -m "Initial commit: Bunker CSV Plotter"
```

### 2. Create GitHub Repository

Option A - Using GitHub CLI (if installed):
```bash
gh repo create bunker-plotter-web --public --source=. --remote=origin
git push -u origin main
```

Option B - Manual:
1. Go to https://github.com/new
2. Name: `bunker-plotter-web`
3. Make it public
4. Don't initialize with README (we already have one)
5. Click "Create repository"
6. Run these commands:
```bash
git remote add origin https://github.com/YOUR_USERNAME/bunker-plotter-web.git
git branch -M main
git push -u origin main
```

### 3. Deploy to Render.com

1. Go to https://render.com/dashboard
2. Click "New +" → "Web Service"
3. Click "Connect GitHub" (authorize if needed)
4. Find and select your `bunker-plotter-web` repository
5. Configure:
   - **Name**: `bunker-plotter` (or your choice)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: `Free`
6. Click "Create Web Service"
7. Wait 2-3 minutes for deployment

### 4. Access Your Application

Your app will be live at:
```
https://bunker-plotter.onrender.com
```
(Or whatever name you chose)

## Updating the Application

After making changes:

```bash
git add .
git commit -m "Description of changes"
git push
```

Render will automatically redeploy (takes ~2 minutes).

## Updating Configuration

To change plot settings:

```bash
# Edit config.json
nano config.json  # or use any editor

# Commit and push
git add config.json
git commit -m "Update plot configuration"
git push
```

## Testing Locally First

Before deploying, test locally:

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Open http://localhost:5000 in your browser.

## Common Issues

### Issue: Git not configured
```bash
git config --global user.email "you@example.com"
git config --global user.name "Your Name"
```

### Issue: GitHub authentication
Use a Personal Access Token:
1. Go to https://github.com/settings/tokens
2. Generate new token (classic)
3. Select `repo` scope
4. Copy the token
5. Use it as password when pushing

### Issue: Render build fails
- Check the build logs in Render dashboard
- Verify all files are committed: `git status`
- Ensure requirements.txt is correct

### Issue: App crashes on Render
- Check the Render logs for errors
- Verify Procfile exists and is correct
- Ensure config.json is valid JSON

## Alternative: Deploy to Railway.app

Railway.app is even simpler:

1. Go to https://railway.app
2. Sign up with GitHub
3. Click "New Project"
4. Select "Deploy from GitHub repo"
5. Choose `bunker-plotter-web`
6. Railway auto-detects Python and deploys
7. Click on your service → "Settings" → "Generate Domain"

That's it! Railway automatically configures everything.

## File Checklist

Ensure these files are in your repository:
- ✅ app.py
- ✅ config.json
- ✅ requirements.txt
- ✅ Procfile
- ✅ templates/index.html
- ✅ .gitignore
- ✅ README.md

Verify with:
```bash
git ls-files
```

## Next Steps

1. Test with your CSV files
2. Customize config.json for your needs
3. Share the URL with your team
4. Monitor usage in Render/Railway dashboard

## Cost

Both Render.com and Railway.app offer generous free tiers:
- **Render**: 750 hours/month free
- **Railway**: $5 credit/month free

For personal/internal use, free tier is usually sufficient.
