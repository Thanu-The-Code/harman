"""Small bounding-box helpers. A bbox is [x0, y0, x1, y1] in pixels unless noted."""


def width(b):
    return b[2] - b[0]


def height(b):
    return b[3] - b[1]


def center(b):
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def area(b):
    return max(0.0, width(b)) * max(0.0, height(b))


def union(boxes):
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def intersection(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]


def iou(a, b):
    inter = intersection(a, b)
    if not inter:
        return 0.0
    ia = area(inter)
    return ia / (area(a) + area(b) - ia)


def v_overlap(a, b):
    """Vertical overlap as a fraction of the shorter box's height."""
    ov = min(a[3], b[3]) - max(a[1], b[1])
    h = min(height(a), height(b))
    return max(0.0, ov) / h if h > 0 else 0.0


def h_overlap(a, b):
    """Horizontal overlap as a fraction of the narrower box's width."""
    ov = min(a[2], b[2]) - max(a[0], b[0])
    w = min(width(a), width(b))
    return max(0.0, ov) / w if w > 0 else 0.0


def contains_point(b, p, pad=0.0):
    return b[0] - pad <= p[0] <= b[2] + pad and b[1] - pad <= p[1] <= b[3] + pad


def inside(inner, outer, pad=0.0):
    return contains_point(outer, center(inner), pad)


def expand(b, dx, dy=None):
    dy = dx if dy is None else dy
    return [b[0] - dx, b[1] - dy, b[2] + dx, b[3] + dy]


def normalize(b, w, h):
    return [round(b[0] / w, 5), round(b[1] / h, 5), round(b[2] / w, 5), round(b[3] / h, 5)]


def denormalize(b, w, h):
    return [b[0] * w, b[1] * h, b[2] * w, b[3] * h]


def poly_to_bbox(poly):
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return [min(xs), min(ys), max(xs), max(ys)]


def cluster_values(values, tol):
    """Group sorted 1-D values whose neighbours are within tol; returns cluster means."""
    if not values:
        return []
    vals = sorted(values)
    groups = [[vals[0]]]
    for v in vals[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def nearest_index(values, v):
    return min(range(len(values)), key=lambda i: abs(values[i] - v))
