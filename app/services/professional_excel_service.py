"""
Professional Excel Report Generation Service
Creates branded Excel reports with logo, colors, and professional formatting
"""
import logging
import os
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side, Protection
from openpyxl.utils import get_column_letter
from openpyxl.drawing.image import Image as XLImage

logger = logging.getLogger(__name__)

# Brand Colors (matching reference format)
PRIMARY_COLOR = "125435"  # Dark green
ACCENT_COLOR = "E8F5E9"   # Light green
SECONDARY_COLOR = "2E7D32"  # Medium green
HEADER_COLOR = "125435"
ALT_ROW_COLOR = "F9FAFB"
BORDER_COLOR = "CCCCCC"

# Logo path
LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'static', 'logo.png')


def create_professional_excel_workbook(title="Inspection Report", sheet_name="Report"):
    """Create a new workbook with professional styling
    
    Args:
        title: Report title
        sheet_name: Name of the active sheet
        
    Returns:
        tuple: (workbook, worksheet)
    """
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    
    # Set default column widths
    ws.column_dimensions['A'].width = 22
    ws.column_dimensions['B'].width = 25
    ws.column_dimensions['C'].width = 22
    ws.column_dimensions['D'].width = 40
    ws.column_dimensions['E'].width = 12
    
    return wb, ws


def add_logo_and_title(ws, title, subtitle=None, start_row=1, max_columns=5):
    """Add logo and title to worksheet
    
    Args:
        ws: Worksheet object
        title: Report title
        subtitle: Optional subtitle
        start_row: Starting row number
        max_columns: Number of columns to span (default 5, use 8 for wider tables)
        
    Returns:
        int: Next available row number
    """
    from openpyxl.styles import Alignment
    
    current_row = start_row
    max_col_letter = get_column_letter(max_columns)
    
    # Row heights: row 1 tall for logo, row 2 shorter for company name
    ws.row_dimensions[current_row].height = 50
    ws.row_dimensions[current_row + 1].height = 22

    # Merge A1:A2 for the logo area (spans both header rows)
    try:
        ws.merge_cells(f'A{current_row}:A{current_row + 1}')
    except Exception:
        pass

    # Add logo if available
    if os.path.exists(LOGO_PATH):
        try:
            img = XLImage(LOGO_PATH)
            # Size logo to visually fill the merged A1:A2 area (rows 1+2 ≈ 72pt total)
            img.width = 80
            img.height = 80
            ws.add_image(img, f'A{current_row}')
        except Exception as e:
            logger.warning(f"Could not add logo to Excel: {e}")

    # Title (next to logo)
    title_cell = ws[f'B{current_row}']
    title_cell.value = title
    title_cell.font = Font(bold=True, size=16, color=PRIMARY_COLOR, name='Calibri')
    title_cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=False)
    ws.merge_cells(f'B{current_row}:{max_col_letter}{current_row}')
    
    # Add company name
    company_cell = ws[f'B{current_row + 1}']
    company_cell.value = "Injaaz Application"
    company_cell.font = Font(bold=True, size=10, color=SECONDARY_COLOR, name='Calibri')
    company_cell.alignment = Alignment(horizontal='left', vertical='center')
    
    current_row += 3
    
    # Subtitle if provided
    if subtitle:
        ws.row_dimensions[current_row].height = 25
        subtitle_cell = ws[f'A{current_row}']
        subtitle_cell.value = subtitle
        subtitle_cell.font = Font(bold=True, size=11, color=SECONDARY_COLOR, name='Calibri')
        subtitle_cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        ws.merge_cells(f'A{current_row}:{max_col_letter}{current_row}')
        current_row += 1
    
    current_row += 1  # Add spacing
    return current_row


