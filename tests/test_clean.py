"""Golden cases drawn from the real Music on 🎧 export.

Every expectation here is a string that actually appears in result.json, so a
failure means the cleaner regressed against real data, not against a fixture
someone invented.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tg2spotify.clean import clean_field, build_hypotheses, extract_feat, split_pairs


def _pairs(**kw):
    """(artist, title) pairs a track's hypotheses cover."""
    return [(h.artist, h.title) for h in build_hypotheses(**kw)]


# ---------------------------------------------------------------- clean_field

def test_handle_only_field_becomes_empty():
    # perf='@moozikestan_bot' -> must never be searched as an artist
    assert clean_field("@moozikestan_bot").text == ""

def test_handle_glued_to_real_artist_keeps_artist():
    assert clean_field("queen/@insomniamusics").text == "queen"

def test_trailing_handle_stripped_from_title():
    assert clean_field("show must go on @insomniamusics").text == "show must go on"
    assert clean_field("15. The Last Man @mosighimatn").text == "The Last Man"

def test_bracket_spam_removed():
    assert clean_field("Are You There {ON @Sickosadism}").text == "Are You There"
    assert clean_field("Maghzhaye Koochake Zang Zadeh [IstgahMusic.com]").text == \
        "Maghzhaye Koochake Zang Zadeh"

def test_real_parentheses_preserved():
    # deleting these would destroy actual title information
    assert clean_field("Existence Life (Rumi Symphony Project: Untold)").text == \
        "Existence Life (Rumi Symphony Project: Untold)"
    assert clean_field("The Last Waltz (feat. Eendo)").text == "The Last Waltz (feat. Eendo)"

def test_domain_removed_from_artist():
    assert clean_field("David Garrett - [www.xyTune.com]").text == "David Garrett"
    assert clean_field("Shahyar Ghanbari (www.MyYazd-Music11.com)").text == "Shahyar Ghanbari"

def test_leading_track_number_stripped():
    assert clean_field("02 Nakhosh").text == "Nakhosh"
    assert clean_field("15. The Last Man").text == "The Last Man"
    assert clean_field("05. Sonata No. 12 In E Minor, Opus 3").text == \
        "Sonata No. 12 In E Minor, Opus 3"

def test_artist_starting_with_number_is_not_mangled():
    # the guard: these are real artist names, not track numbers
    assert clean_field("50 Cent").text == "50 Cent"
    assert clean_field("2 Unlimited").text == "2 Unlimited"
    assert clean_field("30 Seconds To Mars").text == "30 Seconds To Mars"

def test_bitrate_junk_removed():
    assert clean_field("Nakhosh [320kbps]").text == "Nakhosh"
    assert clean_field("Sonata No. 12[1]").text == "Sonata No. 12"

def test_persian_orthography_folded():
    # the same name typed with Arabic vs Persian letters must collapse to one form
    assert clean_field("كتاب").text == "کتاب"            # Arabic kaf -> Persian keheh
    assert clean_field("آيينه ها").text == "آیینه ها"     # Arabic yeh  -> Persian yeh
    assert clean_field("مرد تنهاي").text == clean_field("مرد تنهای").text

def test_whitespace_collapsed():
    assert clean_field("Sam Smith - Writing's  On   The Wall").text == \
        "Sam Smith - Writing's On The Wall"
    assert clean_field("Balduin feat Sue ").text == "Balduin feat Sue"


# ----------------------------------------------------------------- feat logic

def test_feat_extracted():
    body, featured = extract_feat("Can You Hold Me (Feat. Britt Nicole)")
    assert body == "Can You Hold Me"
    assert featured == "Britt Nicole"

def test_feat_without_parens():
    body, featured = extract_feat("The Beautified Project feat. Antimatter")
    assert body == "The Beautified Project"
    assert featured == "Antimatter"

def test_no_feat_is_untouched():
    body, featured = extract_feat("Broken Smile")
    assert body == "Broken Smile" and featured is None


# ------------------------------------------------------------------ splitting

def test_split_on_spaced_dash():
    assert ("Hafez Nazeri", "Existence Life") in split_pairs("Hafez Nazeri - Existence Life")

def test_split_on_unspaced_dash():
    assert ("Ebi", "Hamdam") in split_pairs("Ebi- Hamdam")

def test_split_on_persian_dot():
    assert ("Ghad boland", "Korosh yaghmaei") in split_pairs("Ghad boland . Korosh yaghmaei")

def test_split_on_persian_script_dot():
    assert ("فرهاد مهراد", "آیینه ها") in split_pairs("فرهاد مهراد . آیینه ها")

def test_no_separator_yields_nothing():
    assert split_pairs("Nakhosh") == []


# ------------------------------------------------------------- hypothesis set

def test_well_tagged_track_puts_direct_reading_first():
    h = build_hypotheses(performer="Anathema", title="Are You There {ON @Sickosadism}")
    assert (h[0].artist, h[0].title) == ("Anathema", "Are You There")

