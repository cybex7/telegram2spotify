"""Scoring behaviour. Pure functions, so no network and no fixtures needed."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tg2spotify.score import score


def test_exact_match_with_matching_duration_auto_accepts():
    s = score("Anathema", "Are You There", "Are You There", ["Anathema"], 291000, 291)
    assert s.verdict == "auto" and s.total > 0.95

def test_right_song_wrong_length_goes_to_review_not_auto():
    # a 60s discrepancy usually means a different recording, edit or live cut
    s = score("Archive", "Lights", "Lights", ["Archive"], 1049000, 1109)
    assert s.verdict == "review" and "duration_off" in s.reason

def test_karaoke_impostor_never_auto_accepts():
    s = score("NF", "Can You Hold Me", "Can You Hold Me (Karaoke Version)",
              ["Karaoke Crew"], 213000, 213)
    assert s.verdict != "auto" and "impostor_recording" in s.reason

def test_tribute_band_is_penalised():
    s = score("Queen", "Show Must Go On", "The Show Must Go On (Made Famous By Queen)",
              ["Tribute Players"], 262000, 262)
    assert s.verdict != "auto"

def test_remaster_qualifier_is_ignored_when_comparing():
    s = score("Porcupine Tree", "Russia On Ice",
              "Russia On Ice (Remastered 2011)", ["Porcupine Tree"], 783000, 783)
    assert s.verdict == "auto", s

def test_feat_in_candidate_title_does_not_hurt():
    s = score("King Raam", "The Last Waltz",
              "The Last Waltz (feat. Eendo)", ["King Raam", "Eendo"], 240000, 240)
    assert s.verdict == "auto", s

def test_wrong_song_is_rejected():
    s = score("Ebi", "Hamdam", "Bohemian Rhapsody", ["Queen"], 354000, 200)
    assert s.verdict == "reject"

def test_swapped_hypothesis_still_scores_when_it_is_the_right_way_round():
    # 'Kooleh- Kaveh Yaghmaei' read as (artist=Kaveh Yaghmaei, title=Kooleh)
    s = score("Kaveh Yaghmaei", "Kooleh", "Kooleh", ["Kaveh Yaghmaei"], 250000, 250)
    assert s.verdict == "auto"

def test_reversed_hypothesis_scores_worse_than_correct_one():
    right = score("Kaveh Yaghmaei", "Kooleh", "Kooleh", ["Kaveh Yaghmaei"], 250000, 250)
    wrong = score("Kooleh", "Kaveh Yaghmaei", "Kooleh", ["Kaveh Yaghmaei"], 250000, 250)
    assert right.total > wrong.total, "the catalogue must be able to arbitrate"

def test_titleless_hypothesis_cannot_auto_accept():
    # no artist to check means the only evidence is a title string; too weak
    s = score("", "Nakhosh", "Nakhosh", ["Someone Else"], 200000, 200)
    assert s.verdict != "auto" and "no_artist_in_hypothesis" in s.reason

def test_unknown_duration_never_auto_accepts():
    s = score("Anathema", "Are You There", "Are You There", ["Anathema"], None, None)
    assert s.verdict == "review" and "duration_unknown" in s.reason

def test_persian_script_exact_match_scores_high():
    s = score("فرهاد مهراد", "آیینه ها", "آیینه ها", ["فرهاد مهراد"], 300000, 300)
    assert s.verdict == "auto"

def test_persian_arabic_spelling_variants_still_match():
    # candidate typed with Arabic yeh/kaf, ours with Persian
    s = score("فرهاد مهراد", "آيينه ها", "آیینه ها", ["فرهاد مهراد"], 300000, 300)
    assert s.verdict == "auto"

def test_word_order_difference_tolerated():
    s = score("Hafez Nazeri", "Existence Life", "Life Existence", ["Hafez Nazeri"], 400000, 400)
    assert s.verdict == "auto", s


# ------------------------- regressions found on the first 20 real matches

def test_spotify_dash_suffix_qualifier_is_stripped():
    # THE bug: Spotify writes qualifiers after a dash, not only in brackets.
    # 'Let It Be' vs 'Let It Be - Remastered 2009' scored 0.667 and went to
    # review despite the durations matching to 0.17s.
    s = score("The Beatles", "Let It Be", "Let It Be - Remastered 2009",
              ["The Beatles"], 243000, 243)
    assert s.title_sim == 1.0, s
    assert s.verdict == "auto", s

def test_dash_live_and_radio_edit_suffixes():
    for suffix in ("- Live", "- Radio Edit", "- Single Version",
                   "- 2011 Remaster", "- Acoustic Version"):
        s = score("Keane", "Somewhere Only We Know",
                  f"Somewhere Only We Know {suffix}", ["Keane"], 240000, 240)
        assert s.title_sim == 1.0, (suffix, s)

def test_genuine_dash_in_title_is_not_stripped():
    # a dash that is part of the actual title must survive
    s = score("Artist", "Love - Hate", "Love - Hate", ["Artist"], 200000, 200)
    assert s.title_sim == 1.0 and s.verdict == "auto"

def test_ampersand_joined_artists_match():
    # 'Arad Aria&Kaveh Afagh' scored artist=0.125 against separate Spotify artists
    s = score("Arad Aria&Kaveh Afagh", "While My Guitar Gently Weeps",
              "While My Guitar Gently Weeps", ["Arad Aria", "Kaveh Afagh"], 277000, 277)
    assert s.artist_sim > 0.9, s

def test_comma_joined_artists_match():
    s = score("King Raam, Eendo", "The Last Waltz", "The Last Waltz",
              ["King Raam"], 240000, 240)
    assert s.artist_sim > 0.9, s

def test_single_artist_name_containing_and_still_matches_whole():
    # splitting must not lose a name that legitimately contains 'and'
    s = score("Simon and Garfunkel", "The Boxer", "The Boxer",
              ["Simon & Garfunkel"], 200000, 200)
    assert s.artist_sim > 0.9, s
