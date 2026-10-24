"""SVG-based vector icon provider with crisp Retina high-DPI scaling for ArcVault."""

from __future__ import annotations

from typing import Dict, Optional
from PyQt6.QtCore import QByteArray, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

from arc_vault.core.models import FileCategory


# Clean, modern SVG icon templates (Lucide / Feather inspired)
SVG_ICONS = {
    # App Logo / Vault Lock
    "vault": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
        <circle cx="12" cy="16" r="1.5"/>
    </svg>""",

    "vault_unlocked": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
        <path d="M7 11V7a5 5 0 0 1 9.9-1"/>
        <circle cx="12" cy="16" r="1.5"/>
    </svg>""",

    # Entry point (top level 7z archive folder)
    "entry_point": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
        <rect x="10" y="11" width="8" height="6" rx="1" fill="{color}" fill-opacity="0.2"/>
        <circle cx="14" cy="14" r="1"/>
    </svg>""",

    # Regular Folder
    "folder": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
    </svg>""",

    # Image
    "image": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>
        <circle cx="9" cy="9" r="2"/>
        <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
    </svg>""",

    # Text / Notes
    "text": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="8" y1="13" x2="16" y2="13"/>
        <line x1="8" y1="17" x2="14" y2="17"/>
    </svg>""",

    # Code
    "code": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="16 18 22 12 16 6"/>
        <polyline points="8 6 2 12 8 18"/>
    </svg>""",

    # Document (PDF / Office)
    "document": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/>
        <path d="M6 6h10"/>
        <path d="M6 10h10"/>
        <path d="M6 14h6"/>
    </svg>""",

    # Executables - Windows
    "executable_windows": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="8" height="8" rx="1"/>
        <rect x="13" y="3" width="8" height="8" rx="1"/>
        <rect x="3" y="13" width="8" height="8" rx="1"/>
        <rect x="13" y="13" width="8" height="8" rx="1"/>
    </svg>""",

    # Executables - macOS
    "executable_macos": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8z"/>
        <path d="m9 12 2 2 4-4"/>
    </svg>""",

    # Executables - Unix/Linux
    "executable_unix": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="4 17 10 11 4 5"/>
        <line x1="12" y1="19" x2="20" y2="19"/>
    </svg>""",

    # Archive
    "archive": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect width="20" height="5" x="2" y="3" rx="1"/>
        <path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/>
        <path d="M10 12h4"/>
    </svg>""",

    # Audio
    "audio": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M9 18V5l12-2v13"/>
        <circle cx="6" cy="18" r="3"/>
        <circle cx="18" cy="16" r="3"/>
    </svg>""",

    # Video
    "video": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect width="14" height="14" x="2" y="5" rx="2"/>
        <polygon points="16 10 22 7 22 17 16 14"/>
    </svg>""",

    # Keys / Certificates
    "key_cert": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="7.5" cy="15.5" r="5.5"/>
        <path d="m21 2-9.6 9.6"/>
        <path d="m15.5 7.5 3 3L22 7l-3-3"/>
    </svg>""",

    # Generic file
    "generic": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
        <polyline points="14 2 14 8 20 8"/>
    </svg>""",

    # UI Actions
    "plus": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="12" y1="5" x2="12" y2="19"/>
        <line x1="5" y1="12" x2="19" y2="12"/>
    </svg>""",

    # Inward arrow (importing/adding files into archive)
    "add_file": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/>
        <path d="M12 12v9"/>
        <path d="m8 17 4 4 4-4"/>
    </svg>""",

    # Outward arrow (exporting/extracting files out to local disk)
    "export": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/>
        <path d="M12 12v9"/>
        <path d="m16 16-4-4-4 4"/>
    </svg>""",

    # Dedicated logs pane icon
    "logs": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/>
        <line x1="16" y1="17" x2="8" y2="17"/>
        <polyline points="10 9 9 9 8 9"/>
    </svg>""",

    "trash": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="3 6 5 6 21 6"/>
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
    </svg>""",

    "edit": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>""",

    "save": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
        <polyline points="17 21 17 13 7 13 7 21"/>
        <polyline points="7 3 7 8 15 8"/>
    </svg>""",

    "arrow_up": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="12" y1="19" x2="12" y2="5"/>
        <polyline points="5 12 12 5 19 12"/>
    </svg>""",

    "refresh": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
    </svg>""",

    "sun": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="5"/>
        <line x1="12" y1="1" x2="12" y2="3"/>
        <line x1="12" y1="21" x2="12" y2="23"/>
        <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
        <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
        <line x1="1" y1="12" x2="3" y2="12"/>
        <line x1="21" y1="12" x2="23" y2="12"/>
        <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
        <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>""",

    "moon": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>""",

    "preview": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
        <line x1="15" y1="3" x2="15" y2="21"/>
    </svg>""",
}

