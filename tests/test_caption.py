"""Caption geometry, escaping and the fade expression.

The 1080p test is a regression guard with history behind it: the tool this
package replaces hardcoded these exact pixel values, and they were arrived at
by looking at real output. The move to resolution-relative maths must not
change what a 1080p render looks like.
"""

from __future__ import annotations

import pytest

from claude_reelsmith import caption

# The literal values from the predecessor's hardcoded 1080p layout.
LEGACY_1080P = {
    "primary_size": 52,
    "secondary_size": 38,
    "primary_y": 1080 - 185,
    "secondary_y": 1080 - 105,
    "margin_x": 60,
    "primary_border": 20,
    "secondary_border": 14,
}


def test_1080p_reproduces_the_original_layout_exactly():
    geo = caption.geometry(1920, 1080)
    assert geo.primary_size == LEGACY_1080P["primary_size"]
    assert geo.secondary_size == LEGACY_1080P["secondary_size"]
    assert geo.primary_y == LEGACY_1080P["primary_y"]
    assert geo.secondary_y == LEGACY_1080P["secondary_y"]
    assert geo.margin_x == LEGACY_1080P["margin_x"]
    assert geo.primary_border == LEGACY_1080P["primary_border"]
    assert geo.secondary_border == LEGACY_1080P["secondary_border"]


def test_4k_scales_by_exactly_two():
    hd = caption.geometry(1920, 1080)
    uhd = caption.geometry(3840, 2160)
    assert uhd.primary_size == hd.primary_size * 2
    assert uhd.secondary_size == hd.secondary_size * 2
    assert uhd.margin_x == hd.margin_x * 2
    # Vertical positions are offsets from the bottom, so they scale in the gap.
    assert (2160 - uhd.primary_y) == (1080 - hd.primary_y) * 2
    assert (2160 - uhd.secondary_y) == (1080 - hd.secondary_y) * 2


def test_portrait_sizes_text_to_the_narrow_axis():
    """A 1080-wide portrait frame should get 1080-landscape-sized text.

    Scaling by height would give a 1920 reference and produce text nearly twice
    as large as the frame can carry.
    """
    landscape = caption.geometry(1920, 1080)
    portrait = caption.geometry(1080, 1920)
    assert portrait.primary_size == landscape.primary_size
    assert portrait.margin_x == landscape.margin_x
    # Still anchored to the bottom of the taller frame.
    assert portrait.primary_y > landscape.primary_y


@pytest.mark.parametrize(
    ("width", "height"),
    [(1920, 1080), (3840, 2160), (1080, 1920), (640, 480), (2560, 1440)],
)
def test_captions_always_land_inside_the_frame(width, height):
    geo = caption.geometry(width, height)
    assert 0 < geo.primary_y < height
    assert 0 < geo.secondary_y < height
    assert geo.primary_y < geo.secondary_y, "primary line sits above the secondary line"
    assert 0 < geo.margin_x < width / 2


def test_caption_scale_multiplies_sizes():
    normal = caption.geometry(1920, 1080)
    large = caption.geometry(1920, 1080, scale=2.0)
    assert large.primary_size == normal.primary_size * 2


def test_character_budget_shrinks_as_text_grows():
    geo = caption.geometry(1920, 1080)
    assert geo.primary_max_chars > 0
    # The smaller secondary face fits more characters on the same width.
    assert geo.secondary_max_chars > geo.primary_max_chars


class TestAlphaExpr:
    def test_fades_in_holds_then_fades_out(self):
        expr = caption.alpha_expr(15.0, 1.0)
        assert "lt(t,1.0)" in expr
        assert "lt(t,14.0)" in expr
        assert "lt(t,15.0)" in expr

    def test_shape_is_three_nested_conditionals(self):
        assert caption.alpha_expr(10, 2).count("if(") == 3


