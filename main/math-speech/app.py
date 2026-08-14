"""Small HTTP boundary around MathCAT for Vietnamese mathematical speech."""

from __future__ import annotations

import os
import re
import sys
import threading
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from latex2mathml.converter import convert as latex_to_mathml
from pydantic import BaseModel, Field, model_validator

from vietnamese_renderer import UnsupportedMathML, render_mathml


BASE_DIR = Path(__file__).resolve().parent
VENDOR_DIR = BASE_DIR / "vendor"
# scripts/apply_rule_overrides.py writes the corrected Vietnamese rules here;
# fall back to the pristine upstream tree if that build step has not been run.
PATCHED_RULES_DIR = BASE_DIR / "rules"
_DEFAULT_RULES_DIR = (
    PATCHED_RULES_DIR if PATCHED_RULES_DIR.is_dir() else VENDOR_DIR / "Rules"
)
RULES_DIR = Path(os.getenv("MATHCAT_RULES_DIR", _DEFAULT_RULES_DIR))
LANGUAGE = os.getenv("MATHCAT_LANGUAGE", "vi")
SPEECH_STYLE = os.getenv("MATHCAT_SPEECH_STYLE", "SimpleSpeak")
MAX_INPUT_CHARS = int(os.getenv("MATHCAT_MAX_INPUT_CHARS", "16000"))

sys.path.insert(0, str(VENDOR_DIR))
try:
    import libmathcat_py as mathcat
except ImportError as exc:  # pragma: no cover - exercised by container smoke test
    raise RuntimeError(
        "Missing MathCAT native module. Run scripts/bootstrap_vendor.sh first."
    ) from exc


_MATHCAT_LOCK = threading.RLock()


def _configure_mathcat_for_current_thread() -> None:
    # MathCAT stores part of its rule/preference context per native thread.
    # FastAPI runs sync endpoints in a thread pool, so configure the worker that
    # will immediately perform SetMathML/GetSpokenText.
    mathcat.SetRulesDir(str(RULES_DIR))
    mathcat.SetPreference("TTS", "none")
    mathcat.SetPreference("Language", LANGUAGE)
    mathcat.SetPreference("SpeechStyle", SPEECH_STYLE)


with _MATHCAT_LOCK:
    _configure_mathcat_for_current_thread()


class SpeakRequest(BaseModel):
    latex: str | None = Field(default=None, max_length=MAX_INPUT_CHARS)
    mathml: str | None = Field(default=None, max_length=MAX_INPUT_CHARS)

    @model_validator(mode="after")
    def exactly_one_input(self) -> "SpeakRequest":
        values = (self.latex is not None, self.mathml is not None)
        if sum(values) != 1:
            raise ValueError("Provide exactly one of 'latex' or 'mathml'")
        return self


class SpeakResponse(BaseModel):
    ok: bool
    text: str


def _tidy(spoken: str) -> str:
    # A semicolon can force the downstream sentence splitter to pause too early.
    spoken = re.sub(r"\s*;\s*", ", ", spoken)
    # Several rules emit their word already padded with spaces, so the raw text
    # comes back with runs of blanks ("x  khác 5") that some TTS voices stutter on.
    spoken = re.sub(r"\s+", " ", spoken)
    spoken = re.sub(r"\s+([,.])", r"\1", spoken)
    spoken = re.sub(r"(,\s*){2,}", ", ", spoken)
    return spoken.strip().strip(",").strip()


@lru_cache(maxsize=2048)
def _speak_mathml(mathml: str) -> str:
    # The local renderer guarantees the Vietnamese wording and audible scope of
    # common structures. MathCAT remains the broad fallback for uncommon MathML
    # elements/operators, so adding deterministic rules never narrows coverage.
    if LANGUAGE == "vi":
        try:
            spoken = render_mathml(mathml)
            if spoken:
                return _tidy(spoken)
        except (UnsupportedMathML, ValueError):
            pass
    with _MATHCAT_LOCK:
        _configure_mathcat_for_current_thread()
        mathcat.SetMathML(mathml)
        spoken = mathcat.GetSpokenText()
    return _tidy(spoken)


app = FastAPI(title="Math speech sidecar", version="1.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mathcat_version": mathcat.GetVersion(),
        "language": LANGUAGE,
        "speech_style": SPEECH_STYLE,
        "renderer": "structured-vi+mathcat" if LANGUAGE == "vi" else "mathcat",
    }


@app.post("/speak", response_model=SpeakResponse)
def speak(request: SpeakRequest) -> SpeakResponse:
    try:
        mathml = request.mathml
        if request.latex is not None:
            mathml = latex_to_mathml(request.latex.strip())
        assert mathml is not None
        text = _speak_mathml(mathml.strip())
        return SpeakResponse(ok=True, text=text)
    except Exception as exc:
        # The caller keeps the source formula as a fail-safe; a 422/503 must not
        # terminate the main voice pipeline.
        raise HTTPException(status_code=422, detail=f"Cannot speak formula: {exc}") from exc
