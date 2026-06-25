"""Tests for organize_notes.classify — locks the conservative behavior so the
note organizer never again pollutes real notes with junk terms."""
import unittest

from organize_notes import classify


class TestClassify(unittest.TestCase):
    def test_clean_term_emdash(self):
        self.assertEqual(
            classify("Negligence — failure to exercise reasonable care"),
            ("term", ("Negligence", "failure to exercise reasonable care")))

    def test_clean_term_colon(self):
        r = classify("Consideration: the bargained-for exchange in a contract")
        self.assertEqual(r[0], "term")
        self.assertEqual(r[1][0], "Consideration")

    def test_clean_term_hyphen(self):
        r = classify("Doctrine of Stare decisis - the standard for choosing cases")
        self.assertEqual(r[0], "term")
        self.assertEqual(r[1][0], "Doctrine of Stare decisis")

    # --- the bugs that polluted real notes must now be rejected ---
    def test_definition_line_rejected(self):
        self.assertIsNone(classify("Definition - The establishment of government structure"))

    def test_sentence_fragment_rejected(self):
        self.assertIsNone(classify("The second function of constitutions is to prevent harm"))

    def test_is_sentence_rejected(self):
        self.assertIsNone(classify("If no applicable precedent exists the court is free to act"))

    def test_such_as_not_example(self):
        # "such as" alone is too weak a signal now — must not be pulled.
        self.assertIsNone(classify("for local issues such as zoning"))

    def test_long_term_rejected(self):
        self.assertIsNone(classify("This whole long phrase before the dash - is not a term"))

    # --- examples ---
    def test_example_ex_dot(self):
        self.assertEqual(classify("Ex. If A hits B, A faces civil and criminal")[0], "example")

    def test_example_eg(self):
        self.assertEqual(classify("e.g. a statute making murder a crime")[0], "example")

    def test_plain_note_ignored(self):
        self.assertIsNone(classify("Common law fills the gaps left by other rules"))

    def test_short_line_ignored(self):
        self.assertIsNone(classify("- ok"))


if __name__ == "__main__":
    unittest.main()
