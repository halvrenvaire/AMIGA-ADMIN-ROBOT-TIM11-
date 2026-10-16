"""Mode produksi (deploy EC2): dashboard dan API dari SATU proses dan SATU port.

    uvicorn app.serve:app --host 0.0.0.0 --port 3000

- /api/...  -> API AMIGA (app.main), sama dengan proxy /api di Vite saat development
- /assets/... dan file lain di frontend/dist -> hasil `npm run build`
- alamat lain (mis. /dokumen/123) -> index.html, supaya refresh di halaman React tidak 404
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.config import BACKEND_DIR
from app.main import app as api

DIST = BACKEND_DIR.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Starlette tidak menjalankan lifespan aplikasi yang di-mount, jadi startup API (Bedrock, index SOP,
    # pembaca invoice) dijalankan dari sini
    async with api.router.lifespan_context(api):
        yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/api", api)


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if not (DIST / "index.html").is_file():
        raise HTTPException(503, "Frontend belum di-build. Jalankan `npm run build` di folder frontend.")
    file = (DIST / path).resolve()
    # Hanya file di dalam frontend/dist yang boleh disajikan (cegah ../ keluar folder)
    if path and file.is_file() and file.is_relative_to(DIST.resolve()):
        return FileResponse(file)
    if Path(path).suffix and not path.endswith(".html"):
        raise HTTPException(404, "File tidak ditemukan")
    return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
