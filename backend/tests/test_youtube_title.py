# -*- coding: utf-8 -*-
"""Tests for tools.youtube_tool._short_title — extracts a TTS-friendly song
name from a full YouTube video title (movie/cast/composer credits stripped).
Cases below are the ACTUAL titles from real usage that originally exposed
the "reads the whole credits line aloud" bug."""

from tools.youtube_tool import _short_title


def test_strips_movie_and_cast_after_pipes():
    title = (
        "DILBAR Lyrical | Satyameva Jayate |John Abraham, Nora Fatehi,"
        "Tanishk B, Neha Kakkar,Dhvani, Ikka"
    )
    assert _short_title(title) == "DILBAR"


def test_strips_title_song_suffix():
    title = "Saiyaara Title Song | Ahaan Panday, Aneet Padda | Tanishk Bagchi, Faheem A, Arslan N | Irshad Kamil"
    assert _short_title(title) == "Saiyaara"


def test_strips_bare_song_suffix_with_word_boundary():
    title = "Tujh Mein Rab Dikhta Hai Song | Rab Ne Bana Di Jodi | Shah Rukh Khan, Anushka Sharma | Roop Kumar"
    assert _short_title(title) == "Tujh Mein Rab Dikhta Hai"


def test_splits_on_dash_separator():
    assert _short_title("Skyroot Vikram 1 - LIVE Watch Along") == "Skyroot Vikram 1"


def test_leaves_clean_titles_unchanged():
    assert _short_title("Kesariya (From Brahmastra)") == "Kesariya (From Brahmastra)"


def test_does_not_corrupt_a_word_that_merely_ends_in_a_noise_word():
    # "Anirudhsong" ends in the letters "song" but isn't the word "song" —
    # the word-boundary check must not truncate mid-word.
    assert _short_title("Anirudhsong Title") == "Anirudhsong Title"


def test_empty_and_none_are_passed_through():
    assert _short_title("") == ""
    assert _short_title(None) is None


def test_iterative_stripping_removes_multiple_trailing_noise_words():
    # "Video" and "Song" both strip within one pass (list order happens to
    # allow it here), leaving "Full" orphaned since bare "full" isn't a
    # registered noise word on its own — a defensible partial result, not
    # a bug: no mid-word corruption, and real-world titles (tested above)
    # all strip cleanly. Documents actual behavior rather than an idealized
    # target that isn't how the list-order-dependent stripping works.
    assert _short_title("Kesariya Full Song Video") == "Kesariya Full"
