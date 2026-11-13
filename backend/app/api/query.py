from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import SourceDep
from app.api.schemas import ParseRequest, ParseResponse
from app.engine.query_parser import Catalog, DeterministicQueryParser
from app.services.playlists import PlaylistNotFound, PlaylistNotImported

router = APIRouter(prefix="/api", tags=["query"])
_parser = DeterministicQueryParser()


@router.post("/parse-query", response_model=ParseResponse)
async def parse_query(body: ParseRequest, source: SourceDep) -> ParseResponse:
    try:
        playlist = await source.get(body.playlist_id)
    except PlaylistNotImported:
        raise HTTPException(status_code=409, detail="Import this playlist first") from None
    except PlaylistNotFound:
        raise HTTPException(status_code=404, detail="Playlist not found") from None
    result = _parser.parse(body.text, Catalog.from_entries(playlist.entries))
    return ParseResponse.model_validate(result.model_dump())
