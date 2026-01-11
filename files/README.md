# Bunker CSV Plotter - Web Application

Interactive web-based CSV plotter using Flask and Plotly. Upload CSV files and get interactive, zoomable plots based on your configuration.

## Features

- 📁 Drag-and-drop CSV file upload
- 📊 Interactive Plotly charts (zoom, pan, hover)
- ⚙️ Configurable via JSON
- 🔄 Dual y-axes support
- 🌐 Web-based interface
- 📱 Responsive design

## Local Development

### Prerequisites
- Python 3.9 or higher
- pip

### Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
python app.py
```

3. Open your browser to `http://localhost:5000`

### Testing Locally

Upload the example `bunker.csv` file to see the plots generated based on `config.json`.

## Configuration

Edit `config.json` to customize your plots:

```json
{
    "figure_size": [12, 8],
    "plots": [
        {"left": ["Column1"], "right": ["Column2", "Column3"]},
        {"left": ["Column4"], "right": ["Column5"]}
    ]
}
```

- **left**: Columns for left y-axis
- **right**: Columns for right y-axis (optional)
- Prefix column name with `-` to invert values (multiply by -1)

## Deployment to Render.com

### Step 1: Create a GitHub Repository

1. Initialize git in this directory:
```bash
cd bunker-plotter-web
git init
git add .
git commit -m "Initial commit"
```

2. Create a new repository on GitHub (https://github.com/new)

3. Push your code:
```bash
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

### Step 2: Deploy on Render.com

1. Go to https://render.com and sign up (you can use your GitHub account)

2. Click "New +" → "Web Service"

3. Connect your GitHub repository

4. Configure the service:
   - **Name**: bunker-plotter (or any name you want)
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: Free

5. Click "Create Web Service"

6. Wait for deployment (2-3 minutes)

7. Your app will be live at: `https://bunker-plotter.onrender.com` (or your chosen name)

### Step 3: Update Configuration

To update your plot configuration after deployment:

1. Edit `config.json` locally
2. Commit and push:
```bash
git add config.json
git commit -m "Update plot configuration"
git push
```
3. Render will automatically redeploy (takes ~2 minutes)

## Alternative Deployment (Railway.app)

If you prefer Railway.app:

1. Go to https://railway.app and sign up
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your repository
4. Railway will auto-detect it's a Python app and deploy
5. Your app will be live at the provided URL

## Usage

1. Open your deployed web application
2. Upload a CSV file with Date and Time columns
3. The app will generate interactive plots based on your `config.json`
4. Hover over plots to see values
5. Click and drag to zoom
6. Double-click to reset view

## CSV Format Requirements

Your CSV must have:
- `Date` column (format: MM/DD/YYYY)
- `Time` column (format: HH:MM:SS AM/PM)
- Data columns matching those in `config.json`

The app automatically calculates:
- `duty_gun` = Hz × Gun PW
- `duty_kly` = Hz × FWHM

## Troubleshooting

### Local Testing Issues

**Port already in use:**
```bash
# Change port in app.py or kill the process
lsof -ti:5000 | xargs kill -9
```

**Module not found:**
```bash
pip install -r requirements.txt
```

### Deployment Issues

**Build fails:**
- Check that `requirements.txt` is correct
- Ensure Python version is 3.9+
- Check Render logs for specific errors

**App crashes on startup:**
- Check Render logs for errors
- Verify `Procfile` is present and correct
- Ensure all files are committed to git

**Upload not working:**
- Check file size (max 16MB)
- Ensure CSV format is correct
- Check browser console for errors

## Project Structure

```
bunker-plotter-web/
├── app.py                 # Flask application
├── config.json            # Plot configuration
├── requirements.txt       # Python dependencies
├── Procfile              # Render deployment config
├── templates/
│   └── index.html        # Upload interface
├── uploads/              # Temporary upload directory (auto-created)
└── README.md             # This file
```

## Features Explained

### Interactive Plots
- **Zoom**: Click and drag on any plot
- **Pan**: Hold shift and drag
- **Reset**: Double-click
- **Hover**: See exact values
- **Export**: Use Plotly toolbar to save as PNG

### Dual Y-Axes
The plotter supports multiple series on different scales:
- Left axis: Primary measurements
- Right axis: Secondary measurements with different units
- Each axis can have multiple series

### Column Inversion
Prefix any column name with `-` in config.json to invert its values:
```json
{"left": ["-BeamCT ma"]}
```
This multiplies the values by -1 before plotting.

## Security Notes

- File uploads are limited to 16MB
- Only CSV files are accepted
- Uploaded files are deleted immediately after processing
- No data is stored on the server

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review Render/Railway logs
3. Test locally first to isolate deployment issues

## License

This project is provided as-is for personal or internal use.
