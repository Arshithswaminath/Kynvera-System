import os
from openpyxl import Workbook

from common.datetime_utils import utc_now_naive


def create_report_workbook(generated_dir, visit_info, items):
    os.makedirs(generated_dir, exist_ok=True)
    filename = f"report_{int(utc_now_naive().timestamp())}.xlsx"
    path = os.path.join(generated_dir, filename)
    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    ws.append(["Building", visit_info.get("building_name", "")])
    ws.append([])
    ws.append(["Item", "Description", "Quantity"])
    for i, it in enumerate(items, 1):
        ws.append([i, it.get("description", ""), it.get("quantity", 1)])
    wb.save(path)
    return path, filename