#!/usr/bin/env python3
"""Animate a snake over GitHub's anonymous public contribution calendar."""

import argparse
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cells = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "data-date" not in values or "data-level" not in values:
            return
        day = date.fromisoformat(values["data-date"])
        if day.isoformat() != values["data-date"]:
            raise ValueError("Calendar date is not in YYYY-MM-DD format")
        if values["data-level"] not in {"0", "1", "2", "3", "4"}:
            raise ValueError("Calendar intensity must be an integer from 0 to 4")
        if day in self.cells:
            raise ValueError("Calendar contains duplicate dates")
        self.cells[day] = int(values["data-level"])


def fetch_calendar(username):
    url = f"https://github.com/users/{username}/contributions"
    request = Request(url, headers={"User-Agent": "public-contribution-snake/1.0"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200 or response.url != url:
            raise ValueError("Unexpected calendar response or redirect")
        if response.headers.get_content_type() != "text/html":
            raise ValueError("Calendar response is not HTML")
        html = response.read(2_000_001)
    if len(html) > 2_000_000:
        raise ValueError("Calendar response exceeds size limit")
    parser = CalendarParser()
    parser.feed(html.decode("utf-8"))
    parser.close()
    cells = sorted(parser.cells.items())
    if not 350 <= len(cells) <= 400:
        raise ValueError("Expected a full year of publicly visible calendar dates")
    for previous, current in zip(cells, cells[1:]):
        if current[0] - previous[0] != timedelta(days=1):
            raise ValueError("Calendar dates must be consecutive")
    today = date.today()
    if not today - timedelta(days=2) <= cells[-1][0] <= today + timedelta(days=1):
        raise ValueError("Calendar is stale or has unexpected future dates")
    return cells


def make_svg(username, cells, dark=False):
    namespace = "http://www.w3.org/2000/svg"
    ET.register_namespace("", namespace)

    def add(parent, tag, attributes=None, text=None):
        element = ET.SubElement(parent, f"{{{namespace}}}{tag}", attributes or {})
        element.text = text
        return element

    first, last = cells[0][0], cells[-1][0]
    sunday = first - timedelta(days=(first.weekday() + 1) % 7)
    columns = (last - sunday).days // 7 + 1
    width = 45 + columns * 15
    palette = (
        ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
        if dark else ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
    )
    foreground = "#c9d1d9" if dark else "#57606a"
    background = "#0d1117" if dark else "#ffffff"
    snake_color = "#a371f7" if dark else "#633cf2"
    svg = ET.Element(f"{{{namespace}}}svg", {
        "width": str(width), "height": "158", "viewBox": f"0 0 {width} 158",
        "role": "img", "aria-labelledby": "title desc",
    })
    add(svg, "title", {"id": "title"}, f"{username}'s public contribution calendar snake")
    add(svg, "desc", {"id": "desc"},
        f"Animated snake over GitHub's publicly visible daily intensity levels, "
        f"{first.isoformat()} to {last.isoformat()}. Levels range from 0 to 4. "
        "Private activity and contribution counts are not inferred.")
    add(svg, "rect", {"width": "100%", "height": "100%", "fill": background, "rx": "6"})
    add(svg, "text", {"x": "10", "y": "17", "fill": foreground,
        "font-family": "sans-serif", "font-size": "11"},
        f"Public contribution intensity · {first.isoformat()} – {last.isoformat()}")
    for row, label in [(1, "Mon"), (3, "Wed"), (5, "Fri")]:
        add(svg, "text", {"x": "5", "y": str(41 + row * 15), "fill": foreground,
            "font-family": "sans-serif", "font-size": "9"}, label)
    positions = {}
    grid = add(svg, "g")
    for day, level in cells:
        index = (day - sunday).days
        column, row = divmod(index, 7)
        x, y = 35 + column * 15, 32 + row * 15
        tile = add(grid, "rect", {"x": str(x), "y": str(y), "width": "10",
            "height": "10", "rx": "2", "fill": palette[level]})
        add(tile, "title", text=f"{day.isoformat()}: public intensity level {level} of 4")
        positions.setdefault(column, []).append((x + 5, y + 5))
    route = []
    for column, points in sorted(positions.items()):
        route.extend(sorted(points, key=lambda point: point[1], reverse=bool(column % 2)))
    # Return around the calendar margin so the animation loops without a jump.
    route.extend([(width - 6, route[-1][1]), (width - 6, 141),
                  (28, 141), (28, route[0][1]), route[0]])
    path = "M " + " L ".join(f"{x},{y}" for x, y in route)
    for segment in range(8, -1, -1):
        body = add(svg, "g", {"fill": snake_color})
        if segment:
            add(body, "circle", {"r": str(max(2, 4.2 - segment * 0.22))})
        else:
            add(body, "rect", {"x": "-5", "y": "-4", "width": "10", "height": "8", "rx": "3"})
            for y in (-2, 2):
                add(body, "circle", {"cx": "2", "cy": str(y), "r": "0.9", "fill": background})
        add(body, "animateMotion", {"path": path, "dur": "45s", "repeatCount": "indefinite",
            "rotate": "auto", "begin": f"-{(9 - segment) * 0.12:.2f}s", "calcMode": "paced"})
    add(svg, "text", {"x": "10", "y": "153", "fill": foreground,
        "font-family": "sans-serif", "font-size": "9"}, "Intensity: 0 (none visible) → 4 (highest)")
    return ET.tostring(svg, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="zhuang768")
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", args.username):
        parser.error("Invalid GitHub username")
    try:
        cells = fetch_calendar(args.username)
        outputs = {
            "github-contribution-grid-snake.svg": make_svg(args.username, cells),
            "github-contribution-grid-snake-dark.svg": make_svg(args.username, cells, dark=True),
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for filename, data in outputs.items():
            ET.fromstring(data)
            (args.output_dir / filename).write_bytes(data)
        print(f"Generated two SVGs from {len(cells)} verified public dates "
              f"({cells[0][0]} to {cells[-1][0]}) in {args.output_dir}")
    except (OSError, ValueError) as error:
        print(f"Cannot generate snake: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