def add_info_section(ws, info_data, start_row, title="Information", max_columns=4):
    """Add an information section with key-value pairs
    
    Args:
        ws: Worksheet object
        info_data: List of (label, value) tuples
        start_row: Starting row number
        title: Section title
        max_columns: Number of columns to span (default 4, use 8 for wider tables)
        
    Returns:
        int: Next available row number
    """
    current_row = start_row
    max_col_letter = get_column_letter(max_columns)
    
    # Section title
    ws.row_dimensions[current_row].height = 18
    title_cell = ws[f'A{current_row}']
    title_cell.value = title
    title_cell.font = Font(bold=True, size=14, color=PRIMARY_COLOR, name='Calibri')
    title_cell.fill = PatternFill(start_color=ACCENT_COLOR, end_color=ACCENT_COLOR, fill_type="solid")
    ws.merge_cells(f'A{current_row}:{max_col_letter}{current_row}')
    
    # Add border to all columns in the span
    for col_idx in range(1, max_columns + 1):
        col_letter = get_column_letter(col_idx)
        cell = ws[f'{col_letter}{current_row}']
        cell.border = Border(
            top=Side(style='medium', color=PRIMARY_COLOR),
            bottom=Side(style='medium', color=PRIMARY_COLOR),
            left=Side(style='thin', color=BORDER_COLOR),
            right=Side(style='thin', color=BORDER_COLOR)
        )
    
    current_row += 1
    
    # Add info rows
    for label, value in info_data:
        # Set row height
        ws.row_dimensions[current_row].height = 25
        
        label_cell = ws[f'A{current_row}']
        label_cell.value = label
        label_cell.font = Font(bold=True, size=10, name='Calibri')
        label_cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=False)
        label_cell.fill = PatternFill(start_color=ALT_ROW_COLOR, end_color=ALT_ROW_COLOR, fill_type="solid")
        label_cell.border = Border(
            left=Side(style='thin', color=BORDER_COLOR),
            right=Side(style='thin', color=BORDER_COLOR),
            top=Side(style='thin', color=BORDER_COLOR),
            bottom=Side(style='thin', color=BORDER_COLOR)
        )
        
        value_cell = ws[f'B{current_row}']
        value_cell.value = str(value)
        value_cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
        value_cell.border = Border(
            left=Side(style='thin', color=BORDER_COLOR),
            right=Side(style='thin', color=BORDER_COLOR),
            top=Side(style='thin', color=BORDER_COLOR),
            bottom=Side(style='thin', color=BORDER_COLOR)
        )
        ws.merge_cells(f'B{current_row}:E{current_row}')
        
        # Auto-adjust row height for wrapped content
        if value and len(str(value)) > 50:
            ws.row_dimensions[current_row].height = max(25, min(len(str(value)) // 30 * 15 + 25, 100))
        
        current_row += 1
    
    current_row += 1  # Add spacing
    return current_row


def add_data_table(ws, headers, data_rows, start_row, title=None, col_widths=None):
    """Add a professional data table
    
    Args:
        ws: Worksheet object
        headers: List of column headers
        data_rows: List of data rows (each row is a list)
        start_row: Starting row number
        title: Optional table title
        col_widths: Optional dict of column widths {col_letter: width}
        
    Returns:
        int: Next available row number
    """
    current_row = start_row
    
    # Table title if provided
    if title:
        title_cell = ws[f'A{current_row}']
        title_cell.value = title
        title_cell.font = Font(bold=True, size=13, color=SECONDARY_COLOR, name='Calibri')
        current_row += 1
    
    # Set column widths if provided
    if col_widths:
        for col_letter, width in col_widths.items():
            ws.column_dimensions[col_letter].width = width

    # Detect numeric columns (all non-empty values are int/float)
    numeric_cols = set()
    if data_rows:
        for col_idx in range(1, len(headers) + 1):
            all_numeric = True
            for row in data_rows:
                if col_idx - 1 >= len(row):
                    continue
                value = row[col_idx - 1]
                # Skip empty values
                if value in (None, ""):
                    continue
                if not isinstance(value, (int, float)):
                    all_numeric = False
                    break
            if all_numeric:
                numeric_cols.add(col_idx)
    
    # Header row
    header_row = current_row
    ws.row_dimensions[header_row].height = 35
    
    for col_idx, header in enumerate(headers, start=1):
        col_letter = get_column_letter(col_idx)
        cell = ws[f'{col_letter}{header_row}']
        cell.value = header
        cell.font = Font(bold=True, color="FFFFFF", size=11, name='Calibri')
        cell.fill = PatternFill(start_color=HEADER_COLOR, end_color=HEADER_COLOR, fill_type="solid")
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = Border(
            left=Side(style='thin', color="FFFFFF"),
            right=Side(style='thin', color="FFFFFF"),
            top=Side(style='medium', color=PRIMARY_COLOR),
            bottom=Side(style='medium', color=PRIMARY_COLOR)
        )
    
    current_row += 1
    
    # Data rows with alternating colors
    for row_idx, row_data in enumerate(data_rows):
        is_alternate = row_idx % 2 == 1
        fill_color = ALT_ROW_COLOR if is_alternate else "FFFFFF"
        
        # Set row height for data rows (larger for wrapped text)
        ws.row_dimensions[current_row].height = 40
        
        for col_idx, value in enumerate(row_data, start=1):
            col_letter = get_column_letter(col_idx)
            cell = ws[f'{col_letter}{current_row}']
            cell.value = value

            # Right-align purely numeric columns, left-align others
            if col_idx in numeric_cols:
                cell.alignment = Alignment(horizontal='right', vertical='top', wrap_text=True)
            else:
                cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
            cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
            cell.border = Border(
                left=Side(style='thin', color=BORDER_COLOR),
                right=Side(style='thin', color=BORDER_COLOR),
                top=Side(style='thin', color=BORDER_COLOR),
                bottom=Side(style='thin', color=BORDER_COLOR)
            )
        
        current_row += 1
    
    current_row += 1  # Add spacing
    return current_row


def add_section_header(ws, title, start_row, span_columns=4):
    """Add a section header row
    
    Args:
        ws: Worksheet object
        title: Section title
        start_row: Starting row number
        span_columns: Number of columns to span
        
    Returns:
        int: Next available row number
    """
    # Set row height for section header
    ws.row_dimensions[start_row].height = 30
    
    cell = ws[f'A{start_row}']
    cell.value = title
    cell.font = Font(bold=True, size=13, color=PRIMARY_COLOR, name='Calibri')
    cell.fill = PatternFill(start_color=ACCENT_COLOR, end_color=ACCENT_COLOR, fill_type="solid")
    cell.alignment = Alignment(horizontal='left', vertical='center')
    
    # Merge cells
    end_col = get_column_letter(span_columns)
    ws.merge_cells(f'A{start_row}:{end_col}{start_row}')
    
    # Add border
    for col_idx in range(1, span_columns + 1):
        col_letter = get_column_letter(col_idx)
        cell = ws[f'{col_letter}{start_row}']
        cell.border = Border(
            left=Side(style='thin', color=PRIMARY_COLOR),
            right=Side(style='thin', color=PRIMARY_COLOR),
            top=Side(style='medium', color=PRIMARY_COLOR),
            bottom=Side(style='medium', color=PRIMARY_COLOR)
        )
    
    return start_row + 1


def add_signature_section(ws, signatures, start_row):
    """Add signature section to worksheet
    
    Args:
        ws: Worksheet object
        signatures: Dict of {role: signature_data}
        start_row: Starting row number
        
    Returns:
        int: Next available row number
    """
    current_row = add_section_header(ws, "Signatures & Approval", start_row)
    
    # Headers row
    ws.row_dimensions[current_row].height = 25
    
    ws[f'A{current_row}'].value = "Role"
    ws[f'A{current_row}'].font = Font(bold=True, size=10, name='Calibri')
    ws[f'A{current_row}'].fill = PatternFill(start_color=ALT_ROW_COLOR, end_color=ALT_ROW_COLOR, fill_type="solid")
    ws[f'A{current_row}'].alignment = Alignment(horizontal='left', vertical='center')
    
    ws[f'B{current_row}'].value = "Status"
    ws[f'B{current_row}'].font = Font(bold=True, size=10, name='Calibri')
    ws[f'B{current_row}'].fill = PatternFill(start_color=ALT_ROW_COLOR, end_color=ALT_ROW_COLOR, fill_type="solid")
    ws[f'B{current_row}'].alignment = Alignment(horizontal='left', vertical='center')
    
    ws[f'C{current_row}'].value = "Signed On"
    ws[f'C{current_row}'].font = Font(bold=True, size=10, name='Calibri')
    ws[f'C{current_row}'].fill = PatternFill(start_color=ALT_ROW_COLOR, end_color=ALT_ROW_COLOR, fill_type="solid")
    ws[f'C{current_row}'].alignment = Alignment(horizontal='left', vertical='center')
    
    current_row += 1
    
    # Signature rows
    signed_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    for role, sig_data in signatures.items():
        # Set row height for signature rows
        ws.row_dimensions[current_row].height = 25
        
        ws[f'A{current_row}'].value = role
        
        if sig_data:
            ws[f'B{current_row}'].value = "✓ Signed"
            ws[f'B{current_row}'].font = Font(color="008000", name='Calibri')
            ws[f'C{current_row}'].value = signed_date
        else:
            ws[f'B{current_row}'].value = "Not signed"
            ws[f'B{current_row}'].font = Font(color="999999", name='Calibri')
            ws[f'C{current_row}'].value = "-"
        
        # Add borders
        for col in ['A', 'B', 'C']:
            cell = ws[f'{col}{current_row}']
            cell.border = Border(
                left=Side(style='thin', color=BORDER_COLOR),
                right=Side(style='thin', color=BORDER_COLOR),
                top=Side(style='thin', color=BORDER_COLOR),
                bottom=Side(style='thin', color=BORDER_COLOR)
            )
            cell.alignment = Alignment(horizontal='left', vertical='center')
        
        current_row += 1
    
    current_row += 1
    return current_row


def finalize_workbook(ws):
    """Apply final formatting to worksheet and auto-size columns
    
    Args:
        ws: Worksheet object
    """
    # Auto-size columns based on content
    from openpyxl.utils import get_column_letter
    
    for col in ws.iter_cols(min_col=1, max_col=ws.max_column):
        max_length = 0
        col_letter = get_column_letter(col[0].column)
        
        for cell in col:
            try:
                if cell.value:
                    # Calculate cell content length
                    cell_value = str(cell.value)
                    # Count wrapped lines (estimate based on width)
                    lines = cell_value.count('\n') + 1
                    # Estimate width needed (characters per line)
                    if hasattr(cell, 'alignment') and cell.alignment and cell.alignment.wrap_text:
                        # For wrapped text, use a reasonable width (35 chars is good for wrapped content)
                        length = min(len(cell_value) // lines + 5, 50)
                    else:
                        length = len(cell_value)
                    if length > max_length:
                        max_length = length
            except:
                pass
        
        # Set column width (add 2 for padding, minimum 10, maximum 60)
        adjusted_width = min(max(max_length + 2, 10), 60)
        ws.column_dimensions[col_letter].width = adjusted_width
    
    # Freeze top rows (typically after logo and title)
    ws.freeze_panes = 'A6'
    
    # Set print settings
    ws.page_setup.orientation = ws.ORIENTATION_PORTRAIT
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    
    # Set margins (in inches)
    ws.page_margins.left = 0.5
    ws.page_margins.right = 0.5
    ws.page_margins.top = 0.75
    ws.page_margins.bottom = 0.75
    
    # Add header and footer
    ws.oddHeader.center.text = "Injaaz Application"
    ws.oddHeader.center.size = 10
    ws.oddFooter.left.text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    ws.oddFooter.right.text = "Page &P of &N"
    ws.oddFooter.left.size = 8
    ws.oddFooter.right.size = 8


def recenter_logo(ws, row1_height=50, row2_height=22, logo_px=80):
    """Center the logo image inside the merged A1:A2 cell area.
    
    Must be called AFTER the final column A width has been set so the horizontal
    centering offset is computed correctly.  Replaces the string anchor that
    ws.add_image(img, 'A1') creates with a proper OneCellAnchor that carries the
    centering offsets, which openpyxl then serialises correctly on save.
    
    Args:
        ws: Worksheet that contains the logo image
        row1_height: Height of row 1 in points (default 50)
        row2_height: Height of row 2 in points (default 22)
        logo_px: Displayed logo size in pixels (default 80)
    """
    if not ws._images:
        return
    try:
        from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
        from openpyxl.drawing.xdr import XDRPositiveSize2D

        img = ws._images[0]
        # Column A pixel width: (width_units × 7 px/char + 5 px padding)
        col_a_px = (ws.column_dimensions['A'].width or 22) * 7 + 5
        # Merged row height in pixels: pt × (96 DPI / 72 pt/in)
        rows_px = (row1_height + row2_height) * 96.0 / 72.0
        logo_emu = logo_px * 9525  # 1 px = 9525 EMU
        # EMU offsets to center the image
        h_off = max(0, int((col_a_px - logo_px) / 2.0 * 9525))
        v_off = max(0, int((rows_px  - logo_px) / 2.0 * 9525))
        # Build a proper anchor object (img.anchor is still a plain string at this point)
        marker = AnchorMarker(col=0, row=0, colOff=h_off, rowOff=v_off)
        size   = XDRPositiveSize2D(cx=logo_emu, cy=logo_emu)
        img.anchor = OneCellAnchor(_from=marker, ext=size)
    except Exception as e:
        logger.warning(f"Could not center logo: {e}")


def create_summary_sheet(wb, summary_data, sheet_name="Summary"):
    """Create a summary/dashboard sheet with metrics and optional charts
    
    Args:
        wb: Workbook object
        summary_data: Dictionary with summary info:
            - title: Report title
            - project_name: Project/site name
            - date: Report date
            - status: Workflow status
            - metrics: List of metric dicts with 'label', 'value', 'change' (optional)
            - categories: Dict of category names and counts for pie chart
            - timeline: List of dicts with 'date' and 'value' for line chart (optional)
        sheet_name: Name for the summary sheet
        
    Returns:
        worksheet: The summary worksheet
    """
    from openpyxl.chart import PieChart, BarChart, Reference
    from openpyxl.chart.label import DataLabelList
    from openpyxl.chart.series import DataPoint
    
    # Create or get the summary sheet
    if sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    else:
        ws = wb.create_sheet(sheet_name, 0)  # Insert at beginning
    
    current_row = 1
    
    # Add logo and title
    if os.path.exists(LOGO_PATH):
        try:
            img = XLImage(LOGO_PATH)
            img.width = 50
            img.height = 50
            ws.add_image(img, 'A1')
        except Exception as e:
            logger.warning(f"Could not add logo to summary sheet: {e}")
    
    # Title
    title = summary_data.get('title', 'Report Summary')
    title_cell = ws['B1']
    title_cell.value = title
    title_cell.font = Font(bold=True, size=18, color=PRIMARY_COLOR, name='Calibri')
    title_cell.alignment = Alignment(horizontal='left', vertical='center')
    ws.merge_cells('B1:F1')
    ws.row_dimensions[1].height = 40
    
    # Subtitle with project info
    current_row = 3
    project_name = summary_data.get('project_name', '')
    date = summary_data.get('date', datetime.now().strftime('%Y-%m-%d'))
    status = summary_data.get('status', 'N/A')
    
    info_cell = ws[f'A{current_row}']
    info_cell.value = f"Project: {project_name}  |  Date: {date}  |  Status: {status.replace('_', ' ').title()}"
    info_cell.font = Font(size=11, color=SECONDARY_COLOR, name='Calibri')
    ws.merge_cells(f'A{current_row}:F{current_row}')
    
    current_row += 2
    
    # Metrics cards section
    metrics = summary_data.get('metrics', [])
    if metrics:
        # Section header
        ws[f'A{current_row}'].value = "Key Metrics"
        ws[f'A{current_row}'].font = Font(bold=True, size=14, color=PRIMARY_COLOR, name='Calibri')
        ws[f'A{current_row}'].fill = PatternFill(start_color=ACCENT_COLOR, end_color=ACCENT_COLOR, fill_type="solid")
        ws.merge_cells(f'A{current_row}:F{current_row}')
        ws.row_dimensions[current_row].height = 30
        current_row += 1
        
        # Create metrics row
        col_offset = 0
        for i, metric in enumerate(metrics[:4]):  # Max 4 metrics per row
            col_letter = get_column_letter(col_offset + 1)
            col_letter_end = get_column_letter(col_offset + 2)
            
            # Metric value cell
            value_cell = ws[f'{col_letter}{current_row}']
            value_cell.value = metric.get('value', 0)
            value_cell.font = Font(bold=True, size=24, color=PRIMARY_COLOR, name='Calibri')
            value_cell.alignment = Alignment(horizontal='center', vertical='center')
            ws.merge_cells(f'{col_letter}{current_row}:{col_letter_end}{current_row}')
            
            # Metric label cell
            label_cell = ws[f'{col_letter}{current_row + 1}']
            label_cell.value = metric.get('label', '')
            label_cell.font = Font(size=10, color="666666", name='Calibri')
            label_cell.alignment = Alignment(horizontal='center', vertical='center')
            ws.merge_cells(f'{col_letter}{current_row + 1}:{col_letter_end}{current_row + 1}')
            
            # Add change indicator if provided
            change = metric.get('change')
            if change is not None:
                change_cell = ws[f'{col_letter}{current_row + 2}']
                change_prefix = "+" if change > 0 else ""
                change_cell.value = f"{change_prefix}{change}%"
                change_color = "22C55E" if change >= 0 else "EF4444"
                change_cell.font = Font(size=9, color=change_color, name='Calibri')
                change_cell.alignment = Alignment(horizontal='center', vertical='center')
                ws.merge_cells(f'{col_letter}{current_row + 2}:{col_letter_end}{current_row + 2}')
            
            # Style the metric box
            for row in range(current_row, current_row + 3):
                for col in range(col_offset + 1, col_offset + 3):
                    cell = ws.cell(row=row, column=col)
                    cell.fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
                    cell.border = Border(
                        left=Side(style='thin', color=BORDER_COLOR),
                        right=Side(style='thin', color=BORDER_COLOR),
                        top=Side(style='thin', color=BORDER_COLOR) if row == current_row else Side(style=None),
                        bottom=Side(style='thin', color=BORDER_COLOR) if row == current_row + 2 else Side(style=None)
                    )
            
            col_offset += 2
        
        ws.row_dimensions[current_row].height = 35
        ws.row_dimensions[current_row + 1].height = 20
        ws.row_dimensions[current_row + 2].height = 18
        current_row += 4
    
    # Categories section with pie chart
    categories = summary_data.get('categories', {})
    if categories:
        # Section header
        ws[f'A{current_row}'].value = "Distribution"
        ws[f'A{current_row}'].font = Font(bold=True, size=14, color=PRIMARY_COLOR, name='Calibri')
        ws[f'A{current_row}'].fill = PatternFill(start_color=ACCENT_COLOR, end_color=ACCENT_COLOR, fill_type="solid")
        ws.merge_cells(f'A{current_row}:C{current_row}')
        ws.row_dimensions[current_row].height = 30
        current_row += 1
        
        # Add data for pie chart
        data_start_row = current_row
        for cat_name, cat_value in categories.items():
            ws[f'A{current_row}'].value = cat_name
            ws[f'A{current_row}'].font = Font(size=10, name='Calibri')
            ws[f'B{current_row}'].value = cat_value
            ws[f'B{current_row}'].font = Font(size=10, name='Calibri')
            ws[f'B{current_row}'].alignment = Alignment(horizontal='right')
            current_row += 1
        
        # Create pie chart
        try:
            pie = PieChart()
            pie.title = None
            labels = Reference(ws, min_col=1, min_row=data_start_row, max_row=current_row - 1)
            data = Reference(ws, min_col=2, min_row=data_start_row, max_row=current_row - 1)
            pie.add_data(data)
            pie.set_categories(labels)
            pie.width = 10
            pie.height = 8
            
            # Add data labels
            pie.dataLabels = DataLabelList()
            pie.dataLabels.showPercent = True
            pie.dataLabels.showVal = False
            pie.dataLabels.showCatName = False
            
            # Set colors for pie slices
            colors_list = ["125435", "1a7a4d", "34d399", "6ee7b7", "a7f3d0", "d1fae5"]
            for i, _ in enumerate(categories.keys()):
                point = DataPoint(idx=i)
                point.graphicalProperties.solidFill = colors_list[i % len(colors_list)]
                pie.series[0].data_points.append(point)
            
            # Position the chart
            ws.add_chart(pie, f'D{data_start_row}')
        except Exception as e:
            logger.warning(f"Could not create pie chart: {e}")
        
        current_row += 2
    
    # Set column widths
    ws.column_dimensions['A'].width = 18
    ws.column_dimensions['B'].width = 12
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 12
    ws.column_dimensions['E'].width = 12
    ws.column_dimensions['F'].width = 12
    
    # Add generation timestamp
    current_row += 1
    timestamp_cell = ws[f'A{current_row}']
    timestamp_cell.value = f"Report generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}"
    timestamp_cell.font = Font(size=9, color="999999", italic=True, name='Calibri')
    ws.merge_cells(f'A{current_row}:F{current_row}')
    
    return ws


def create_multi_sheet_report(wb, sheets_config):
    """Create a multi-sheet Excel report with consistent styling
    
    Args:
        wb: Workbook object
        sheets_config: List of sheet configurations, each with:
            - name: Sheet name
            - title: Sheet title
            - type: 'data' or 'summary'
            - content: Sheet-specific content data
            
    Returns:
        Workbook with all sheets created
    """
    for sheet_config in sheets_config:
        sheet_name = sheet_config.get('name', 'Sheet')
        sheet_type = sheet_config.get('type', 'data')
        
        if sheet_type == 'summary':
            create_summary_sheet(wb, sheet_config.get('content', {}), sheet_name)
        else:
            # Create data sheet
            if sheet_name == wb.active.title:
                ws = wb.active
            else:
                ws = wb.create_sheet(sheet_name)
            
            # Add content based on config
            content = sheet_config.get('content', {})
            current_row = add_logo_and_title(
                ws, 
                content.get('title', sheet_name),
                content.get('subtitle')
            )
            
            # Add info section if provided
            info_data = content.get('info_data', [])
            if info_data:
                current_row = add_info_section(ws, info_data, current_row)
            
            # Add data table if provided
            headers = content.get('headers', [])
            data_rows = content.get('data_rows', [])
            if headers and data_rows:
                current_row = add_data_table(
                    ws, headers, data_rows, current_row,
                    title=content.get('table_title')
                )
            
            finalize_workbook(ws)
    
    return wb


def add_conditional_formatting(ws, start_row, end_row, column, rules):
    """Add conditional formatting to a column
    
    Args:
        ws: Worksheet object
        start_row: Starting row
        end_row: Ending row
        column: Column letter
        rules: List of dicts with 'condition', 'value', 'fill_color'
            e.g., [{'condition': 'greaterThan', 'value': 0, 'fill_color': 'C6EFCE'}]
    """
    from openpyxl.formatting.rule import CellIsRule
    
    cell_range = f'{column}{start_row}:{column}{end_row}'
    
    for rule in rules:
        condition = rule.get('condition', 'equal')
        value = rule.get('value', 0)
        fill_color = rule.get('fill_color', 'FFFFFF')
        text_color = rule.get('text_color', '000000')
        
        ws.conditional_formatting.add(
            cell_range,
            CellIsRule(
                operator=condition,
                formula=[str(value)],
                fill=PatternFill(start_color=fill_color, end_color=fill_color, fill_type='solid'),
                font=Font(color=text_color)
            )
        )
