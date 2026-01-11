"""
Bunker CSV Plotter - Web Application
Uses Plotly for interactive plotting
"""

import json
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from flask import Flask, render_template, request, jsonify
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create uploads directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Default config
DEFAULT_CONFIG = {
    "figure_size": [12, 8],
    "plots": [
        {"left": ["CCPS"], "right": ["Ekly (kV)", "Ikly (A)"]},
        {"left": ["GunVfil (v)"], "right": ["Gun Ifil (A)"]},
        {"left": ["GunHV (kV)"], "right": ["Icath (mA)", "-BeamCT ma"]},
        {"left": ["duty_gun"], "right": ["duty_kly"]},
        {"left": ["Guide Iip (æA)"], "right": ["Sacn Iip (æA)"]}
    ]
}

def load_config(config_path='config.json'):
    """Load configuration from JSON file or use default."""
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return DEFAULT_CONFIG


def load_and_parse_csv(filepath):
    """Load CSV and parse Date/Time into datetime index."""
    # First, read header to get column count
    with open(filepath, 'r', encoding='latin-1') as f:
        header_line = f.readline()
    num_cols = len(header_line.split(','))

    # Read only the expected number of columns (ignores trailing comments)
    df = pd.read_csv(
        filepath,
        encoding='latin-1',
        usecols=range(num_cols),
        dtype={'Date': str, 'Time': str}
    )

    # Combine Date and Time columns into a datetime
    df['datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'].astype(str),
        format='%m/%d/%Y %I:%M:%S %p',
        errors='coerce'
    )
    df = df.set_index('datetime')

    # Drop rows where datetime parsing failed
    df = df[df.index.notna()]

    # Calculated columns - find columns by partial match due to encoding variations
    gun_pw_cols = [c for c in df.columns if 'Gun PW' in c]
    fwhm_cols = [c for c in df.columns if 'FWHM' in c]
    
    if gun_pw_cols and 'Hz' in df.columns:
        df['duty_gun'] = df['Hz'] * df[gun_pw_cols[0]]
    if fwhm_cols and 'Hz' in df.columns:
        df['duty_kly'] = df['Hz'] * df[fwhm_cols[0]]

    return df


def parse_column(col_spec):
    """Parse column specification, handling inversion prefix.
    
    Returns (column_name, invert_flag, display_name)
    """
    if col_spec.startswith('-'):
        col_name = col_spec[1:]
        return col_name, True, f"-{col_name}"
    return col_spec, False, col_spec


def create_plotly_figure(df, plot_config):
    """Create interactive Plotly figure with subplots."""
    num_plots = len(plot_config)
    
    # Create subplots with secondary y-axes
    specs = [[{"secondary_y": True}] for _ in range(num_plots)]
    
    fig = make_subplots(
        rows=num_plots,
        cols=1,
        specs=specs,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=[f"Plot {i+1}" for i in range(num_plots)]
    )
    
    # Color palette
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', 
              '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    for i, subplot_config in enumerate(plot_config, start=1):
        # Normalize config to dict format
        if isinstance(subplot_config, dict):
            left_cols = subplot_config.get("left", [])
            right_cols = subplot_config.get("right", [])
        else:
            # Simple list format - all on left axis
            left_cols = subplot_config
            right_cols = []
        
        color_idx = 0
        
        # Plot left axis columns
        for col_spec in left_cols:
            col, invert, display_name = parse_column(col_spec)
            if col in df.columns:
                data = -df[col] if invert else df[col]
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=data,
                        name=display_name,
                        mode='lines+markers',
                        marker=dict(size=3),
                        line=dict(color=colors[color_idx % len(colors)]),
                        legendgroup=f"plot{i}",
                    ),
                    row=i,
                    col=1,
                    secondary_y=False
                )
                color_idx += 1
        
        # Plot right axis columns
        for col_spec in right_cols:
            col, invert, display_name = parse_column(col_spec)
            if col in df.columns:
                data = -df[col] if invert else df[col]
                fig.add_trace(
                    go.Scatter(
                        x=df.index,
                        y=data,
                        name=display_name,
                        mode='lines+markers',
                        marker=dict(size=3),
                        line=dict(color=colors[color_idx % len(colors)]),
                        legendgroup=f"plot{i}",
                    ),
                    row=i,
                    col=1,
                    secondary_y=True
                )
                color_idx += 1
        
        # Update y-axis labels
        left_labels = [parse_column(c)[2] for c in left_cols]
        right_labels = [parse_column(c)[2] for c in right_cols]
        
        if left_labels:
            fig.update_yaxes(
                title_text=" / ".join(left_labels),
                row=i,
                col=1,
                secondary_y=False
            )
        if right_labels:
            fig.update_yaxes(
                title_text=" / ".join(right_labels),
                row=i,
                col=1,
                secondary_y=True
            )
    
    # Update x-axis label on bottom plot only
    fig.update_xaxes(title_text="Time", row=num_plots, col=1)
    
    # Update layout
    fig.update_layout(
        height=200 * num_plots,
        showlegend=True,
        hovermode='x unified',
        template='plotly_white'
    )
    
    return fig


@app.route('/')
def index():
    """Render the upload page."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle CSV file upload and generate plot."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename.endswith('.csv'):
        return jsonify({'error': 'File must be a CSV'}), 400
    
    try:
        # Save uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Load and parse CSV
        df = load_and_parse_csv(filepath)
        
        # Load config
        config = load_config()
        plot_config = config.get('plots', [])
        
        # Create Plotly figure
        fig = create_plotly_figure(df, plot_config)
        
        # Convert to HTML
        plot_html = fig.to_html(full_html=False, include_plotlyjs='cdn')
        
        # Clean up uploaded file
        os.remove(filepath)
        
        return jsonify({
            'success': True,
            'plot_html': plot_html,
            'num_rows': len(df),
            'columns': list(df.columns)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
