# 🚀 Bunker CSV Plotter - Quick Start

## What I Built For You

A complete web application that:
- ✅ Accepts CSV file uploads via drag-and-drop or file picker
- ✅ Generates interactive Plotly plots (zoom, pan, hover)
- ✅ Uses your existing config.json format
- ✅ Supports dual y-axes like your matplotlib version
- ✅ Ready to deploy to Render.com or Railway.app
- ✅ 100% compatible with Claude Code

## What's Different from Your Original

| Feature | Old (matplotlib) | New (Plotly Web App) |
|---------|-----------------|---------------------|
| Interface | Command line | Web browser |
| Plots | Static images | Interactive (zoom, hover) |
| Sharing | Send image files | Share URL |
| Updates | Run script again | Upload new CSV |
| Access | Local computer only | Accessible from anywhere |

## File Structure

```
bunker-plotter-web/
├── app.py                      # Flask backend (converted from your script)
├── config.json                 # Your existing config (copied)
├── templates/index.html        # Beautiful upload interface
├── requirements.txt            # Python dependencies
├── Procfile                    # Deployment config
├── README.md                   # Full documentation
├── CLAUDE_CODE_DEPLOYMENT.md   # Step-by-step deployment
└── test_config.py             # Validation script
```

## Deploying with Claude Code

### Option 1: Render.com (Recommended)

1. **Setup Git:**
```bash
cd bunker-plotter-web
git init
git add .
git commit -m "Initial commit"
```

2. **Push to GitHub:**
```bash
# Create repo on GitHub first, then:
git remote add origin https://github.com/YOUR_USERNAME/bunker-plotter-web.git
git branch -M main
git push -u origin main
```

3. **Deploy on Render:**
   - Go to https://render.com
   - New + → Web Service
   - Connect your GitHub repo
   - Name: `bunker-plotter`
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app`
   - Click "Create Web Service"

4. **Done!** Your app will be at `https://bunker-plotter.onrender.com`

### Option 2: Railway.app (Even Easier)

1. Push to GitHub (same as above)
2. Go to https://railway.app
3. New Project → Deploy from GitHub
4. Select your repo
5. Done! Railway auto-configures everything

## Testing Locally

If you want to test before deploying:

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## How It Works

1. **User uploads CSV** → Your bunker.csv format with Date/Time columns
2. **Backend processes** → Same logic as your original script:
   - Parses Date/Time into datetime index
   - Calculates duty_gun and duty_kly
   - Handles column inversion (- prefix)
3. **Plotly renders** → Interactive plots with:
   - Multiple subplots (stacked)
   - Dual y-axes (left/right)
   - Zoom, pan, hover
   - Export to PNG

## Updating Configuration

To change plots after deployment:

```bash
# Edit config.json
nano config.json

# Push changes
git add config.json
git commit -m "Update plot configuration"
git push
```

Render/Railway will auto-redeploy in ~2 minutes.

## Key Features Preserved

✅ **Dual y-axes** - Left/right columns work exactly like before
✅ **Column inversion** - Prefix with `-` to invert (e.g., `-BeamCT ma`)
✅ **Auto calculations** - duty_gun and duty_kly computed automatically
✅ **Encoding handling** - Latin-1 encoding for special characters (æ, etc.)
✅ **Date/Time parsing** - Same MM/DD/YYYY HH:MM:SS AM/PM format

## New Features Added

🎉 **Interactive plots** - Click and drag to zoom, hover for values
🎉 **Web interface** - Access from any device with a browser
🎉 **Shareable** - Send URL to colleagues
🎉 **No installation** - Users don't need Python or any software
🎉 **Beautiful UI** - Modern, gradient design with drag-and-drop

## Cost

**Free!** Both Render and Railway have generous free tiers:
- Render: 750 hours/month
- Railway: $5 credit/month

For personal/internal use, you'll stay within free limits.

## Security

- ✅ 16MB file size limit
- ✅ CSV files only
- ✅ Files deleted immediately after processing
- ✅ No data storage
- ✅ HTTPS enabled automatically

## Next Steps

1. **Deploy** using CLAUDE_CODE_DEPLOYMENT.md
2. **Test** with your bunker.csv file
3. **Customize** config.json if needed
4. **Share** the URL with your team

## Need Help?

- See `README.md` for full documentation
- See `CLAUDE_CODE_DEPLOYMENT.md` for detailed deployment steps
- Run `python test_config.py` to validate your setup

## What Changed in Code

Your original `plot_bunker.py` was converted to:

1. **app.py** - Flask web server with same plotting logic
2. **matplotlib → Plotly** - Interactive plots instead of static
3. **CLI → Web** - Upload interface instead of command line
4. **Subplots** - Same stacked layout, but with zoom/pan

All your plotting logic (dual axes, inversion, calculations) is preserved!

---

**Ready to deploy?** Open `CLAUDE_CODE_DEPLOYMENT.md` and follow the steps!