def test_handle_performer_recovers_artist_from_title():
    # perf is a bot handle; the real artist is inside the title
    p = _pairs(performer="@moozikestan_bot",
               title="Hafez Nazeri - Existence Life (Rumi Symphony Project: Untold)")
    assert ("Hafez Nazeri", "Existence Life (Rumi Symphony Project: Untold)") in p

def test_fully_swapped_fields_recovered():
    # perf holds 'Artist . Title', title holds only a channel handle
    p = _pairs(performer="فرهاد مهراد . آیینه ها", title="@Adabvaavayparsi")
    assert ("فرهاد مهراد", "آیینه ها") in p

def test_ambiguous_dash_order_emits_both_directions():
    # 'Ebi- Hamdam' is Artist-Title, 'Kooleh- Kaveh Yaghmaei' is Title-Artist.
    # The cleaner must not choose; both readings must be offered.
    p = _pairs(performer=None, title="Ebi- Hamdam")
    assert ("Ebi", "Hamdam") in p and ("Hamdam", "Ebi") in p

def test_both_fields_null_falls_back_to_filename():
    p = _pairs(performer=None, title=None, filename="Kooleh- Kaveh Yaghmaei.mp3")
    assert ("Kaveh Yaghmaei", "Kooleh") in p

def test_filename_track_number_stripped():
    p = _pairs(performer=None, title=None, filename="02 Nakhosh.mp3")
    assert any(t == "Nakhosh" for _, t in p)

def test_mangled_extension_does_not_leak_into_title():
    p = _pairs(performer=None, title=None, filename="Mister Mister.mp3 x-amz-content-sh")
    assert any(t == "Mister Mister" for _, t in p)

def test_id3_used_as_independent_vote():
    p = _pairs(performer="@gelofen400", title="Damahi-Niaz",
               id3_artist="Damahi", id3_title="Niaz")
    assert ("Damahi", "Niaz") in p

def test_hypotheses_are_deduplicated_and_capped():
    hs = build_hypotheses(performer="Ebi", title="Ebi - Hamdam",
                          filename="Ebi - Hamdam.mp3", id3_artist="Ebi", id3_title="Hamdam")
    pairs = [(h.artist, h.title) for h in hs]
    assert len(pairs) == len(set(pairs)), "duplicate hypotheses leaked"
    assert len(hs) <= 8, f"too many hypotheses ({len(hs)}) -> wasted API calls"

def test_bare_title_last_resort_present():
    hs = build_hypotheses(performer=None, title="Nakhosh")
    assert any(h.artist == "" and h.title == "Nakhosh" for h in hs)

def test_empty_input_yields_no_hypotheses():
    assert build_hypotheses(performer=None, title=None) == []

def test_every_hypothesis_records_its_source():
    for h in build_hypotheses(performer="Anathema", title="Are You There"):
        assert h.source, "hypothesis must be traceable to the rule that produced it"


# ------------------------------- regressions found on the real 738-track run

def test_channel_noise_remainder_is_dropped():
    # After '@jmctv' is stripped, '♪telegram channel♪' was surviving and being
    # used as the ARTIST, outranking the correct guess. It must become empty.
    assert clean_field("@jmctv♪telegram channel♪").text == ""
    assert clean_field("telegram channel").text == ""
    assert clean_field("♪♪♪").text == ""
    assert clean_field("@MusicMisItalia6").text == ""

def test_real_words_containing_channel_survive():
    # the noise rule must not eat legitimate titles
    assert clean_field("Channel Orange").text == "Channel Orange"

def test_channel_noise_does_not_become_top_hypothesis():
    hs = build_hypotheses(performer="@jmctv♪telegram channel♪", title="Ebi- Hamdam")
    assert ("Ebi", "Hamdam") in [(h.artist, h.title) for h in hs]
    assert all("telegram" not in h.artist.lower() for h in hs)

def test_artist_in_trailing_parentheses_is_tried():
    # '#320: I Have Seen Your Soul (Martin Herzberg)' -- the artist is the paren
    p = _pairs(performer=None, title="I Have Seen Your Soul (Martin Herzberg)")
    assert ("Martin Herzberg", "I Have Seen Your Soul") in p

def test_feat_parenthetical_is_not_mistaken_for_artist():
    p = _pairs(performer="King Raam", title="The Last Waltz (feat. Eendo)")
    assert not any(a.lower().startswith(("feat", "ft")) for a, _ in p)

def test_filename_underscores_become_spaces():
    p = _pairs(performer=None, title=None,
               filename="Souad_Massi_Le_Bien_Et_Le_Mal.mp3")
    assert any("Souad Massi Le Bien Et Le Mal" in t for _, t in p)

def test_filename_download_id_suffix_stripped():
    p = _pairs(performer=None, title=None, filename="King-Raam-The-Last-Waltz_3136300.mp3")
    assert all("3136300" not in t for _, t in p)
