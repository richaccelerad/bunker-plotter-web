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
    header_cols = [c.strip() for c in header_line.rstrip('\n').split(',') if c.strip()]
    num_cols = len(header_cols)

    # Read only the expected number of columns (ignores trailing commas/comments)
    df = pd.read_csv(
        filepath,
        encoding='latin-1',
        usecols=range(num_cols),
        names=header_cols,
        skiprows=1,
        dtype={'Date': str, 'Time': str}
    )

    # Normalize column names (map old names to new names)
    column_renames = {
        'Icath (mA)': 'Icath (A)',
        'BeamCT ma': 'BeamCT (A)',
        # Handle encoding variations for special characters
    }
    # Find and rename columns with encoding issues
    for col in df.columns:
        if 'Guide Iip' in col and col != 'Guide Iip (uA)':
            column_renames[col] = 'Guide Iip (uA)'
        if 'Sacn Iip' in col or ('Scan Iip' in col and col != 'Scan Iip (uA)'):
            column_renames[col] = 'Scan Iip (uA)'
        if 'Gun PW' in col and col != 'Gun PW (us)':
            column_renames[col] = 'Gun PW (us)'
        if 'FWHM' in col and col != 'FWHM (us)':
            column_renames[col] = 'FWHM (us)'
        if 'Gun Iip' in col and col != 'Gun Iip (uA)':
            column_renames[col] = 'Gun Iip (uA)'

    df = df.rename(columns=column_renames)

    # Combine Date and Time columns into a datetime
    df['datetime'] = pd.to_datetime(
        df['Date'].astype(str) + ' ' + df['Time'].astype(str),
        format='%m/%d/%Y %I:%M:%S %p',
        errors='coerce'
    )
    df = df.set_index('datetime')

    # Drop rows where datetime parsing failed
    df = df[df.index.notna()]

    # Calculated columns (divide by 1e6 to convert us to seconds)
    if 'Gun PW (us)' in df.columns and 'Hz' in df.columns:
        df['duty_gun'] = df['Hz'] * df['Gun PW (us)'] / 1e6
    if 'FWHM (us)' in df.columns and 'Hz' in df.columns:
        df['duty_kly'] = df['Hz'] * df['FWHM (us)'] / 1e6

    return df


def parse_column(col_spec):
    """Parse column specification, handling inversion prefix.
    
    Returns (column_name, invert_flag, display_name)
    """
    if col_spec.startswith('-'):
        col_name = col_spec[1:]
        return col_name, True, f"-{col_name}"
    return col_spec, False, col_spec


def find_on_periods(df):
    """Find time periods where the system is 'on' (Ikly > 20 and Icath > 0.1)."""
    if 'Ikly (A)' not in df.columns or 'Icath (A)' not in df.columns:
        return []

    # Create boolean mask for "on" condition
    on_mask = (df['Ikly (A)'] > 20) & (df['Icath (A)'] > 0.1)

    # Find transitions (start and end of "on" periods)
    periods = []
    in_on_period = False
    start_time = None

    for i, (time, is_on) in enumerate(zip(df.index, on_mask)):
        if is_on and not in_on_period:
            # Start of an "on" period
            start_time = time
            in_on_period = True
        elif not is_on and in_on_period:
            # End of an "on" period
            periods.append((start_time, df.index[i-1]))
            in_on_period = False

    # Handle case where data ends while still "on"
    if in_on_period:
        periods.append((start_time, df.index[-1]))

    return periods


