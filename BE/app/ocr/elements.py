"""Factories for form-builder elements, mirroring what the builder's toolbar `create()` produces
(FE src/vendor/react-form-builder/toolbar.jsx)."""
import html
import re
import uuid

DISPLAY = {
    "Header": "Header Text",
    "Label": "Label",
    "Paragraph": "Paragraph",
    "TextInput": "Text Input",
    "EmailInput": "Email",
    "PhoneNumber": "Phone Number",
    "NumberInput": "Number Input",
    "TextArea": "Multi-line Input",
    "Checkboxes": "Checkboxes",
    "RadioButtons": "Multiple Choice",
    "Dropdown": "Dropdown",
    "DatePicker": "Date",
    "Signature": "Signature",
    "Table": "Table",
    "Image": "Image",
    "TwoColumnRow": "Two Column Row",
    "ThreeColumnRow": "Three Columns Row",
    "MultiColumnRow": "Multi Column Row",
}

PREFIX = {
    "TextInput": "text_input_",
    "EmailInput": "email_input_",
    "PhoneNumber": "phone_input_",
    "NumberInput": "number_input_",
    "TextArea": "text_area_",
    "Checkboxes": "checkboxes_",
    "RadioButtons": "radiobuttons_",
    "Dropdown": "dropdown_",
    "DatePicker": "date_picker_",
    "Signature": "signature_",
    "Table": "table_",
    "TwoColumnRow": "two_col_row_",
    "ThreeColumnRow": "three_col_row_",
}

MULTI_COLUMN = {4: ("four_col_row_", "col-md-3"), 5: ("five_col_row_", "col"), 6: ("six_col_row_", "col-md-2")}

ANSWERABLE = {"TextInput", "EmailInput", "PhoneNumber", "NumberInput", "TextArea", "Checkboxes", "RadioButtons", "Dropdown"}
OPTION_KEY = {"Checkboxes": "checkboxes_option_", "RadioButtons": "radiobuttons_option_", "Dropdown": "dropdown_option_"}


def new_id():
    return str(uuid.uuid4()).upper()


def slug(text):
    """Same rule as DynamicOptionList._setValue so option values stay in sync when edited."""
    return re.sub(r"[^A-Za-z0-9]+", "_", text).lower()


def escape(text):
    return html.escape(text or "", quote=False)


def _base(element):
    return {
        "id": new_id(),
        "element": element,
        "text": DISPLAY[element],
        "required": False,
        "canHavePageBreakBefore": True,
        "canHaveAlternateForm": True,
        "canHaveDisplayHorizontal": True,
        "canHaveOptionCorrect": True,
        "canHaveOptionValue": True,
        "canPopulateFromApi": True,
    }


def static_element(element, text, bold=False):
    e = _base(element)
    e.update(static=True, bold=bool(bold), italic=False, content=escape(text))
    return e


def image_element(src, width=None, height=None):
    e = _base("Image")
    e.update(field_name="image_" + new_id(), src=src, label="")
    if width:
        e["width"] = int(width)
    if height:
        e["height"] = int(height)
    return e


def input_element(element, label):
    e = _base(element)
    if element in ANSWERABLE:
        e["canHaveAnswer"] = True
    e["field_name"] = PREFIX[element] + new_id()
    e["label"] = escape(label)
    if element == "DatePicker":
        e.update(
            readOnly=False,
            defaultToday=False,
            dateFormat="MM/dd/yyyy",
            timeFormat="hh:mm aa",
            showTimeSelect=False,
            showTimeSelectOnly=False,
            showTimeInput=False,
        )
    if element == "Signature":
        e["readOnly"] = False
    return e


def option_element(element, label, option_texts):
    e = input_element(element, label)
    key_prefix = OPTION_KEY[element]
    e["options"] = [{"value": slug(t) or f"option_{i + 1}", "text": t, "key": key_prefix + new_id()} for i, t in enumerate(option_texts)]
    if element in ("Checkboxes", "RadioButtons"):
        e["inline"] = False
    return e


def table_element(label, columns, header, body, reference=False):
    """columns: [{"text", "title"?}] leaf columns; header/body: explicit grids of cell dicts.
    reference=True: printed for information only (a revision history), nothing is filled in.

    Cell dicts: {"text": "..."} fixed text, {"input": "text"} a cell to fill in,
    {"covered": True} hidden under a neighbour's rowspan/colspan; plus optional
    "rowspan"/"colspan". Plain strings are accepted too ("" = input, "x" = fixed text).
    """
    e = input_element("Table", label)
    e["columns"] = [{"key": "col_" + new_id(), **({"text": c} if isinstance(c, str) else c)} for c in columns]
    e["header"] = [list(r) for r in header]
    e["rows"] = [{"key": "row_" + new_id(), "cells": list(r)} for r in body]
    if reference:
        e["reference"] = True
    return e


def container_element(count):
    if count == 2:
        e = _base("TwoColumnRow")
        e["field_name"] = PREFIX["TwoColumnRow"] + new_id()
    elif count == 3:
        e = _base("ThreeColumnRow")
        e["field_name"] = PREFIX["ThreeColumnRow"] + new_id()
    else:
        prefix, class_name = MULTI_COLUMN[count]
        e = _base("MultiColumnRow")
        e["field_name"] = prefix + new_id()
        e["col_count"] = count
        e["class_name"] = class_name
    e["label"] = ""
    e["canHaveAnswer"] = False
    e["childItems"] = []
    e["isContainer"] = True
    return e
