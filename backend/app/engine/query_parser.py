"""Turn a typed request into a validated ``QuerySpec``.

The deterministic parser is the baseline and the only parser shipped. It never
invents songs: every artist or album it returns is resolved against the
metadata of the selected playlist. Names it cannot find are reported back as
unrecognized, names that match several things are returned as ambiguities for
the user to pick from, and requests the app cannot honour are listed as
unsupported with a reason.

A pluggable ``QueryParser`` protocol exists so an optional model-based parser
could be added later. Any such parser may only see the user's own text, never
Spotify-derived playlist data (see docs/spotify-compatibility.md).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from app.engine.models import PlaylistEntry, QuerySpec, ShuffleMode, normalize_name

MAX_QUERY_LENGTH = 500
MAX_NAME_TOKENS = 8

EDITION_RE = re.compile(
    r"\s*[\(\[][^)\]]*(deluxe|remaster|expanded|edition|anniversary|bonus|version)[^)\]]*[\)\]]",
    re.IGNORECASE,
)

Kind = Literal["artist", "album"]
Polarity = Literal["include", "exclude"]


# ----------------------------------------------------------------------- catalog


@dataclass
class CatalogItem:
    id: str
    name: str
    kind: Kind
    count: int
    detail: str = ""


@dataclass
class Catalog:
    """Artist and album names that actually occur in one playlist."""

    artists: dict[str, list[CatalogItem]] = field(default_factory=dict)  # by normalized name
    albums: dict[str, list[CatalogItem]] = field(default_factory=dict)  # by normalized name
    album_bases: dict[str, list[CatalogItem]] = field(default_factory=dict)  # edition-free title
    artist_tokens: dict[str, list[CatalogItem]] = field(default_factory=dict)  # single name words
    album_artist: dict[str, set[str]] = field(default_factory=dict)  # album id -> artist ids

    @classmethod
    def from_entries(cls, entries: Sequence[PlaylistEntry]) -> Catalog:
        artist_counts: Counter[str] = Counter()
        artist_names: dict[str, str] = {}
        album_counts: Counter[str] = Counter()
        album_info: dict[str, tuple[str, str]] = {}
        album_artist: dict[str, set[str]] = defaultdict(set)
        for e in entries:
            for a in e.artists:
                artist_counts[a.key] += 1
                artist_names.setdefault(a.key, a.name)
            if e.album and e.album.key and e.album.name:
                k = e.album.key
                album_counts[k] += 1
                owners = e.album.artists or e.artists[:1]
                album_info.setdefault(k, (e.album.name, ", ".join(a.name for a in owners)))
                album_artist[k].update(a.key for a in e.artists)

        cat = cls(album_artist=dict(album_artist))
        for k, n in artist_counts.items():
            item = CatalogItem(k, artist_names[k], "artist", n)
            norm = normalize_name(item.name)
            cat.artists.setdefault(norm, []).append(item)
            words = norm.split()
            if len(words) > 1:
                for w in words:
                    if len(w) > 2 and w not in STOPWORDS:
                        cat.artist_tokens.setdefault(w, []).append(item)
        for k, n in album_counts.items():
            name, by = album_info[k]
            item = CatalogItem(k, name, "album", n, detail=f"by {by}")
            cat.albums.setdefault(normalize_name(name), []).append(item)
            base = normalize_name(EDITION_RE.sub("", name))
            cat.album_bases.setdefault(base, []).append(item)
        # Disambiguate same-named artists by an album they appear on.
        for items in cat.artists.values():
            if len(items) > 1:
                for item in items:
                    top = max(
                        (aid for aid, arts in cat.album_artist.items() if item.id in arts),
                        key=lambda aid: album_counts[aid],
                        default=None,
                    )
                    if top:
                        item.detail = f"appears on {album_info[top][0]}"
        return cat


# ---------------------------------------------------------------------- results


class EntityOption(BaseModel):
    id: str
    name: str
    kind: Kind
    entry_count: int
    detail: str = ""


class ResolvedEntity(BaseModel):
    text: str
    polarity: Polarity
    kind: Kind
    options: list[EntityOption]  # all of them apply (for example every edition of an album)


class Ambiguity(BaseModel):
    text: str
    polarity: Polarity
    question: str
    options: list[EntityOption]


class ParseResult(BaseModel):
    query: str
    spec: QuerySpec | None
    draft_spec: QuerySpec | None = None  # resolved parts only, while clarification is pending
    resolved: list[ResolvedEntity] = Field(default_factory=list)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    unrecognized: list[str] = Field(default_factory=list)
    unsupported: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    set_fields: list[str] = Field(default_factory=list)

    @property
    def needs_clarification(self) -> bool:
        return bool(self.ambiguities or self.contradictions)


class QueryParser(Protocol):
    def parse(self, text: str, catalog: Catalog) -> ParseResult: ...


# ------------------------------------------------------------------ vocabulary

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "me",
    "my",
    "i",
    "please",
    "some",
    "all",
    "any",
    "every",
    "is",
    "are",
    "be",
    "it",
    "that",
    "this",
    "these",
    "those",
    "for",
    "with",
    "by",
    "from",
    "off",
    "only",
    "just",
    "songs",
    "song",
    "tracks",
    "track",
    "music",
    "play",
    "playing",
    "give",
    "make",
    "want",
    "would",
    "like",
    "can",
    "you",
    "let",
    "s",
    "playlist",
    "already",
    "album",
    "albums",
    "artist",
    "artists",
    "stuff",
    "everything",
    "but",
    "also",
    "plus",
    "too",
    "include",
    "including",
    "except",
    "excluding",
    "exclude",
    "without",
    "no",
    "not",
    "nothing",
    "minus",
    "skip",
    "skipping",
    "leave",
    "out",
    "remove",
    "drop",
    "then",
    "mix",
    "shuffle",
    "shuffled",
    "order",
    "ordered",
    "queue",
    "list",
    "here",
    "now",
    "them",
    "their",
    "his",
    "her",
    "its",
    "anything",
    "have",
    "has",
    "do",
    "dont",
    "don",
    "t",
    "get",
    "put",
    "keep",
    "keeping",
    "as",
    "well",
    "same",
    "into",
    "up",
    "one",
    "ones",
    "something",
    "ok",
    "okay",
    "hey",
    "via",
    "featuring",
    "feat",
    "ft",
    "w",
    "first",
    "so",
    "features",
    "feature",
    "versions",
    "version",
    "lot",
    "bunch",
    "more",
}

EXCLUDE_TRIGGERS = [
    ("but", "not"),
    ("leave", "out"),
    ("nothing", "from"),
    ("nothing", "by"),
    ("except",),
    ("excluding",),
    ("exclude",),
    ("without",),
    ("minus",),
    ("skip",),
    ("skipping",),
    ("no",),
    ("not",),
    ("remove",),
    ("drop",),
    ("ignore",),
    ("ignoring",),
    ("hold",),
    ("delete",),
]
INCLUDE_TRIGGERS = [
    ("but", "include"),
    ("only",),
    ("just",),
    ("include",),
    ("including",),
    ("plus",),
    ("also",),
    ("add",),
    ("with",),
    ("featuring",),
    ("feat",),
    ("ft",),
]
CONJUNCTIONS = {"and", "or", "plus", "also"}
ARTIST_CUES_BEFORE = {"by", "artist", "featuring", "feat", "ft", "with"}
ALBUM_CUES_BEFORE = {"from", "off", "album", "on"}
ARTIST_CUES_AFTER = {"songs", "song", "tracks", "track", "features", "stuff", "music"}
ALBUM_CUES_AFTER = {"album", "lp", "ep", "record"}

UNSUPPORTED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\b(most|least) played\b|\bplay counts?\b|\blistening history\b"),
        "Play counts are not available from the Spotify Web API, so ordering by plays is not supported.",
    ),
    (
        re.compile(
            r"\b((most|least) )?popular(ity)?\b|\btop (songs|tracks|hits)\b|"
            r"\bbiggest hits\b|\bhits\b"
        ),
        "Popularity is not available to this app, so it cannot pick hits.",
    ),
    (
        re.compile(r"\bdeep cuts?\b"),
        "Deep cuts mode needs an honest popularity source, which this app does not have yet.",
    ),
    (
        re.compile(r"\bsimilar\b|\brecommend|\bdiscover|\bnew music\b|\bsounds like\b"),
        "Recommendations are out of scope: PlaylistIQ only works with songs already in the playlist.",
    ),
    (
        re.compile(r"\bnot (already )?in (this|the|my) playlist\b|\badd (new |more |other )?songs\b"),
        "PlaylistIQ only selects songs already in this playlist; it cannot add new ones.",
    ),
    (
        re.compile(
            r"\b((high|low) )?(bpm|tempo|energy|mood|vibe|danceab\w*|acoustic\w*|"
            r"instrumental|chill|hype|sad|happy|upbeat|mellow|genre|lyrics)\b"
        ),
        "Audio features, moods and genres are not available, so they cannot be used as filters.",
    ),
    (
        re.compile(
            r"\bfor (studying|study|working out|the gym|a workout|running|sleep|sleeping|"
            r"a party|parties|driving|work|focus)\b"
        ),
        "Activities and contexts are not available, so they cannot be used as filters.",
    ),
    (
        re.compile(r"\bexplicit\b|\bclean (version|songs|tracks)\b"),
        "Filtering by explicit content is not supported yet.",
    ),
    (
        re.compile(
            r"\b((19|20)?\d0s|nineties|eighties|seventies|sixties)\b|"
            r"\breleased (in|before|after|between)( (19|20)\d\d)?\b|"
            r"\brelease (year|date)\b|\bfrom (19|20)\d\d\b"
        ),
        "Filtering by release year is not supported yet.",
    ),
    (
        re.compile(r"\b(delete|edit|modify|change|reorder|overwrite)\b.*\b(my|the|this) playlist\b"),
        "PlaylistIQ never modifies your original playlist. Use export to create a new one.",
    ),
    (
        re.compile(r"\bon (my )?(phone|speaker|tv|device)\b|\bstart playing\b|\bplay it now\b"),
        "PlaylistIQ previews an order and can export a new playlist; it does not control playback.",
    ),
]

# (pattern, handler) pairs for ordering instructions. Matched spans are blanked
# out before entity matching so words like "no" in "no same artist back to back"
# are not read as exclusions.
_N = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def _num(text: str) -> int:
    return NUMBER_WORDS.get(text, int(text) if text.isdigit() else 1)


ORDER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\bat least {_N} (songs?|tracks?) (between|apart|gap)\b"), "gap_n"),
    (re.compile(rf"\b{_N} (songs?|tracks?) apart\b"), "gap_n"),
    (re.compile(rf"\b(gap|spacing|space) (of )?{_N}\b"), "gap_n_last"),
    (
        re.compile(
            rf"\b(no|avoid|never|don t|dont) (the )?same artist(s)? (twice )?within "
            rf"(any )?{_N} (songs?|tracks?)\b"
        ),
        "gap_within",
    ),
    (
        re.compile(
            r"\b(no|avoid|never|don t|dont|without|not) (the )?(same artist|repeat(ed)? "
            r"artists?|artist repeats?|repeats?|repeating|"
            r"consecutive (songs|tracks)? ?(by|from) the same artist)"
            r"( twice)?( (back to back|in a row|consecutively|next to each other|"
            r"one after another|consecutive))?\b"
        ),
        "gap_1",
    ),
    (
        re.compile(
            r"\b(avoid|no|without) (back to back|consecutive) (songs?|tracks?|artists?)?"
            r"( (by|from) the same artist)?\b"
        ),
        "gap_1",
    ),
    (re.compile(r"\bback to back\b|\bin a row\b"), "gap_1"),
    (
        re.compile(
            r"\b(spread (them |it |the artists |artists )?out|mix (it|them) up|"
            r"balanced?|variety|vary the artists|evenly)\b"
        ),
        "balanced",
    ),
    (
        re.compile(
            r"\b(true|truly|pure|purely|completely|fully|totally|just) random(ly)?\b|"
            r"\brandom (order|shuffle)\b|\brandomly\b|\brandomise\b|\brandomize\b|"
            r"\bfisher yates\b|\brandom\b"
        ),
        "random",
    ),
    (
        re.compile(
            r"\b(recently|newly|most recently|latest|newest|last) added\b|"
            r"\bnewest (first|songs|tracks|additions)\b|\bnew additions\b|"
            r"\b(recently|newly|latest|last) added first\b|"
            r"\blatest additions\b|\bwhat i added recently\b"
        ),
        "recent",
    ),
    (re.compile(r"\bstrict(ly)?\b|\bmust never\b|\bguarantee\b"), "strict"),
    (re.compile(r"\bseed (\d{1,18})\b"), "seed"),
    (
        re.compile(
            r"\b(primary|lead|main) artists? only\b|\bonly (the )?(primary|lead|main) "
            r"artists?\b|\b(no|without|exclude|excluding|skip) (features|feats|collabs|"
            r"collaborations|guest (spots|verses|appearances))\b"
        ),
        "primary",
    ),
]


# ----------------------------------------------------------------------- parser


@dataclass
class _Mention:
    start: int
    end: int
    text: str
    artists: list[CatalogItem]
    albums: list[CatalogItem]
    album_editions: bool
    partial: bool
    polarity: Polarity = "include"


class DeterministicQueryParser:
    """Rule-based parser. Fast, explainable, and fully offline."""

    def parse(self, text: str, catalog: Catalog) -> ParseResult:
        result = ParseResult(query=text, spec=None)
        if len(text) > MAX_QUERY_LENGTH:
            result.unsupported.append(f"Requests are limited to {MAX_QUERY_LENGTH} characters.")
            return result

        spec_fields: dict[str, object] = {}
        norm = normalize_name(text.replace("-", " "))

        for pattern, reason in UNSUPPORTED_PATTERNS:
            if pattern.search(norm):
                result.unsupported.append(reason)
                norm = pattern.sub(" | ", norm)

        norm = self._extract_ordering(norm, spec_fields, result)
        tokens = norm.split()
        mentions = self._find_mentions(tokens, catalog)
        self._assign_polarity(tokens, mentions)

        include: dict[Kind, list[str]] = {"artist": [], "album": []}
        exclude: dict[Kind, list[str]] = {"artist": [], "album": []}
        include_artist_ids = {
            i.id for m in mentions if m.polarity == "include" and len(m.artists) == 1 for i in m.artists
        }

        prev: tuple[_Mention, Kind] | None = None
        for m in mentions:
            sibling_kind = None
            if prev and m.start - prev[0].end == 1 and tokens[prev[0].end] in CONJUNCTIONS:
                sibling_kind = prev[1]
            elif prev and m.start == prev[0].end and prev[0].polarity == m.polarity:
                sibling_kind = prev[1]  # list written with commas, now removed
            kind, options, ambiguous_reason = self._classify(
                m, tokens, include_artist_ids, catalog, sibling_kind
            )
            prev = (m, kind) if kind else None
            if ambiguous_reason:
                result.ambiguities.append(
                    Ambiguity(
                        text=m.text,
                        polarity=m.polarity,
                        question=ambiguous_reason,
                        options=[_opt(o) for o in options],
                    )
                )
                continue
            assert kind is not None
            target = include if m.polarity == "include" else exclude
            for o in options:
                if o.id not in target[kind]:
                    target[kind].append(o.id)
            result.resolved.append(
                ResolvedEntity(
                    text=m.text, polarity=m.polarity, kind=kind, options=[_opt(o) for o in options]
                )
            )
            if kind == "album" and len(options) > 1:
                result.notes.append(
                    f'"{m.text}" matched {len(options)} editions: ' + ", ".join(o.name for o in options) + "."
                )

        result.unrecognized = self._leftovers(tokens, mentions)

        for kind, ids in include.items():
            clash = [i for i in ids if i in exclude[kind]]
            for i in clash:
                name = next(o.name for r in result.resolved for o in r.options if o.id == i)
                msg = f"{name} is both included and excluded. Which one did you mean?"
                if msg not in result.contradictions:
                    result.contradictions.append(msg)

        spec_fields.update(
            {
                "include_artist_ids": include["artist"],
                "exclude_artist_ids": exclude["artist"],
                "include_album_ids": include["album"],
                "exclude_album_ids": exclude["album"],
            }
        )
        result.set_fields = sorted(k for k, v in spec_fields.items() if v not in ([], None))
        if result.contradictions:
            return result
        if spec_fields.get("shuffle_mode") == ShuffleMode.RANDOM and "minimum_artist_gap" in spec_fields:
            spec_fields["shuffle_mode"] = ShuffleMode.BALANCED
            result.notes.append(
                "Asked for random order and artist spacing; used balanced mode, which "
                "randomizes while keeping the spacing."
            )
        try:
            spec = QuerySpec.model_validate(spec_fields)
        except ValidationError as exc:  # pragma: no cover - guarded above
            result.contradictions.append(str(exc))
            return result
        # Never hand back a runnable spec while a name is unresolved: dropping it
        # silently could select far more (or fewer) songs than the user asked for.
        if result.ambiguities:
            result.draft_spec = spec
        else:
            result.spec = spec
        return result

    # ordering ---------------------------------------------------------------
    def _extract_ordering(self, norm: str, fields: dict[str, object], result: ParseResult) -> str:
        for pattern, action in ORDER_PATTERNS:
            for m in pattern.finditer(norm):
                if action == "gap_n":
                    fields["minimum_artist_gap"] = _num(m.group(1))
                    fields.setdefault("shuffle_mode", ShuffleMode.BALANCED)
                elif action == "gap_n_last":
                    fields["minimum_artist_gap"] = _num(m.groups()[-1])
                    fields.setdefault("shuffle_mode", ShuffleMode.BALANCED)
                elif action == "gap_within":
                    fields["minimum_artist_gap"] = _num(m.group(6))
                    fields.setdefault("shuffle_mode", ShuffleMode.BALANCED)
                elif action == "gap_1":
                    fields.setdefault("minimum_artist_gap", 1)
                    fields.setdefault("shuffle_mode", ShuffleMode.BALANCED)
                elif action == "balanced":
                    fields.setdefault("shuffle_mode", ShuffleMode.BALANCED)
                elif action == "random":
                    fields["shuffle_mode"] = ShuffleMode.RANDOM
                elif action == "recent":
                    fields["shuffle_mode"] = ShuffleMode.RECENTLY_ADDED
                elif action == "strict":
                    fields["strict_constraints"] = True
                elif action == "seed":
                    fields["seed"] = int(m.group(1))
                elif action == "primary":
                    fields["primary_artist_only"] = True
                    result.notes.append("Only the primary (first-credited) artist is matched.")
            norm = pattern.sub(" | ", norm)
        if fields.get("shuffle_mode") == ShuffleMode.RECENTLY_ADDED and ("minimum_artist_gap" in fields):
            result.notes.append("Recently added mode ignores artist spacing.")
        return norm

    # entity matching --------------------------------------------------------
    def _find_mentions(self, tokens: list[str], cat: Catalog) -> list[_Mention]:
        mentions: list[_Mention] = []
        i = 0
        while i < len(tokens):
            found = None
            for n in range(min(MAX_NAME_TOKENS, len(tokens) - i), 0, -1):
                phrase = " ".join(tokens[i : i + n])
                if "|" in phrase:
                    continue
                artists = cat.artists.get(phrase, [])
                albums = cat.albums.get(phrase, [])
                editions = False
                bases = cat.album_bases.get(phrase, [])
                if len(bases) > len(albums):
                    albums, editions = bases, True
                if n == 1 and phrase in STOPWORDS and not artists:
                    continue
                if artists or albums:
                    found = _Mention(i, i + n, phrase, artists, albums, editions, partial=False)
                    break
            if found is None and tokens[i] in cat.artist_tokens and tokens[i] not in STOPWORDS:
                items = cat.artist_tokens[tokens[i]]
                found = _Mention(i, i + 1, tokens[i], items, [], False, partial=True)
            if found:
                mentions.append(found)
                i = found.end
            else:
                i += 1
        return mentions

    def _assign_polarity(self, tokens: list[str], mentions: list[_Mention]) -> None:
        polarity: Polarity = "include"
        switches: dict[int, Polarity] = {}
        i = 0
        while i < len(tokens):
            matched = False
            for trig, pol in [(t, "exclude") for t in EXCLUDE_TRIGGERS] + [
                (t, "include") for t in INCLUDE_TRIGGERS
            ]:
                if tuple(tokens[i : i + len(trig)]) == trig:
                    switches[i] = pol  # type: ignore[assignment]
                    i += len(trig)
                    matched = True
                    break
            if not matched:
                i += 1
        starts = {m.start: m for m in mentions}
        for i in range(len(tokens)):
            if i in switches:
                polarity = switches[i]
            if i in starts:
                starts[i].polarity = polarity

    def _classify(
        self,
        m: _Mention,
        tokens: list[str],
        include_artist_ids: set[str],
        cat: Catalog,
        sibling_kind: Kind | None = None,
    ) -> tuple[Kind | None, list[CatalogItem], str | None]:
        before = tokens[m.start - 1] if m.start > 0 else ""
        after = tokens[m.end] if m.end < len(tokens) else ""
        artists, albums = m.artists, m.albums

        if artists and albums:
            if before in ALBUM_CUES_BEFORE or after in ALBUM_CUES_AFTER:
                artists = []
            elif before in ARTIST_CUES_BEFORE or after in ARTIST_CUES_AFTER or sibling_kind == "artist":
                albums = []
            elif sibling_kind == "album":
                artists = []
            else:
                return (
                    None,
                    artists + albums,
                    (f'"{m.text}" is both an artist and an album in this playlist. Which one?'),
                )

        if artists:
            # A local file credited by name only is treated as the same artist as the
            # catalog artist with that exact name.
            with_ids = [a for a in artists if not a.id.startswith("local-artist:")]
            same_name = len({normalize_name(a.name) for a in artists}) == 1
            if len(with_ids) <= 1 and same_name:
                return "artist", artists, None
            if len(artists) > 1:
                if m.partial:
                    q = f'"{m.text}" could be several artists in this playlist. Which one?'
                else:
                    q = f'More than one artist called "{artists[0].name}" is in this playlist.'
                return None, artists, q
            return "artist", artists, None

        # Albums: editions of one release are applied together; the same title by
        # different artists is ambiguous unless an included artist settles it.
        owners = {a.detail for a in albums}
        if len(owners) > 1 and include_artist_ids:
            preferred = [a for a in albums if cat.album_artist.get(a.id, set()) & include_artist_ids]
            if preferred:
                albums = preferred
                owners = {a.detail for a in albums}
        if len(owners) > 1:
            return (
                None,
                albums,
                (f'More than one album called "{albums[0].name}" is in this playlist. Which one?'),
            )
        return "album", albums, None

    def _leftovers(self, tokens: list[str], mentions: list[_Mention]) -> list[str]:
        covered = {i for m in mentions for i in range(m.start, m.end)}
        runs: list[str] = []
        current: list[str] = []
        for i, t in enumerate(tokens):
            meaningful = (
                i not in covered and t != "|" and t not in STOPWORDS and not t.isdigit() and len(t) > 1
            )
            if meaningful:
                current.append(t)
            elif current:
                runs.append(" ".join(current))
                current = []
        if current:
            runs.append(" ".join(current))
        return runs


def _opt(item: CatalogItem) -> EntityOption:
    return EntityOption(
        id=item.id, name=item.name, kind=item.kind, entry_count=item.count, detail=item.detail
    )