# Category colors for Light and Dark themes
CATEGORY_COLORS_DARK = {
    FileCategory.ENTRY_POINT: "#38BDF8",  # Sky Blue
    FileCategory.FOLDER: "#FBBF24",       # Amber
    FileCategory.IMAGE: "#A78BFA",        # Purple
    FileCategory.TEXT: "#34D399",         # Emerald
    FileCategory.CODE: "#60A5FA",         # Blue
    FileCategory.DOCUMENT: "#F472B6",     # Pink
    FileCategory.EXECUTABLE_WINDOWS: "#F87171",  # Red
    FileCategory.EXECUTABLE_MACOS: "#FB7185",    # Rose
    FileCategory.EXECUTABLE_UNIX: "#34D399",     # Mint
    FileCategory.ARCHIVE: "#F59E0B",      # Orange
    FileCategory.AUDIO: "#818CF8",        # Indigo
    FileCategory.VIDEO: "#EC4899",        # Magenta
    FileCategory.KEY_CERT: "#EAB308",     # Gold
    FileCategory.GENERIC: "#94A3B8",      # Slate
}

CATEGORY_COLORS_LIGHT = {
    FileCategory.ENTRY_POINT: "#0284C7",
    FileCategory.FOLDER: "#D97706",
    FileCategory.IMAGE: "#7C3AED",
    FileCategory.TEXT: "#059669",
    FileCategory.CODE: "#2563EB",
    FileCategory.DOCUMENT: "#DB2777",
    FileCategory.EXECUTABLE_WINDOWS: "#DC2626",
    FileCategory.EXECUTABLE_MACOS: "#E11D48",
    FileCategory.EXECUTABLE_UNIX: "#059669",
    FileCategory.ARCHIVE: "#D97706",
    FileCategory.AUDIO: "#4F46E5",
    FileCategory.VIDEO: "#BE185D",
    FileCategory.KEY_CERT: "#CA8A04",
    FileCategory.GENERIC: "#64748B",
}


