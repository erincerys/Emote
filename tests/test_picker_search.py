from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from emote import debouncer
from emote.picker import EmojiPicker


class SearchDebounceTests(TestCase):
    @patch("emote.debouncer.GLib.timeout_add", return_value=7)
    def test_search_waits_for_the_debounce_interval(self, timeout_add):
        search = debouncer.SearchDebouncer(Mock())

        search.search("cat")

        self.assertEqual(debouncer.DEBOUNCE_INTERVAL, 0.2)
        timeout_add.assert_called_once_with(200, search._run, "cat")
        self.assertEqual(search.source_id, 7)


class MinimumSearchLengthTests(TestCase):
    def make_picker(self, searching=False):
        return SimpleNamespace(
            searching=searching,
            scroller=SimpleNamespace(
                get_vadjustment=Mock(return_value=Mock(get_value=Mock(return_value=80)))
            ),
            active_category="animals-nature",
            selected_index=0,
            display_emojis=[],
            emojis_per_row=8,
            nav_items={"animals-nature": Mock()},
            nav_icons={"animals-nature": Mock()},
            search_scroll_position=120.0 if searching else None,
            search_scroll_category="animals-nature" if searching else None,
            search_selected_index=None,
            search_grid_state=None,
            replace_rows=Mock(),
            show_catalogue=Mock(),
            schedule_search_scroll_restore=Mock(),
        )

    @patch("emote.picker.emojis.search")
    def test_short_query_keeps_the_catalogue(self, search):
        picker = self.make_picker()

        EmojiPicker.apply_search(picker, " ab ")

        search.assert_not_called()
        picker.replace_rows.assert_not_called()
        self.assertFalse(picker.searching)
        self.assertIsNone(picker.search_scroll_position)

    @patch("emote.picker.emojis.search", return_value=[{"char": "🐱"}])
    def test_third_character_enters_search(self, search):
        picker = self.make_picker()
        EmojiPicker.apply_search(picker, "ca")

        EmojiPicker.apply_search(picker, "cat")

        search.assert_called_once_with("cat")
        self.assertTrue(picker.searching)
        self.assertEqual(picker.search_scroll_position, 80)
        self.assertEqual(picker.search_scroll_category, "animals-nature")
        picker.replace_rows.assert_called_once()

    def test_deleting_below_three_restores_like_clearing(self):
        for query in ("", "ca"):
            with self.subTest(query=query):
                picker = self.make_picker(searching=True)

                EmojiPicker.apply_search(picker, query)

                picker.show_catalogue.assert_called_once_with(reset_scroll=False)
                picker.schedule_search_scroll_restore.assert_called_once_with(
                    120.0, "animals-nature"
                )
                self.assertIsNone(picker.search_scroll_position)

    def test_resize_with_short_query_rebuilds_the_catalogue(self):
        picker = SimpleNamespace(
            pending_grid_restore=None,
            get_grid_anchor=Mock(return_value=None),
            display_emojis=[],
            search_entry=SimpleNamespace(get_text=Mock(return_value="ca")),
            active_category="food-drink",
            apply_search=Mock(),
            show_catalogue=Mock(),
            set_active_category=Mock(),
        )

        EmojiPicker.refresh_rows(picker)

        picker.apply_search.assert_not_called()
        picker.show_catalogue.assert_called_once_with(reset_scroll=False)
        picker.set_active_category.assert_called_once_with("food-drink")
