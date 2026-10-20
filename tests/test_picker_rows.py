from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from emote.picker import EmojiPicker


class PickerRowTests(TestCase):
    @patch("emote.picker.Gtk.GestureClick.new")
    @patch("emote.picker.Gtk.EventControllerMotion.new")
    @patch("emote.picker.Gtk.Label")
    @patch("emote.picker.Gtk.Box")
    def test_row_handlers_do_not_hold_their_row(
        self, _box, _label, motion_new, click_new
    ):
        picker = SimpleNamespace(
            on_row_motion=Mock(), on_row_leave=Mock(), on_row_right_pressed=Mock()
        )

        EmojiPicker.setup_row(picker, None, Mock())

        connects = (
            motion_new.return_value.connect.call_args_list
            + click_new.return_value.connect.call_args_list
        )
        self.assertEqual(len(connects), 4)
        for call in connects:
            self.assertEqual(len(call.args), 2, call)

    def test_row_handlers_find_their_row_through_the_controller(self):
        box = SimpleNamespace(hovered_index=None)
        controller = SimpleNamespace(get_widget=Mock(return_value=box))
        picker = SimpleNamespace(
            row_index_at=Mock(return_value=3),
            update_preview=Mock(),
            append_emoji=Mock(),
        )

        EmojiPicker.on_row_motion(picker, controller, 10, 0)
        self.assertEqual(box.hovered_index, 3)
        picker.update_preview.assert_called_once_with(3)

        EmojiPicker.on_row_leave(picker, controller)
        self.assertIsNone(box.hovered_index)

        EmojiPicker.on_row_right_pressed(picker, controller, 1, 10, 0)
        picker.row_index_at.assert_called_with(box, 10)
        picker.append_emoji.assert_called_once_with(3)
