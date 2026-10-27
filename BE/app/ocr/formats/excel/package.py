"""Parts of an .xlsx package that openpyxl does not expose, read straight from the zip:

  pictures      logos anchored in cells (drawing parts)
  controls      Form Control check boxes / option buttons (VML drawing + ctrlProps)
  validations   Excel 2010+ data validation kept in the sheet's extLst (lists that point at another
                sheet are written there, and openpyxl drops them)

Everything is keyed by sheet name.
"""
import base64
import html
import posixpath
import re
from xml.etree import ElementTree as ET

NS = {
    "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "x14": "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main",
    "xm": "http://schemas.microsoft.com/office/excel/2006/main",
}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".bmp": "image/bmp"}
CONTROL_KINDS = {"checkbox": "checkbox", "radio": "radio"}


def _xml(z, part):
    try:
        from defusedxml.ElementTree import fromstring  # entity-expansion safe when installed
    except ImportError:  # pragma: no cover
        fromstring = ET.fromstring
    return fromstring(z.read(part))


class Package:
    def __init__(self, zf):
        self.z = zf
        self.names = set(zf.namelist())
        self.sheet_parts = self._sheet_parts()

    def rels(self, part):
        path = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
        if path not in self.names:
            return {}
        out = {}
        for el in _xml(self.z, path).findall("rel:Relationship", NS):
            if el.get("TargetMode") == "External":
                continue
            target = el.get("Target", "")
            full = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
            out[el.get("Id")] = (full, el.get("Type", ""))
        return out

    def _sheet_parts(self):
        if "xl/workbook.xml" not in self.names:
            return {}
        rels = self.rels("xl/workbook.xml")
        out = {}
        for sheet_el in _xml(self.z, "xl/workbook.xml").findall("main:sheets/main:sheet", NS):
            part = rels.get(sheet_el.get(f"{{{NS['r']}}}id"), (None, ""))[0]
            if part in self.names:
                out[sheet_el.get("name")] = part
        return out

    # ---- pictures --------------------------------------------------------------------------
    def pictures(self):
        out = {}
        for name, sheet_part in self.sheet_parts.items():
            for drawing_part, kind in self.rels(sheet_part).values():
                if not kind.endswith("/drawing") or drawing_part not in self.names:
                    continue
                d_rels = self.rels(drawing_part)
                for anchor in list(_xml(self.z, drawing_part)):
                    frm = anchor.find("xdr:from", NS)
                    blip = anchor.find(".//a:blip", NS)
                    if frm is None or blip is None:
                        continue
                    media = d_rels.get(blip.get(f"{{{NS['r']}}}embed"), (None, ""))[0]
                    mime = IMAGE_TYPES.get(posixpath.splitext(media or "")[1].lower())
                    if not media or media not in self.names or mime is None:
                        continue  # EMF/WMF and other vector formats cannot be shown in a browser
                    ext = anchor.find("xdr:ext", NS)
                    if ext is None:
                        ext = anchor.find(".//a:xfrm/a:ext", NS)
                    cx = int(ext.get("cx", 0)) if ext is not None else 0
                    cy = int(ext.get("cy", 0)) if ext is not None else 0
                    out.setdefault(name, []).append({
                        "row": int(frm.find("xdr:row", NS).text),
                        "col": int(frm.find("xdr:col", NS).text),
                        "src": f"data:{mime};base64," + base64.b64encode(self.z.read(media)).decode("ascii"),
                        "width": round(cx / 9525) or None,  # EMU -> px
                        "height": round(cy / 9525) or None,
                    })
        return out

    # ---- form controls -----------------------------------------------------------------------
    _SHAPE = re.compile(r"<v:shape\b(?P<attrs>[^>]*)>(?P<body>.*?)</v:shape>", re.S | re.I)
    _TAG = re.compile(r"<[^>]+>")

    @staticmethod
    def _tag(body, name):
        m = re.search(rf"<x:{name}>\s*(.*?)\s*</x:{name}>", body, re.S | re.I)
        return m.group(1) if m else None

    def _ctrl_props(self, sheet_part, rels):
        """{shape id: (checked, linked cell, part)} from ctrlProps (written by Excel 2010+)."""
        out = {}
        data = self.z.read(sheet_part).decode("utf-8", "ignore")
        for m in re.finditer(r"<control\b([^>]*)>", data):
            attrs = dict(re.findall(r'([\w:]+)="([^"]*)"', m.group(1)))
            part = rels.get(attrs.get("r:id"), (None, ""))[0]
            if not attrs.get("shapeId") or part not in self.names:
                continue
            props = self.z.read(part).decode("utf-8", "ignore")
            checked = re.search(r'\bchecked="(\w+)"', props)
            link = re.search(r'\bfmlaLink="([^"]+)"', props)
            out[attrs["shapeId"]] = (checked.group(1) if checked else None, link.group(1) if link else None, part)
        return out

    def controls(self):
        out = {}
        for name, sheet_part in self.sheet_parts.items():
            rels = self.rels(sheet_part)
            vml_parts = [p for p, kind in rels.values() if kind.endswith("/vmlDrawing") and p in self.names]
            if not vml_parts:
                continue
            props = self._ctrl_props(sheet_part, rels)
            for vml in vml_parts:
                text = self.z.read(vml).decode("utf-8", "ignore")
                for m in self._SHAPE.finditer(text):
                    body = m.group("body")
                    kind = re.search(r'<x:ClientData[^>]*ObjectType="(\w+)"', body, re.I)
                    kind = CONTROL_KINDS.get(kind.group(1).lower()) if kind else None
                    anchor = self._tag(body, "Anchor")
                    if kind is None or anchor is None:
                        continue
                    try:
                        nums = [int(x) for x in anchor.split(",")]
                    except ValueError:
                        continue
                    if len(nums) != 8:
                        continue
                    caption = re.search(r"<v:textbox\b[^>]*>(.*?)</v:textbox>", body, re.S | re.I)
                    caption = " ".join(html.unescape(self._TAG.sub(" ", caption.group(1))).split()) if caption else ""
                    checked = (self._tag(body, "Checked") or "0").strip() == "1"
                    link = self._tag(body, "FmlaLink")
                    spid = re.search(r'o:spid="_x0000_s(\d+)"', m.group("attrs"))
                    if spid and spid.group(1) in props:
                        state, plink, _ = props[spid.group(1)]
                        if state is not None:
                            checked = state.lower() == "checked"
                        link = link or plink
                    shape_id = spid.group(1) if spid else None
                    out.setdefault(name, []).append({
                        "kind": kind, "text": caption, "checked": checked,
                        "anchor": tuple(nums),  # left col, dx px, top row, dy px, right col, dx, bottom row, dy
                        "link": link.strip() if link else None,
                        # where it is stored, so a filled copy can tick it
                        "vml": vml, "spid": shape_id, "ctrl_prop": props.get(shape_id, (None, None, None))[2],
                    })
        return out

    # ---- Excel 2010+ data validation ---------------------------------------------------------
    def x14_validations(self):
        """{sheet name: [(type, formula1, sqref)]}"""
        out = {}
        for name, part in self.sheet_parts.items():
            raw = self.z.read(part)
            if b"dataValidation" not in raw or b"x14" not in raw:
                continue
            root = _xml(self.z, part)
            for dv in root.iter(f"{{{NS['x14']}}}dataValidation"):
                f1 = dv.find("x14:formula1/xm:f", NS)
                sqref = dv.find("xm:sqref", NS)
                if sqref is not None and sqref.text:
                    out.setdefault(name, []).append((dv.get("type", "none"), f1.text if f1 is not None else None, sqref.text))
        return out