class IconProvider:
    """Caches and provides SVG-based QIcons and QPixmaps with crisp Retina scaling."""

    _cache: Dict[str, QIcon] = {}
    _pixmap_cache: Dict[str, QPixmap] = {}

    @classmethod
    def _render_svg_pixmap(cls, renderer: QSvgRenderer, size: int, dpr: float) -> QPixmap:
        """
        Render an SVG directly to a QImage of exact physical dimensions (size * dpr),
        then assign devicePixelRatio(dpr) and convert to QPixmap.
        This completely avoids painter coordinate double-scaling under high-DPI displays.
        """
        phys = max(1, int(round(size * dpr)))
        img = QImage(phys, phys, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        renderer.render(painter, QRectF(0.0, 0.0, float(phys), float(phys)))
        painter.end()

        img.setDevicePixelRatio(dpr)
        pixmap = QPixmap.fromImage(img)
        pixmap.setDevicePixelRatio(dpr)
        return pixmap

    @classmethod
    def get_category_icon(cls, category: FileCategory, dark_mode: bool = True, size: int = 24) -> QIcon:
        """Get icon for a specific file category."""
        key_name = category.value
        svg_key = key_name
        if svg_key not in SVG_ICONS:
            svg_key = "generic"

        color_map = CATEGORY_COLORS_DARK if dark_mode else CATEGORY_COLORS_LIGHT
        color = color_map.get(category, "#94A3B8" if dark_mode else "#64748B")
        return cls.get_icon(svg_key, color=color, dark_mode=dark_mode, size=size)

    @classmethod
    def get_category_pixmap(
        cls,
        category: FileCategory,
        size: int = 64,
        dark_mode: bool = True,
        dpr: Optional[float] = None,
    ) -> QPixmap:
        """Directly render a file category icon as a crisp Retina high-DPI QPixmap."""
        svg_key = category.value if category.value in SVG_ICONS else "generic"
        color_map = CATEGORY_COLORS_DARK if dark_mode else CATEGORY_COLORS_LIGHT
        color = color_map.get(category, "#94A3B8" if dark_mode else "#64748B")
        return cls.get_pixmap(svg_key, size=size, color=color, dark_mode=dark_mode, dpr=dpr)

    @classmethod
    def get_icon(cls, name: str, color: Optional[str] = None, dark_mode: bool = True, size: int = 24) -> QIcon:
        """
        Get or render SVG icon populated with standard and Retina (2x/3x) pixmaps
        with antialiasing to prevent pixelation on MacBooks and HiDPI displays.
        """
        if color is None:
            color = "#F1F5F9" if dark_mode else "#1E293B"

        cache_key = f"{name}_{color}_{size}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        svg_template = SVG_ICONS.get(name)
        if not svg_template:
            svg_template = SVG_ICONS["generic"]

        svg_data = svg_template.format(color=color).encode("utf-8")
        renderer = QSvgRenderer(QByteArray(svg_data))

        icon = QIcon()

        # Add 1x, 2x (Retina), and 3x pixmaps for the requested logical size
        for dpr in (1.0, 2.0, 3.0):
            icon.addPixmap(cls._render_svg_pixmap(renderer, size, dpr))

        # Also register common standard UI sizes so scaling across any Qt component
        # (e.g. QToolBar at 20px/24px/32px, QMenu, QToolButton) always has a razor-sharp pixel-exact render
        common_sizes = (16, 18, 20, 22, 24, 28, 32, 48, 64)
        for s in common_sizes:
            if s == size:
                continue
            for dpr in (1.0, 2.0, 3.0):
                icon.addPixmap(cls._render_svg_pixmap(renderer, s, dpr))

        cls._cache[cache_key] = icon
        return icon

    @classmethod
    def get_pixmap(
        cls,
        name: str,
        size: int = 24,
        color: Optional[str] = None,
        dark_mode: bool = True,
        dpr: Optional[float] = None,
    ) -> QPixmap:
        """Render SVG directly into a high-DPI Retina QPixmap with proper devicePixelRatio."""
        if color is None:
            color = "#F1F5F9" if dark_mode else "#1E293B"

        if dpr is None:
            app = QApplication.instance()
            screen = app.primaryScreen() if app else None
            dpr = screen.devicePixelRatio() if screen else 2.0

        cache_key = f"{name}_{color}_{size}_{dpr}"
        if cache_key in cls._pixmap_cache:
            return cls._pixmap_cache[cache_key]

        svg_template = SVG_ICONS.get(name)
        if not svg_template:
            svg_template = SVG_ICONS["generic"]

        svg_data = svg_template.format(color=color).encode("utf-8")
        renderer = QSvgRenderer(QByteArray(svg_data))

        pixmap = cls._render_svg_pixmap(renderer, size, dpr)
        cls._pixmap_cache[cache_key] = pixmap
        return pixmap

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()
        cls._pixmap_cache.clear()