class TestEscaping:
    def test_windows_path_colon_is_escaped(self):
        assert caption.escape_filter_value("C:/Windows/Fonts/arial.ttf") == \
            r"C\:/Windows/Fonts/arial.ttf"

    def test_backslash_is_escaped_before_anything_else(self):
        assert caption.escape_filter_value(r"a\b") == r"a\\b"

    def test_filter_metacharacters_are_escaped(self):
        escaped = caption.escape_filter_value("a,b[c]d'e")
        for char in (",", "[", "]", "'"):
            assert f"\\{char}" in escaped


class TestLogoPlacement:
    @pytest.mark.parametrize(
        "position", ["top-right", "top-left", "bottom-right", "bottom-left"]
    )
    def test_every_corner_is_supported(self, position):
        assert caption.logo_overlay_xy(position, 55)

    def test_unknown_position_is_rejected(self):
        with pytest.raises(ValueError, match="Unknown logo position"):
            caption.logo_overlay_xy("middle", 10)

    def test_right_side_positions_measure_from_the_frame_width(self):
        assert caption.logo_overlay_xy("top-right", 55).startswith("W-w-55")


class TestTextFiles:
    def test_text_goes_to_sidecars_not_the_filter_string(self, tmp_path):
        nasty = "O'Brien, Anna: \"Sonata\" [live] 50% \\ 100"
        primary, secondary = caption.write_text_files(
            str(tmp_path), "clip01", nasty, "second line"
        )
        # Verbatim on disk: no escaping is applied to the content itself.
        assert open(primary, encoding="utf-8").read() == nasty
        assert open(secondary, encoding="utf-8").read() == "second line"

    def test_no_trailing_newline_is_written(self, tmp_path):
        primary, _ = caption.write_text_files(str(tmp_path), "c", "Name", "")
        assert not open(primary, encoding="utf-8").read().endswith("\n")

    def test_chain_references_files_and_never_inlines_text(self, tmp_path):
        primary, secondary = caption.write_text_files(
            str(tmp_path), "c", "Anna Petrova", "violin"
        )
        chain = caption.drawtext_chain(
            geo=caption.geometry(1920, 1080),
            primary_font="/usr/share/fonts/x.ttf",
            secondary_font="/usr/share/fonts/y.ttf",
            primary_file=primary,
            secondary_file=secondary,
            alpha="1",
            font_color="white",
            box_color="black@0.5",
        )
        assert "textfile=" in chain
        assert "Anna Petrova" not in chain, "caption text must never enter the filtergraph"

    def test_single_line_caption_emits_one_drawtext(self, tmp_path):
        primary, secondary = caption.write_text_files(str(tmp_path), "c", "Only", "")
        chain = caption.drawtext_chain(
            geo=caption.geometry(1920, 1080),
            primary_font="/f.ttf", secondary_font="/f.ttf",
            primary_file=primary, secondary_file=secondary,
            alpha="1", font_color="white", box_color="black@0.5",
            has_secondary=False,
        )
        assert chain.count("drawtext=") == 1

    def test_shadow_scales_with_the_frame(self, tmp_path):
        primary, secondary = caption.write_text_files(str(tmp_path), "c", "A", "B")
        kwargs = dict(
            primary_font="/f.ttf", secondary_font="/f.ttf",
            primary_file=primary, secondary_file=secondary,
            alpha="1", font_color="white", box_color="black@0.0",
            draw_box=False, shadow=3,
        )
        hd = caption.drawtext_chain(geo=caption.geometry(1920, 1080), **kwargs)
        uhd = caption.drawtext_chain(geo=caption.geometry(3840, 2160), **kwargs)
        assert "shadowx=3:" in hd
        assert "shadowx=6:" in uhd

    def test_box_is_omitted_when_disabled(self, tmp_path):
        primary, secondary = caption.write_text_files(str(tmp_path), "c", "A", "B")
        chain = caption.drawtext_chain(
            geo=caption.geometry(1920, 1080),
            primary_font="/f.ttf", secondary_font="/f.ttf",
            primary_file=primary, secondary_file=secondary,
            alpha="1", font_color="white", box_color="black@0.5",
            draw_box=False,
        )
        assert "box=1" not in chain
