"""
Regression tests for the Maharashtra CET parsers.

Each test pins a bug that was silently dropping or corrupting real rows, with
the row counts measured against the official 2025-26 CET Cell PDFs. The
category/gender assertions are the ones worth guarding hardest — they decide
what a student is told they can apply for.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import state_MH as mh
import state_MH_arch as mh_arch


class TestCategoryTokenRegex(unittest.TestCase):
    """DEF*/PWD* codes lose their trailing H/O/S when the column is narrow.

    Confirmed in the CAP1-4 engineering text dumps: DEFRSEBC (138x),
    PWDROBC (63x) and PWDRSEBC (11x) all appear WITHOUT a trailing letter,
    every single time. While [HOS] was mandatory these columns never
    registered, so every rank beneath them was discarded -- 210 rank records,
    all of them disability or defence reserved seats.
    """

    def test_bare_def_pwd_codes_are_recognised(self):
        for code in ("DEFRSEBC", "PWDROBC", "PWDRSEBC", "DEFROBC", "PWDRSC"):
            self.assertRegex(code, mh.CATEGORY_TOKEN_RE,
                             f"{code} must be recognised without a trailing H/O/S")

    def test_suffixed_codes_still_recognised(self):
        for code in ("DEFRSEBCS", "PWDROBCS", "DEFOPENS", "PWDSCH", "GOPENS", "LSTH"):
            self.assertRegex(code, mh.CATEGORY_TOKEN_RE)

    def test_non_categories_still_rejected(self):
        for junk in ("2025", "Civil", "Engineering", "", "Status"):
            self.assertNotRegex(junk, mh.CATEGORY_TOKEN_RE)


class TestGenderSemantics(unittest.TestCase):
    """G is General (gender-neutral), NOT Boys.

    The legend printed on every CET Cell cutoff page reads: "Starting
    character G-General, L-Ladies, End character H-Home University, O-Other
    than Home University, S-State Level, AI-All India Seat."

    Maharashtra's 30% female quota is horizontal -- L* seats are reserved for
    women *on top of* their access to the G* pool. Labelling G as "Boys" made
    every gender-neutral seat read male-only, hiding most of the seat pool
    from female candidates. (The college-predictor dataset, built separately,
    independently labels GOPENS "Gender-Neutral".)
    """

    def test_g_prefix_is_gender_neutral(self):
        for code in ("GOPENS", "GOPENH", "GOBCS", "GSCS", "GSTS", "GNT1S"):
            _, gender, _ = mh.normalise_category(code)
            self.assertEqual(gender, "All", f"{code}: G means General, not Boys")

    def test_l_prefix_is_female_reserved(self):
        for code in ("LOPENS", "LOPENH", "LOBCS", "LSCH", "LSTS"):
            _, gender, _ = mh.normalise_category(code)
            self.assertEqual(gender, "Girls", f"{code}: L means Ladies")


class TestHorizontalFlags(unittest.TestCase):
    """PWD and DEF are horizontal flags over a base category, not categories.

    DEF used to short-circuit to OTHER without decoding its base, so
    DEFROBCS landed in OTHER while PWDROBC landed in OBC-NCL -- the same
    OBC base bucketed two different ways.
    """

    def test_def_and_pwd_decode_the_same_base_category(self):
        self.assertEqual(mh.normalise_category("DEFROBCS")[0], "OBC-NCL")
        self.assertEqual(mh.normalise_category("PWDROBC")[0], "OBC-NCL")
        self.assertEqual(mh.normalise_category("DEFOBCS")[0], "OBC-NCL")

    def test_flag_is_recorded_in_sub_pool(self):
        for code, flag in (("PWDROBC", "PWDR"), ("PWDOPENS", "PWD"),
                           ("DEFROBCS", "DEFR"), ("DEFOBCS", "DEF")):
            self.assertEqual(mh.normalise_category(code)[2], flag)

    def test_quota_pools_are_flagged_not_miscategorised(self):
        for code, flag in (("TFWS", "TFWS"), ("ORPHAN", "ORPHAN"), ("MI", "MIN")):
            cat, _, sub = mh.normalise_category(code)
            self.assertEqual(cat, "OTHER")
            self.assertEqual(sub, flag)

    def test_base_categories_carry_no_flag(self):
        for code in ("GOPENS", "LOBCH", "EWS", "GSCS"):
            self.assertEqual(mh.normalise_category(code)[2], "")


class TestAllotmentPatterns(unittest.TestCase):
    """The allotment-type tail is genuinely absent on some rows, and seat-type
    codes can contain digits.

    Engineering CAP4 has 26 rows that end right after the branch name, and
    pharmacy CAP4 has 15 rows whose seat type is GNT1H/GNT2H/GNT3H -- codes
    the old [A-Z]{1,12} class could not match because of the digit. 46 rows
    across the AI PDFs were lost to the character class alone, all of them
    Nomadic Tribe reserved seats.
    """

    FLAT_WITH_TAIL = (
        "    1   83256 (30.5397513)   0100552410   01005 - Sant Gadge Baba "
        "College          Paper and Pulp Technology          MH to AI   LSTH"
    )
    FLAT_NO_TAIL = (
        " 43      80106 (34.0714946)       0112561210    01125 - Dwarka Bahu "
        "Uddeshiya Gramin Vikas Foundation          Mechanical Engineering     "
    )
    RANKROW_DIGIT_SEATTYPE = (
        "        70       9669 (36.2252678)      1611682310"
        "                    NEET         MH to AI     GNT1H"
    )

    def test_flat_row_with_tail_matches(self):
        m = mh.ALLOT_PATTERN_FLAT.match(self.FLAT_WITH_TAIL)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(8), "MH to AI")
        self.assertEqual(m.group(9), "LSTH")

    def test_flat_row_without_tail_is_kept(self):
        m = mh.ALLOT_PATTERN_FLAT.match(self.FLAT_NO_TAIL)
        self.assertIsNotNone(m, "tail-less CAP4 rows must not be dropped")
        self.assertIsNone(m.group(8), "allotment_type is None when absent")
        self.assertIsNone(m.group(9), "seat_type is None when absent")

    def test_digit_bearing_seat_type_matches(self):
        m = mh.ALLOT_PATTERN_RANKROW.match(self.RANKROW_DIGIT_SEATTYPE)
        self.assertIsNotNone(m, "GNT1H contains a digit and must still match")
        self.assertEqual(m.group(7), "GNT1H")


class TestPageHeaderIsNotData(unittest.TestCase):
    """The masking rule must not let the page header through.

    Masking only ([\\d.]+) spans leaves "(Integrated 5 Years) for the Year
    2025-26" intact, so 2025 and 26 parse as ranks. There are 1,562 such
    header lines in CAP1 and 1,516 in CAP2 (and none in CAP3/CAP4) -- exactly
    where the phantom rows showed up before "Degree Courses" was added to
    SKIP_PREFIXES.
    """

    HEADER = (
        "        Degree Courses In Engineering and Technology & Master of "
        "Engineering and Technology (Integrated 5 Years) for the Year 2025-26"
    )

    def test_year_header_is_skipped(self):
        self.assertTrue(self.HEADER.strip().startswith(mh.SKIP_PREFIXES))

    def test_masking_alone_would_not_save_us(self):
        masked = re.sub(r"\([\d.]+\)", lambda m: " " * len(m.group()), self.HEADER)
        self.assertRegex(masked, r"\d{2,7}",
                         "digits survive the mask — the prefix guard is load-bearing")


class TestExamAttribution(unittest.TestCase):
    """Each stream must name the exam it is actually admitted on.

    Only engineering and pharmacy go through MHT-CET. B.Arch candidates qualify
    via NATA or JEE Main Paper 2 and are ranked on NATA/2 + Class XII% (max
    200); B.Design has its own MAH-B.Design CET. MAH-AAC-CET is the Fine Art
    exam and belongs to neither — labelling these streams with it was wrong and
    would invite cross-stream rank comparisons that mean nothing.
    """

    def test_arch_is_not_attributed_to_a_cet_it_does_not_use(self):
        self.assertNotIn("AAC", mh_arch.CET_NAME)
        self.assertNotIn("MHT-CET", mh_arch.CET_NAME)
        self.assertIn("NATA", mh_arch.CET_NAME)

    def test_mhtcet_streams_are_labelled_mhtcet(self):
        for stream in ("engineering", "pharmacy"):
            self.assertEqual(mh.STREAM_CONFIG[stream]["cet_name"], "MHT-CET", stream)

    def test_bdesign_has_its_own_cet(self):
        self.assertEqual(mh.STREAM_CONFIG["bdesign"]["cet_name"], "MAH-B.Design CET")


class TestArchCategorySemantics(unittest.TestCase):
    """state_MH_arch.py keeps its OWN copy of the category decoder.

    That duplication is why the G-means-General and DEF-decodes-its-base fixes
    had to be applied twice; these assertions keep the two copies honest. The
    downstream build_clean.py rejects a 'Boys' gender value outright, which is
    how the missed second copy surfaced.
    """

    def test_g_is_gender_neutral(self):
        for code in ("GOPENH", "GOPENO", "GOBCH", "GNT1H"):
            self.assertEqual(mh_arch.normalise_seat_type(code)[1], "All", code)

    def test_l_is_female_reserved(self):
        for code in ("LOPENH", "LOPENO", "LOBCH"):
            self.assertEqual(mh_arch.normalise_seat_type(code)[1], "Girls", code)

    def test_def_and_pwd_decode_base_category(self):
        self.assertEqual(mh_arch.normalise_seat_type("DEFROBCS")[0], "OBC-NCL")
        self.assertEqual(mh_arch.normalise_seat_type("PWDROBC")[0], "OBC-NCL")

    def test_matches_the_engineering_decoder(self):
        """The two copies must not drift apart."""
        for code in ("GOPENH", "LOPENH", "GOBCH", "EWS", "TFWS", "ORPHAN",
                     "MI", "DEFROBCS", "PWDROBC", "GNT1H", "GSEBCH"):
            self.assertEqual(mh_arch.normalise_seat_type(code),
                             mh.normalise_category(code),
                             f"{code}: arch and engg decoders disagree")


class TestArchAllotPattern(unittest.TestCase):
    """Round 1 has no carry-forward colour marker, and seat types can be short.

    The marker denotes "carried forward from a previous round", which cannot
    exist in Round 1 -- so a mandatory marker dropped 100% of R1 (0 rows
    parsed, vs ~1,600 for each later round). Separately {4,12} rejected AI (2),
    EWS/SC/ST (3). Making the marker optional and widening the class took
    architecture from 4,905 to 8,054 rows, with R1 going 0 -> 1,789.
    """

    R1_NO_MARKER = (
        "         1        4        163.00      AR25102461      "
        "AMEYA RAJENDRA KAMTHE                              M           "
        "OPEN         GOPENH"
    )
    R2_WITH_MARKER = (
        "         1        4        163.00      AR25102461      "
        "AMEYA RAJENDRA KAMTHE                              M           "
        "OPEN        ^ GOPENH"
    )
    SHORT_SEAT_TYPE = (
        "         7       89        141.20      AR25100888      "
        "SOME CANDIDATE NAME                                F           "
        "OPEN        ^ AI"
    )

    def test_round1_row_without_marker_matches(self):
        m = mh_arch.ALLOT_PATTERN.match(self.R1_NO_MARKER)
        self.assertIsNotNone(m, "R1 has no marker and must still parse")
        self.assertEqual(m.group(8), "GOPENH")

    def test_row_with_marker_still_matches(self):
        m = mh_arch.ALLOT_PATTERN.match(self.R2_WITH_MARKER)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(8), "GOPENH")

    def test_short_seat_type_matches(self):
        m = mh_arch.ALLOT_PATTERN.match(self.SHORT_SEAT_TYPE)
        self.assertIsNotNone(m, "'AI' is 2 chars and must not be rejected")
        self.assertEqual(m.group(8), "AI")


if __name__ == "__main__":
    unittest.main(verbosity=2)
