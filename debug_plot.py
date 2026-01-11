"""
Debug script to test Plotly figure generation directly.
Run with: python debug_plot.py <csv_file>
Opens the result in your browser.
"""

import sys
import os
import webbrowser
import tempfile

# Import from app.py
from app import load_and_parse_csv, load_config, create_plotly_figure

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_plot.py <csv_file>")
        print("Example: python debug_plot.py data.csv")
        sys.exit(1)

    csv_file = sys.argv[1]

    if not os.path.exists(csv_file):
        print(f"Error: File not found: {csv_file}")
        sys.exit(1)

    print(f"Loading CSV: {csv_file}")
    df = load_and_parse_csv(csv_file)
    print(f"DataFrame shape: {df.shape}")
    print(f"Columns: {list(df.columns)}")
    print(f"Index type: {type(df.index)}")
    print(f"First 3 index values: {df.index[:3].tolist()}")

    print("\nLoading config...")
    config = load_config()
    plot_config = config.get('plots', [])
    print(f"Number of plots configured: {len(plot_config)}")

    print("\nCreating figure...")
    fig, matched_cols, missing_cols = create_plotly_figure(df, plot_config)
    print(f"Matched columns: {matched_cols}")
    print(f"Missing columns: {missing_cols}")
    print(f"Number of traces: {len(fig.data)}")

    # Check trace data
    for i, trace in enumerate(fig.data[:3]):  # First 3 traces
        print(f"\nTrace {i}: {trace.name}")
        print(f"  x length: {len(trace.x) if trace.x is not None else 'None'}")
        print(f"  y length: {len(trace.y) if trace.y is not None else 'None'}")
        if trace.y is not None and len(trace.y) > 0:
            print(f"  y sample: {trace.y[:3]}")

    # Generate standalone HTML
    print("\nGenerating HTML...")
    html = fig.to_html(full_html=True, include_plotlyjs='cdn')
    print(f"HTML length: {len(html)} characters")

    # Save to temp file and open
    output_file = os.path.join(os.path.dirname(csv_file) or '.', 'debug_plot.html')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\nSaved to: {output_file}")
    print("Opening in browser...")
    webbrowser.open(f'file://{os.path.abspath(output_file)}')

if __name__ == '__main__':
    main()