def create_plotly_figure(df, plot_config):
    """Create interactive Plotly figure with subplots.

    Returns (fig, matched_cols, missing_cols)
    """
    num_plots = len(plot_config)
    matched_cols = []
    missing_cols = []

    # Create subplots with secondary y-axes
    specs = [[{"secondary_y": True}] for _ in range(num_plots)]

    fig = make_subplots(
        rows=num_plots,
        cols=1,
        specs=specs,
        shared_xaxes=True,
        vertical_spacing=0.02,
    )

    # Find "on" periods and add background shading using paper coordinates
    on_periods = find_on_periods(df)
    shapes = []
    for start, end in on_periods:
        # Single shape spanning entire plot height
        shapes.append(dict(
            type="rect",
            x0=start, x1=end,
            y0=0, y1=1,
            xref='x',
            yref='paper',
            fillcolor="gray",
            opacity=0.4,
            layer="below",
            line_width=0,
        ))
    fig.update_layout(shapes=shapes)
    
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
        left_colors = []  # Track colors for left axis
        right_colors = []  # Track colors for right axis

        # Count valid columns for each axis
        valid_left = [c for c in left_cols if parse_column(c)[0] in df.columns]
        valid_right = [c for c in right_cols if parse_column(c)[0] in df.columns]

        # Plot left axis columns
        for col_spec in left_cols:
            col, invert, display_name = parse_column(col_spec)
            if col in df.columns:
                matched_cols.append(col)
            else:
                missing_cols.append(col)
            if col in df.columns:
                data = -df[col] if invert else df[col]
                trace_color = colors[color_idx % len(colors)]
                left_colors.append(trace_color)
                # Use legend, legend2, legend3, etc. for each subplot
                legend_name = "legend" if i == 1 else f"legend{i}"
                # Add (L) or (R) to legend name
                legend_display = f"{display_name} (L)"
                fig.add_trace(
                    go.Scatter(
                        x=df.index.tolist(),
                        y=data.tolist(),
                        name=legend_display,
                        mode='lines+markers',
                        marker=dict(size=3),
                        line=dict(color=trace_color),
                        legendgroup=f"plot{i}",
                        legend=legend_name,
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
                matched_cols.append(col)
            else:
                missing_cols.append(col)
            if col in df.columns:
                data = -df[col] if invert else df[col]
                trace_color = colors[color_idx % len(colors)]
                right_colors.append(trace_color)
                legend_name = "legend" if i == 1 else f"legend{i}"
                legend_display = f"{display_name} (R)"
                fig.add_trace(
                    go.Scatter(
                        x=df.index.tolist(),
                        y=data.tolist(),
                        name=legend_display,
                        mode='lines+markers',
                        marker=dict(size=3),
                        line=dict(color=trace_color),
                        legendgroup=f"plot{i}",
                        legend=legend_name,
                    ),
                    row=i,
                    col=1,
                    secondary_y=True
                )
                color_idx += 1

        # Update y-axis labels
        left_labels = [parse_column(c)[2] for c in left_cols if parse_column(c)[0] in df.columns]
        right_labels = [parse_column(c)[2] for c in right_cols if parse_column(c)[0] in df.columns]

        # Determine axis colors (use trace color if only one trace on that axis)
        left_axis_color = left_colors[0] if len(left_colors) == 1 else None
        right_axis_color = right_colors[0] if len(right_colors) == 1 else None

        if left_labels:
            axis_style = {}
            if left_axis_color:
                axis_style = dict(
                    title_font=dict(color=left_axis_color),
                    tickfont=dict(color=left_axis_color),
                )
            fig.update_yaxes(
                title_text=" / ".join(left_labels),
                row=i,
                col=1,
                secondary_y=False,
                showgrid=True,
                gridcolor='lightgray',
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=False,
                **axis_style
            )
        if right_labels:
            axis_style = {}
            if right_axis_color:
                axis_style = dict(
                    title_font=dict(color=right_axis_color),
                    tickfont=dict(color=right_axis_color),
                )
            fig.update_yaxes(
                title_text=" / ".join(right_labels),
                row=i,
                col=1,
                secondary_y=True,
                showgrid=False,  # Only left axis has gridlines
                showline=True,
                linewidth=1,
                linecolor='black',
                mirror=False,
                **axis_style
            )

        # Add frame (top and bottom lines for x-axis)
        fig.update_xaxes(
            row=i,
            col=1,
            showline=True,
            linewidth=1,
            linecolor='black',
            mirror=True,  # Shows line on opposite side too
        )
    
    # Update x-axis label on bottom plot only
    fig.update_xaxes(title_text="Time", row=num_plots, col=1)
    
    # Calculate legend positions for each subplot
    # Each subplot takes up roughly 1/num_plots of the vertical space
    plot_height = 1.0 / num_plots
    legend_configs = {}

    for i in range(1, num_plots + 1):
        legend_name = "legend" if i == 1 else f"legend{i}"
        # Position legend at the top-right of each subplot
        # y position: top of subplot (1 - (i-1)*plot_height), slightly inside
        y_pos = 1 - (i - 1) * plot_height - 0.02
        legend_configs[legend_name] = dict(
            x=1.02,
            y=y_pos,
            xanchor='left',
            yanchor='top',
            bgcolor='rgba(255,255,255,0.8)',
            bordercolor='rgba(0,0,0,0.1)',
            borderwidth=1,
        )

    # Update layout
    fig.update_layout(
        height=250 * num_plots,
        hovermode='x unified',
        template='plotly_white',
        **legend_configs
    )

    return fig, matched_cols, missing_cols


@app.errorhandler(413)
def too_large(e):
    return jsonify({'error': 'File too large (16MB max)'}), 413


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
        fig, matched_cols, missing_cols = create_plotly_figure(df, plot_config)

        # Generate full standalone HTML (this works reliably)
        plot_html = fig.to_html(full_html=True, include_plotlyjs='cdn')

        # Save to a temp file that can be served
        plot_file = os.path.join(app.config['UPLOAD_FOLDER'], 'latest_plot.html')
        with open(plot_file, 'w', encoding='utf-8') as f:
            f.write(plot_html)

        # Clean up uploaded file
        os.remove(filepath)

        return jsonify({
            'success': True,
            'plot_url': '/plot',
            'num_rows': len(df),
            'columns': list(df.columns),
            'matched_columns': matched_cols,
            'missing_columns': missing_cols
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/plot')
def serve_plot():
    """Serve the latest generated plot."""
    plot_file = os.path.join(app.config['UPLOAD_FOLDER'], 'latest_plot.html')
    if os.path.exists(plot_file):
        with open(plot_file, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html'}
    return 'No plot available', 404


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
