from __future__ import annotations
import io
import unittest
from pathlib import Path
from PIL import Image
from poster_engine import SIZES, PALETTES, default_spec, offline_background_bytes, render_poster, high_res_png
from ai_services import local_instruction, image_size, build_art_prompt


class PosterEngineTests(unittest.TestCase):
    def test_all_layouts_as_valid_png(self):
        metadata={"title":"2026 한신초등학교 꿈나눔예술제","subtitle":"예술로 피어나는 우리의 이야기","when":"2026.10.21 - 10.24","where":"한신초등학교 강당","details":"작품 전시회 · 예술 발표회","organizer":"HANSIN SCHOOL"}
        for i in range(3):
            art=offline_background_bytes("A4 세로 · 210×297mm", "autumn", i)
            output=render_poster(art, metadata, [], default_spec(i), "A4 세로 · 210×297mm")
            image=Image.open(io.BytesIO(output))
            self.assertEqual(image.size,SIZES["A4 세로 · 210×297mm"])
            self.assertEqual(image.format,"PNG")
            self.assertGreater(len(output),50_000)

    def test_reference_prompt_excludes_text(self):
        prompt=build_art_prompt({"title":"꿈나눔예술제"},"따뜻한",0,"autumn")
        self.assertIn("DO NOT put any text",prompt)

    def test_natural_language_without_api(self):
        changes=local_instruction("제목 크게, 배경은 파란색, 사진 작게",default_spec(0))
        self.assertEqual(changes["spec"]["palette"],"ocean")
        self.assertGreater(changes["spec"]["title_scale"],1.0)
        self.assertLess(changes["spec"]["photo_scale"],1.0)

    def test_image_ratio(self):
        self.assertEqual(image_size("A3 세로 · 297×420mm"),"1024x1536")
        self.assertEqual(image_size("가로형 · 3:2"),"1536x1024")
        self.assertEqual(image_size("정사각형 · 1:1"),"1024x1024")

    def test_print_resample(self):
        art=offline_background_bytes("A4 세로 · 210×297mm","autumn")
        png=render_poster(art,{"title":"테스트"},[],default_spec(0),"A4 세로 · 210×297mm")
        high=high_res_png(png,"A4 세로 · 210×297mm",dpi=300)
        image=Image.open(io.BytesIO(high))
        self.assertEqual(image.size,(2480,3508))


if __name__=="__main__":
    unittest.main()
