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
