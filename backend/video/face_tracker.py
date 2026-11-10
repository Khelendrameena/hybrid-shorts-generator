"""Face detection + simple centroid tracking with OpenCV Haar cascades
(no extra model downloads; works offline). Gives, per sampled time, the
dominant face centre (normalised 0..1) — used for face-aware 9:16 cropping
and for the visual-suitability feature. If OpenCV/cascade is unavailable,
returns empty tracking and the renderer falls back to centre crop.
OCR lives here too as an OPTIONAL easyocr hook (graceful no-op if absent)."""
from __future__ import annotations

from pathlib import Path


def _cascade():
    try:
        import cv2  # type: ignore

        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        clf = cv2.CascadeClassifier(str(path))
        return clf if not clf.empty() else None
    except Exception:
        return None  # minimal OpenCV builds may lack CascadeClassifier — degrade, never crash


def track_faces(video_path: str | Path, sample_interval: float = 2.0,
                duration: float | None = None) -> list[dict]:
    try:
        import cv2  # type: ignore
    except Exception:
        return []
    clf = _cascade()
    if clf is None:
        return []
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = duration or (total / fps if fps else 0)
    out: list[dict] = []
    last_center = None
    t = 0.0
    while t < dur:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok or frame is None:
            t += sample_interval
            continue
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = clf.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
        best = None
        for (x, y, fw, fh) in faces:
            area = fw * fh
            if best is None or area > best[0]:
                best = (area, (x + fw / 2) / w, (y + fh / 2) / h, fw / w, fh / h)
        if best is not None:
            _, cx, cy, fw_n, fh_n = best
            last_center = (round(cx, 3), round(cy, 3))
            out.append({"time": round(t, 2), "face_count": len(faces),
                        "center_x": last_center[0], "center_y": last_center[1],
                        "face_w": round(fw_n, 3), "face_h": round(fh_n, 3)})
        else:
            out.append({"time": round(t, 2), "face_count": 0,
                        "center_x": last_center[0] if last_center else 0.5,
                        "center_y": last_center[1] if last_center else 0.5,
                        "face_w": 0.0, "face_h": 0.0})
        t += sample_interval
    cap.release()
    return out


def dominant_face_center(track: list[dict], start: float, end: float) -> tuple[float, float, float]:
    """(centre_x, centre_y, face_coverage_ratio) averaged over [start, end]."""
    rows = [r for r in track if start <= r["time"] <= end]
    if not rows:
        return 0.5, 0.5, 0.0
    with_face = [r for r in rows if r.get("face_count", 0) > 0]
    coverage = len(with_face) / len(rows)
    if not with_face:
        return 0.5, 0.5, 0.0
    cx = sum(r["center_x"] for r in with_face) / len(with_face)
    cy = sum(r["center_y"] for r in with_face) / len(with_face)
    return round(cx, 3), round(cy, 3), round(coverage, 3)


def ocr_frame(image_path: str | Path) -> list[str]:
    """Optional OCR. Returns [] when easyocr is not installed — by design."""
    try:
        import easyocr  # type: ignore
    except Exception:
        return []
    try:
        reader = ocr_frame._reader  # type: ignore[attr-defined]
    except AttributeError:
        reader = easyocr.Reader(["en", "hi"], gpu=False, verbose=False)
        ocr_frame._reader = reader  # type: ignore[attr-defined]
    try:
        return [t for _, t, conf in reader.readtext(str(image_path)) if conf > 0.4]
    except Exception:
        return []
