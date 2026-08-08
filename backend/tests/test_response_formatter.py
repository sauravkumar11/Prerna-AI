"""Tests for voice.response_formatter — the semantic cleanup layer that
strips raw implementation-detail text (paths, URLs, YouTube titles, window
titles) before it reaches TTS. Covers every category named in the v1.1 UX
spec: YouTube titles, file paths, URLs, window titles, long technical
strings, and natural-text passthrough."""
import pytest

from voice.response_formatter import format_for_speech


# ── YouTube / media titles ─────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ('Playing "DILBAR Lyrical | Satyameva Jayate | John Abraham, Nora Fatehi"', "Playing Dilbar."),
    ('Playing "believer imagine dragons official video"', "Playing Believer Imagine Dragons."),
    ('Playing "Shape of You"', "Playing Shape of You."),  # already-clean title left as-is, not re-cased
])
def test_youtube_titles_stripped_to_core_name(text, expected):
    assert format_for_speech(text) == expected


def test_playing_with_a_url_defers_to_url_cleaner_not_title_cleaner():
    """A URL passed where a title was expected shouldn't get mangled into
    word-salad by the title cleaner — the URL cleaner should catch it.
    Verb matches the original text's intent (no 'open' in "Playing...",
    so "Going to", not "Opening")."""
    out = format_for_speech('Playing https://youtube.com/watch?v=abc123')
    assert "Https" not in out and "Watch" not in out
    assert out == "Going to YouTube."


# ── File paths ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    (r"Opened C:\Users\Saurav\Downloads\Resume.pdf", "I have opened your resume."),
    (r"Opened C:\Users\Saurav\Downloads\resume_v4_final_latest.pdf", "I have opened your resume."),
    (r"Opened \\SERVER\Shared\team_notes.docx", "I have opened your team notes."),
])
def test_file_paths_humanized(text, expected):
    assert format_for_speech(text) == expected


def test_long_descriptive_filename_falls_back_to_generic_file_wording():
    out = format_for_speech(r"Opened C:\Users\Saurav\Downloads\Q3_Financial_Summary_And_Projections_2026.xlsx")
    assert out == "I have opened the file."


# ── URLs ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Opening https://youtube.com/results?search_query=Dilbar+song", "Opening YouTube."),
    ("Opening https://mail.google.com/mail/u/0/#inbox", "Opening Gmail."),
    ("Opening https://chatgpt.com/c/abc-123-def", "Opening ChatGPT."),
])
def test_known_urls_map_to_friendly_site_names(text, expected):
    assert format_for_speech(text) == expected


def test_unknown_url_falls_back_to_capitalized_domain_label():
    out = format_for_speech("Opening https://myrandomsite.example.com/page?x=1")
    assert out == "Opening Myrandomsite."


# ── Window titles ──────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Successfully switched to Visual Studio Code", "Opening Visual Studio Code."),
    ("Window title: Visual Studio Code - prerna_project_refactored", "Opening Visual Studio Code."),
])
def test_window_titles_cleaned(text, expected):
    assert format_for_speech(text) == expected


# ── Long technical strings (generic fallback) ──────────────────────────

def test_long_unrecognized_technical_string_gets_soft_capped():
    text = (
        "Task completed with exit code 0 after processing 14523 rows "
        "across 3 worker threads in batch mode"
    )
    out = format_for_speech(text)
    assert len(out.split()) <= 11  # capped, not read in full (18 words in the input)
    assert out.startswith("Task completed with exit code 0")


def test_short_text_under_the_word_limit_is_never_truncated():
    text = "Volume set to 50 percent."
    assert format_for_speech(text) == text


# ── Natural / already-clean text passes through untouched ──────────────

@pytest.mark.parametrize("text", [
    "Closed that tab.",
    "Volume set to 50 percent.",
    "Sent Resume.pdf to Varsha on WhatsApp.",
    "Alarm set for 7 AM.",
])
def test_already_natural_text_is_not_mangled(text):
    """The core safety property: tools that already set a good `speech=`
    must come out completely unchanged — this is a targeted cleanup pass,
    not a general rewriter, and it must be a safe no-op on clean input."""
    assert format_for_speech(text) == text


# ── Empty / edge input ──────────────────────────────────────────────────

def test_empty_and_whitespace_input_do_not_crash():
    assert format_for_speech("") == ""
    assert format_for_speech("   ") == "   "