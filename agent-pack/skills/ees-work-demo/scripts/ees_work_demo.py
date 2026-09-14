"""Authenticated, read-only delivery of the browser-only EES Work demonstration.

Installed by the pinned wheel builder, never registered as an Open WebUI Tool.
No business client, model invocation, user content, or storage is involved.
"""

from pathlib import Path

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse


FILES = {"index.html": "text/html", "ees-work.css": "text/css", "ees-work.js": "text/javascript"}
HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'none'; "
        "frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
    ),
}


def install(app, verified_user):
    """Use the host's existing verified-user dependency and fixed local files."""
    directory = Path(__file__).resolve().with_name("ees_work_demo_ui")

    async def deliver(asset):
        if asset not in FILES:
            raise HTTPException(status_code=404, detail="Not found")
        path = directory / asset
        if path.is_symlink() or not path.is_file():
            raise HTTPException(status_code=404, detail="Demo file unavailable")
        return FileResponse(path, media_type=FILES[asset], headers=HEADERS)

    @app.get("/ees-work-demo/", include_in_schema=False)
    async def index(user=Depends(verified_user)):
        return await deliver("index.html")

    @app.get("/ees-work-demo/{asset}", include_in_schema=False)
    async def asset_file(asset: str, user=Depends(verified_user)):
        return await deliver(asset)
